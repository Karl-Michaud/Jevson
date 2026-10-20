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
from typing import Any

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
