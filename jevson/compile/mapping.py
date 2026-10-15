"""DESIGN §4.2: each normalised field → a class and a primitive, or a named refusal.

| field | becomes |
|---|---|
| object | its properties, recursively; an object's own default never makes it class A |
| constant; a leaf with a default and no deciding `x-jevson` key (DESIGN §3.5) | class A: no node |
| `bool` | `predicate` (the tie band is `probabilities.interpret`'s) |
| string/int enum, 2-255 values | `choice` over opaque ids `c0…cN` in declared order |
| integer range declared `ordinal: true`, 2-10 levels | `score`, levels lowest first |
| any other string, number, decimal, integer, or scalar array | `unbounded_field` (class G), or |
|  | `source_selection_dropped` when a `default_extractor` is set |
| array of enum (multi-label) | `not_yet_supported` until Phase 7, with or without a default |

Subtrees the normaliser refused (`Kind.REFUSED`) are skipped, and a field whose `source` or
`generate` `declarations.py` already refused gets no second reason; every new refusal goes to the
same `Refusals`, so one `CompileError` names every pointer (R14).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal

from jevson.compile import questions
from jevson.compile.nodes import node_id, option_id
from jevson.compile.normalise import Kind, SchemaNode
from jevson.compile.refusal import Refusals
from jevson.errors import RefusalCode
from jevson.types import MAX_OPTIONS, DecisionKind, DecisionNode, JSONValue, Option, OptionSource, ProvenanceKind

MIN_LEVELS, MAX_LEVELS = 2, 10
MAX_ORDINAL_SPAN = 10_000
"""An ordinal range wider than this is refused before its levels are listed."""


def map_tree(root: SchemaNode, refusals: Refusals, *, default_extractor: str | None) -> tuple[DecisionNode, ...]:
    """The decision nodes of a normalised tree, in schema order; problems go to `refusals`."""
    if root.kind is Kind.REFUSED:
        return ()
    if root.kind is not Kind.OBJECT:
        refusals.add(root.pointer, RefusalCode.MALFORMED_SCHEMA, "the root must be an object schema")
        return ()
    mapper = _Mapper(refusals, default_extractor)
    mapper.object(root)
    return tuple(mapper.nodes)


class _Mapper:
    def __init__(self, refusals: Refusals, default_extractor: str | None) -> None:
        self.refusals = refusals
        self.default_extractor = default_extractor
        self.nodes: list[DecisionNode] = []

    def refuse(self, node: SchemaNode, code: RefusalCode, message: str) -> None:
        self.refusals.add(node.pointer, code, message)

    def object(self, node: SchemaNode) -> None:
        for name, child in node.properties:
            if child.kind is Kind.OBJECT:
                self.object(child)
            elif child.kind not in (Kind.REFUSED, Kind.CONSTANT):
                self.field(name, child)

    def field(self, name: str, node: SchemaNode) -> None:
        declaration = node.declaration
        if declaration is not None and (declaration.declares_source or declaration.generate is not None):
            return  # declarations.py refused it: source_selection_dropped, or not_yet_supported (Phase 4)
        items = node.items
        if items is not None and items.kind is Kind.REFUSED:
            return
        if items is not None and items.kind is Kind.ENUM:
            return self.refuse(node, RefusalCode.NOT_YET_SUPPORTED, "multi-label enum arrays are lifted in Phase 7")
        ordinal = declaration is not None and declaration.ordinal
        if ordinal and node.kind is not Kind.INTEGER:
            return self.refuse(node, RefusalCode.ORDINAL_LEVELS, "ordinal: true needs an integer range")
        if node.has_default and not (declaration is not None and declaration.decides):
            return  # class A: omitted, so the caller's default applies
        label = questions.label(name, node)
        if node.kind is Kind.BOOLEAN:
            self.nodes.append(
                DecisionNode(
                    node_id(node.pointer, DecisionKind.PREDICATE),
                    DecisionKind.PREDICATE,
                    questions.bool_question(label),
                    OptionSource.PREDICATE,
                    node.pointer,
                )
            )
        elif node.kind is Kind.ENUM:
            self.enum(node, label)
        elif ordinal:
            self.ordinal(node, label)
        else:
            self.unbounded(node)
        return None

    def enum(self, node: SchemaNode, label: str) -> None:
        if not all(isinstance(v, str | int) and not isinstance(v, bool) for v in node.values):
            return self.refuse(node, RefusalCode.ENUM_VALUE_TYPE, "enum values must be strings or integers")
        if len(node.values) > MAX_OPTIONS:
            return self.refuse(node, RefusalCode.ENUM_SIZE, f"{len(node.values)} values; a choice takes 2-255")
        self.choice(node, DecisionKind.CHOICE, questions.enum_question(label), node.values)
        return None

    def ordinal(self, node: SchemaNode, label: str) -> None:
        levels = _levels(node.keywords)
        if levels is None or not MIN_LEVELS <= len(levels) <= MAX_LEVELS:
            found = "an unbounded range" if levels is None else f"{len(levels)} levels"
            return self.refuse(node, RefusalCode.ORDINAL_LEVELS, f"an ordinal needs 2-10 levels; found {found}")
        self.choice(node, DecisionKind.SCORE, questions.ordinal_question(label), levels)
        return None

    def choice(self, node: SchemaNode, kind: DecisionKind, question: str, values: tuple[JSONValue, ...]) -> None:
        self.nodes.append(
            DecisionNode(
                node_id(node.pointer, kind),
                kind,
                question,
                OptionSource.SCHEMA_ENUM,
                node.pointer,
                tuple(Option(option_id(i), questions.option_description(v)) for i, v in enumerate(values)),
                provenance=ProvenanceKind.DECLARED_OPTION,
                values=values,
            )
        )

    def unbounded(self, node: SchemaNode) -> None:
        if self.default_extractor is not None:
            self.refuse(
                node,
                RefusalCode.SOURCE_SELECTION_DROPPED,
                f"default_extractor {self.default_extractor!r} would source-select this field, and Phase 0r "
                "dropped source selection [Q2, Q9]; declare `generate`, or make the field an enum, instead",
            )
        else:
            self.refuse(
                node,
                RefusalCode.UNBOUNDED_FIELD,
                "class G: an unbounded value with no default and no `generate`; declare one, or make it an enum",
            )


def _levels(keywords: Mapping[str, object]) -> tuple[JSONValue, ...] | None:
    """The integers an ordinal range allows, lowest first; None when a bound is missing or too wide.

    `minimum`/`exclusiveMinimum` and `maximum`/`exclusiveMaximum` combine to the tighter bound, and
    a positive `multipleOf` keeps only its multiples, so every level passes final validation."""
    lows = [math.ceil(v) for v in _numbers(keywords, "minimum")]
    lows += [math.floor(v) + 1 for v in _numbers(keywords, "exclusiveMinimum")]
    highs = [math.floor(v) for v in _numbers(keywords, "maximum")]
    highs += [math.ceil(v) - 1 for v in _numbers(keywords, "exclusiveMaximum")]
    if not lows or not highs or min(highs) - max(lows) > MAX_ORDINAL_SPAN:
        return None
    steps = [Decimal(repr(s)) for s in _numbers(keywords, "multipleOf") if s > 0]  # exact: 3 % 0.1 is not 0.0
    return tuple(v for v in range(max(lows), min(highs) + 1) if all(Decimal(v) % s == 0 for s in steps))


def _numbers(keywords: Mapping[str, object], key: str) -> list[float]:
    value = keywords.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return [float(value)]
    return []
