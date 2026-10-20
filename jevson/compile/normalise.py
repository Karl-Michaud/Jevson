"""The DESIGN §3.5 normalisation table: Pydantic or raw JSON Schema 2020-12 → a `SchemaNode` tree.

Class A, before mapping: static local `$ref`s are inlined (merging the keywords beside them),
`Optional` and flat `anyOf` null branches are stripped, constants are recognised, `Decimal` becomes
a decimal value, a flat `allOf` merges, a union with two or more non-null branches (Pydantic's
discriminated unions included) becomes a `Kind.UNION` whose branches sit at its own pointer, and
every construct the compiler cannot honour is refused with a named reason. Node pointers are
**instance** pointers (RFC 6901), so two fields of one `$defs` type get distinct pointers. Array
items sit at `<array>/-`.

`normalise()` keeps collecting after a refusal and marks the refused subtree `Kind.REFUSED`, so the
mapping stage can add its own refusals to the same `CompileError` (R14). `normalise_schema()`
returns a whole tree or raises.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from importlib import metadata
from typing import Literal, TypeAlias

from jevson.compile.declarations import KEYWORD, FieldDeclaration, parse_declaration
from jevson.compile.refusal import Refusals, child_pointer
from jevson.compile.untyped import as_json, as_list, as_object
from jevson.errors import RefusalCode
from jevson.types import JSONValue

Schema: TypeAlias = dict[str, object]
Stack: TypeAlias = tuple[str, ...]
Site: TypeAlias = Literal["root", "field", "inner"]

MAX_NODES = 10_000
MAX_DEPTH = 64
MIN_PYDANTIC = (2, 12)

ANNOTATIONS = frozenset(
    {"title", "description", "default", "examples", "$comment", "deprecated", "readOnly", "writeOnly", KEYWORD}
)
KEPT = frozenset(
    {"minLength", "maxLength", "pattern", "format", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}
    | {"multipleOf", "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties", "dependentRequired"}
)
"""Kept on the node for final validation only."""
DYNAMIC = frozenset({"$dynamicRef", "$recursiveRef", "$dynamicAnchor", "$recursiveAnchor"})
UNSUPPORTED = frozenset(
    {"not", "if", "then", "else", "contains", "minContains", "maxContains", "dependentSchemas"}
    | {"unevaluatedProperties", "unevaluatedItems", "propertyNames"}
)
SCALARS = frozenset({"string", "number", "integer", "boolean"})
_DECIMAL = object()
"""The `type` the normaliser gives Pydantic's `Decimal` shape; no schema can spell it."""
_UNION = object()
"""The `type` the normaliser gives a union of two or more non-null branches."""
_BRANCHES = "\x00branches"
"""Where a `_UNION` schema keeps its resolved branches; no schema can spell the key's first character."""
_NO_SCHEMA = object()
"""A Pydantic model whose schema could not be read; distinct from a literal `None` schema."""
FLAT_ALL_OF_KEYS = frozenset({"type", "properties", "required", "title", "description"})


class Kind(StrEnum):
    OBJECT = "object"
    ARRAY = "array"
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    ENUM = "enum"
    CONSTANT = "constant"
    DECIMAL = "decimal"
    """Emitted in `.value` as the string form (DESIGN §3.5, [L18])."""
    UNION = "union"
    """Two or more non-null branches, resolved by a discriminator (DESIGN §3.2, `compile/unions.py`)."""
    REFUSED = "refused"
    """Only from `normalise()`; the reason is in its `Refusals`."""


@dataclass(frozen=True)
class SchemaNode:
    pointer: str
    kind: Kind
    required: bool = True
    nullable: bool = False
    has_default: bool = False
    default: JSONValue = None
    values: tuple[JSONValue, ...] = ()
    """An `ENUM`'s options in declared order, or a `CONSTANT`'s one value."""
    properties: tuple[tuple[str, SchemaNode], ...] = ()
    items: SchemaNode | None = None
    branches: tuple[SchemaNode, ...] = ()
    """A `UNION`'s branches in declared order, each at the union's own instance pointer."""
    title: str | None = None
    keywords: Mapping[str, object] = field(default_factory=dict[str, object])
    description: str | None = None
    declaration: FieldDeclaration | None = None
    """Only on object properties; a model-level `x-jevson` (root or `$defs`) is never one [L18]."""


def normalise_schema(schema: object) -> SchemaNode:
    """The whole normalised tree, or `CompileError` naming every offending pointer."""
    refusals = Refusals()
    node = normalise(schema, refusals)
    refusals.raise_if_any()
    return node


def normalise(schema: object, refusals: Refusals) -> SchemaNode:
    """Normalise `schema` (a JSON Schema dict or a Pydantic model class), adding problems to `refusals`."""
    root = _json_schema_of(schema, refusals)
    if root is _NO_SCHEMA:
        return SchemaNode("", Kind.REFUSED)
    return _Normaliser(root, refusals).node(root, "", "root", required=True, stack=("#",), depth=0)


def _json_schema_of(schema: object, refusals: Refusals) -> object:
    method = getattr(schema, "model_json_schema", None)
    if method is None:
        return schema
    try:
        found = re.match(r"(\d+)\.(\d+)", metadata.version("pydantic"))
        if not found or (int(found[1]), int(found[2])) < MIN_PYDANTIC:
            refusals.add("", RefusalCode.PYDANTIC_TOO_OLD, "Pydantic >= 2.12 is required [L18]")
            return _NO_SCHEMA
        return method(mode="validation")
    except Exception as error:  # Pydantic raises its own types for annotations it cannot emit
        refusals.add("", RefusalCode.MALFORMED_SCHEMA, f"model_json_schema failed: {error}")
        return _NO_SCHEMA


class _Normaliser:
    def __init__(self, root: object, refusals: Refusals) -> None:
        self.root = root
        self.refusals = refusals
        self.count = 0

    def refuse(self, pointer: str, code: RefusalCode, message: str, required: bool = True) -> SchemaNode:
        self.refusals.add(pointer, code, message)
        return SchemaNode(pointer, Kind.REFUSED, required=required)

    def node(self, raw: object, pointer: str, site: Site, *, required: bool, stack: Stack, depth: int) -> SchemaNode:
        self.count += 1
        if self.count > MAX_NODES or depth > MAX_DEPTH:
            return self.refuse("", RefusalCode.SCHEMA_TOO_LARGE, f"over {MAX_NODES} nodes or {MAX_DEPTH} levels")
        if raw is True or raw == {}:
            return self.refuse(pointer, RefusalCode.ANY_FIELD, "Any: no type to decide over", required)
        literal = as_object(raw)
        if literal is None:
            return self.refuse(pointer, RefusalCode.MALFORMED_SCHEMA, "a schema must be an object", required)
        schema, stack = self.resolve(literal, pointer, stack)
        declaration = self.declaration(schema, pointer, site) if schema is not None else None
        nullable = False
        while schema is not None and (isinstance(schema.get("type"), list) or {"anyOf", "oneOf"} & schema.keys()):
            schema, stripped = self.strip_nulls(schema, pointer, stack)
            nullable = nullable or stripped
        if schema is None:
            return SchemaNode(pointer, Kind.REFUSED, required=required)
        if "pattern" in schema and not _is_regex(schema["pattern"]):  # final validation would raise after spend
            message = f"pattern {schema['pattern']!r} is not a valid regular expression"
            return self.refuse(pointer, RefusalCode.MALFORMED_SCHEMA, message, required)
        shaped = self.shape(schema, pointer, stack, depth)
        return SchemaNode(
            pointer,
            shaped.kind,
            required=required,
            nullable=nullable or shaped.nullable,
            has_default="default" in schema,
            default=as_json(schema.get("default")),
            values=shaped.values,
            properties=shaped.properties,
            items=shaped.items,
            branches=shaped.branches,
            title=t if isinstance(t := schema.get("title"), str) else None,
            keywords={k: v for k, v in schema.items() if k in KEPT or (k == "additionalProperties" and v is False)},
            description=d if isinstance(d := schema.get("description"), str) else None,
            declaration=declaration,
        )

    def declaration(self, schema: Schema, pointer: str, site: Site) -> FieldDeclaration | None:
        if KEYWORD not in schema or site == "root":
            return None  # the root's x-jevson is model-level, like one inside $defs
        if site == "inner":
            self.refusals.add(pointer, RefusalCode.MISPLACED_DECLARATION, "x-jevson belongs on an object property")
            return None
        return parse_declaration(schema[KEYWORD], pointer, self.refusals)

    # --- $ref and allOf ---------------------------------------------------------------------

    def resolve(self, schema: Schema, pointer: str, stack: Stack) -> tuple[Schema | None, Stack]:
        """Inline `$ref` chains and a one-branch `allOf`; merge a flat `allOf`."""
        if dynamic := sorted(DYNAMIC & schema.keys()):
            self.refusals.add(pointer, RefusalCode.DYNAMIC_REF, f"{dynamic[0]} is not supported")
            return None, stack
        current: Schema | None = schema
        while current is not None and ({"$ref", "allOf"} & current.keys()):
            if "$ref" in current:
                target, stack = self.target(current.pop("$ref"), pointer, stack)
            else:
                target = self.flat_all_of(current.pop("allOf"), pointer, stack)
            current = self.merge(target, current, pointer) if target is not None else None
        return current, stack

    def target(self, ref: object, pointer: str, stack: Stack) -> tuple[Schema | None, Stack]:
        if not isinstance(ref, str) or not ref.startswith("#"):
            self.refusals.add(pointer, RefusalCode.EXTERNAL_REF, f"only local $refs are inlined: {ref!r}")
            return None, stack
        if ref in stack:
            self.refusals.add(pointer, RefusalCode.RECURSIVE_REF, f"{ref} refers to itself")
            return None, stack
        found: object = self.root
        for token in [t.replace("~1", "/").replace("~0", "~") for t in ref[1:].split("/")[1:]]:
            found = parent.get(token) if (parent := as_object(found)) is not None else None
        target = as_object(found)
        if target is None:
            self.refusals.add(pointer, RefusalCode.EXTERNAL_REF, f"{ref} does not resolve in this document")
            return None, stack
        target.pop(KEYWORD, None)  # model-level json_schema_extra, never a field declaration [L18]
        return target, (*stack, ref)

    def merge(self, target: Schema, siblings: Schema, pointer: str) -> Schema | None:
        """2020-12 applies a `$ref` and its siblings together; sibling annotations win."""
        for key in sorted(target.keys() & siblings.keys() - ANNOTATIONS):
            if target[key] != siblings[key]:
                self.refusals.add(pointer, RefusalCode.REF_SIBLING_CONFLICT, f"{key!r} differs beside its $ref")
                return None
        return target | siblings

    def flat_all_of(self, raw: object, pointer: str, stack: Stack) -> Schema | None:
        branches = [as_object(b) for b in as_list(raw) or [None]]
        if len(branches) == 1 and branches[0] is not None:
            return branches[0]
        properties: Schema = {}
        required: list[object] = []
        for branch in branches:
            resolved = self.resolve(branch, pointer, stack)[0] if branch is not None else None
            own = as_object(resolved.get("properties", {})) if resolved is not None else None
            if resolved is None or own is None or not self.is_flat(resolved, own, properties):
                self.refusals.add(pointer, RefusalCode.NON_FLAT_ALL_OF, "only an allOf of plain object schemas merges")
                return None
            properties |= own
            required += as_list(resolved.get("required", [])) or []
        return {"type": "object", "properties": properties, "required": required}

    @staticmethod
    def is_flat(branch: Schema, own: Schema, merged: Schema) -> bool:
        return (
            branch.keys() <= FLAT_ALL_OF_KEYS
            and branch.get("type", "object") == "object"
            and not own.keys() & merged.keys()
        )

    # --- nulls and unions -----------------------------------------------------------------------

    def strip_nulls(self, schema: Schema, pointer: str, stack: Stack) -> tuple[Schema | None, bool]:
        """One layer of `type: [T, "null"]`, or of a flat `anyOf`/`oneOf` (`Optional[T]`, `Decimal`, unions).

        `node()` repeats it until none is left."""
        types = as_list(schema.get("type"))
        if types is not None:
            rest = [t for t in types if t != "null"]
            if len(rest) > 1:
                shared = {k: v for k, v in schema.items() if k not in ANNOTATIONS and k != "type"}
                branches = [shared | {"type": t} for t in rest]
                annotations = {k: v for k, v in schema.items() if k in ANNOTATIONS}
                return annotations | {"type": _UNION, _BRANCHES: branches}, len(rest) < len(types)
            return {k: v for k, v in schema.items() if k != "type"} | {"type": rest[0] if rest else "null"}, len(
                rest
            ) < len(types)
        keys = sorted({"anyOf", "oneOf"} & schema.keys())
        if len(keys) > 1:
            self.refusals.add(pointer, RefusalCode.UNSUPPORTED_KEYWORD, "anyOf beside oneOf is not supported")
            return None, False
        raw = [as_object(b) for b in as_list(schema[keys[0]]) or [None]]
        branches = [b for b in raw if b is not None]
        if len(branches) < len(raw):
            self.refusals.add(pointer, RefusalCode.MALFORMED_SCHEMA, f"{keys[0]} must be a list of schemas")
            return None, False
        if any(KEYWORD in b for b in branches):
            self.refusals.add(
                pointer, RefusalCode.MISPLACED_DECLARATION, "x-jevson belongs on the property, not a branch"
            )
        # `discriminator` (OpenAPI, emitted by Pydantic) only names the tag; the branches carry it.
        siblings = {k: v for k, v in schema.items() if k not in (keys[0], "discriminator")}
        return self.collapse(branches, siblings, pointer, stack)

    def collapse(
        self, branches: list[Schema], siblings: Schema, pointer: str, stack: Stack
    ) -> tuple[Schema | None, bool]:
        resolved = [self.resolve(b, pointer, stack)[0] for b in branches]
        if None in resolved:
            return None, False
        kept = [b for b in resolved if b is not None and b.get("type") != "null"]
        nullable = len(kept) < len(resolved)
        if len(kept) == 1:
            return self.merge(kept[0], siblings, pointer), nullable
        if not kept:
            return siblings | {"const": None}, nullable
        if sorted(str(b.get("type")) for b in kept) == ["number", "string"] and any("pattern" in b for b in kept):
            number = next(b for b in kept if b.get("type") == "number")
            return siblings | number | {"type": _DECIMAL}, nullable  # Pydantic's Decimal [L18]
        return siblings | {"type": _UNION, _BRANCHES: kept}, nullable

    def union(self, schema: Schema, pointer: str, stack: Stack, depth: int) -> SchemaNode:
        """Every branch is normalised, so a refusal in any branch is found before any call (R14)."""
        branches = tuple(
            self.node(b, pointer, "inner", required=True, stack=stack, depth=depth + 1)
            for b in as_list(schema[_BRANCHES]) or []
        )
        return SchemaNode(pointer, Kind.UNION, branches=branches)

    # --- kinds ----------------------------------------------------------------------------------

    def shape(self, schema: Schema, pointer: str, stack: Stack, depth: int) -> SchemaNode:
        """The node's kind and children; `node()` adds what every kind shares."""
        if schema.get("type") is _UNION:
            return self.union(schema, pointer, stack, depth)
        if unsupported := sorted(UNSUPPORTED & schema.keys()):
            return self.refuse(pointer, RefusalCode.UNSUPPORTED_KEYWORD, f"{', '.join(unsupported)} not supported")
        if schema.get("format") == "binary" or "contentEncoding" in schema:
            return self.refuse(pointer, RefusalCode.BYTES_FIELD, "bytes are not supported")
        if "const" in schema:
            return SchemaNode(pointer, Kind.CONSTANT, values=(as_json(schema["const"]),))
        if "enum" in schema:
            return self.enum(schema["enum"], pointer)
        return self.typed(schema, pointer, stack, depth)

    def typed(self, schema: Schema, pointer: str, stack: Stack, depth: int) -> SchemaNode:
        kind = schema.get("type")
        if kind is None:
            kind = "object" if "properties" in schema else "array" if {"items", "prefixItems"} & schema.keys() else None
        if kind == "object":
            return self.object(schema, pointer, stack, depth)
        if kind == "array":
            return self.array(schema, pointer, stack, depth)
        if kind == "null":
            return SchemaNode(pointer, Kind.CONSTANT, values=(None,))
        scalar = Kind.DECIMAL if kind is _DECIMAL else Kind(kind) if isinstance(kind, str) and kind in SCALARS else None
        if scalar is not None:
            return SchemaNode(pointer, scalar)
        if kind is None:
            return self.refuse(pointer, RefusalCode.ANY_FIELD, "Any: no type to decide over")
        return self.refuse(pointer, RefusalCode.MALFORMED_SCHEMA, f"unknown type {kind!r}")

    def enum(self, raw: object, pointer: str) -> SchemaNode:
        values = as_list(raw)
        if values is None:
            return self.refuse(pointer, RefusalCode.MALFORMED_SCHEMA, "enum must be a list")
        options = tuple(as_json(v) for v in values if v is not None)
        if not options:
            return self.refuse(pointer, RefusalCode.ENUM_SIZE, "an enum needs at least one non-null value")
        kind = Kind.CONSTANT if len(options) == 1 else Kind.ENUM
        return SchemaNode(pointer, kind, nullable=len(options) < len(values), values=options)

    def object(self, schema: Schema, pointer: str, stack: Stack, depth: int) -> SchemaNode:
        properties, required = as_object(schema.get("properties", {})), as_list(schema.get("required", []))
        extra = schema.get("additionalProperties", True)
        if "patternProperties" in schema or as_object(extra) is not None or (extra is True and not properties):
            return self.refuse(pointer, RefusalCode.DICT_FIELD, "dict[str, X] and free-form objects are not supported")
        if properties is None or required is None:
            return self.refuse(pointer, RefusalCode.MALFORMED_SCHEMA, "properties must be an object, required a list")
        children = tuple(
            (
                name,
                self.node(
                    sub, child_pointer(pointer, name), "field", required=name in required, stack=stack, depth=depth + 1
                ),
            )
            for name, sub in properties.items()
        )
        return SchemaNode(pointer, Kind.OBJECT, properties=children)

    def array(self, schema: Schema, pointer: str, stack: Stack, depth: int) -> SchemaNode:
        items = schema.get("items", True)
        if "prefixItems" in schema or as_list(items) is not None:
            return self.refuse(pointer, RefusalCode.TUPLE_FIELD, "tuples are not supported")
        item = self.node(items, f"{pointer}/-", "inner", required=True, stack=stack, depth=depth + 1)
        if item.kind is Kind.UNION:
            return self.refuse(pointer, RefusalCode.UNION_IN_ARRAY, "arrays of unions are not supported in v0")
        if item.kind is Kind.OBJECT:
            return self.refuse(pointer, RefusalCode.ARRAY_OF_OBJECTS, "arrays of objects are not supported in v0")
        return SchemaNode(pointer, Kind.ARRAY, items=item)


def _is_regex(pattern: object) -> bool:
    """A `pattern` the validator can compile (jsonschema uses Python's `re`)."""
    if not isinstance(pattern, str):
        return False
    try:
        re.compile(pattern)
    except re.error:
        return False
    return True
