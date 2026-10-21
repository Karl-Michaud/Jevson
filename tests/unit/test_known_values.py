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
    with pytest.raises(PreflightError, match=r"^known= must map JSON pointers to values$"):
        resolve(INVOICE, [("/paid", True)])  # type: ignore[arg-type]
    with pytest.raises(PreflightError, match="'/nowhere', which is not a decided field"):
        resolve(INVOICE, {"/nowhere": 1})
    with pytest.raises(PreflightError, match="'/paid' is not one of the field's declared values"):
        resolve(INVOICE, {"/paid": "yes"})
    with pytest.raises(PreflightError) as caught:
        resolve(summary(maxLength=3, pattern="^[a-z]+$"), {"/summary": "TOO LONG"})
    assert str(caught.value) == (
        "known= value for '/summary' fails its field schema: "
        "'TOO LONG' does not match '^[a-z]+$'; 'TOO LONG' is too long"
    )


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


@pytest.mark.parametrize(("kind", "note"), [("cat", "x" * 40), ("cat", "ab"), ("dog", "ab")])
def test_a_known_value_in_a_discriminated_union_is_checked_against_its_selected_branch(kind: str, note: str) -> None:
    result, backend, llm = resolve(Pet, {"/pet/kind": kind, "/pet/note": note})
    assert result.value == {"pet": {"kind": kind, "note": note}}
    assert result.satisfies_schema is True  # a value only another branch admits raises: see the test below
    assert backend.calls == []
    assert llm.calls == []


def test_a_known_value_in_a_discriminated_union_that_no_branch_admits_raises_before_any_call() -> None:
    with pytest.raises(PreflightError, match="'/pet/note' fails its field schema"):
        resolve(Pet, {"/pet/kind": "cat", "/pet/note": "x" * 101})


SHORT_NOTE = {"type": "string", "maxLength": 2, "x-jevson": UNION_GENERATE}
PICKED = {"enum": ["c", "d"]}
LABELS = {"type": "array", "items": {"enum": ["x", "y"]}, "default": []}


def two_shapes(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    """A union whose branches declare `/t/v` with different kinds (not only different constraints)."""

    def branch(title: str, kind: str, v: dict[str, Any]) -> dict[str, Any]:
        properties = {"kind": {"const": kind}, "v": v}
        return {"type": "object", "title": title, "description": f"{title} ticket", "properties": properties}

    branches = [branch("First", "a", first), branch("Second", "b", second)]
    return {"type": "object", "properties": {"t": {"anyOf": branches}}, "required": ["t"]}


@pytest.mark.parametrize(
    ("first", "second", "value"),
    [
        (SHORT_NOTE, PICKED, "zzzzz"),  # too long for the string, not an option of the enum
        (PICKED, SHORT_NOTE, "zzzzz"),
        (SHORT_NOTE, PICKED, "x" * 60),
        (LABELS, SHORT_NOTE, "zzzzz"),  # too long for the string, not an array
        (SHORT_NOTE, LABELS, "zzzzz"),
        (LABELS, SHORT_NOTE, ["q"]),  # not a declared label, not a string
        (LABELS, PICKED, "x"),  # a label, but not inside an array, and not an option of the enum
    ],
)
def test_a_known_value_no_branch_admits_raises_even_when_branches_declare_different_kinds(
    first: dict[str, Any], second: dict[str, Any], value: Any
) -> None:
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"] * 4)
    with pytest.raises(PreflightError, match="'/t/v'"):
        asyncio.run(Jevson(backend, llm=llm).aresolve(two_shapes(first, second), "Refund: $40.", known={"/t/v": value}))
    assert backend.calls == []
    assert llm.calls == []


@pytest.mark.parametrize(
    ("first", "second", "value"),
    [(SHORT_NOTE, PICKED, "ok"), (SHORT_NOTE, PICKED, "d"), (LABELS, SHORT_NOTE, ["y", "x"]), (LABELS, PICKED, "c")],
)
def test_a_known_value_one_branch_admits_passes_preflight_when_branches_declare_different_kinds(
    first: dict[str, Any], second: dict[str, Any], value: Any
) -> None:
    result, _, llm = resolve_first_branch(two_shapes(first, second), {"/t/v": value})  # no PreflightError
    assert result.value["t"]["v"] == value
    assert llm.calls == []


def test_a_known_discriminator_checks_a_branch_field_against_its_selected_branch_only() -> None:
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"])
    with pytest.raises(PreflightError, match="'/pet/note' fails its field schema"):  # only Cat admits 40 characters
        asyncio.run(
            Jevson(backend, llm=llm).aresolve(Pet, "Refund: $40.", known={"/pet/kind": "dog", "/pet/note": "x" * 40})
        )
    assert backend.calls == []
    assert llm.calls == []


def test_a_known_discriminator_refuses_a_value_only_the_unselected_branch_declares() -> None:
    schema = two_shapes(LABELS, PICKED)
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"])
    declared = "'/t/v' is not one of the field's declared values"
    with pytest.raises(PreflightError, match=declared):  # "d" is an option of Second only; kind "a" selects First
        asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known={"/t/kind": "a", "/t/v": "d"}))
    with pytest.raises(PreflightError, match=declared):  # labels only First admits; kind "b" selects Second
        asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known={"/t/kind": "b", "/t/v": ["x"]}))
    assert backend.calls == []
    assert llm.calls == []


FLAG = {"type": "boolean", "description": "the refund is approved"}


def rating(low: int, high: int) -> dict[str, Any]:
    return {"type": "integer", "minimum": low, "maximum": high, "x-jevson": {"ordinal": True}}


@pytest.mark.parametrize(
    ("field", "value"), [(FLAG, True), (FLAG, False), (PICKED, "d"), (rating(1, 5), 1), (rating(1, 5), 5)]
)
def test_a_declared_known_value_of_each_decided_kind_skips_its_question(field: dict[str, Any], value: Any) -> None:
    schema = {"type": "object", "properties": {"v": field}, "required": ["v"]}
    result, backend, _ = resolve(schema, {"/v": value})
    assert result.value == {"v": value}
    assert result.satisfies_schema is True
    assert backend.calls == []


@pytest.mark.parametrize(("field", "value"), [(FLAG, 1), (FLAG, "true"), (rating(1, 5), 6), (rating(1, 5), True)])
def test_an_undeclared_known_value_of_a_decided_kind_raises_before_any_call(field: dict[str, Any], value: Any) -> None:
    schema = {"type": "object", "properties": {"v": field}, "required": ["v"]}
    with pytest.raises(PreflightError, match="'/v' is not one of the field's declared values"):
        resolve(schema, {"/v": value})


@pytest.mark.parametrize(
    ("first", "second", "value", "admitted"),
    [
        (FLAG, PICKED, True, True),
        (PICKED, FLAG, "c", True),
        (FLAG, PICKED, "zz", False),
        (PICKED, FLAG, 1, False),
        (rating(1, 3), rating(1, 5), 5, True),  # the any-branch rule: the selected branch decides later
        (rating(1, 3), FLAG, 4, False),
        (rating(1, 3), PICKED, "c", True),
    ],
)
def test_a_known_value_is_judged_by_each_branch_declaration_of_its_own_kind(
    first: dict[str, Any], second: dict[str, Any], value: Any, admitted: bool
) -> None:
    schema = two_shapes(first, second)
    if admitted:
        result, _, _ = resolve_first_branch(schema, {"/t/v": value})
        assert result.value["t"]["v"] == value
        return
    backend, llm = FakeBackend(default=first_branch), ScriptedLLM(["ok"])
    with pytest.raises(PreflightError, match="'/t/v'"):
        asyncio.run(Jevson(backend, llm=llm).aresolve(schema, "Refund: $40.", known={"/t/v": value}))
    assert backend.calls == []
