"""The DESIGN §3.5 normalisation table, and the Phase 2 exit criteria it alone can satisfy."""

from __future__ import annotations

import copy
import enum
import json
from decimal import Decimal
from pathlib import Path
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from jevson.compile import normalise as normalise_module
from jevson.compile.normalise import Kind, SchemaNode, normalise, normalise_schema
from jevson.compile.refusal import Refusals
from jevson.errors import CompileError, RefusalCode

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schemas"


class Tier(enum.Enum):
    basic = "basic"
    pro = "pro"


class Only(enum.Enum):
    only = "only"


class Address(BaseModel):
    model_config = {"json_schema_extra": {"x-jevson": {"question": "model-level, never a field's"}}}
    kind: Tier
    verified: bool


class Idiomatic(BaseModel):
    """PLAN Phase 2: nested submodel, Enum, single-member Enum, Optional[Literal], Literal, defaulted leaves."""

    address: Address = Field(description="where", json_schema_extra={"x-jevson": {"question": "Which address?"}})
    shipping: Address | None = None
    tier: Tier
    only: Only
    size: Literal["s", "m"] | None = None
    marker: Literal["x"]
    currency: str = "USD"
    plan: Tier = Tier.basic
    labels: list[Literal["p", "q"]] = []
    tags: list[Literal["p", "q"]] = Field(default_factory=list)


def refusals_of(schema: object) -> list[tuple[str, str]]:
    refusals = Refusals()
    normalise(schema, refusals)
    return [(r.pointer, r.reason) for r in refusals.reasons]


def child(node: SchemaNode, *path: str) -> SchemaNode:
    for name in path:
        node = dict(node.properties)[name]
    return node


def walk(node: SchemaNode) -> list[SchemaNode]:
    found = [node]
    for _, sub in node.properties:
        found += walk(sub)
    return found + (walk(node.items) if node.items else [])


# --- idiomatic Pydantic ---------------------------------------------------------------------


def test_idiomatic_pydantic_normalises_without_refusal() -> None:
    root = normalise_schema(Idiomatic)
    assert root.kind is Kind.OBJECT
    assert child(root, "address").kind is Kind.OBJECT
    assert child(root, "address", "kind").values == ("basic", "pro")
    assert child(root, "tier").kind is Kind.ENUM
    assert (child(root, "only").kind, child(root, "only").values) == (Kind.CONSTANT, ("only",))
    size = child(root, "size")
    assert (size.kind, size.values, size.nullable, size.has_default) == (Kind.ENUM, ("s", "m"), True, True)
    assert (child(root, "marker").kind, child(root, "marker").values) == (Kind.CONSTANT, ("x",))
    currency, plan = child(root, "currency"), child(root, "plan")
    assert (currency.kind, currency.has_default, currency.default, currency.required) == (
        Kind.STRING,
        True,
        "USD",
        False,
    )
    assert (plan.kind, plan.default, plan.required) == (Kind.ENUM, "basic", False)


def test_optional_submodel_keeps_its_leaves_as_a_nullable_object() -> None:
    shipping = child(normalise_schema(Idiomatic), "shipping")
    assert (shipping.kind, shipping.nullable, shipping.has_default, shipping.default) == (Kind.OBJECT, True, True, None)
    assert child(shipping, "kind").kind is Kind.ENUM
    assert child(shipping, "verified").kind is Kind.BOOLEAN


def test_two_fields_of_one_defs_type_get_distinct_instance_pointers() -> None:
    root = normalise_schema(Idiomatic)
    assert child(root, "address", "kind").pointer == "/address/kind"
    assert child(root, "shipping", "kind").pointer == "/shipping/kind"


def test_list_literal_default_empty_and_default_factory_normalise_identically() -> None:
    root = normalise_schema(Idiomatic)
    labels, tags = child(root, "labels"), child(root, "tags")
    assert labels.kind is tags.kind is Kind.ARRAY
    assert labels.items is not None
    assert tags.items is not None
    assert labels.items.values == tags.items.values == ("p", "q")
    assert (labels.required, tags.required) == (False, False)


def test_decimal_and_optional_decimal_with_a_source_refuse_only_with_source_selection_dropped() -> None:
    class Money(BaseModel):
        total: Decimal = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "money"}}})
        tip: Decimal | None = Field(None, json_schema_extra={"x-jevson": {"source": {"extractor": "money"}}})

    refusals = Refusals()
    root = normalise(Money, refusals)
    assert [(r.pointer, r.reason) for r in refusals.reasons] == [
        ("/total", RefusalCode.SOURCE_SELECTION_DROPPED),
        ("/tip", RefusalCode.SOURCE_SELECTION_DROPPED),
    ]
    assert child(root, "total").kind is child(root, "tip").kind is Kind.DECIMAL
    assert (child(root, "total").nullable, child(root, "tip").nullable) == (False, True)


def test_a_pydantic_model_and_its_emitted_json_schema_normalise_identically() -> None:
    assert normalise_schema(Idiomatic) == normalise_schema(Idiomatic.model_json_schema(mode="validation"))


# --- x-jevson placement [L18] ---------------------------------------------------------------


def test_x_jevson_beside_a_ref_is_found_and_model_level_extra_is_not_a_declaration() -> None:
    root = normalise_schema(Idiomatic)
    address = child(root, "address")
    assert address.declaration is not None
    assert address.declaration.question == "Which address?"
    assert address.description == "where"
    assert child(root, "shipping").declaration is None
    assert root.declaration is None


def test_x_jevson_on_array_items_or_a_union_branch_is_misplaced() -> None:
    schema = {
        "type": "object",
        "properties": {
            "a": {"type": "array", "items": {"enum": ["x", "y"], "x-jevson": {"question": "q"}}},
            "b": {"anyOf": [{"type": "boolean", "x-jevson": {}}, {"type": "null"}]},
        },
    }
    assert refusals_of(schema) == [
        ("/a/-", RefusalCode.MISPLACED_DECLARATION),
        ("/b", RefusalCode.MISPLACED_DECLARATION),
    ]


# --- allOf, unions, nulls ---------------------------------------------------------------------


def obj(**properties: object) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": sorted(properties)}


def test_a_flat_all_of_of_object_schemas_merges() -> None:
    schema = {
        "$defs": {"B": obj(b={"type": "boolean"})},
        **obj(x={"allOf": [obj(a={"enum": ["1", "2"]}), {"$ref": "#/$defs/B"}]}),
    }
    x = child(normalise_schema(schema), "x")
    assert x.kind is Kind.OBJECT
    assert [name for name, _ in x.properties] == ["a", "b"]
    assert child(x, "a").required
    assert child(x, "b").required


def test_a_one_branch_all_of_inlines_like_a_ref() -> None:
    schema = {"$defs": {"T": {"enum": ["a", "b"]}}, **obj(t={"allOf": [{"$ref": "#/$defs/T"}], "description": "d"})}
    t = child(normalise_schema(schema), "t")
    assert (t.kind, t.description) == (Kind.ENUM, "d")


@pytest.mark.parametrize(
    "branches",
    [
        [obj(a={"type": "boolean"}), {"type": "string"}],
        [obj(a={"type": "boolean"}), obj(a={"type": "boolean"})],
        [obj(a={"type": "boolean"}), {**obj(b={"type": "boolean"}), "anyOf": [{}]}],
        [obj(a={"type": "boolean"}), "no"],
        "no",
    ],
)
def test_a_non_flat_all_of_refuses(branches: object) -> None:
    assert refusals_of(obj(x={"allOf": branches})) == [("/x", RefusalCode.NON_FLAT_ALL_OF)]


def test_a_discriminated_union_normalises_to_its_branches_at_its_own_pointer() -> None:
    class Cat(BaseModel):
        pet: Literal["cat"]
        indoor: bool

    class Dog(BaseModel):
        pet: Literal["dog"]

    class Owner(BaseModel):
        pet: Cat | Dog = Field(discriminator="pet")

    union = dict(normalise_schema(Owner).properties)["pet"]
    assert union.kind is Kind.UNION
    assert [(b.pointer, b.kind, b.title) for b in union.branches] == [
        ("/pet", Kind.OBJECT, "Cat"),
        ("/pet", Kind.OBJECT, "Dog"),
    ]
    assert [p.pointer for _, p in union.branches[0].properties] == ["/pet/pet", "/pet/indoor"]


@pytest.mark.parametrize(
    ("field", "kinds", "nullable"),
    [
        ({"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]}, [Kind.STRING, Kind.INTEGER], True),
        ({"type": ["boolean", "integer"], "description": "d"}, [Kind.BOOLEAN, Kind.INTEGER], False),
        ({"oneOf": [{"enum": ["a", "b"]}, obj(x={"type": "boolean"})]}, [Kind.ENUM, Kind.OBJECT], False),
    ],
)
def test_unions_with_two_or_more_non_null_branches_normalise(field: object, kinds: list[Kind], nullable: bool) -> None:
    union = dict(normalise_schema(obj(u=field)).properties)["u"]
    assert (union.kind, [b.kind for b in union.branches], union.nullable) == (Kind.UNION, kinds, nullable)
    assert all(b.description is None for b in union.branches)  # a type list's annotations stay on the union


def test_any_of_beside_one_of_and_arrays_of_unions_refuse() -> None:
    schema = obj(
        u={"anyOf": [{"type": "string"}], "oneOf": [{"type": "string"}]},
        a={"type": "array", "items": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
    )
    assert refusals_of(schema) == [("/u", RefusalCode.UNSUPPORTED_KEYWORD), ("/a", RefusalCode.UNION_IN_ARRAY)]


def test_null_forms_strip_to_nullable_values() -> None:
    root = normalise_schema(
        obj(
            a={"type": ["boolean", "null"]},
            b={"enum": ["x", "y", None]},
            c={"type": "null"},
            d={"anyOf": [{"type": "null"}]},
            e={"oneOf": [{"anyOf": [{"type": "integer"}, {"type": "null"}]}]},
            f={"const": 3},
            g={"type": ["null"]},
        )
    )
    assert (child(root, "a").kind, child(root, "a").nullable) == (Kind.BOOLEAN, True)
    assert (child(root, "b").kind, child(root, "b").values, child(root, "b").nullable) == (Kind.ENUM, ("x", "y"), True)
    assert (child(root, "c").kind, child(root, "c").values) == (Kind.CONSTANT, (None,))
    assert (child(root, "d").kind, child(root, "d").nullable) == (Kind.CONSTANT, True)
    assert (child(root, "e").kind, child(root, "e").nullable) == (Kind.INTEGER, True)
    assert (child(root, "f").kind, child(root, "f").values) == (Kind.CONSTANT, (3,))
    assert (child(root, "g").kind, child(root, "g").values, child(root, "g").nullable) == (Kind.CONSTANT, (None,), True)


def test_validation_keywords_are_kept_and_structure_is_not() -> None:
    field = {"type": "number", "exclusiveMinimum": 0, "multipleOf": 0.5, "format": "float", "title": "t", "x-vendor": 1}
    root = normalise_schema({**obj(n=field), "additionalProperties": False})
    assert child(root, "n").keywords == {"exclusiveMinimum": 0, "multipleOf": 0.5, "format": "float"}
    assert root.keywords == {"additionalProperties": False}


# --- named refusals -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ({"$ref": "#"}, RefusalCode.RECURSIVE_REF),
        ({"$dynamicRef": "#meta"}, RefusalCode.DYNAMIC_REF),
        ({"$ref": "other.json#/T"}, RefusalCode.EXTERNAL_REF),
        ({"$ref": "#/$defs/Missing"}, RefusalCode.EXTERNAL_REF),
        ({"$ref": 3}, RefusalCode.EXTERNAL_REF),
        ({"type": "object", "additionalProperties": {"type": "integer"}}, RefusalCode.DICT_FIELD),
        ({"type": "object"}, RefusalCode.DICT_FIELD),
        ({"type": "object", "patternProperties": {"^a": {}}}, RefusalCode.DICT_FIELD),
        ({"type": "array", "prefixItems": [{"type": "integer"}]}, RefusalCode.TUPLE_FIELD),
        ({"type": "array", "items": [{"type": "integer"}]}, RefusalCode.TUPLE_FIELD),
        ({}, RefusalCode.ANY_FIELD),
        ({"description": "anything"}, RefusalCode.ANY_FIELD),
        ({"type": "string", "format": "binary"}, RefusalCode.BYTES_FIELD),
        ({"type": "string", "contentEncoding": "base64"}, RefusalCode.BYTES_FIELD),
        ({"type": "array", "items": obj(a={"type": "boolean"})}, RefusalCode.ARRAY_OF_OBJECTS),
        ({"type": "string", "not": {"const": "a"}}, RefusalCode.UNSUPPORTED_KEYWORD),
        ({"enum": []}, RefusalCode.ENUM_SIZE),
        ({"enum": "ab"}, RefusalCode.MALFORMED_SCHEMA),
        ({"type": "date"}, RefusalCode.MALFORMED_SCHEMA),
        ({"type": "decimal"}, RefusalCode.MALFORMED_SCHEMA),
        ("string", RefusalCode.MALFORMED_SCHEMA),
        ({"anyOf": "no"}, RefusalCode.MALFORMED_SCHEMA),
        ({"type": "object", "properties": [], "additionalProperties": False}, RefusalCode.MALFORMED_SCHEMA),
        ({"$ref": "#/$defs/Max", "maximum": 5}, RefusalCode.REF_SIBLING_CONFLICT),
    ],
)
def test_each_unsupported_construct_refuses_with_its_named_reason(field: object, code: RefusalCode) -> None:
    schema = {"$defs": {"Max": {"type": "integer", "maximum": 10}}, **obj(f=field)}
    assert refusals_of(schema) == [("/f", code)]


def test_a_recursive_pydantic_model_refuses_with_recursive_ref() -> None:
    class Node(BaseModel):
        child: Node | None = None

    assert refusals_of(Node) == [("/child", RefusalCode.RECURSIVE_REF)]


def test_an_array_with_no_items_schema_is_any_at_its_items() -> None:
    assert refusals_of(obj(a={"type": "array"})) == [("/a/-", RefusalCode.ANY_FIELD)]


def test_oversized_and_overdeep_schemas_refuse_instead_of_recursing() -> None:
    deep: dict[str, object] = {"type": "boolean"}
    for _ in range(normalise_module.MAX_DEPTH + 2):
        deep = obj(d=deep)
    assert refusals_of(deep) == [("", RefusalCode.SCHEMA_TOO_LARGE)]
    wide = obj(**{f"p{i}": {"type": "boolean"} for i in range(normalise_module.MAX_NODES + 1)})
    assert ("", RefusalCode.SCHEMA_TOO_LARGE) in refusals_of(wide)


def test_refusal_is_total_and_lists_every_offending_pointer() -> None:
    schema = obj(
        a={"type": "array", "prefixItems": []},
        b={"type": "object", "additionalProperties": {}},
        c={"type": "string", "x-jevson": {"source": {"extractor": "llm"}}},
        d=obj(e={"type": "string", "x-jevson": {"order": "semantic", "bogus": 1}}),
        f={"anyOf": [obj(t={"type": "array", "prefixItems": []}), {"type": "integer"}]},
        ok={"type": "boolean"},
    )
    with pytest.raises(CompileError) as raised:
        normalise_schema(schema)
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [
        ("/a", RefusalCode.TUPLE_FIELD),
        ("/b", RefusalCode.DICT_FIELD),
        ("/c", RefusalCode.SOURCE_SELECTION_DROPPED),
        ("/d/e", RefusalCode.UNKNOWN_DECLARATION_KEY),
        ("/d/e", RefusalCode.SEMANTIC_ORDER),
        ("/f/t", RefusalCode.TUPLE_FIELD),  # inside a union branch: every branch is normalised
    ]


def test_property_names_are_escaped_in_pointers() -> None:
    root = normalise_schema(obj(**{"a/b": {"type": "boolean"}, "c~d": {"type": "boolean"}}))
    assert [sub.pointer for _, sub in root.properties] == ["/a~1b", "/c~0d"]


# --- Pydantic integration and hygiene ----------------------------------------------------------


def test_pydantic_older_than_2_12_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(normalise_module.metadata, "version", lambda _: "2.11.9")
    assert refusals_of(Idiomatic) == [("", RefusalCode.PYDANTIC_TOO_OLD)]


def test_a_model_pydantic_cannot_emit_refuses_instead_of_raising() -> None:
    class Broken:
        @staticmethod
        def model_json_schema(mode: str) -> object:
            raise TypeError(f"cannot emit in {mode} mode")

    assert refusals_of(Broken()) == [("", RefusalCode.MALFORMED_SCHEMA)]


def test_normalising_never_mutates_the_callers_schema() -> None:
    schema = Idiomatic.model_json_schema(mode="validation")
    before = copy.deepcopy(schema)
    normalise_schema(schema)
    assert schema == before


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.schema.json")), ids=lambda p: p.name)
def test_real_schemas_normalise_or_refuse_with_the_network_stubbed_to_raise(path: Path) -> None:
    """Zero network calls: tests/unit/conftest.py makes every socket connection raise."""
    refusals = Refusals()
    root = normalise(json.loads(path.read_text(encoding="utf-8")), refusals)
    refused = [n for n in walk(root) if n.kind is Kind.REFUSED]
    assert not refused or refusals
