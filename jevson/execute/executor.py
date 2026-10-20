"""Runs a decision graph: steps in dependency order, then each level's decisions in one request (R3),
and its adjudication questions in another.

- **Preflight** (DESIGN §8.2) budgets every level before the first call; a question that cannot fit
  even alone raises `PreflightError`, and a level over a limit is split (`Cost.level_splits`).
- **Answers** are read with `probabilities.interpret`, so ties, refusals and invalid answers become
  `Unresolved` and no probability threshold drops a commit (DESIGN §6.2). A decision whose
  dependency did not resolve is `Unresolved(dependency_unresolved)` and is never asked.
- **Limit rejections** are never retried unchanged: a `context_limit` or `question_limit` rejection
  bisects the request, and a lone question that still overflows is `Unresolved(budget_exceeded)`.
- **Cost**: a cache hit counts in `cache_hits` only; every other attempt, retried or failed, counts as
  a decision request with its request id. Every decision event carries preflight's estimate for its
  request, and `Cost` sums it over the billed responses beside their `input_tokens` (DESIGN §8.2).
  Every event goes to the `CostSink` as it happens, and every exception raised after the first spend
  carries the partial `Result` with its `Cost`.

- **Generative fields** (DESIGN §6.3): a `generate` step drafts through the caller's `LLM`
  (`drafting.py`); a well-formed draft enters the level state at `drafts.<step id>`, and its criteria
  ride in the level's adjudication request, apart from every other question: only adjudication is
  ever asked over a state holding drafts (DESIGN §5.2), and each such state holds only the drafts its
  questions name. The two groups are budgeted and split separately.
  After the level's request, failing fields are redrafted and re-adjudicated together, one request
  per round, until each is admitted or its `redraft_budget` is spent (`policy.RedraftLoop`).
  Decisions are recorded as `node@attempt`. Budgets use the source-only state plus each node's
  declared size, which includes its draft at `max_draft_chars` (`budget.with_drafts`).

- **Multi-label enum arrays** (DESIGN §4.2): each value's membership predicate keeps its outcome under
  its node id (`DecisionNode.key`); `assemble/cardinality.py` folds them into the array.

- **Unions** (DESIGN §3.2): a node inside union branches runs only when its branch is selected
  (`branches.py`); a discriminator's answer selects a branch and commits its constants.

An extraction step (class D, deferred) runs through an injected runner per `StepKind`.

Length (~500 lines, over the ~400 convention): the redraft loop drives `_decide` and `_Run` directly,
and moving it out would make both public for one caller; union gating lives in `branches.py`, leaving
only its call sites here. Split if either grows again.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from jevson.adjudicate.criteria import judge
from jevson.assemble.assembler import Committed, Outcome, assemble
from jevson.assemble.cardinality import fold
from jevson.compile.questions import QUESTION_TEMPLATE_VERSION
from jevson.config import JevsonConfig
from jevson.errors import BackendError, ExtractorError, LLMError, PreflightError, UsageError
from jevson.execute import budget
from jevson.execute.branches import Branches
from jevson.execute.drafting import TOOL_SCHEMA, messages, read
from jevson.execute.policy import RedraftLoop
from jevson.execute.state import LevelState
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.protocols import LLM, Backend, CostSink
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
    Drafting,
    InvalidAnswer,
    JSONValue,
    OptionSource,
    ProvenanceKind,
    Question,
    Rejection,
    StepKind,
    StepNode,
    Unresolved,
    UnresolvedReason,
)

_NO_DRAFTING = Drafting("", "")
StepRunner = Callable[[StepNode, LevelState], Awaitable[JSONValue]]
LIMIT_CODES = frozenset({"context_limit", "question_limit"})
_OVERFLOW = "budget_exceeded"
StateOf = Callable[[list[Question]], str]
"""The state of a request over these questions: only what they read."""


@dataclass
class _Tally:
    """The running cost of one call, frozen into a `Cost` whenever a `Result` is built."""

    requests: int = 0
    input_tokens: int = 0
    estimated: int = 0
    request_ids: list[str] = field(default_factory=list[str])
    cache_hits: int = 0
    transport_retries: int = 0
    level_splits: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    redrafts: int = 0
    wall_clock: dict[str, float] = field(default_factory=dict[str, float])

    def freeze(self) -> Cost:
        return Cost(
            decision_requests=self.requests,
            decision_input_tokens=self.input_tokens,
            decision_input_tokens_estimated=self.estimated,
            decision_request_ids=tuple(self.request_ids),
            cache_hits=self.cache_hits,
            transport_retries=self.transport_retries,
            level_splits=self.level_splits,
            llm_input_tokens=self.llm_input_tokens,
            llm_output_tokens=self.llm_output_tokens,
            redrafts=self.redrafts,
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
        self.sizes: dict[str, int] = {}
        """Each question's declared size in estimated tokens, by question name."""
        self.source = ""
        self.extracted: dict[str, JSONValue] = {}
        """Extraction step outputs by step id; they are budgeted as part of the state."""
        self.drafting = RedraftLoop(config.redraft_budget)
        self.adjudicates: dict[str, StepNode] = {}
        """The generate step each adjudication node checks, by node id."""
        self.nodes: dict[str, DecisionNode] = {}
        self.answers: dict[str, Answer | str] = {}
        """Adjudication answers awaiting their field's verdict, by node id."""
        self.branches: Branches

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
            "union_fanout": str(config.union_fanout).lower(),
        }
        outcomes, holes, overflow = fold(self.nodes.values(), self.outcomes, self.decisions)
        return assemble(
            self.schema,
            outcomes,
            array_holes=holes,
            overflow=overflow,
            decisions=self.decisions,
            cost=self.tally.freeze(),
            model=tuple(self.models),
            versions=versions,
            rejections=tuple(self.drafting.rejections),
        )

    def state(self, nodes: Sequence[DecisionNode], *, budgeted: bool = False) -> str:
        """The state for a request over `nodes`: the drafts they read. A budgeted state leaves out the
        generated drafts, which each node's declared size already counts."""
        drafts: dict[str, JSONValue] = {}
        for node in nodes:
            for dependency in sorted(node.dependencies):
                if dependency in self.extracted:
                    drafts[dependency] = self.extracted[dependency]
        pending = self.drafting.pending()
        if not budgeted:
            drafts |= {self.adjudicates[n.id].id: pending[self.adjudicates[n.id].id] for n in nodes
                       if n.id in self.adjudicates}  # fmt: skip
        return LevelState(self.source, drafts).serialise()


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
    llm: LLM | None = None,
    declared_size: budget.DeclaredSize = budget.declared_tokens,
) -> Result:
    """Resolve `graph` over `source`. `known` values (already validated) replace their nodes.

    `declared_size` budgets each node at its declared maximum (DESIGN §8.2); the drafts of
    generative fields are added to it here, at their `max_draft_chars`."""
    run = _Run(schema, config, cost_sink)
    run.source = source
    run.targets = {node_id: node.key for node_id, node in graph.nodes.items()}
    generate = {n.id: n for n in graph.nodes.values() if isinstance(n, StepNode) and n.drafting is not None}
    run.adjudicates = {
        n.id: generate[d] for n in graph.nodes.values() if isinstance(n, DecisionNode) for d in n.dependencies
        if d in generate
    }  # fmt: skip
    runners = dict(steps or {})
    sized = budget.with_drafts(declared_size, run.adjudicates)
    names = _preflight(run, graph, source, runners, llm, known=known or {}, declared_size=sized)
    run.branches = Branches(graph, known or {})
    for pointer, value in (known or {}).items():
        if pointer not in run.branches.deferred:
            run.outcomes[pointer] = Committed(pointer, value, DecidedBy.CALLER)
    run.branches.commit_open(run.outcomes)
    for level in graph.levels():
        drafted: list[StepNode] = []
        for step in level.steps:
            if step.target in run.outcomes or not _runs(run, step):
                continue
            if step.drafting is not None and llm is not None:
                await _draft(run, llm, step, step.drafting, None)
                drafted.append(step)
            else:
                run.extracted[step.id] = await _run_step(run, runners[step.kind], step, LevelState(source))
        await _decide(run, backend, _askable(run, level.decisions), names)
        await _redraft(run, backend, llm, drafted, names)
    return run.result()


def _askable(run: _Run, nodes: Sequence[DecisionNode]) -> list[DecisionNode]:
    """The nodes to ask now: undecided class C nodes, and the checks of drafts awaiting a verdict."""
    pending = run.drafting.pending()
    return [
        n for n in nodes
        if (run.adjudicates[n.id].id in pending if n.id in run.adjudicates
            else not {n.key, n.target} & run.outcomes.keys() and _runs(run, n))
    ]  # fmt: skip


def _runs(run: _Run, node: DecisionNode | StepNode) -> bool:
    """Whether a node's branch lets it run. A node under an unresolved discriminator is
    `dependency_unresolved`; a known field inside a branch is never asked (`Branches.commit_open`)."""
    gate = run.branches.gate(node.branch)
    if gate == "unresolved":
        run.outcomes.setdefault(node.key, Unresolved(node.target, UnresolvedReason.DEPENDENCY_UNRESOLVED))
    return not (
        gate in ("unresolved", "closed")
        or node.id in run.branches.selected  # selected by known=
        or node.target in run.branches.deferred
    )


async def _redraft(
    run: _Run, backend: Backend, llm: LLM | None, drafted: Sequence[StepNode], names: Mapping[str, Question]
) -> None:
    """Judge this level's drafts, then redraft the failing ones until each is admitted or exhausted."""
    checks = {step.id: [n for n in run.nodes.values() if run.adjudicates.get(n.id) is step] for step in drafted}
    while True:
        pending = run.drafting.pending()
        for step in drafted:
            if step.id in pending:
                _judge(run, step, checks[step.id])
        due = run.drafting.to_redraft()
        if not due or llm is None:
            break
        for step, rejection in due:
            run.tally.redrafts += 1
            await _draft(run, llm, step, step.drafting or _NO_DRAFTING, rejection)
        await _decide(run, backend, _askable(run, [n for step, _ in due for n in checks[step.id]]), names)
    for step in drafted:
        run.outcomes[step.target] = run.drafting.outcome(step.id, gated=bool(checks[step.id]))


def _judge(run: _Run, step: StepNode, nodes: Sequence[DecisionNode]) -> None:
    attempt = run.drafting.attempt(step.id)
    answers = {n.id: a for n in nodes if not isinstance(a := run.answers.pop(n.id, _OVERFLOW), str)}
    drafting = step.drafting or _NO_DRAFTING
    decisions, failing = judge(drafting, {n.id: n for n in nodes}, answers, run.config.tie_margin_hundredths)
    for node_id, decision in decisions.items():
        run.decisions[f"{node_id}@{attempt}"] = decision
    run.drafting.verdict(step.id, failing)


async def _draft(run: _Run, llm: LLM, step: StepNode, drafting: Drafting, rejection: Rejection | None) -> None:
    started = time.perf_counter()
    try:
        response = await asyncio.wait_for(
            llm.complete(messages(drafting, run.source, rejection), TOOL_SCHEMA), run.config.step_timeout_s
        )
    except TimeoutError:
        run.emit(CostEvent("llm", succeeded=False))
        raise LLMError("timeout", f"{step.id} exceeded step_timeout_s", run.result()) from None
    except Exception as failure:
        run.emit(CostEvent("llm", succeeded=False))
        code = failure.code if isinstance(failure, LLMError) else "llm_exception"
        raise LLMError(code, f"{step.id}: {type(failure).__name__}", run.result()) from None
    finally:
        run.clock("LLM", started)
    draft = read(response, drafting.max_draft_chars)
    run.tally.llm_input_tokens += draft.input_tokens
    run.tally.llm_output_tokens += draft.output_tokens
    run.emit(CostEvent("llm", input_tokens=draft.input_tokens, output_tokens=draft.output_tokens))
    run.drafting.offer(step, drafting.max_draft_chars, draft)


def _preflight(
    run: _Run,
    graph: DecisionGraph,
    source: str,
    runners: Mapping[StepKind, StepRunner],
    llm: LLM | None,
    *,
    known: Mapping[str, JSONValue],
    declared_size: budget.DeclaredSize,
) -> dict[str, Question]:
    """Every check that must fail before anything is spent; returns each decision's question."""
    config = run.config
    nodes = [n for level in graph.levels() for n in level.decisions if n.target not in known]
    run.nodes = {n.id: n for n in nodes}
    questions = {n.id: Question(f"q{i}", n.kind, n.question, n.options) for i, n in enumerate(nodes)}
    run.sizes = {questions[n.id].name: declared_size(n) for n in nodes}
    steps = [s for level in graph.levels() for s in level.steps if s.target not in known]
    if llm is None and any(s.drafting is not None for s in steps):
        raise UsageError("a generative field needs an LLM: Jevson(backend, llm=...)")
    missing = sorted({s.kind.value for s in steps if s.drafting is None} - {k.value for k in runners})
    if missing:
        raise UsageError(f"no step runner for {', '.join(missing)}")
    try:
        source.encode("utf-8")
    except UnicodeEncodeError:
        raise PreflightError("the source is not valid Unicode text (it holds a lone surrogate)") from None
    state = LevelState(source).serialise()
    too_big = budget.oversized(state, list(questions.values()), run.sizes, config)
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


async def _decide(run: _Run, backend: Backend, nodes: Sequence[DecisionNode], names: Mapping[str, Question]) -> None:
    """Ask `nodes` in as few requests as fit. Class C answers are recorded at once; adjudication
    answers wait in `run.answers` for their field's verdict."""
    ready: list[DecisionNode] = []
    for node in nodes:
        if any(isinstance(run.outcomes.get(run.targets[d]), Unresolved) for d in node.dependencies):
            run.outcomes[node.key] = Unresolved(node.target, UnresolvedReason.DEPENDENCY_UNRESOLVED)
        else:
            ready.append(node)
    answers: dict[str, Answer | str] = {}
    plain = [node for node in ready if node.id not in run.adjudicates]
    for group in (plain, [node for node in ready if node.id in run.adjudicates]):
        if group:
            answers |= await _ask_group(run, backend, group, names)
    for node in sorted(ready, key=lambda n: len(n.branch)):  # under fan-out, discriminators first
        if node.key in run.outcomes or not _runs(run, node):
            continue  # an unselected branch's answer is discarded
        if node.id in run.adjudicates:
            run.answers[node.id] = answers[names[node.id].name]
        else:
            _record(run, node, answers[names[node.id].name])


async def _ask_group(
    run: _Run, backend: Backend, group: Sequence[DecisionNode], names: Mapping[str, Question]
) -> dict[str, Answer | str]:
    """Ask one group in as few requests as fit the budget. Adjudication questions form their own group,
    so a state holding drafts reaches only the questions that check them (invariant 7)."""
    budgeted = run.state(group, budgeted=True)
    questions = [names[node.id] for node in group]
    by_name = {names[node.id].name: node for node in group}
    too_big = budget.oversized(budgeted, questions, run.sizes, run.config)  # extracted outputs grow a state
    chunks = budget.split(budgeted, [q for q in questions if q not in too_big], run.sizes, run.config)
    run.tally.level_splits += max(len(chunks) - 1, 0)
    answers: dict[str, Answer | str] = {q.name: _OVERFLOW for q in too_big}

    def state_of(chunk: list[Question]) -> str:
        return run.state([by_name[q.name] for q in chunk])

    for chunk in chunks:
        answers |= await _ask(run, backend, state_of, chunk)
    return answers


def _record(run: _Run, node: DecisionNode, answer: Answer | str) -> None:
    union = node.option_source is OptionSource.SCHEMA_UNION
    if isinstance(answer, str):
        reason: UnresolvedReason | None = UnresolvedReason.BUDGET_EXCEEDED
        selected = None
    else:
        reading = interpret(node, answer, run.config.tie_margin_hundredths)
        run.decisions[f"{node.id}@0"] = reading.decision
        selected = reading.decision.selected
        reason = reading.reason if reading.status == "unresolved" else None
    if reason is not None or selected is None:
        run.outcomes[node.key] = Unresolved(node.target, reason or UnresolvedReason.INVALID_BACKEND_ANSWER)
        if union:
            run.branches.failed.add(node.id)
        return
    if union:
        run.branches.selected[node.id] = str(selected)
        run.branches.commit_open(run.outcomes)
        return
    if node.kind is DecisionKind.PREDICATE:
        run.outcomes[node.key] = Committed(node.target, selected, DecidedBy.DECISION)
        return
    index = [option.id for option in node.options].index(str(selected))
    value = node.values[index] if node.values else str(selected)
    provenance = DeclaredOption(str(selected)) if node.provenance is ProvenanceKind.DECLARED_OPTION else None
    run.outcomes[node.target] = Committed(node.target, value, DecidedBy.DECISION, provenance)


async def _ask(run: _Run, backend: Backend, state_of: StateOf, chunk: list[Question]) -> dict[str, Answer | str]:
    """One request, bisected on a limit rejection; never the same request twice. Each half's state is
    rebuilt from its own questions, so it carries only the drafts they read."""
    state = state_of(chunk)
    started = time.perf_counter()
    estimate = budget.request_tokens(state, chunk, run.sizes)
    try:
        response = await backend.ask(state, chunk, run.config.model)
    except BackendError as error:
        rejected = error
    except Exception as failure:  # a caller-supplied backend outside the hierarchy
        raise BackendError("backend_exception", type(failure).__name__, run.result()) from None
    else:
        _count_response(run, response, estimate)
        return _match(chunk, response)
    finally:
        run.clock("decision", started)
    _count_failure(run, rejected.cost, estimate)
    if rejected.code not in LIMIT_CODES:
        detail = str(rejected).removeprefix(f"{rejected.code}: ")
        raise BackendError(rejected.code, detail, run.result()) from None
    if len(chunk) == 1:
        return {chunk[0].name: _OVERFLOW}
    run.tally.level_splits += 1
    half = len(chunk) // 2
    return await _ask(run, backend, state_of, chunk[:half]) | await _ask(run, backend, state_of, chunk[half:])


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


def _count_response(run: _Run, response: BackendResponse, estimate: int) -> None:
    if response.model not in run.models:
        run.models.append(response.model)
    if response.cache_hit:
        run.tally.cache_hits += 1
        run.emit(CostEvent("decision", response.request_id, cache_hit=True, estimated_input_tokens=estimate))
        return
    for rid in response.retried_request_ids:
        run.emit(CostEvent("decision", rid, transport_retry=True, succeeded=False, estimated_input_tokens=estimate))
    tally = run.tally
    tally.requests += 1 + response.transport_retries
    tally.transport_retries += response.transport_retries
    tally.input_tokens += response.input_tokens
    tally.estimated += estimate
    tally.request_ids += [*response.retried_request_ids, response.request_id]
    run.emit(CostEvent("decision", response.request_id, response.input_tokens, estimated_input_tokens=estimate))


def _count_failure(run: _Run, cost: Cost, estimate: int) -> None:
    tally = run.tally
    tally.requests += cost.decision_requests
    tally.transport_retries += cost.transport_retries
    tally.request_ids += cost.decision_request_ids
    ids: list[str | None] = [*cost.decision_request_ids]
    for attempt in range(cost.decision_requests):
        rid = ids[attempt] if attempt < len(ids) else None
        failed = CostEvent("decision", rid, transport_retry=attempt > 0, succeeded=False)
        run.emit(replace(failed, estimated_input_tokens=estimate))
