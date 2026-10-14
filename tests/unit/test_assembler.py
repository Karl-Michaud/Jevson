"""Defaults and absence, unresolved subtrees, and validation (PLAN Phase 1, DESIGN §6.1)."""

from __future__ import annotations

from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from jevson.assemble.assembler import Committed, assemble
from jevson.types import Cost, DecidedBy, Decision, DecisionKind, DeclaredOption, Unresolved, UnresolvedReason


def schema_of(model: type[BaseModel]) -> dict[str, Any]:
    return model.model_json_schema(mode="validation")


class Ticket(BaseModel):
    priority: Literal["low", "high"]
    note: str | None = "x"


PRIORITY = Committed("/priority", "high", DecidedBy.DECISION, DeclaredOption("o1"))


# --- defaults and absence --------------------------------------------------------------------


def test_an_undeclared_defaulted_leaf_is_omitted_and_pydantic_supplies_the_default() -> None:
    result = assemble(schema_of(Ticket), [PRIORITY])
    assert result.value == {"priority": "high"}
    assert Ticket.model_validate(result.value).note == "x"
    assert (result.complete, result.satisfies_schema) == (True, True)


def test_absent_is_present_and_empty_and_versions_has_no_unicode_keys() -> None:
    result = assemble(schema_of(Ticket), [PRIORITY], versions={"question_templates": "1", "tie_margin": "10"})
    assert result.absent == ()
    assert not [key for key in result.versions if "unicode" in key or "grapheme" in key]


# --- unresolved ------------------------------------------------------------------------------


@pytest.mark.parametrize("reason", [UnresolvedReason.REFUSED, UnresolvedReason.TIE])
def test_an_unresolved_field_is_a_value_with_its_key_omitted(reason: UnresolvedReason) -> None:
    hole = Unresolved("/priority", reason)
    result = assemble(schema_of(Ticket), [hole])
    assert result.value == {}
    assert result.unresolved == (hole,)
    assert result.absent == ()
    assert result.complete is False
    assert result.satisfies_schema is False
    assert [v.keyword for v in result.violations] == ["required"]


class Address(BaseModel):
    country: Literal["US", "CA"]
    kind: Literal["home", "work"]


class Customer(BaseModel):
    tier: Literal["gold", "silver"]
    address: Address


COUNTRY = Committed("/address/country", "US", DecidedBy.DECISION, DeclaredOption("o0"))


def test_nested_values_are_placed_by_pointer() -> None:
    result = assemble(
        schema_of(Customer),
        [Committed("/tier", "gold", DecidedBy.DECISION), COUNTRY, Committed("/address/kind", "work", DecidedBy.CALLER)],
    )
    assert result.value == {"tier": "gold", "address": {"country": "US", "kind": "work"}}
    assert result.provenance == {"/address/country": DeclaredOption("o0")}
    assert result.satisfies_schema is True


def test_an_unresolved_subtree_omits_everything_under_it() -> None:
    hole = Unresolved("/address", UnresolvedReason.TIE)
    result = assemble(schema_of(Customer), [Committed("/tier", "gold", DecidedBy.DECISION), hole, COUNTRY])
    assert result.value == {"tier": "gold"}
    assert result.unresolved == (hole,)
    assert "/address/country" not in result.decided_by


def test_an_unresolved_root_yields_an_empty_object() -> None:
    root = Unresolved("", UnresolvedReason.DEPENDENCY_UNRESOLVED)
    result = assemble(schema_of(Customer), [root, Committed("/tier", "gold", DecidedBy.DECISION)])
    assert result.value == {}
    assert result.unresolved == (root,)
    assert result.decided_by == {}


# --- validation ------------------------------------------------------------------------------


class Short(BaseModel):
    code: str = Field(max_length=3)


def test_a_complete_object_failing_max_length_is_complete_but_not_satisfying() -> None:
    result = assemble(schema_of(Short), [Committed("/code", "ABCDE", DecidedBy.LLM_DECISION)])
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
    decision = Decision(DecisionKind.PREDICATE, True, {"true": 90, "false": 10}, None, "/c")
    outcomes = [
        Committed("/a", "x", DecidedBy.DIRECT),
        Committed("/b", "y", DecidedBy.LLM),
        Committed("/c", True, DecidedBy.DECISION),
    ]
    result = assemble(
        {"type": "object"},
        outcomes,
        decisions={"/c#predicate@0": decision},
        cost=Cost(decision_requests=1),
        model=("gpt-6-luna",),
    )
    assert result.ungated == ("/a", "/b")
    assert result.decisions == {"/c#predicate@0": decision}
    assert result.cost.decision_requests == 1
    assert result.model == ("gpt-6-luna",)


def test_committed_values_are_copied_not_aliased() -> None:
    payload: dict[str, Any] = {"k": [1]}
    result = assemble({"type": "object"}, [Committed("/obj", payload, DecidedBy.CALLER)])
    payload["k"].append(2)
    assert result.value == {"obj": {"k": [1]}}


# --- misuse is refused -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcomes", "message"),
    [
        ([Committed("/a", 1, DecidedBy.CODE), Committed("/a", 2, DecidedBy.CODE)], "two outcomes"),
        ([Committed("", {}, DecidedBy.CODE)], "root is never committed"),
        ([Committed("a", 1, DecidedBy.CODE)], "not a JSON pointer"),
        ([Committed("/a", 1, DecidedBy.CODE), Committed("/a/b", 2, DecidedBy.CODE)], "under the leaf"),
    ],
)
def test_malformed_outcomes_are_refused(outcomes: list[Committed], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        assemble({"type": "object"}, outcomes)
