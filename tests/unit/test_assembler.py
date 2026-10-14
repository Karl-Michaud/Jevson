"""The DESIGN §5.6 absence table, object abstention, unresolved subtrees, and validation."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from jevson.assemble.assembler import Abstained, Committed, assemble
from jevson.types import (
    Cost,
    DecidedBy,
    Decision,
    DecisionKind,
    DeclaredOption,
    Span,
    Unresolved,
    UnresolvedReason,
)


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema(mode="validation")


class OptionalWithDefault(BaseModel):
    name: str | None = "x"


class RequiredNullable(BaseModel):
    name: str | None


class RequiredNotNullable(BaseModel):
    name: str


class NotRequired(BaseModel):
    name: str = "anonymous"


SPAN = Span("doc", 3, 9)


# --- the DESIGN §5.6 table, row by row --------------------------------------------------------


def test_optional_with_a_non_null_default_is_omitted_and_pydantic_supplies_the_default() -> None:
    result = assemble(
        schema_of(OptionalWithDefault), [Abstained("/name", (SPAN,), 88)], source_selected=frozenset({"/name"})
    )
    assert result.value == {}
    assert result.absent[0].pointer == "/name"
    assert result.absent[0].candidates_seen == (SPAN,)
    assert result.absent[0].abstain_probability == 88
    assert result.complete is True
    assert result.satisfies_schema is True
    assert OptionalWithDefault.model_validate(result.value).name == "x"


def test_not_required_is_omitted_and_absent() -> None:
    result = assemble(schema_of(NotRequired), [Abstained("/name")])
    assert (result.value, [a.pointer for a in result.absent], result.complete) == ({}, ["/name"], True)


def test_required_nullable_yields_null_and_absent() -> None:
    result = assemble(schema_of(RequiredNullable), [Abstained("/name")])
    assert result.value == {"name": None}
    assert [a.pointer for a in result.absent] == ["/name"]
    assert (result.complete, result.satisfies_schema) == (True, True)


@pytest.mark.parametrize(
    ("no_candidates", "reason"),
    [(False, UnresolvedReason.ABSTAINED), (True, UnresolvedReason.NO_CANDIDATES)],
)
def test_required_not_nullable_is_omitted_and_unresolved(no_candidates: bool, reason: UnresolvedReason) -> None:
    result = assemble(schema_of(RequiredNotNullable), [Abstained("/name", (SPAN,), 70, no_candidates)])
    assert result.value == {}
    assert result.unresolved == (Unresolved("/name", reason, (SPAN,), 70),)
    assert result.absent == ()
    assert result.complete is False
    assert result.satisfies_schema is False
    assert [v.keyword for v in result.violations] == ["required"]


@pytest.mark.parametrize("model", [OptionalWithDefault, RequiredNullable, RequiredNotNullable])
def test_a_refusal_never_follows_the_table(model: type[BaseModel]) -> None:
    refused = Unresolved("/name", UnresolvedReason.REFUSED)
    result = assemble(schema_of(model), [refused])
    assert result.value == {}
    assert result.unresolved == (refused,)
    assert result.absent == ()
    assert result.complete is False


# --- objects ---------------------------------------------------------------------------------


class Address(BaseModel):
    street: str
    country: Literal["US", "CA"]


class Invoice(BaseModel):
    number: str
    shipping: Address | None = None


class StrictInvoice(BaseModel):
    shipping: Address


CLASS_D = frozenset({"/shipping/street"})
COUNTRY = Committed("/shipping/country", "US", DecidedBy.DECISION, DeclaredOption("o0"))


def test_an_object_whose_class_d_descendants_all_abstained_is_itself_absent() -> None:
    result = assemble(
        schema_of(Invoice),
        [Committed("/number", "INV-1", DecidedBy.CALLER), Abstained("/shipping/street", (SPAN,)), COUNTRY],
        source_selected=CLASS_D,
    )
    assert result.value == {"number": "INV-1"}  # the committed enum under it is discarded
    assert [a.pointer for a in result.absent] == ["/shipping"]
    assert result.absent[0].candidates_seen == (SPAN,)
    assert "/shipping/country" not in result.decided_by
    assert (result.complete, result.satisfies_schema) == (True, True)


def test_a_required_abstained_object_is_unresolved_once_at_its_pointer() -> None:
    result = assemble(schema_of(StrictInvoice), [Abstained("/shipping/street"), COUNTRY], source_selected=CLASS_D)
    assert result.value == {}
    assert result.unresolved == (Unresolved("/shipping", UnresolvedReason.ABSTAINED),)


def test_an_object_with_a_committed_class_d_descendant_is_not_abstained() -> None:
    street = Committed("/shipping/street", "1 Main St", DecidedBy.DECISION, SPAN)
    result = assemble(
        schema_of(Invoice), [Committed("/number", "1", DecidedBy.CODE), street, COUNTRY], source_selected=CLASS_D
    )
    assert result.value == {"number": "1", "shipping": {"street": "1 Main St", "country": "US"}}
    assert result.provenance == {"/shipping/country": DeclaredOption("o0"), "/shipping/street": SPAN}
    assert result.satisfies_schema is True


def test_an_object_with_a_refused_class_d_descendant_is_not_abstained() -> None:
    refused = Unresolved("/shipping/street", UnresolvedReason.REFUSED)
    result = assemble(
        schema_of(Invoice), [Committed("/number", "1", DecidedBy.CODE), refused, COUNTRY], source_selected=CLASS_D
    )
    assert result.value == {"number": "1", "shipping": {"country": "US"}}
    assert result.unresolved == (refused,)
    assert result.absent == ()


def test_an_object_without_class_d_descendants_is_never_abstained() -> None:
    result = assemble(schema_of(Invoice), [Committed("/number", "1", DecidedBy.CODE), COUNTRY])
    assert result.value == {"number": "1", "shipping": {"country": "US"}}


class Outer(BaseModel):
    inner: Invoice | None = None


def test_nested_abstained_objects_collapse_at_the_outermost() -> None:
    outcomes = [Abstained("/inner/number"), Abstained("/inner/shipping/street")]
    result = assemble(
        schema_of(Outer), outcomes, source_selected=frozenset({"/inner/number", "/inner/shipping/street"})
    )
    assert result.value == {}
    assert [a.pointer for a in result.absent] == ["/inner"]


# --- unresolved subtrees and the root --------------------------------------------------------


def test_an_unresolved_root_yields_an_empty_object() -> None:
    root = Unresolved("", UnresolvedReason.DEPENDENCY_UNRESOLVED)
    result = assemble(schema_of(Invoice), [root, Committed("/number", "1", DecidedBy.CODE)])
    assert result.value == {}
    assert result.unresolved == (root,)
    assert result.decided_by == {}


def test_an_unresolved_subtree_omits_everything_under_it() -> None:
    hole = Unresolved("/shipping", UnresolvedReason.TIE)
    result = assemble(schema_of(Invoice), [Committed("/number", "1", DecidedBy.CODE), hole, COUNTRY])
    assert result.value == {"number": "1"}
    assert result.unresolved == (hole,)


# --- validation ------------------------------------------------------------------------------


class Short(BaseModel):
    code: str = Field(max_length=3)


def test_a_complete_object_failing_max_length_is_complete_but_not_satisfying() -> None:
    result = assemble(schema_of(Short), [Committed("/code", "ABCDE", DecidedBy.DECISION, SPAN)])
    assert result.complete is True
    assert result.satisfies_schema is False
    assert [(v.pointer, v.keyword) for v in result.violations] == [("/code", "maxLength")]


def test_violation_pointers_escape_tokens() -> None:
    schema = {"type": "object", "properties": {"a/b~c": {"type": "string", "maxLength": 1}}}
    result = assemble(schema, [Committed("/a~1b~0c", "too long", DecidedBy.DECISION)])
    assert result.value == {"a/b~c": "too long"}
    assert [v.pointer for v in result.violations] == ["/a~1b~0c"]


# --- pass-through and ungated ----------------------------------------------------------------


def test_ungated_fields_and_pass_through_fields() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}, "c": {}}}
    decision = Decision(DecisionKind.PREDICATE, True, {"true": 90, "false": 10}, None, "/c")
    result = assemble(
        schema,
        [
            Committed("/a", "x", DecidedBy.DIRECT, SPAN),
            Committed("/b", "y", DecidedBy.LLM),
            Committed("/c", True, DecidedBy.DECISION),
        ],
        decisions={"/c#predicate@0": decision},
        cost=Cost(decision_requests=1),
        model=("gpt-6-luna",),
        versions={"question_templates": "1"},
    )
    assert result.ungated == ("/a", "/b")
    assert result.decisions == {"/c#predicate@0": decision}
    assert (result.cost.decision_requests, result.model, result.versions) == (
        1,
        ("gpt-6-luna",),
        {"question_templates": "1"},
    )


def test_committed_values_are_copied_not_aliased() -> None:
    schema: dict[str, Any] = {"type": "object"}
    payload: dict[str, Any] = {"k": [1]}
    result = assemble(schema, [Committed("/obj", payload, DecidedBy.CALLER)])
    payload["k"].append(2)
    assert result.value == {"obj": {"k": [1]}}


# --- misuse is refused -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcomes", "message"),
    [
        ([Committed("/a", 1, DecidedBy.CODE), Committed("/a", 2, DecidedBy.CODE)], "two outcomes"),
        ([Committed("", {}, DecidedBy.CODE)], "root is never"),
        ([Abstained("")], "root is never"),
        ([Committed("a", 1, DecidedBy.CODE)], "not a JSON pointer"),
        ([Committed("/a", 1, DecidedBy.CODE), Committed("/a/b", 2, DecidedBy.CODE)], "under the leaf"),
    ],
)
def test_malformed_outcomes_are_refused(outcomes: list[Committed | Abstained], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        assemble({"type": "object"}, outcomes)


def test_only_local_refs_are_followed() -> None:
    schema = {"type": "object", "properties": {"a": {"$ref": "https://example.com/s.json"}}, "required": ["a"]}
    with pytest.raises(ValueError, match="only local"):
        assemble(schema, [Abstained("/a")])


def test_a_self_referencing_ref_cannot_loop() -> None:
    schema = {"type": "object", "$defs": {"L": {"$ref": "#/$defs/L"}}, "properties": {"a": {"$ref": "#/$defs/L"}}}
    with pytest.raises(ValueError, match="too deep"):
        assemble(schema, [Abstained("/a/b")])


def test_a_type_list_with_null_is_nullable() -> None:
    schema = {"type": "object", "properties": {"a": {"type": ["string", "null"]}}, "required": ["a"]}
    assert assemble(schema, [Abstained("/a")]).value == {"a": None}


def test_with_a_committed_class_d_sibling_a_required_abstained_descendant_is_unresolved() -> None:
    street = Committed("/shipping/street", "1 Main St", DecidedBy.DECISION, SPAN)
    result = assemble(
        schema_of(Invoice),
        [Committed("/number", "1", DecidedBy.CODE), street, Abstained("/shipping/country")],
        source_selected=frozenset({"/shipping/street", "/shipping/country"}),
    )
    assert result.value == {"number": "1", "shipping": {"street": "1 Main St"}}
    assert result.unresolved == (Unresolved("/shipping/country", UnresolvedReason.ABSTAINED),)
    assert result.satisfies_schema is False
