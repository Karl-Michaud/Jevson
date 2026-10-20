"""PLAN Phase 2: `compile_schema()` maps the normalised tree to a decision graph (DESIGN §4.2)."""

from __future__ import annotations

import asyncio
import enum
import json
import socket
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from jevson import CompileError, FakeBackend, RefusalCode, Result, compile_schema
from jevson.assemble.assembler import Committed, Outcome, assemble
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.types import (
    Answer,
    DecidedBy,
    DecisionKind,
    DecisionNode,
    DeclaredOption,
    Option,
    OptionSource,
    ProvenanceKind,
    Question,
    Unresolved,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "schemas"
SOURCE = "Order 17: urgent. Ship to a lit lane in France for a pro customer."


class Tier(enum.Enum):
    basic = "basic"
    pro = "pro"


class Only(enum.Enum):
    only = "only"


class Street(BaseModel):
    lit: bool = Field(description="the street is lit")
    kind: Literal["road", "lane"]


class Address(BaseModel):
    street: Street
    country: Literal["uk", "fr"]


class Customer(BaseModel):
    address: Address
    tier: Tier


class Order(BaseModel):
    """Three object levels under the root (customer → address → street), and one `$defs` type twice."""

    customer: Customer
    billing: Address
    urgent: bool = Field(description="the order is urgent")


class Idiomatic(BaseModel):
    """PLAN Phase 2: nested submodel, Enum, single-member Enum, Optional[Literal], Literal, defaulted leaves."""

    address: Address = Field(description="where the order goes")  # a sibling keyword beside the $ref
    shipping: Address | None = None
    tier: Tier
    only: Only
    size: Literal["s", "m"] | None = None
    marker: Literal["x"]
    currency: str = "USD"
    plan: Tier = Tier.basic


def ids(schema: object, **options: Any) -> list[str]:
    return list(compile_schema(schema, **options).nodes)


def refusals(schema: object, **options: Any) -> list[tuple[str, str]]:
    with pytest.raises(CompileError) as caught:
        compile_schema(schema, **options)
    return [(r.pointer, r.reason) for r in caught.value.reasons]


def obj(**properties: object) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": sorted(properties)}


def run(graph: DecisionGraph, schema: dict[str, Any], backend: FakeBackend) -> Result:
    """The executor's part (Phase 3), as in test_end_to_end: one request per level, values by option id."""
    outcomes: list[Outcome] = []
    for level in graph.levels():
        named = {f"q{i}": node for i, node in enumerate(level.decisions)}
        asked = [Question(name, n.kind, n.question, n.options) for name, n in named.items()]
        response = asyncio.run(backend.ask(SOURCE, asked, "fake"))
        for answer in response.answers:
            node = named[answer.name]
            reading = interpret(node, answer, tie_margin=10)
            selected = reading.decision.selected
            if reading.status == "unresolved" or selected is None:
                assert reading.reason is not None
                outcomes.append(Unresolved(node.target, reading.reason))
            elif isinstance(selected, bool):
                outcomes.append(Committed(node.target, selected, DecidedBy.DECISION))
            else:
                value = node.values[[o.id for o in node.options].index(selected)]
                outcomes.append(Committed(node.target, value, DecidedBy.DECISION, DeclaredOption(selected)))
    return assemble(schema, outcomes)


def second_option(question: Question) -> Answer:
    if question.kind is DecisionKind.PREDICATE:
        return FakeBackend.predicate(0.9)(question)
    return FakeBackend.select("c1", 0.9)(question)


# --- the exit criteria --------------------------------------------------------------------------


def test_a_three_level_nested_object_compiles_with_instance_pointers_and_assembles_back() -> None:
    schema = Order.model_json_schema(mode="validation")
    graph = compile_schema(Order)
    assert list(graph.nodes) == [
        "/customer/address/street/lit#predicate",
        "/customer/address/street/kind#choice",
        "/customer/address/country#choice",
        "/customer/tier#choice",
        "/billing/street/lit#predicate",
        "/billing/street/kind#choice",
        "/billing/country#choice",
        "/urgent#predicate",
    ]
    assert all(node.id.startswith(f"{node.target}#") for node in graph.nodes.values())
    result = run(graph, schema, FakeBackend(default=second_option))
    street = {"lit": True, "kind": "lane"}
    assert result.value == {
        "customer": {"address": {"street": street, "country": "fr"}, "tier": "pro"},
        "billing": {"street": street, "country": "fr"},
        "urgent": True,
    }
    assert result.satisfies_schema
    assert Order.model_validate(result.value).customer.tier is Tier.pro


def test_two_fields_sharing_one_defs_type_get_distinct_stable_ids() -> None:
    first, second = ids(Order), ids(Order)
    assert first == second
    assert "/customer/address/country#choice" in first
    assert "/billing/country#choice" in first
    assert len(set(first)) == len(first)


@pytest.mark.parametrize("model", [Order, Idiomatic])
def test_a_pydantic_model_and_its_emitted_json_schema_compile_to_identical_graphs(model: type[BaseModel]) -> None:
    from_model = compile_schema(model).nodes
    from_schema = compile_schema(model.model_json_schema(mode="validation")).nodes
    assert from_model == from_schema
    assert list(from_model) == list(from_schema)
    assert compile_schema(model).constants == compile_schema(model.model_json_schema(mode="validation")).constants


def test_idiomatic_pydantic_compiles_and_its_class_a_fields_emit_no_node() -> None:
    assert ids(Idiomatic) == [
        "/address/street/lit#predicate",
        "/address/street/kind#choice",
        "/address/country#choice",
        "/shipping/street/lit#predicate",  # Optional[Address] = None: its enum and bool leaves are decided
        "/shipping/street/kind#choice",
        "/shipping/country#choice",
        "/tier#choice",
    ]  # only, marker (constants), size, currency, plan (undeclared defaulted leaves) are class A


def test_a_flat_all_of_a_defaulted_decimal_and_bound_keywords_emit_no_node_of_their_own() -> None:
    """Class A at compile level, not only in the normaliser: the merged allOf decides only its enum."""
    schema = {
        "type": "object",
        "required": ["x", "c", "r"],
        "properties": {
            "x": {
                "allOf": [
                    {"type": "object", "properties": {"a": {"enum": ["1", "2"]}}, "required": ["a"]},
                    {"type": "object", "properties": {"b": {"const": 5}}, "required": ["b"]},
                ]
            },
            "c": {"const": "k"},
            "r": {"type": "integer", "x-jevson": {"ordinal": True}, "exclusiveMinimum": 0, "maximum": 3},
            "f": {"type": "string", "format": "date", "default": "2020-01-01"},
            "money": {
                "anyOf": [{"type": "number"}, {"type": "string", "pattern": "^-?\\d+(\\.\\d+)?$"}],
                "default": "1",
            },
        },
    }
    graph = compile_schema(schema)
    assert list(graph.nodes) == ["/x/a#choice", "/r#score"]
    assert [(c.pointer, c.value) for c in graph.constants] == [("/x/b", 5), ("/c", "k")]


class Kinded(BaseModel):
    kind: Literal["a", "b"]


@pytest.mark.parametrize(
    ("declaration", "reason"),
    [
        ({"source": {"extractor": "llm"}}, "source_selection_dropped"),
        ({"generate": {"criteria": ["is short"]}}, "generate_field_type"),
        ({"question": "Which one?"}, "misplaced_declaration"),
        ({"ordinal": True}, "ordinal_levels"),
        ({"bogus": 1}, "unknown_declaration_key"),
        ({"order": "semantic"}, "semantic_order"),
        ({"order": "source"}, "source_selection_dropped"),
    ],
)
def test_x_jevson_beside_a_nested_models_ref_is_applied_or_refused_never_dropped(
    declaration: dict[str, Any], reason: str
) -> None:
    class Holder(BaseModel):
        a: Kinded = Field(json_schema_extra={"x-jevson": declaration})

    assert "$ref" in Holder.model_json_schema(mode="validation")["properties"]["a"]
    assert refusals(Holder) == [("/a", reason)]
    assert refusals(Holder.model_json_schema(mode="validation")) == [("/a", reason)]


def test_an_optional_submodel_whose_leaves_declare_sources_refuses_only_with_source_selection_dropped() -> None:
    class Sourced(BaseModel):
        city: str = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "llm"}}})

    class Holder(BaseModel):
        place: Sourced | None = None

    assert refusals(Holder) == [("/place/city", RefusalCode.SOURCE_SELECTION_DROPPED)]


def test_list_literal_with_an_empty_default_and_a_default_factory_are_decided_alike() -> None:
    """An array's default never makes it class A while its items are decided (DESIGN §3.5)."""

    class Tagged(BaseModel):
        labels: list[Literal["p", "q"]] = []
        tags: list[Literal["p", "q"]] = Field(default_factory=list)
        required: list[Literal["p", "q"]]

    graph = compile_schema(Tagged)
    ids = sorted(graph.nodes)
    assert ids == [f"/{name}#member:c{i}" for name in ("labels", "required", "tags") for i in (0, 1)]
    by_target = {name: [n for n in graph.nodes.values() if n.target == f"/{name}"] for name in ("labels", "tags")}
    assert [n.question for n in by_target["labels"]] == [
        n.question.replace("tags", "labels") for n in by_target["tags"]
    ]


def test_decimal_and_optional_decimal_declaring_a_source_refuse_only_with_source_selection_dropped() -> None:
    source: dict[str, Any] = {"x-jevson": {"source": {"extractor": "money"}}}

    class Money(BaseModel):
        total: Decimal = Field(json_schema_extra=source)
        tip: Decimal | None = Field(default=None, json_schema_extra=source)

    assert refusals(Money) == [
        ("/total", RefusalCode.SOURCE_SELECTION_DROPPED),
        ("/tip", RefusalCode.SOURCE_SELECTION_DROPPED),
    ]


def test_compile_schema_makes_no_network_call() -> None:
    with pytest.raises(RuntimeError, match="stubbed"):
        socket.create_connection(("example.com", 443))  # the autouse stub of conftest.py is active
    for path in sorted(FIXTURES.glob("*.schema.json")):
        outcome: DecisionGraph | CompileError
        try:
            outcome = compile_schema(json.loads(path.read_text(encoding="utf-8")))
        except CompileError as error:
            outcome = error
        assert isinstance(outcome, DecisionGraph) or outcome.reasons, path.name


# --- the mapping table ----------------------------------------------------------------------------


def test_bool_enum_and_ordinal_map_to_predicate_choice_and_score_over_opaque_ids() -> None:
    nodes = compile_schema(
        obj(
            paid={"type": "boolean", "description": "the invoice is paid."},
            size={"enum": ["s", 2]},
            rating={"type": "integer", "minimum": 1, "maximum": 3, "x-jevson": {"ordinal": True}},
        )
    ).nodes
    assert nodes["/paid#predicate"] == DecisionNode(
        "/paid#predicate",
        DecisionKind.PREDICATE,
        "According to the source, is it true that the invoice is paid?",
        OptionSource.PREDICATE,
        "/paid",
    )
    assert nodes["/size#choice"] == DecisionNode(
        "/size#choice",
        DecisionKind.CHOICE,
        "Which of these is the size?",
        OptionSource.SCHEMA_ENUM,
        "/size",
        (Option("c0", '"s"'), Option("c1", '"2"')),
        provenance=ProvenanceKind.DECLARED_OPTION,
        values=("s", 2),
    )
    rating = nodes["/rating#score"]
    assert (rating.kind, rating.question) == (DecisionKind.SCORE, "Which level best describes the rating?")
    assert [o.id for o in rating.options] == ["c0", "c1", "c2"]
    assert rating.values == (1, 2, 3)


@pytest.mark.parametrize(
    ("keywords", "levels"),
    [
        ({"minimum": 0, "maximum": 9}, list(range(10))),
        ({"exclusiveMinimum": 0, "exclusiveMaximum": 4}, [1, 2, 3]),
        ({"minimum": 0.5, "maximum": 3.5}, [1, 2, 3]),
        ({"minimum": 0, "exclusiveMinimum": 1, "maximum": 4, "exclusiveMaximum": 4}, [2, 3]),
        ({"minimum": 0, "maximum": 40, "multipleOf": 10}, [0, 10, 20, 30, 40]),
        ({"minimum": 1, "maximum": 3, "multipleOf": 0.1}, [1, 2, 3]),
    ],
)
def test_ordinal_levels_honour_every_bound_keyword(keywords: dict[str, object], levels: list[int]) -> None:
    field = {"type": "integer", "x-jevson": {"ordinal": True}, **keywords}
    assert compile_schema(obj(r=field)).nodes["/r#score"].values == tuple(levels)


def test_defaulted_leaves_are_class_a_unless_a_key_asks_for_a_decision() -> None:
    schema = obj(
        flag={"type": "boolean", "default": False},
        asked={"type": "boolean", "default": False, "x-jevson": {"question": "it ships today"}},
        rating={"type": "integer", "minimum": 1, "maximum": 2, "default": 1, "x-jevson": {"ordinal": True}},
        note={"type": "string", "default": ""},
        notes={"type": "array", "items": {"type": "string"}, "default": []},
        fixed={"const": 3},
    )
    assert ids(schema) == ["/asked#predicate", "/rating#score"]


UNBOUNDED, ORDINAL = RefusalCode.UNBOUNDED_FIELD, RefusalCode.ORDINAL_LEVELS


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ({"enum": [f"v{i}" for i in range(256)]}, RefusalCode.ENUM_SIZE),
        ({"enum": [1.5, 2.5]}, RefusalCode.ENUM_VALUE_TYPE),
        ({"enum": [True, "x"]}, RefusalCode.ENUM_VALUE_TYPE),
        ({"enum": ["a", "a"]}, RefusalCode.INDISTINGUISHABLE_OPTIONS),
        ({"enum": ["1", 1]}, RefusalCode.INDISTINGUISHABLE_OPTIONS),
        ({"enum": ["a", "b", "a", None]}, RefusalCode.INDISTINGUISHABLE_OPTIONS),
        ({"type": "integer", "minimum": 0, "maximum": 10, "x-jevson": {"ordinal": True}}, RefusalCode.ORDINAL_LEVELS),
        ({"type": "integer", "minimum": 3, "maximum": 3, "x-jevson": {"ordinal": True}}, RefusalCode.ORDINAL_LEVELS),
        ({"type": "integer", "minimum": 0, "x-jevson": {"ordinal": True}}, RefusalCode.ORDINAL_LEVELS),
        ({"type": "integer", "minimum": 0, "maximum": 10**12, "x-jevson": {"ordinal": True}}, ORDINAL),
        ({"type": "number", "minimum": 1, "maximum": 5, "x-jevson": {"ordinal": True}}, RefusalCode.ORDINAL_LEVELS),
        ({"enum": ["a", "b"], "x-jevson": {"ordinal": True}}, RefusalCode.ORDINAL_LEVELS),
        ({"type": "string"}, UNBOUNDED),
        ({"type": "string", "format": "date", "default": "", "x-jevson": {"question": "the date"}}, UNBOUNDED),
        ({"type": "number", "minimum": 0, "maximum": 1}, UNBOUNDED),
        ({"type": "integer", "minimum": 1, "maximum": 5}, UNBOUNDED),
        ({"type": "array", "items": {"type": "string"}}, UNBOUNDED),
        ({"x-jevson": {"generate": {"criteria": ["c"]}}, "type": "integer"}, RefusalCode.GENERATE_FIELD_TYPE),
        ({"x-jevson": {"source": {"extractor": "nope"}}, "type": "string"}, RefusalCode.SOURCE_SELECTION_DROPPED),
    ],
)
def test_each_unmappable_field_refuses_with_one_named_reason(field: dict[str, object], code: RefusalCode) -> None:
    assert refusals(obj(f=field)) == [("/f", code)]


def test_indistinguishable_enum_options_are_named_and_the_size_message_states_the_real_bound() -> None:
    with pytest.raises(CompileError) as caught:
        compile_schema(obj(f={"enum": ["1", 1, "b"]}))
    assert [r.message for r in caught.value.reasons] == ['values "1" and 1 render as the same option "1"']
    with pytest.raises(CompileError) as caught:
        compile_schema(obj(f={"enum": [f"v{i}" for i in range(256)]}))
    assert [r.message for r in caught.value.reasons] == ["256 values; an enum takes at most 255"]


def test_an_enum_of_exactly_255_values_compiles_as_a_choice_or_a_multi_label_array() -> None:
    values = [f"v{i}" for i in range(255)]
    graph = compile_schema(obj(f={"enum": values}, tags={"type": "array", "items": {"enum": values}}))
    assert len(graph.nodes["/f#choice"].options) == 255
    assert len([n for n in graph.nodes.values() if n.target == "/tags"]) == 255  # one membership each


def messages(schema: object) -> list[str]:
    with pytest.raises(CompileError) as caught:
        compile_schema(schema)
    return [r.message for r in caught.value.reasons]


@pytest.mark.parametrize(
    ("declaration", "message"),
    [
        ({"ordinal": True}, "ordinal: true needs an integer range, not an object"),
        (
            {"question": "Which one?"},
            "x-jevson.question decides one field; an object is compiled from its properties, so declare "
            "the question on the property it asks about",
        ),
        ({"order": "semantic"}, "x-jevson.order: semantic is out of v0 (R7); remove the key"),
    ],
)
def test_each_new_refusal_beside_a_ref_says_exactly_what_to_do(declaration: dict[str, Any], message: str) -> None:
    class Holder(BaseModel):
        a: Kinded = Field(json_schema_extra={"x-jevson": declaration})

    assert messages(Holder) == [message]


def test_a_null_in_a_multi_label_items_enum_says_exactly_what_to_do() -> None:
    assert messages(obj(tags={"type": "array", "items": {"enum": ["a", "b", None]}})) == [
        "a multi-label array's item enum cannot include null: membership is asked per declared value; "
        "drop the null, or make the whole array optional instead"
    ]


def test_default_extractor_turns_unbounded_fields_into_source_selection_dropped() -> None:
    schema = obj(vendor={"type": "string"}, total={"type": "number"}, kind={"enum": ["a", "b"]})
    dropped = RefusalCode.SOURCE_SELECTION_DROPPED
    assert refusals(schema, default_extractor="llm") == [("/vendor", dropped), ("/total", dropped)]
    assert refusals(schema) == [("/vendor", UNBOUNDED), ("/total", UNBOUNDED)]
    assert refusals(schema, extractors=frozenset({"llm"})) == refusals(schema)


def test_an_array_whose_items_were_refused_gets_only_the_normalisers_reason() -> None:
    assert refusals(obj(anything={"type": "array", "items": {}})) == [("/anything/-", RefusalCode.ANY_FIELD)]


@pytest.mark.parametrize("root", [{"type": "string"}, {"enum": ["a", "b"]}, {"type": "array", "items": {}}])
def test_a_root_that_is_not_an_object_refuses(root: dict[str, object]) -> None:
    assert ("", RefusalCode.MALFORMED_SCHEMA) in refusals(root)


def test_refusal_is_total_across_normalising_and_mapping() -> None:
    schema = obj(
        free={"type": "string"},
        many={"enum": list(range(300))},
        any={},
        nested=obj(rating={"type": "integer", "x-jevson": {"ordinal": True}}, tags={"type": "object"}),
        source={"type": "string", "x-jevson": {"source": {}}},
        fine={"type": "boolean", "description": "it is fine"},
    )
    assert sorted(refusals(schema)) == [
        ("/any", RefusalCode.ANY_FIELD),
        ("/free", UNBOUNDED),
        ("/many", RefusalCode.ENUM_SIZE),
        ("/nested/rating", RefusalCode.ORDINAL_LEVELS),
        ("/nested/tags", RefusalCode.DICT_FIELD),
        ("/source", RefusalCode.SOURCE_SELECTION_DROPPED),
    ]


def test_a_schema_with_nothing_to_decide_compiles_to_an_empty_graph() -> None:
    graph = compile_schema(obj(currency={"type": "string", "default": "USD"}, kind={"const": "invoice"}))
    assert (dict(graph.nodes), graph.levels()) == ({}, ())


def test_decision_node_values_must_align_with_options() -> None:
    options = (Option("c0", "a"), Option("c1", "b"))
    with pytest.raises(ValueError, match="align"):
        DecisionNode("/x#choice", DecisionKind.CHOICE, "q", OptionSource.SCHEMA_ENUM, "/x", options, values=("a",))


# --- distinct questions (ASTERION-29) ------------------------------------------------------------


class Addr(BaseModel):
    kind: Literal["home", "work"]
    verified: bool = Field(description="the address was verified")


class Shipment(BaseModel):
    billing: Addr
    shipping: Addr | None


def test_same_named_nested_fields_render_distinct_questions() -> None:
    questions = {node.id: node.question for node in compile_schema(Shipment).nodes.values()}
    assert questions == {
        "/billing/kind#choice": "Which of these is the billing kind?",
        "/billing/verified#predicate": (
            "According to the source, for the billing, is it true that the address was verified?"
        ),
        "/shipping/kind#choice": "Which of these is the shipping kind?",
        "/shipping/verified#predicate": (
            "According to the source, for the shipping, is it true that the address was verified?"
        ),
    }


def test_a_unique_label_stays_unqualified_and_ordinals_are_scoped_too() -> None:
    rating = {"type": "integer", "minimum": 1, "maximum": 3, "x-jevson": {"ordinal": True}}
    nodes = compile_schema(obj(seller=obj(rating=rating, tier={"enum": ["a", "b"]}), buyer=obj(rating=rating))).nodes
    assert nodes["/seller/tier#choice"].question == "Which of these is the tier?"
    assert nodes["/seller/rating#score"].question == "Which level best describes the seller rating?"
    assert nodes["/buyer/rating#score"].question == "Which level best describes the buyer rating?"


def test_two_fields_declaring_one_question_refuse_duplicate_question() -> None:
    asked = {"enum": ["a", "b"], "x-jevson": {"question": "the plan"}}
    assert refusals(obj(old=obj(tier=asked), new=obj(tier=asked))) == [("/new/tier", RefusalCode.DUPLICATE_QUESTION)]


def test_one_declared_question_over_different_options_is_not_a_duplicate() -> None:
    first = {"enum": ["a", "b"], "x-jevson": {"question": "plan"}}
    second = {"enum": ["a", "c"], "x-jevson": {"question": "plan"}}
    nodes = compile_schema(obj(old=first, new=second)).nodes
    assert nodes["/old#choice"].question == nodes["/new#choice"].question == "Which of these is the plan?"


def test_the_duplicate_question_refusal_names_the_first_pointer() -> None:
    asked = {"type": "boolean", "x-jevson": {"question": "it ships today"}}
    with pytest.raises(CompileError) as caught:
        compile_schema(obj(a=asked, b=asked, c=asked))
    reasons = caught.value.reasons
    assert [(r.pointer, r.reason) for r in reasons] == [
        ("/b", RefusalCode.DUPLICATE_QUESTION),
        ("/c", RefusalCode.DUPLICATE_QUESTION),
    ]
    assert all("/a" in r.message for r in reasons)


@pytest.mark.parametrize("field", [{"type": "boolean"}, {"type": "boolean", "description": " . "}])
def test_a_decided_bool_with_no_statement_refuses_bool_predicate_missing(field: dict[str, object]) -> None:
    assert refusals(obj(verified=field)) == [("/verified", RefusalCode.BOOL_PREDICATE_MISSING)]
