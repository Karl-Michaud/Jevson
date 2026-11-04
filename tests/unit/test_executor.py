"""The executor on hand-built graphs: steps, timeouts, bisection, dependencies, and cost accounting."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Sequence
from dataclasses import replace
from typing import Any, cast

import pytest
from hypothesis import given

from jevson import (
    BackendError,
    BackendResponse,
    Cost,
    CostEvent,
    ExtractorError,
    FakeBackend,
    JevsonConfig,
    LLMError,
    PreflightError,
    Result,
    UsageError,
    compile_schema,
)
from jevson.compile import questions as templates
from jevson.execute import budget
from jevson.execute.executor import StepRunner, execute
from jevson.execute.state import LevelState
from jevson.graph import DecisionGraph
from jevson.types import (
    DecisionKind,
    DecisionNode,
    InvalidAnswer,
    JSONValue,
    Option,
    OptionSource,
    PredicateAnswer,
    Question,
    StepKind,
    StepNode,
    Unresolved,
    UnresolvedReason,
)
from tests.property.test_compiler_properties import supported
from tests.property.test_normalise_properties import DETERMINISTIC

SCHEMA: dict[str, Any] = {"type": "object"}


def flag(name: str, deps: frozenset[str] = frozenset()) -> DecisionNode:
    return DecisionNode(f"/{name}#predicate", DecisionKind.PREDICATE, f"Is {name} set?", OptionSource.PREDICATE,
                        f"/{name}", dependencies=deps)  # fmt: skip


def run(graph: DecisionGraph, backend: Any, **kwargs: Any) -> Result:
    kwargs.setdefault("config", JevsonConfig())
    return asyncio.run(execute(graph, SCHEMA, "the source", backend=backend, **kwargs))


class Recorder:
    def __init__(self) -> None:
        self.events: list[CostEvent] = []

    def record(self, cost_event: CostEvent) -> None:
        self.events.append(cost_event)


# --- steps --------------------------------------------------------------------------------


def test_a_runner_step_runs_before_the_decisions_that_depend_on_it_and_its_output_is_in_state() -> None:
    """A hand-built graph with an injected runner (class D's path, deferred; no compiled v0 graph has
    one). Its output sits under `drafts` until class D returns (PLAN §9.2); no LLM draft is involved."""
    order: list[str] = []

    async def draft(step: StepNode, state: LevelState) -> JSONValue:
        order.append(step.id)
        return {"text": "drafted"}

    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    step = StepNode("/a#generate", StepKind.GENERATE, "/a")
    graph = DecisionGraph([flag("b", frozenset({step.id})), step])
    result = run(graph, backend, steps={StepKind.GENERATE: draft})
    assert order == ["/a#generate"]
    assert backend.calls[0].state == '{"source": "the source", "drafts": {"/a#generate": {"text": "drafted"}}}'
    assert result.value == {"b": True}
    assert set(result.cost.wall_clock_by_component) == {"LLM", "decision"}


def never(kind: StepKind) -> tuple[DecisionGraph, StepRunner]:
    async def hang(step: StepNode, state: LevelState) -> JSONValue:
        await asyncio.sleep(3600)
        return None

    step = StepNode(f"/x#{kind}", kind, "/x", frozenset({"/first#predicate"}))
    return DecisionGraph([flag("first"), step, flag("after", frozenset({step.id}))]), hang


@pytest.mark.parametrize(("kind", "error"), [(StepKind.GENERATE, LLMError), (StepKind.EXTRACT, ExtractorError)])
def test_a_step_that_never_returns_times_out_with_the_partial_result(kind: StepKind, error: type[Exception]) -> None:
    graph, hang = never(kind)
    config = JevsonConfig(step_timeout_s=0.01)
    with pytest.raises(error) as raised:
        run(graph, FakeBackend(default=FakeBackend.predicate(0.9)), steps={kind: hang}, config=config)
    assert getattr(raised.value, "code", None) == "timeout"
    partial: Result = raised.value.result
    assert partial.value == {"first": True}
    assert partial.cost.decision_requests == 1


def test_a_step_that_raises_is_a_typed_error() -> None:
    async def broken(step: StepNode, state: LevelState) -> JSONValue:
        raise RuntimeError("boom")

    step = StepNode("/x#generate", StepKind.GENERATE, "/x")
    with pytest.raises(LLMError) as raised:
        run(DecisionGraph([step]), FakeBackend(), steps={StepKind.GENERATE: broken})
    assert raised.value.code == "step_failed"


def test_a_step_without_a_runner_is_refused_before_any_call() -> None:
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    step = StepNode("/x#generate", StepKind.GENERATE, "/x")
    with pytest.raises(UsageError, match="generate"):
        run(DecisionGraph([flag("a"), step]), backend)
    assert backend.calls == []


def test_a_draft_that_outgrows_the_budget_makes_its_level_budget_exceeded() -> None:
    async def huge(step: StepNode, state: LevelState) -> JSONValue:
        return "x" * 3000

    step = StepNode("/x#generate", StepKind.GENERATE, "/x")
    graph = DecisionGraph([step, flag("b", frozenset({step.id}))])
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    result = run(graph, backend, steps={StepKind.GENERATE: huge}, config=JevsonConfig(max_input_tokens=200))
    assert result.unresolved == (Unresolved("/b", UnresolvedReason.BUDGET_EXCEEDED),)
    assert backend.calls == []


# --- decisions ----------------------------------------------------------------------------


def test_a_decision_whose_dependency_is_unresolved_is_never_asked() -> None:
    backend = FakeBackend({"q0": FakeBackend.tie()}, default=FakeBackend.predicate(0.9))
    graph = DecisionGraph([flag("a"), flag("b", frozenset({"/a#predicate"})), flag("c")])
    result = run(graph, backend)
    assert [len(call.questions) for call in backend.calls] == [2]
    assert set(result.unresolved) == {
        Unresolved("/a", UnresolvedReason.TIE),
        Unresolved("/b", UnresolvedReason.DEPENDENCY_UNRESOLVED),
    }
    assert result.value == {"c": True}


def test_a_hand_built_node_without_values_commits_its_option_id() -> None:
    node = DecisionNode("/k#choice", DecisionKind.CHOICE, "Which?", OptionSource.SCHEMA_ENUM, "/k",
                        (Option("x", "X"), Option("y", "Y")))  # fmt: skip
    result = run(DecisionGraph([node]), FakeBackend(default=FakeBackend.select("y", 0.9)))
    assert result.value == {"k": "y"}
    assert result.provenance == {}


class Overflowing:
    """Rejects any request holding `poison` with the context-limit error; answers the rest."""

    def __init__(self, poison: str, code: str = "context_limit") -> None:
        self.poison, self.code = poison, code
        self.requests: list[tuple[str, ...]] = []

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        names = tuple(q.name for q in questions)
        self.requests.append(names)
        if self.poison in names:
            cost = Cost(decision_requests=1, decision_request_ids=(f"bad-{len(self.requests)}",))
            failed = Result({}, False, cost=cost)
            raise BackendError(self.code, "Decision input exceeds the token limit.", failed)
        answers = tuple(PredicateAnswer(name, 0.9) for name in names)
        return BackendResponse(answers, 10 * len(names), f"ok-{len(self.requests)}", "fake")


@pytest.mark.parametrize("code", ["context_limit", "question_limit"])
def test_a_run_time_overflow_is_bisected_to_isolate_the_one_field(code: str) -> None:
    graph = DecisionGraph([flag(name) for name in "abcde"])
    backend = Overflowing("q3", code)
    sink = Recorder()
    result = run(graph, backend, cost_sink=sink)
    assert result.unresolved == (Unresolved("/d", UnresolvedReason.BUDGET_EXCEEDED),)
    assert result.value == {"a": True, "b": True, "c": True, "e": True}
    assert len(set(backend.requests)) == len(backend.requests), "a request was retried unchanged"
    assert backend.requests[0] == ("q0", "q1", "q2", "q3", "q4")
    assert ("q3",) in backend.requests
    failures = sum(1 for names in backend.requests if "q3" in names)
    assert result.cost.decision_requests == len(backend.requests)
    assert result.cost.level_splits == failures - 1
    assert [e.succeeded for e in sink.events].count(False) == failures


def test_any_other_backend_error_carries_the_partial_result_and_all_cost() -> None:
    class Failing(FakeBackend):
        async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
            if self.calls:
                cost = Cost(decision_requests=3, decision_request_ids=("r1", "r2", "r3"), transport_retries=2)
                raise BackendError("server_error", "The server had an error.", Result({}, False, cost=cost))
            return await super().ask(state, questions, model)

    graph = DecisionGraph([flag("a"), flag("b", frozenset({"/a#predicate"}))])
    sink = Recorder()
    with pytest.raises(BackendError) as raised:
        run(graph, Failing(default=FakeBackend.predicate(0.9)), cost_sink=sink)
    error = raised.value
    assert error.code == "server_error"
    assert str(error) == "server_error: The server had an error."
    assert error.result.value == {"a": True}
    assert (error.cost.decision_requests, error.cost.transport_retries) == (4, 2)
    assert error.cost.decision_request_ids == ("fake-1", "r1", "r2", "r3")
    assert [(e.request_id, e.transport_retry, e.succeeded) for e in sink.events[1:]] == [
        ("r1", False, False), ("r2", True, False), ("r3", True, False),
    ]  # fmt: skip


def test_a_backend_raising_outside_the_hierarchy_becomes_a_backend_error() -> None:
    class Broken:
        async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
            raise KeyError("oops")

    with pytest.raises(BackendError) as raised:
        run(DecisionGraph([flag("a")]), Broken())
    assert (raised.value.code, raised.value.result.value) == ("backend_exception", {})


def test_missing_and_repeated_answers_are_invalid_for_their_questions() -> None:
    class Sloppy:
        async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
            answers = (PredicateAnswer("q0", 0.9), PredicateAnswer("q0", 0.9), PredicateAnswer("q2", 0.9))
            return BackendResponse(answers, 5, "r", "fake")

    result = run(DecisionGraph([flag("a"), flag("b"), flag("c")]), Sloppy())
    assert set(result.unresolved) == {
        Unresolved("/a", UnresolvedReason.INVALID_BACKEND_ANSWER),
        Unresolved("/b", UnresolvedReason.INVALID_BACKEND_ANSWER),
    }
    assert result.value == {"c": True}


def test_an_invalid_answer_from_the_backend_is_invalid_backend_answer() -> None:
    backend = FakeBackend({"q0": FakeBackend.answer(InvalidAnswer("q0", "bad"))})
    assert run(DecisionGraph([flag("a")]), backend).unresolved == (
        Unresolved("/a", UnresolvedReason.INVALID_BACKEND_ANSWER),
    )


def test_transport_retries_and_cache_hits_are_counted_apart() -> None:
    class Replies:
        def __init__(self, *responses: BackendResponse) -> None:
            self.responses = list(responses)

        async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
            return self.responses.pop(0)

    retried = BackendResponse((PredicateAnswer("q0", 0.9),), 40, "ok", "m1", transport_retries=2,
                              retried_request_ids=("f1", "f2"))  # fmt: skip
    hit = BackendResponse((PredicateAnswer("q1", 0.9),), 40, "old", "m2", cache_hit=True)
    graph = DecisionGraph([flag("a"), flag("b", frozenset({"/a#predicate"}))])
    sink = Recorder()
    result = run(graph, Replies(retried, hit), cost_sink=sink)
    # Both requests hold one same-length question over the same state, so one estimate fits both.
    state = LevelState("the source").serialise()
    estimate = budget.estimate_tokens(state) + budget.declared_tokens(flag("a"))
    assert result.cost == replace(
        result.cost,
        decision_requests=3,
        decision_input_tokens=40,
        decision_input_tokens_estimated=estimate,  # the cache hit is billed nothing and estimated nothing
        decision_request_ids=("f1", "f2", "ok"),
        cache_hits=1,
        transport_retries=2,
    )
    assert result.model == ("m1", "m2")
    assert sink.events == [
        CostEvent("decision", "f1", transport_retry=True, succeeded=False, estimated_input_tokens=estimate),
        CostEvent("decision", "f2", transport_retry=True, succeeded=False, estimated_input_tokens=estimate),
        CostEvent("decision", "ok", 40, estimated_input_tokens=estimate, model="m1"),
        CostEvent("decision", "old", cache_hit=True, estimated_input_tokens=estimate, model="m2"),
    ]  # a failed attempt names no model; each response names its own (R15)


# --- state, budget and R13 ------------------------------------------------------------------


def test_state_is_keyed_objects_only() -> None:
    assert LevelState("s").serialise() == '{"source": "s"}'
    assert LevelState("é").serialise() == '{"source": "é"}'
    with pytest.raises(ValueError, match="R13"):
        LevelState("s", {"d": {"nested": ["a"]}})


def test_split_packs_in_order_within_both_limits() -> None:
    qs = [Question(f"q{i}", DecisionKind.PREDICATE, "x" * 30) for i in range(5)]
    per = budget.question_tokens(qs[0])
    sizes = {q.name: per for q in qs}
    config = JevsonConfig(max_input_tokens=budget.estimate_tokens("s") + 2 * per, max_questions_per_request=200)
    chunks = budget.split("s", qs, sizes, config)
    assert [[q.name for q in c] for c in chunks] == [["q0", "q1"], ["q2", "q3"], ["q4"]]
    assert budget.oversized("s", qs, sizes, JevsonConfig(max_input_tokens=per)) == qs
    assert budget.request_tokens("s", qs[:2], sizes) == budget.estimate_tokens("s") + 2 * per
    assert budget.estimate_tokens("ab") == 1
    assert budget.estimate_tokens("é" * 3) == 2


def test_each_node_is_budgeted_at_its_declared_size() -> None:
    """The hook Phase 4 uses to budget drafts before they exist: a node declared larger than its text
    is split out, or refused before any call when it cannot fit at all."""
    graph = DecisionGraph([flag("a"), flag("big"), flag("c")])
    small = budget.declared_tokens(flag("a"))
    room = budget.estimate_tokens(LevelState("the source").serialise()) + 3 * small  # a+big fit; c does not

    def declared(node: DecisionNode) -> int:
        return 2 * small if node.target == "/big" else small

    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    result = run(graph, backend, config=JevsonConfig(max_input_tokens=room), declared_size=declared)
    assert [[q.name for q in call.questions] for call in backend.calls] == [["q0", "q1"], ["q2"]]
    assert result.cost.level_splits == 1
    state = budget.estimate_tokens(LevelState("the source").serialise())
    assert result.cost.decision_input_tokens_estimated == (state + 3 * small) + (state + small)

    def huge(node: DecisionNode) -> int:
        return room * 2 if node.target == "/big" else small

    untouched = FakeBackend(default=FakeBackend.predicate(0.9))
    with pytest.raises(PreflightError, match="/big"):
        run(graph, untouched, config=JevsonConfig(max_input_tokens=room), declared_size=huge)
    assert untouched.calls == []


def test_an_oversized_node_in_a_later_level_raises_before_the_first_call() -> None:
    """Preflight sizes every level, not only the first: no spend on level 0 when level 1 cannot fit."""
    graph = DecisionGraph([flag("a"), flag("big", frozenset({"/a#predicate"}))])
    small = budget.declared_tokens(flag("a"))

    def huge(node: DecisionNode) -> int:
        return 10**6 if node.target == "/big" else small

    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    with pytest.raises(PreflightError, match="/big"):
        run(graph, backend, config=JevsonConfig(max_input_tokens=10_000), declared_size=huge)
    assert backend.calls == []


POSITIONAL = re.compile(r"\[\d+\]")


def test_no_template_references_a_collection_element_by_position() -> None:
    texts = [v for k, v in vars(templates).items() if k.isupper() and isinstance(v, str)]
    assert texts
    assert not [t for t in texts if POSITIONAL.search(t)]


@DETERMINISTIC
@given(supported())
def test_no_compiled_question_or_state_path_references_by_position(case: tuple[dict[str, object], list[str]]) -> None:
    """R13 over generated schemas: once the interpolated field labels are removed, no question text
    has a `[<digits>]`; option ids are opaque; the state holds only keyed objects."""
    schema, _ = case
    graph = compile_schema(schema)
    for node in graph.nodes.values():
        assert isinstance(node, DecisionNode)
        labels = node.target.split("/")[1:]
        text = node.question
        for label in sorted(labels, key=len, reverse=True):
            text = text.replace(label.replace("~1", "/").replace("~0", "~").replace("_", " "), "")
        assert not POSITIONAL.search(text)
        assert all(re.fullmatch(r"c\d+", option.id) for option in node.options)
    state = json.loads(LevelState("[3] source", {"/a#generate": {"k": "[1]"}}).serialise())
    assert not _lists(state)


def _lists(value: object) -> bool:
    if isinstance(value, dict):
        return any(_lists(child) for child in cast("dict[str, object]", value).values())
    return isinstance(value, list)


# --- the opt-in adjudication options are recorded (DESIGN §8.1; ASTERION-48) ---------------------------


def test_versions_record_options() -> None:
    graph = DecisionGraph([flag("a")])
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    chosen = run(graph, backend, config=JevsonConfig(criterion_template="1.2.0", draft_screen=True)).versions
    assert (chosen["criterion_template"], chosen["draft_screen"]) == ("1.2.0", "true")
    default = run(graph, backend).versions
    assert (default["criterion_template"], default["draft_screen"]) == ("1.1.0", "false")
    assert default["question_templates"] == templates.QUESTION_TEMPLATE_VERSION
