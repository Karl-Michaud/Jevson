"""PLAN Phase 3, known values: a `known=` value that fails its field schema raises `PreflightError`
before any call (ASTERION-44).

The declared-values check (`test_facade.py`) covers enum and boolean fields; these cases cover a value
of the right type and declared kind that breaks a field constraint (`maxLength`, `minLength`,
`pattern`, `format`), including one reached through a `$ref` and one on a Pydantic model. A known
value is checked against the field's JSON Schema constraints only; Pydantic field validators run in
final validation (`satisfies_schema`), as before.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field

from jevson import DecidedBy, FakeBackend, Jevson, PreflightError, Result
from jevson.types import DecisionKind, Question
from tests.adversarial.hostile_llm import ScriptedLLM

GENERATE = {"generate": {"criteria": ["mentions the refund amount stated in the source"]}}


def passes(question: Question) -> Any:
    if question.kind is DecisionKind.SCORE:
        return FakeBackend.select(question.options[-1].id)(question)
    return FakeBackend.predicate(0.9)(question)


def summary(**constraints: Any) -> dict[str, Any]:
    field = {"type": "string", **constraints, "x-jevson": GENERATE}
    return {"type": "object", "properties": {"summary": field}, "required": ["summary"]}


def via_ref(**constraints: Any) -> dict[str, Any]:
    return {
        "type": "object",
        "$defs": {"Short": {"type": "string", **constraints}},
        "properties": {"summary": {"$ref": "#/$defs/Short", "x-jevson": GENERATE}},
        "required": ["summary"],
    }


class Ticket(BaseModel):
    summary: str = Field(max_length=5, json_schema_extra={"x-jevson": GENERATE})


def resolve(schema: object, known: dict[str, Any]) -> tuple[Result, FakeBackend, ScriptedLLM]:
    backend, llm = FakeBackend(default=passes), ScriptedLLM(["drafted"])
    result = asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known=known))
    return result, backend, llm


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        (summary(maxLength=5), "x" * 50),
        (summary(minLength=3), "x"),
        (summary(pattern="^[a-z]+$"), "NOT LOWER"),
        (summary(format="email"), "not an email"),
        (via_ref(maxLength=5), "x" * 50),
        (Ticket, "x" * 50),
    ],
    ids=["maxLength", "minLength", "pattern", "format", "maxLength through a $ref", "pydantic max_length"],
)
def test_a_known_value_that_fails_its_field_schema_raises_before_any_call(schema: object, value: str) -> None:
    backend, llm = FakeBackend(default=passes), ScriptedLLM(["drafted"])
    with pytest.raises(PreflightError, match="/summary"):
        asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known={"/summary": value}))
    assert backend.calls == []
    assert llm.calls == []


@pytest.mark.parametrize(
    ("schema", "value"),
    [
        (summary(maxLength=5), "short"),
        (summary(pattern="^[a-z]+$"), "lower"),
        (summary(format="email"), "a@example.com"),
        (via_ref(maxLength=5), "short"),
        (Ticket, "short"),
    ],
    ids=["maxLength", "pattern", "format", "maxLength through a $ref", "pydantic max_length"],
)
def test_a_known_value_that_meets_its_field_schema_still_skips_its_nodes(schema: object, value: str) -> None:
    result, backend, llm = resolve(schema, {"/summary": value})
    assert result.value == {"summary": value}
    assert result.decided_by == {"/summary": DecidedBy.CALLER}
    assert result.satisfies_schema
    assert backend.calls == []
    assert llm.calls == []


def test_a_known_null_is_checked_by_nullability_not_by_string_constraints() -> None:
    schema = {
        "type": "object",
        "properties": {"size": {"enum": ["small", "large", None], "maxLength": 4}},
        "required": ["size"],
    }
    result, backend, _ = resolve(schema, {"/size": None})
    assert result.value == {"size": None}
    assert backend.calls == []
    with pytest.raises(PreflightError, match="/size"):
        resolve(schema, {"/size": "large"})  # declared, but over the field's own maxLength


INVOICE = {
    "type": "object",
    "properties": {
        "kind": {"enum": ["invoice"]},  # a one-value enum is a constant, checked by the executor
        "paid": {"type": "boolean", "description": "the invoice is paid"},
        "tags": {"type": "array", "items": {"enum": ["urgent", "late"]}},
    },
    "required": ["kind", "paid"],
}


def test_a_known_constant_does_not_stop_the_check_of_the_values_after_it() -> None:
    with pytest.raises(PreflightError, match="/paid"):
        resolve(INVOICE, {"/kind": "invoice", "/paid": "yes"})


def test_a_multi_label_known_value_must_be_a_list() -> None:
    for value in (5, "urgent", {"urgent": True}):
        with pytest.raises(PreflightError, match="/tags"):
            resolve(INVOICE, {"/tags": value})


def test_each_refusal_says_what_is_wrong() -> None:
    with pytest.raises(PreflightError, match="must map JSON pointers to values"):
        resolve(INVOICE, [("/paid", True)])  # type: ignore[arg-type]
    with pytest.raises(PreflightError, match="'/nowhere', which is not a decided field"):
        resolve(INVOICE, {"/nowhere": 1})
    with pytest.raises(PreflightError, match="'/paid' is not one of the field's declared values"):
        resolve(INVOICE, {"/paid": "yes"})
    with pytest.raises(
        PreflightError, match=r"'/summary' fails its field schema: .* does not match .*; .* is too long"
    ):
        resolve(summary(maxLength=3, pattern="^[a-z]+$"), {"/summary": "TOO LONG"})


UNION_GENERATE = {"generate": {"criteria": ["is short"]}}


def ticket_branch(title: str, kind: str, max_length: int) -> dict[str, Any]:
    note = {"type": "string", "maxLength": max_length, "x-jevson": UNION_GENERATE}
    return {
        "type": "object",
        "title": title,
        "description": f"{title} ticket",
        "properties": {"kind": {"const": kind}, "note": note},
        "required": ["kind", "note"],
    }


def union_of(first: int, second: int) -> dict[str, Any]:
    branches = [ticket_branch("Short", "s", first), ticket_branch("Long", "l", second)]
    return {"type": "object", "properties": {"t": {"anyOf": branches}}, "required": ["t"]}


def first_branch(question: Question) -> Any:
    if question.kind is DecisionKind.CHOICE:
        return FakeBackend.select(question.options[0].id)(question)
    return passes(question)


def resolve_first_branch(schema: object, known: dict[str, Any]) -> tuple[Result, FakeBackend, ScriptedLLM]:
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"] * 4)
    result = asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known=known))
    return result, backend, llm


@pytest.mark.parametrize(("first", "second"), [(50, 5), (5, 50)], ids=["valid in the first", "valid in the last"])
def test_a_known_value_inside_union_branches_is_refused_only_if_every_branch_refuses_it(
    first: int, second: int
) -> None:
    note = "x" * 20  # within one branch's maxLength, over the other's
    result, _, llm = resolve_first_branch(union_of(first, second), {"/t/note": note})  # no PreflightError
    assert result.value["t"]["note"] == note
    assert llm.calls == []
    assert result.satisfies_schema is (first == 50)  # the selected branch's own constraint decides, after the run


def test_a_known_value_inside_union_branches_that_every_branch_refuses_raises_before_any_call() -> None:
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"])
    with pytest.raises(PreflightError, match="'/t/note' fails its field schema"):
        asyncio.run(Jevson(backend, llm=llm).aresolve(union_of(50, 5), "Refund: $40.", known={"/t/note": "x" * 60}))
    assert backend.calls == []
    assert llm.calls == []


class Cat(BaseModel):
    kind: Literal["cat"]
    note: str = Field(max_length=100, json_schema_extra={"x-jevson": UNION_GENERATE})


class Dog(BaseModel):
    kind: Literal["dog"]
    note: str = Field(max_length=3, json_schema_extra={"x-jevson": UNION_GENERATE})


class Pet(BaseModel):
    pet: Cat | Dog = Field(discriminator="kind")


@pytest.mark.parametrize(
    ("kind", "note", "valid"),
    [("cat", "x" * 40, True), ("cat", "ab", True), ("dog", "ab", True), ("dog", "x" * 40, False)],
)
def test_a_known_value_in_a_discriminated_union_is_checked_against_its_selected_branch(
    kind: str, note: str, valid: bool
) -> None:
    result, backend, llm = resolve(Pet, {"/pet/kind": kind, "/pet/note": note})
    assert result.value == {"pet": {"kind": kind, "note": note}}
    assert result.satisfies_schema is valid  # a value only another branch admits fails final validation
    assert backend.calls == []
    assert llm.calls == []


def test_a_known_value_in_a_discriminated_union_that_no_branch_admits_raises_before_any_call() -> None:
    with pytest.raises(PreflightError, match="'/pet/note' fails its field schema"):
        resolve(Pet, {"/pet/kind": "cat", "/pet/note": "x" * 101})
