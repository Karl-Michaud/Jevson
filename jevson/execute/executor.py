"""Runs a decision graph: steps in dependency order, then each level's decisions as one request (R3).

- **Preflight** (DESIGN §8.2) budgets every level before the first call; a question that cannot fit
  even alone raises `PreflightError`, and a level over a limit is split (`Cost.level_splits`).
- **Answers** are read with `probabilities.interpret`, so ties, refusals and invalid answers become
  `Unresolved` and no probability threshold drops a commit (DESIGN §6.2). A decision whose
  dependency did not resolve is `Unresolved(dependency_unresolved)` and is never asked.
- **Limit rejections** are never retried unchanged: a `context_limit` or `question_limit` rejection
  bisects the request, and a lone question that still overflows is `Unresolved(budget_exceeded)`.
- **Cost**: a cache hit counts in `cache_hits` only; every other attempt, retried or failed, counts as
  a decision request with its request id. Every event goes to the `CostSink` as it happens, and every
  exception raised after the first spend carries the partial `Result` with its `Cost`.

Steps have no producers in v0 (generative fields are Phase 4); a runner per `StepKind` is injected.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from jevson.assemble.assembler import Committed, Outcome, assemble
from jevson.compile.questions import QUESTION_TEMPLATE_VERSION
from jevson.config import JevsonConfig
from jevson.errors import BackendError, ExtractorError, LLMError, PreflightError, UsageError
from jevson.execute import budget
from jevson.execute.state import LevelState
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.protocols import Backend, CostSink
from jevson.result import Result
from jevson.types import (
    Answer,
    BackendResponse,
    Cost,
    CostEvent,
    DecidedBy,
    Decision,
    DecisionKind,
    DecisionNode,
    DeclaredOption,
    InvalidAnswer,
    JSONValue,
    ProvenanceKind,
    Question,
    StepKind,
    StepNode,
    Unresolved,
    UnresolvedReason,
)

StepRunner = Callable[[StepNode, LevelState], Awaitable[JSONValue]]
LIMIT_CODES = frozenset({"context_limit", "question_limit"})
_OVERFLOW = "budget_exceeded"


@dataclass
class _Tally:
    """The running cost of one call, frozen into a `Cost` whenever a `Result` is built."""

    requests: int = 0
    input_tokens: int = 0
    request_ids: list[str] = field(default_factory=list[str])
    cache_hits: int = 0
    transport_retries: int = 0
    level_splits: int = 0
    wall_clock: dict[str, float] = field(default_factory=dict[str, float])

    def freeze(self) -> Cost:
        return Cost(
            decision_requests=self.requests,
            decision_input_tokens=self.input_tokens,
            decision_request_ids=tuple(self.request_ids),
            cache_hits=self.cache_hits,
            transport_retries=self.transport_retries,
            level_splits=self.level_splits,
            wall_clock_by_component=dict(self.wall_clock),
        )


class _Run:
    """The mutable state of one `execute()` call."""

    def __init__(self, schema: Mapping[str, Any], config: JevsonConfig, sink: CostSink | None) -> None:
        self.schema, self.config, self.sink = schema, config, sink
        self.tally = _Tally()
        self.outcomes: dict[str, Outcome] = {}
        self.decisions: dict[str, Decision] = {}
        self.models: list[str] = []
        self.targets: dict[str, str] = {}

    def emit(self, event: CostEvent) -> None:
        if self.sink is not None:
            self.sink.record(event)

    def clock(self, component: str, started: float) -> None:
        self.tally.wall_clock[component] = self.tally.wall_clock.get(component, 0.0) + time.perf_counter() - started

    def result(self) -> Result:
        config = self.config
        versions = {
            "question_templates": QUESTION_TEMPLATE_VERSION,
            "model": config.model,
            "max_input_tokens": str(config.max_input_tokens),
            "max_questions_per_request": str(config.max_questions_per_request),
            "budget_estimator": budget.ESTIMATOR_VERSION,
            "tie_margin_hundredths": str(config.tie_margin_hundredths),
            "default_extractor": config.default_extractor or "none",
            "redraft_budget": str(config.redraft_budget),
        }
        return assemble(
            self.schema,
            self.outcomes.values(),
            decisions=self.decisions,
            cost=self.tally.freeze(),
            model=tuple(self.models),
            versions=versions,
        )


async def execute(
    graph: DecisionGraph,
    schema: Mapping[str, Any],
    source: str,
    *,
    backend: Backend,
    config: JevsonConfig,
    known: Mapping[str, JSONValue] | None = None,
    cost_sink: CostSink | None = None,
    steps: Mapping[StepKind, StepRunner] | None = None,
) -> Result:
    """Resolve `graph` over `source`. `known` values (already validated) replace their nodes."""
    run = _Run(schema, config, cost_sink)
    run.targets = {node_id: node.target for node_id, node in graph.nodes.items()}
    runners = dict(steps or {})
    names = _preflight(graph, source, config, runners, known or {})
    for pointer, value in (known or {}).items():
        run.outcomes[pointer] = Committed(pointer, value, DecidedBy.CALLER)
    state = LevelState(source)
    for level in graph.levels():
        for step in level.steps:
            state = state.with_draft(step.id, await _run_step(run, runners[step.kind], step, state))
        pending = [node for node in level.decisions if node.target not in run.outcomes]
        await _decide(run, backend, state, pending, names)
    return run.result()


def _preflight(
    graph: DecisionGraph,
    source: str,
    config: JevsonConfig,
    runners: Mapping[StepKind, StepRunner],
    known: Mapping[str, JSONValue],
) -> dict[str, Question]:
    """Every check that must fail before anything is spent; returns each decision's question."""
    nodes = [n for level in graph.levels() for n in level.decisions if n.target not in known]
    questions = {n.id: Question(f"q{i}", n.kind, n.question, n.options) for i, n in enumerate(nodes)}
    missing = sorted({s.kind.value for level in graph.levels() for s in level.steps} - {k.value for k in runners})
    if missing:
        raise UsageError(f"no step runner for {', '.join(missing)}")
    try:
        source.encode("utf-8")
    except UnicodeEncodeError:
        raise PreflightError("the source is not valid Unicode text (it holds a lone surrogate)") from None
    state = LevelState(source).serialise()
    too_big = budget.oversized(state, list(questions.values()), config)
    if too_big:
        named = ", ".join(n.target for n in nodes if questions[n.id] in too_big)
        raise PreflightError(f"the source and one question exceed max_input_tokens={config.max_input_tokens}: {named}")
    return questions


async def _run_step(run: _Run, runner: StepRunner, step: StepNode, state: LevelState) -> JSONValue:
    started = time.perf_counter()
    error = LLMError if step.kind is StepKind.GENERATE else ExtractorError
    try:
        return await asyncio.wait_for(runner(step, state), run.config.step_timeout_s)
    except TimeoutError:
        raise error("timeout", f"{step.id} exceeded step_timeout_s", run.result()) from None
    except Exception as failure:
        raise error("step_failed", f"{step.id}: {type(failure).__name__}", run.result()) from None
    finally:
        run.clock(step.protocol, started)


async def _decide(
    run: _Run, backend: Backend, state: LevelState, nodes: Sequence[DecisionNode], names: Mapping[str, Question]
) -> None:
    ready: list[DecisionNode] = []
    for node in nodes:
        if any(isinstance(run.outcomes.get(run.targets[d]), Unresolved) for d in node.dependencies):
            run.outcomes[node.target] = Unresolved(node.target, UnresolvedReason.DEPENDENCY_UNRESOLVED)
        else:
            ready.append(node)
    if not ready:
        return
    serialised = state.serialise()
    questions = [names[node.id] for node in ready]
    too_big = budget.oversized(serialised, questions, run.config)  # only drafts can grow a state
    chunks = budget.split(serialised, [q for q in questions if q not in too_big], run.config)
    run.tally.level_splits += max(len(chunks) - 1, 0)
    answers: dict[str, Answer | str] = {q.name: _OVERFLOW for q in too_big}
    for chunk in chunks:
        answers |= await _ask(run, backend, serialised, chunk)
    for node in ready:
        _record(run, node, answers[names[node.id].name])


def _record(run: _Run, node: DecisionNode, answer: Answer | str) -> None:
    if isinstance(answer, str):
        run.outcomes[node.target] = Unresolved(node.target, UnresolvedReason.BUDGET_EXCEEDED)
        return
    reading = interpret(node, answer, run.config.tie_margin_hundredths)
    run.decisions[f"{node.id}@0"] = reading.decision
    selected = reading.decision.selected
    if reading.status == "unresolved" or selected is None:
        run.outcomes[node.target] = Unresolved(node.target, reading.reason or UnresolvedReason.INVALID_BACKEND_ANSWER)
        return
    if node.kind is DecisionKind.PREDICATE:
        run.outcomes[node.target] = Committed(node.target, selected, DecidedBy.DECISION)
        return
    index = [option.id for option in node.options].index(str(selected))
    value = node.values[index] if node.values else str(selected)
    provenance = DeclaredOption(str(selected)) if node.provenance is ProvenanceKind.DECLARED_OPTION else None
    run.outcomes[node.target] = Committed(node.target, value, DecidedBy.DECISION, provenance)


async def _ask(run: _Run, backend: Backend, state: str, chunk: list[Question]) -> dict[str, Answer | str]:
    """One request, bisected on a limit rejection; never the same request twice."""
    started = time.perf_counter()
    try:
        response = await backend.ask(state, chunk, run.config.model)
    except BackendError as error:
        rejected = error
    except Exception as failure:  # a caller-supplied backend outside the hierarchy
        raise BackendError("backend_exception", type(failure).__name__, run.result()) from None
    else:
        _count_response(run, response)
        return _match(chunk, response)
    finally:
        run.clock("decision", started)
    _count_failure(run, rejected.cost)
    if rejected.code not in LIMIT_CODES:
        detail = str(rejected).removeprefix(f"{rejected.code}: ")
        raise BackendError(rejected.code, detail, run.result()) from None
    if len(chunk) == 1:
        return {chunk[0].name: _OVERFLOW}
    run.tally.level_splits += 1
    half = len(chunk) // 2
    return await _ask(run, backend, state, chunk[:half]) | await _ask(run, backend, state, chunk[half:])


def _match(chunk: list[Question], response: BackendResponse) -> dict[str, Answer | str]:
    """Answers by name; a missing or duplicated name is an invalid answer for that question."""
    seen: dict[str, list[Answer]] = {}
    for answer in response.answers:
        seen.setdefault(getattr(answer, "name", ""), []).append(answer)
    matched: dict[str, Answer | str] = {}
    for question in chunk:
        found = seen.get(question.name, [])
        matched[question.name] = found[0] if len(found) == 1 else InvalidAnswer(question.name, "missing or repeated")
    return matched


def _count_response(run: _Run, response: BackendResponse) -> None:
    if response.model not in run.models:
        run.models.append(response.model)
    if response.cache_hit:
        run.tally.cache_hits += 1
        run.emit(CostEvent("decision", response.request_id, cache_hit=True))
        return
    for rid in response.retried_request_ids:
        run.emit(CostEvent("decision", rid, transport_retry=True, succeeded=False))
    tally = run.tally
    tally.requests += 1 + response.transport_retries
    tally.transport_retries += response.transport_retries
    tally.input_tokens += response.input_tokens
    tally.request_ids += [*response.retried_request_ids, response.request_id]
    run.emit(CostEvent("decision", response.request_id, response.input_tokens))


def _count_failure(run: _Run, cost: Cost) -> None:
    tally = run.tally
    tally.requests += cost.decision_requests
    tally.transport_retries += cost.transport_retries
    tally.request_ids += cost.decision_request_ids
    ids: list[str | None] = [*cost.decision_request_ids]
    for attempt in range(cost.decision_requests):
        rid = ids[attempt] if attempt < len(ids) else None
        run.emit(CostEvent("decision", rid, transport_retry=attempt > 0, succeeded=False))
