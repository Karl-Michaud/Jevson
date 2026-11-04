"""PLAN Phase 3 exit criteria through `Jevson.aresolve()` with the fake backend.

The criteria J3c owns (synchronous `resolve()`, the library loop, threads, fork, live stability) are
not here.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, Field, field_validator

from jevson import (
    BackendError,
    CachingBackend,
    CompileError,
    Cost,
    CostEvent,
    DecidedBy,
    DeclaredOption,
    FakeBackend,
    Jevson,
    JevsonConfig,
    PreflightError,
    Result,
    SchemaViolation,
    Unresolved,
    UnresolvedReason,
    UsageError,
)
from jevson.backends.fake import Script
from jevson.types import Answer, DecisionKind, Question

SOURCE = "Invoice from Acme Corp. Paid in full. Software licences. Rated 4 of 5."


class Invoice(BaseModel):
    paid: bool = Field(description="the invoice is paid")
    category: Literal["software", "hardware", "services"]
    priority: Literal["low", "high"]


def confident(question: Question) -> Answer:
    """Every predicate true at 0.9; every choice picks its first option at 0.9."""
    if question.kind is DecisionKind.PREDICATE:
        return FakeBackend.predicate(0.9)(question)
    return FakeBackend.select(question.options[0].id, 0.9)(question)


def resolve(schema: object, backend: Any, **kwargs: Any) -> Result:
    config = kwargs.pop("config", None)
    sink = kwargs.pop("cost_sink", None)
    return asyncio.run(Jevson(backend, config=config, cost_sink=sink).aresolve(schema, SOURCE, **kwargs))


def without_clock(result: Result) -> Result:
    return replace(result, cost=replace(result.cost, wall_clock_by_component={}))


class Events:
    def __init__(self) -> None:
        self.events: list[CostEvent] = []

    def record(self, cost_event: CostEvent) -> None:
        self.events.append(cost_event)


def test_n_independent_nodes_resolve_in_exactly_one_backend_call() -> None:
    backend = FakeBackend(default=confident)
    result = resolve(Invoice, backend)
    assert len(backend.calls) == 1
    assert len(backend.calls[0].questions) == 3
    assert result.value == {"paid": True, "category": "software", "priority": "low"}
    assert (result.complete, result.satisfies_schema) == (True, True)
    assert result.provenance == {"/category": DeclaredOption("c0"), "/priority": DeclaredOption("c0")}
    assert result.decided_by == dict.fromkeys(("/paid", "/category", "/priority"), DecidedBy.DECISION)
    assert result.cost.decision_requests == 1
    assert result.cost.decision_request_ids == ("fake-1",)
    assert result.model == ("fake-backend",)
    assert result.versions["model"] == "gpt-6-luna"
    assert backend.calls[0].model == "gpt-6-luna"
    assert backend.calls[0].state == '{"source": "' + SOURCE + '"}'
    assert result.absent == ()  # PLAN Phase 1: present and empty in v0
    assert not [key for key in result.versions if "grapheme" in key or "unicode" in key]


@pytest.mark.parametrize("p", [0.45, 0.50, 0.55])
def test_a_predicate_inside_the_tie_band_is_unresolved_tie(p: float) -> None:
    result = resolve(Invoice, FakeBackend({"q0": FakeBackend.predicate(p)}, default=confident))
    assert result.unresolved == (Unresolved("/paid", UnresolvedReason.TIE),)
    assert "paid" not in result.value
    true = round(p * 100)
    assert result.decisions["/paid#predicate@0"].distribution_hundredths == {"true": true, "false": 100 - true}
    assert result.satisfies_schema is False  # paid is required


def test_a_choice_whose_top_two_are_within_the_margin_is_a_tie() -> None:
    near = FakeBackend.distribution({"c0": 0.45, "c1": 0.35, "c2": 0.20})
    result = resolve(Invoice, FakeBackend({"q1": near}, default=confident))
    assert result.unresolved == (Unresolved("/category", UnresolvedReason.TIE),)


def test_a_refusal_is_unresolved_refused_recorded_and_never_retried() -> None:
    backend = FakeBackend({"q1": FakeBackend.refuse()}, default=confident)
    result = resolve(Invoice, backend)
    assert result.unresolved == (Unresolved("/category", UnresolvedReason.REFUSED),)
    assert result.decisions["/category#choice@0"].selected is None
    assert result.value == {"paid": True, "priority": "low"}
    assert len(backend.calls) == 1


def test_a_low_probability_commit_is_reported_not_dropped() -> None:
    low = FakeBackend.distribution({"c0": 0.10, "c1": 0.38, "c2": 0.52})
    result = resolve(Invoice, FakeBackend({"q1": low}, default=confident))
    assert result.value["category"] == "services"
    assert result.decisions["/category#choice@0"].distribution_hundredths["c2"] == 52
    assert result.complete


def test_a_choice_whose_top_is_below_half_still_commits() -> None:
    """No default threshold: 0.34 against three options at 0.22 is outside the tie margin, so it commits."""
    low = FakeBackend.distribution({"c0": 0.34, "c1": 0.22, "c2": 0.22, "c3": 0.22})
    schema = {"type": "object", "properties": {"k": {"enum": ["a", "b", "c", "d"]}}, "required": ["k"]}
    result = resolve(schema, FakeBackend(default=low))
    assert result.value == {"k": "a"}
    assert result.complete
    assert result.decisions["/k#choice@0"].distribution_hundredths["c0"] == 34


def test_known_values_skip_their_nodes_and_are_decided_by_the_caller() -> None:
    backend = FakeBackend(default=confident)
    result = resolve(Invoice, backend, known={"/category": "hardware"})
    assert [q.instructions for q in backend.calls[0].questions if "category" in q.instructions] == []
    assert result.value["category"] == "hardware"
    assert result.decided_by["/category"] is DecidedBy.CALLER
    assert "/category" not in result.provenance
    assert "/category#choice@0" not in result.decisions


@pytest.mark.parametrize(
    "known",
    [
        {"/category": "furniture"},
        {"/category": None},
        {"/paid": "yes"},
        {"/nowhere": 1},
        {"/category": 1},
    ],
)
def test_an_invalid_known_value_raises_preflight_error_before_any_call(known: dict[str, Any]) -> None:
    backend = FakeBackend(default=confident)
    with pytest.raises(PreflightError):
        resolve(Invoice, backend, known=known)
    assert backend.calls == []


def test_known_none_is_accepted_for_a_nullable_field() -> None:
    schema = {"type": "object", "properties": {"size": {"enum": ["s", "m", None]}}, "required": ["size"]}
    result = resolve(schema, FakeBackend(default=confident), known={"/size": None})
    assert result.value == {"size": None}
    assert result.satisfies_schema


def test_known_must_be_a_mapping_and_source_a_string() -> None:
    backend = FakeBackend(default=confident)
    with pytest.raises(PreflightError):
        resolve(Invoice, backend, known=[("/paid", True)])
    with pytest.raises(PreflightError):
        asyncio.run(Jevson(backend).aresolve(Invoice, ["a", "b"]))  # type: ignore[arg-type]
    assert backend.calls == []


class Strict(BaseModel):
    category: Literal["software", "hardware"]

    @field_validator("category")
    @classmethod
    def only_software(cls, value: str) -> str:
        if value != "software":
            raise ValueError("only software is accepted")
        return value


def test_a_value_passing_jsonschema_but_failing_model_validate_does_not_satisfy_the_schema() -> None:
    hardware = FakeBackend.select("c1", 0.9)
    result = resolve(Strict, FakeBackend(default=hardware))
    assert result.value == {"category": "hardware"}
    assert result.complete is True
    assert result.satisfies_schema is False
    assert [(v.pointer, v.keyword) for v in result.violations] == [("/category", "model_validate")]


def test_an_unresolved_required_field_fails_the_schema_or_raises_when_asked() -> None:
    backend = FakeBackend({"q0": FakeBackend.tie()}, default=confident)
    result = resolve(Invoice, backend)
    assert (result.complete, result.satisfies_schema) == (False, False)
    config = JevsonConfig(raise_on_unresolved_required=True)
    with pytest.raises(SchemaViolation) as raised:
        resolve(Invoice, FakeBackend({"q0": FakeBackend.tie()}, default=confident), config=config)
    assert raised.value.result.unresolved == (Unresolved("/paid", UnresolvedReason.TIE),)
    assert raised.value.cost.decision_requests == 1


def test_an_unresolved_optional_field_does_not_raise() -> None:
    schema = {"type": "object", "properties": {"size": {"enum": ["s", "m"]}}}
    config = JevsonConfig(raise_on_unresolved_required=True)
    result = resolve(schema, FakeBackend(default=FakeBackend.tie()), config=config)
    assert result.unresolved == (Unresolved("/size", UnresolvedReason.TIE),)
    assert result.satisfies_schema is True


def test_identical_inputs_give_identical_results() -> None:
    first = resolve(Invoice, FakeBackend(default=confident))
    second = resolve(Invoice, FakeBackend(default=confident))
    assert without_clock(first) == without_clock(second)


def test_a_run_replayed_through_caching_backend_reproduces_the_result(tmp_path: Path) -> None:
    script: dict[str, Script] = {"q0": FakeBackend.predicate(0.5), "q2": FakeBackend.refuse()}
    recorded = resolve(Invoice, CachingBackend(FakeBackend(script, default=confident), tmp_path))
    offline = FakeBackend(default=FakeBackend.refuse())
    replayed = resolve(Invoice, CachingBackend(offline, tmp_path, replay_only=True))
    assert offline.calls == []
    assert replace(replayed, cost=Cost()) == replace(recorded, cost=Cost())
    assert (replayed.cost.cache_hits, replayed.cost.decision_requests) == (1, 0)
    assert replayed.cost.decision_request_ids == ()


def test_replay_only_miss_is_a_backend_error_with_the_partial_result(tmp_path: Path) -> None:
    with pytest.raises(BackendError) as raised:
        resolve(Invoice, CachingBackend(FakeBackend(default=confident), tmp_path, replay_only=True))
    assert raised.value.code == "replay_miss"
    assert raised.value.result.cost.decision_requests == 0


def test_every_cost_event_reaches_the_sink() -> None:
    sink = Events()
    resolve(Invoice, FakeBackend(default=confident), cost_sink=sink)
    (event,) = sink.events
    assert (event.component, event.request_id, event.succeeded) == ("decision", "fake-1", True)
    assert event.input_tokens > 0


def test_the_estimate_is_recorded_beside_the_billed_input_tokens() -> None:
    """DESIGN §8.2: every response's billed `input_tokens` is compared with preflight's estimate."""
    sink = Events()
    result = resolve(Invoice, FakeBackend(default=confident), cost_sink=sink)
    (event,) = sink.events
    assert event.estimated_input_tokens is not None
    assert event.estimated_input_tokens >= event.input_tokens > 0  # pessimistic against the fake's chars/4
    assert result.cost.decision_input_tokens == event.input_tokens
    assert result.cost.decision_input_tokens_estimated == event.estimated_input_tokens


def test_a_schema_that_cannot_compile_raises_before_any_call() -> None:
    backend = FakeBackend(default=confident)
    with pytest.raises(CompileError):
        resolve({"type": "object", "properties": {"note": {"type": "string"}}, "required": ["note"]}, backend)
    assert backend.calls == []


def test_a_source_too_large_for_any_request_raises_preflight_error_before_any_call() -> None:
    backend = FakeBackend(default=confident)
    with pytest.raises(PreflightError, match="/paid"):
        resolve(Invoice, backend, config=JevsonConfig(max_input_tokens=60))
    assert backend.calls == []


def test_a_level_over_the_question_limit_splits() -> None:
    backend = FakeBackend(default=confident)
    result = resolve(Invoice, backend, config=JevsonConfig(max_questions_per_request=2))
    assert [len(call.questions) for call in backend.calls] == [2, 1]
    assert result.cost.level_splits == 1
    assert result.complete


def test_redraft_budget_is_recorded_per_call() -> None:
    result = resolve(Invoice, FakeBackend(default=confident), redraft_budget=3)
    assert result.versions["redraft_budget"] == "3"


# --- lifecycle ------------------------------------------------------------------------------


def test_there_is_no_default_backend() -> None:
    with pytest.raises(UsageError):
        Jevson(None)  # type: ignore[arg-type]


def test_a_closed_instance_raises_usage_error() -> None:
    with Jevson(FakeBackend(default=confident)) as jevson:
        pass
    with pytest.raises(UsageError):
        asyncio.run(jevson.aresolve(Invoice, SOURCE))

    async def closed_async() -> None:
        async with Jevson(FakeBackend(default=confident)) as inner:
            assert (await inner.aresolve(Invoice, SOURCE)).complete
        with pytest.raises(UsageError):
            await inner.aresolve(Invoice, SOURCE)
        with pytest.raises(UsageError):
            async with inner:
                pass

    asyncio.run(closed_async())
    assert "closed=True" in repr(jevson)


class Entered(FakeBackend):
    def __init__(self) -> None:
        super().__init__(default=confident)
        self.log: list[str] = []

    async def __aenter__(self) -> Entered:
        self.log.append("enter")
        return self

    async def __aexit__(self, *_: object) -> None:
        self.log.append("exit")


def test_async_with_jevson_enters_its_backend() -> None:
    backend = Entered()

    async def run() -> None:
        async with Jevson(backend) as jevson:
            await jevson.aresolve(Invoice, SOURCE)
            assert backend.log == ["enter"]

    asyncio.run(run())
    assert backend.log == ["enter", "exit"]
