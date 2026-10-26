"""PLAN Phase 4: generative fields, adjudication, the redraft loop, and ReplayLLM, against fakes.

Each exit criterion has a test here, named after it; the central property over hostile LLMs is in
`tests/adversarial/test_hostile_llm.py`. The live injection regression and the human-labelled
redraft bar are J4b's.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from jevson import (
    CompileError,
    CostEvent,
    DecidedBy,
    DecisionsBackend,
    FakeBackend,
    Jevson,
    JevsonConfig,
    LLMError,
    MissingCredentials,
    PreflightError,
    RefusalCode,
    Rejection,
    ReplayLLM,
    Result,
    Unresolved,
    UnresolvedReason,
    UsageError,
    compile_schema,
    dry_run,
)
from jevson.adjudicate.criteria import PASS_RULES, judge
from jevson.adjudicate.dryrun import DryRun
from jevson.adjudicate.rubrics import rubric_passes
from jevson.checks import Check, CheckRule
from jevson.compile.draft_screen import SCREEN_REJECTION
from jevson.compile.questions import redraft_prompt, screen_question
from jevson.execute import budget
from jevson.execute.drafting import TOOL_SCHEMA, malformed, read
from jevson.execute.state import LevelState
from jevson.llm import replay as replay_module
from jevson.types import (
    DecisionKind,
    DecisionNode,
    Drafting,
    InvalidAnswer,
    LLMResponse,
    Message,
    Option,
    OptionSource,
    PredicateAnswer,
    Question,
    ScoreAnswer,
    StepKind,
    StepNode,
)
from tests.adversarial.hostile_llm import Hang, ScriptedLLM

CRITERIA = ["mentions the refund amount stated in the source", "is one sentence"]
RUBRIC = {"description": "how faithfully it reflects the source", "levels": ["poor", "ok", "good"], "minimum": "ok"}


def schema(generate: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    field = {"type": "string", "x-jevson": {"generate": {"criteria": CRITERIA} if generate is None else generate}}
    properties: dict[str, Any] = {"summary": field, **extra}
    return {"type": "object", "properties": properties, "required": ["summary"]}


def resolve(backend: FakeBackend, llm: Any, schema_: dict[str, Any] | None = None, **kwargs: Any) -> Result:
    config = kwargs.pop("config", JevsonConfig())
    sink = kwargs.pop("cost_sink", None)
    jevson = Jevson(backend, llm=llm, config=config, cost_sink=sink)
    return asyncio.run(jevson.aresolve(schema() if schema_ is None else schema_, "Refund: $40.", **kwargs))


def passes(question: Question) -> Any:
    """A passing answer: 0.9 on a criterion, the top level of a rubric."""
    if question.kind is DecisionKind.SCORE:
        return FakeBackend.select(question.options[-1].id)(question)
    return FakeBackend.predicate(0.9)(question)


def passing() -> FakeBackend:
    return FakeBackend(default=passes)


def by_criterion(**scripts: Any) -> FakeBackend:
    """Answer each criterion question by a keyword in it; everything else passes."""

    def answer(question: Question) -> Any:
        for word, script in scripts.items():
            if word in question.instructions:
                return script(question)
        return passes(question)

    return FakeBackend(default=answer)


# --- compile -------------------------------------------------------------------------------


def test_a_declared_generative_field_compiles_to_a_step_plus_criterion_nodes() -> None:
    graph = compile_schema(schema({"criteria": CRITERIA, "rubric": RUBRIC, "instructions": "Be brief"}))
    nodes = graph.nodes
    assert list(nodes) == ["/summary#generate", "/summary#criterion:0", "/summary#criterion:1", "/summary#rubric"]
    step = nodes["/summary#generate"]
    assert isinstance(step, StepNode)
    assert step.kind is StepKind.GENERATE
    assert step.drafting is not None
    assert step.drafting.prompt == "Write the summary for the source below. Be brief. Return only the value."
    assert step.drafting.max_draft_chars == 4000
    assert step.drafting.rubric_minimum == "c1"
    for node_id in list(nodes)[1:]:
        node = nodes[node_id]
        assert isinstance(node, DecisionNode)
        assert node.dependencies == {"/summary#generate"}
        assert node.target == "/summary"
    criterion = nodes["/summary#criterion:0"]
    assert isinstance(criterion, DecisionNode)
    assert criterion.question == (
        "Does `drafts./summary#generate` meet this criterion: mentions the refund amount stated in the source?"
    )
    [level] = graph.levels()
    assert [s.id for s in level.steps] == ["/summary#generate"]


def test_the_rubric_template_renders_the_declared_description() -> None:
    rubric = compile_schema(schema({"rubric": RUBRIC})).nodes["/summary#rubric"]
    assert isinstance(rubric, DecisionNode)
    assert rubric.kind is DecisionKind.SCORE
    assert rubric.question == (
        "Which level best describes `drafts./summary#generate` against this rubric: "
        "how faithfully it reflects the source?"
    )
    assert [o.description for o in rubric.options] == ['"poor"', '"ok"', '"good"']


def test_a_rubric_without_a_description_refuses_with_every_other_offending_pointer() -> None:
    undescribed = {"levels": ["poor", "good"], "minimum": "good"}
    bad = schema({"criteria": ["c"], "rubric": undescribed}, other={"type": "string"})
    with pytest.raises(CompileError) as raised:
        compile_schema(bad)
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [
        ("/summary", RefusalCode.RUBRIC_DESCRIPTION_MISSING),
        ("/other", RefusalCode.UNBOUNDED_FIELD),
    ]


def test_an_unbounded_string_with_neither_source_nor_generate_still_refuses() -> None:
    with pytest.raises(CompileError) as raised:
        compile_schema({"type": "object", "properties": {"s": {"type": "string"}}})
    assert [r.reason for r in raised.value.reasons] == [RefusalCode.UNBOUNDED_FIELD]


@pytest.mark.parametrize(
    "field",
    [
        {"type": "integer"},
        {"type": "boolean"},
        {"enum": ["a", "b"]},
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": {"a": {"type": "boolean", "description": "a holds"}}},
        {"const": "x"},
    ],
)
def test_generate_on_anything_but_a_string_refuses_by_name(field: dict[str, Any]) -> None:
    declared = {**field, "x-jevson": {"generate": {"criteria": ["c"]}}}
    with pytest.raises(CompileError) as raised:
        compile_schema({"type": "object", "properties": {"f": declared}})
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [("/f", RefusalCode.GENERATE_FIELD_TYPE)]


def test_a_generated_string_with_a_default_is_still_generated() -> None:
    graph = compile_schema(schema({"criteria": ["c"]}) | {"required": []})
    assert "/summary#generate" in graph.nodes
    defaulted = {"type": "string", "default": "", "x-jevson": {"generate": {}}}
    assert list(compile_schema({"type": "object", "properties": {"d": defaulted}}).nodes) == ["/d#generate"]


def test_two_identical_criteria_on_one_field_refuse_as_duplicate_questions() -> None:
    with pytest.raises(CompileError) as raised:
        compile_schema(schema({"criteria": ["same", "same"]}))
    assert [r.reason for r in raised.value.reasons] == [RefusalCode.DUPLICATE_QUESTION]


# --- adjudication -------------------------------------------------------------------------


def test_all_criteria_for_a_field_are_adjudicated_in_one_batched_call() -> None:
    backend = passing()
    llm = ScriptedLLM(["Refund of $40."])
    result = resolve(backend, llm, schema({"criteria": [*CRITERIA, "is polite"], "rubric": RUBRIC}))
    assert len(backend.calls) == 1
    [call] = backend.calls
    assert len(call.questions) == 4
    assert call.state == '{"source": "Refund: $40.", "drafts": {"/summary#generate": "Refund of $40."}}'
    assert result.value == {"summary": "Refund of $40."}
    assert result.decided_by == {"/summary": DecidedBy.LLM_DECISION}
    assert result.ungated == ()
    assert result.provenance == {}
    assert llm.calls[0][1] == TOOL_SCHEMA


@pytest.mark.parametrize(("limit", "sizes", "splits"), [(200, [3], 0), (3, [3], 0), (2, [2, 1], 1)])
def test_a_fields_criteria_split_across_requests_only_under_design_8_2(
    limit: int, sizes: list[int], splits: int
) -> None:
    """PLAN Phase 4, amended 2026-10-19: one request unless the level is split under DESIGN §8.2."""
    backend = passing()
    criteria = [*CRITERIA, "is polite"]
    config = JevsonConfig(max_questions_per_request=limit)
    result = resolve(backend, ScriptedLLM(["Refund of $40."]), schema({"criteria": criteria}), config=config)
    assert [len(call.questions) for call in backend.calls] == sizes
    assert result.cost.level_splits == splits
    assert result.value == {"summary": "Refund of $40."}
    assert result.decided_by == {"/summary": DecidedBy.LLM_DECISION}


def test_rejection_names_the_specific_failing_criteria() -> None:
    backend = by_criterion(sentence=FakeBackend.predicate(0.1))
    result = resolve(backend, ScriptedLLM(["Draft one. Two.", "Draft three. Four."]))
    assert result.rejections == (
        Rejection("/summary", ("is one sentence",), "Draft one. Two."),
        Rejection("/summary", ("is one sentence",), "Draft three. Four."),
    )


def test_failing_criteria_are_passed_back_to_the_llm_on_a_redraft() -> None:
    backend = by_criterion(sentence=FakeBackend.predicate(0.1))
    llm = ScriptedLLM(["Draft one. Two.", "Draft three."])
    resolve(backend, llm)
    first, second = (messages for messages, _ in llm.calls)
    assert len(first) == 1
    assert [m.role for m in second] == ["user", "assistant", "user"]
    assert second[1].content == "Draft one. Two."
    assert second[2].content == (
        "That draft does not meet these criteria: is one sentence. Write the summary again. Return only the value."
    )


def test_redraft_budget_is_bounded_and_exhaustion_is_unresolved_redraft_exhausted() -> None:
    backend = FakeBackend(default=FakeBackend.predicate(0.1))
    llm = ScriptedLLM(["a", "b", "c", "d", "e"])
    result = resolve(backend, llm, redraft_budget=3)
    assert len(llm.calls) == 4
    assert result.unresolved == (Unresolved("/summary", UnresolvedReason.REDRAFT_EXHAUSTED, detail="3 redraft(s)"),)
    assert "summary" not in result.value
    assert result.satisfies_schema is False
    assert result.cost.redrafts == 3
    assert result.versions["redraft_budget"] == "3"
    assert [r.draft for r in result.rejections] == ["a", "b", "c", "d"]


def test_a_redraft_budget_of_zero_never_redrafts() -> None:
    llm = ScriptedLLM(["a"])
    result = resolve(FakeBackend(default=FakeBackend.predicate(0.1)), llm, redraft_budget=0)
    assert len(llm.calls) == 1
    assert result.unresolved[0].reason is UnresolvedReason.REDRAFT_EXHAUSTED


def test_a_redraft_that_passes_is_admitted() -> None:
    calls: list[int] = []

    def answer(question: Question) -> Any:
        calls.append(1)
        return PredicateAnswer(question.name, 0.1 if len(calls) <= 2 else 0.9)

    backend = FakeBackend(default=answer)
    result = resolve(backend, ScriptedLLM(["bad", "good"]))
    assert result.value == {"summary": "good"}
    assert len(result.rejections) == 1
    assert result.decided_by["/summary"] is DecidedBy.LLM_DECISION


def test_a_repeated_draft_triggers_no_second_adjudication_and_counts_against_the_budget() -> None:
    backend = FakeBackend(default=FakeBackend.predicate(0.1))
    llm = ScriptedLLM(["same draft"])
    result = resolve(backend, llm, redraft_budget=2)
    assert len(llm.calls) == 3
    assert len(backend.calls) == 1
    assert result.cost.redrafts == 2
    assert result.unresolved[0].reason is UnresolvedReason.REDRAFT_EXHAUSTED
    assert len(result.rejections) == 1
    assert not any(key.endswith("@1") for key in result.decisions)


def test_a_criterion_tie_counts_as_failed_is_named_and_triggers_a_redraft() -> None:
    answers = iter([0.5, 0.9, 0.9, 0.9])
    backend = FakeBackend(default=lambda q: PredicateAnswer(q.name, next(answers)))
    result = resolve(backend, ScriptedLLM(["first", "second"]))
    assert result.rejections == (Rejection("/summary", (CRITERIA[0],), "first"),)
    assert result.value == {"summary": "second"}
    decisions = result.decisions
    assert set(decisions) == {f"/summary#criterion:{i}@{n}" for i in (0, 1) for n in (0, 1)}
    assert decisions["/summary#criterion:0@0"].selected is None
    assert decisions["/summary#criterion:0@1"].selected is True


@pytest.mark.parametrize(
    ("probability", "passes"), [(0.56, True), (0.55, False), (0.45, False), (0.44, False), (1.0, True)]
)
def test_a_criterion_passes_at_p_at_least_0_56(probability: float, passes: bool) -> None:
    result = resolve(by_criterion(sentence=FakeBackend.predicate(probability)), ScriptedLLM(["d"]), redraft_budget=0)
    assert ("summary" in result.value) is passes


def test_an_unanswered_check_counts_as_failed() -> None:
    node = DecisionNode("/s#criterion:0", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/s")
    drafting = Drafting("p", "s", checks=(Check(node.id, "c", CheckRule.CRITERION),))
    assert judge(drafting, {node.id: node}, {node.id: None}, 10) == ({}, ("c",))


def test_a_criterion_passes_at_0_56_whatever_the_tie_margin() -> None:
    node = DecisionNode("/s#criterion:0", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/s")
    drafting = Drafting("p", "s", checks=(Check(node.id, "c", CheckRule.CRITERION),))
    for margin, probability, failing in [(0, 0.52, ("c",)), (0, 0.56, ()), (20, 0.58, ("c",))]:
        answers = {node.id: PredicateAnswer("q0", probability)}
        assert judge(drafting, {node.id: node}, answers, margin)[1] == failing


@pytest.mark.parametrize("script", [FakeBackend.refuse(), FakeBackend.answer(InvalidAnswer("q1", "junk"))])
def test_a_refused_or_invalid_criterion_counts_as_failed(script: Any) -> None:
    result = resolve(by_criterion(sentence=script), ScriptedLLM(["d"]), redraft_budget=0)
    assert result.rejections == (Rejection("/summary", ("is one sentence",), "d"),)


def rubric_node() -> DecisionNode:
    levels = tuple(Option(f"c{i}", f'"{name}"') for i, name in enumerate(["poor", "ok", "good"]))
    return DecisionNode("/s#rubric", DecisionKind.SCORE, "q", OptionSource.SCHEMA_RUBRIC, "/s", levels)


@pytest.mark.parametrize(
    ("probabilities", "passes"),
    [
        ({"c0": 0.0, "c1": 0.8, "c2": 0.2}, True),
        ({"c0": 0.8, "c1": 0.2, "c2": 0.0}, False),
        ({"c0": 0.0, "c1": 0.5, "c2": 0.5}, True),  # a tie, both levels at or above the minimum
        ({"c0": 0.5, "c1": 0.5, "c2": 0.0}, False),  # a tie straddling the minimum
        ({"c0": 0.3, "c1": 0.3, "c2": 0.4}, False),  # every level inside the margin of the top
    ],
)
def test_a_rubric_passes_when_its_most_probable_level_reaches_the_minimum(
    probabilities: dict[str, float], passes: bool
) -> None:
    index = sum(i * p for i, p in enumerate(probabilities.values()))
    answer = ScoreAnswer("q0", index, probabilities)
    assert rubric_passes(rubric_node(), answer, "c1", 10)[1] is passes


def test_a_refused_rubric_counts_as_failed() -> None:
    answer = FakeBackend.refuse()(Question("q0", DecisionKind.SCORE, "q", rubric_node().options))
    assert rubric_passes(rubric_node(), answer, "c1", 10)[1] is False


def test_a_rubric_is_judged_end_to_end_with_its_rejection_text() -> None:
    backend = FakeBackend(default=FakeBackend.select("c0"))
    result = resolve(backend, ScriptedLLM(["d"]), schema({"rubric": RUBRIC}), redraft_budget=0)
    assert result.rejections == (
        Rejection("/summary", ("how faithfully it reflects the source (at least 'ok')",), "d"),
    )


# --- drafts --------------------------------------------------------------------------------


def test_a_field_with_no_declared_criteria_is_admitted_ungated() -> None:
    backend = passing()
    result = resolve(backend, ScriptedLLM(["anything"]), schema({}))
    assert result.value == {"summary": "anything"}
    assert result.decided_by == {"/summary": DecidedBy.LLM}
    assert result.ungated == ("/summary",)
    assert backend.calls == []


@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(None, "prose", 1, 1),
        LLMResponse({"valeu": "x"}, "", 1, 1),
        LLMResponse({"value": 3}, "", 1, 1),
        LLMResponse({"value": "x", "extra": 1}, "", 1, 1),
        LLMResponse({"value": "x" * 11}, "", 1, 1),
    ],
)
def test_malformed_llm_output_is_a_failed_draft(response: LLMResponse) -> None:
    backend = passing()
    result = resolve(backend, ScriptedLLM([response]), schema({"criteria": ["c"], "max_draft_chars": 10}))
    assert result.unresolved[0].reason is UnresolvedReason.REDRAFT_EXHAUSTED
    [first, _] = result.rejections
    assert first.criteria == (malformed(10),)
    assert len(first.draft) <= 10
    assert backend.calls == []


def test_a_malformed_first_draft_is_redrafted_and_the_good_redraft_is_admitted() -> None:
    llm = ScriptedLLM([LLMResponse(None, "prose", 1, 1), "fine"])
    result = resolve(passing(), llm)
    assert result.value == {"summary": "fine"}
    assert "a single string value" in llm.calls[1][0][2].content
    assert set(result.decisions) == {"/summary#criterion:0@1", "/summary#criterion:1@1"}


def test_read_never_raises_and_counts_only_sane_tokens() -> None:
    draft = read(LLMResponse({"value": "ok"}, 3, True, -1), 10)  # type: ignore[arg-type]
    assert (draft.text, draft.input_tokens, draft.output_tokens) == ("ok", 0, 0)
    assert read(object(), 10).text is None


def test_llm_tokens_and_events_are_counted() -> None:
    events: list[CostEvent] = []

    class Sink:
        def record(self, cost_event: CostEvent) -> None:
            events.append(cost_event)

    result = resolve(passing(), ScriptedLLM(["d"]), cost_sink=Sink())
    assert (result.cost.llm_input_tokens, result.cost.llm_output_tokens) == (7, 3)
    assert [e.component for e in events] == ["llm", "decision"]
    assert set(result.cost.wall_clock_by_component) == {"LLM", "decision"}


# --- errors --------------------------------------------------------------------------------


def test_an_llm_exception_is_llm_error_with_the_partial_result() -> None:
    extra = {"paid": {"type": "boolean", "description": "the invoice is paid"}}
    with pytest.raises(LLMError) as raised:
        resolve(passing(), ScriptedLLM([RuntimeError("boom")]), schema(**extra))
    assert raised.value.code == "llm_exception"
    assert raised.value.result.cost is raised.value.cost


def test_a_never_returning_llm_times_out() -> None:
    with pytest.raises(LLMError) as raised:
        resolve(passing(), ScriptedLLM([Hang()]), config=JevsonConfig(step_timeout_s=0.01))
    assert raised.value.code == "timeout"


def test_an_llm_exception_on_a_redraft_carries_the_rejections_so_far() -> None:
    llm = ScriptedLLM(["bad", RuntimeError("boom")])
    with pytest.raises(LLMError) as raised:
        resolve(FakeBackend(default=FakeBackend.predicate(0.1)), llm)
    assert [r.draft for r in raised.value.result.rejections] == ["bad"]
    assert raised.value.result.cost.decision_requests == 1


def test_a_generative_field_without_an_llm_is_refused_before_any_call() -> None:
    backend = passing()
    with pytest.raises(UsageError, match="llm"):
        resolve(backend, None)
    assert backend.calls == []


# --- budget --------------------------------------------------------------------------------


def test_preflight_accounts_for_max_draft_chars_before_any_spend() -> None:
    backend, llm = passing(), ScriptedLLM(["d"])
    config = JevsonConfig(max_input_tokens=5000)
    with pytest.raises(PreflightError, match="/summary"):
        resolve(backend, llm, schema({"criteria": ["c"], "max_draft_chars": 4000}), config=config)
    assert backend.calls == []
    assert llm.calls == []
    small = resolve(backend, llm, schema({"criteria": ["c"], "max_draft_chars": 100}), config=config)
    assert small.value == {"summary": "d"}


def test_an_over_length_draft_is_a_failed_draft_not_a_context_limit_error_after_spend() -> None:
    backend = passing()
    result = resolve(backend, ScriptedLLM(["x" * 101]), schema({"criteria": ["c"], "max_draft_chars": 100}))
    assert backend.calls == []
    assert result.unresolved[0].reason is UnresolvedReason.REDRAFT_EXHAUSTED


@pytest.mark.parametrize("source", ["", "s", "abc"])
@pytest.mark.parametrize("n", [0, 1, 3, 10, 50])
@pytest.mark.parametrize("char", ["\x00", "a", "\U0001f600"])
def test_the_declared_draft_size_covers_what_a_worst_case_draft_adds_to_a_state(source: str, n: int, char: str) -> None:
    """The `drafts` wrapper included: a draft is budgeted at what it adds to the request's state."""
    step = StepNode("/s#generate", StepKind.GENERATE, "/s", drafting=Drafting("p", "s", n))
    bare = budget.estimate_tokens(LevelState(source).serialise())
    drafted = budget.estimate_tokens(LevelState(source, {"/s#generate": char * n}).serialise())
    assert budget.draft_tokens(step) >= drafted - bare


@pytest.mark.parametrize("source", ["", "s", "abc", "a longer source text"])
def test_a_step_without_drafting_is_budgeted_at_what_its_empty_entry_adds_to_a_state(source: str) -> None:
    """Measured on the state itself, not on the budget's own constants: covered, and within the one
    token that rounding the key and the wrapper together can add."""
    bare = budget.estimate_tokens(LevelState(source).serialise())
    added = budget.estimate_tokens(LevelState(source, {"/e#extract": ""}).serialise()) - bare
    assert added <= budget.draft_tokens(StepNode("/e#extract", StepKind.EXTRACT, "/e")) <= added + 1


def test_each_request_carries_only_the_drafts_its_questions_name() -> None:
    two = schema(other={"type": "string", "x-jevson": {"generate": {"criteria": ["names the customer"]}}})
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    result = resolve(backend, ScriptedLLM(["d"]), two, config=JevsonConfig(max_questions_per_request=2))
    states = [call.state for call in backend.calls]
    assert states == [
        '{"source": "Refund: $40.", "drafts": {"/summary#generate": "d"}}',
        '{"source": "Refund: $40.", "drafts": {"/other#generate": "d"}}',
    ]
    assert result.complete


# --- known, replay, dry run ----------------------------------------------------------------


def test_a_known_generated_field_skips_its_step_and_criteria() -> None:
    backend, llm = passing(), ScriptedLLM(["d"])
    result = resolve(backend, llm, known={"/summary": "given"})
    assert result.value == {"summary": "given"}
    assert result.decided_by == {"/summary": DecidedBy.CALLER}
    assert backend.calls == []
    assert llm.calls == []
    with pytest.raises(PreflightError):
        resolve(backend, llm, known={"/summary": 3})


def test_replay_llm_reproduces_a_recorded_run_exactly(tmp_path: Path) -> None:
    def run(llm: Any) -> Result:
        result = resolve(by_criterion(sentence=FakeBackend.predicate(0.1)), llm)
        return replace(result, cost=replace(result.cost, wall_clock_by_component={}))  # timings are excluded

    recording = ReplayLLM(ScriptedLLM(["A. B.", "C. D."]), tmp_path, llm_id="scripted-1")
    first = run(recording)
    replayed = run(ReplayLLM(None, tmp_path, llm_id="scripted-1", replay_only=True))
    assert replayed == first
    assert recording.misses == 2
    with pytest.raises(LLMError) as raised:
        run(ReplayLLM(None, tmp_path, llm_id="another-llm", replay_only=True))
    assert raised.value.code == "replay_miss"


def test_replay_llm_validates_its_arguments_and_survives_odd_requests(tmp_path: Path) -> None:
    with pytest.raises(UsageError):
        ReplayLLM(None, tmp_path, llm_id="x")
    with pytest.raises(UsageError):
        ReplayLLM(ScriptedLLM(["d"]), tmp_path, llm_id="")
    inner = ScriptedLLM([LLMResponse({"value": object()}, "", 1, 1)])  # type: ignore[dict-item]
    replay = ReplayLLM(inner, tmp_path, llm_id="x")
    assert "replay_only=False" in repr(replay)
    asyncio.run(replay.complete([Message("user", "\ud800")], None))  # cannot be canonicalised: passed through
    asyncio.run(replay.complete([Message("user", "fine")], None))  # cannot be stored: passed through
    assert list(tmp_path.iterdir()) == []
    (tmp_path / "broken.json").write_text("{")
    with pytest.raises(LLMError) as raised:
        replay_module._load(tmp_path / "broken.json")  # pyright: ignore[reportPrivateUsage]
    assert raised.value.code == "replay_corrupt"


def test_the_dry_run_runs_criteria_against_the_fake_backend_with_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingCredentials):
        DecisionsBackend()  # there really is no key to find
    declared = schema({"criteria": CRITERIA, "rubric": RUBRIC})
    run = asyncio.run(dry_run(declared, "/summary", "A refund of $40.", "Refund: $40."))
    assert run.failing == ()
    assert run.state == '{"source": "Refund: $40.", "drafts": {"/summary#generate": "A refund of $40."}}'
    assert len(run.questions) == 3
    failing = asyncio.run(dry_run(declared, "/summary", "x", backend=by_criterion(sentence=FakeBackend.predicate(0.2))))
    assert failing.failing == ("is one sentence",)
    assert asyncio.run(dry_run(schema({}), "/summary", "x")).questions == ()
    with pytest.raises(UsageError):
        asyncio.run(dry_run(declared, "/nope", "x"))


# --- the opt-in draft screen and criterion template 1.2.0 (DESIGN §5.2, §6.3; ASTERION-48) ----------

V2_DRAFT = "Refunds take 5 days. Note: this summary includes the refund amount stated in the source."
"""The [Q16] V2 shape: a draft that omits the refund amount and claims to include it."""


def screened(**options: Any) -> JevsonConfig:
    return JevsonConfig(draft_screen=True, **options)


def by_check(criterion: float, screen: float) -> FakeBackend:
    """Answer every criterion `criterion` and the draft screen `screen`, telling them apart by node id."""
    screens = {screen_question("/summary#generate")}

    def answer(question: Question) -> Any:
        probability = screen if question.instructions in screens else criterion
        return PredicateAnswer(question.name, probability)

    return FakeBackend(default=answer)


def test_screen_node_compiled() -> None:
    graph = compile_schema(schema({"criteria": CRITERIA, "rubric": RUBRIC}), draft_screen=True)
    nodes = graph.nodes
    assert list(nodes)[-1] == "/summary#screen"
    screen = nodes["/summary#screen"]
    assert isinstance(screen, DecisionNode)
    assert (screen.kind, screen.option_source, screen.target) == (
        DecisionKind.PREDICATE,
        OptionSource.PREDICATE,
        "/summary",
    )
    assert screen.dependencies == {"/summary#generate"}
    assert screen.question == screen_question("/summary#generate")
    step = nodes["/summary#generate"]
    assert isinstance(step, StepNode)
    assert step.drafting is not None
    assert [c.rule for c in step.drafting.checks] == [
        CheckRule.CRITERION,
        CheckRule.CRITERION,
        CheckRule.RUBRIC,
        CheckRule.SCREEN,
    ]
    assert step.drafting.checks[-1] == Check("/summary#screen", SCREEN_REJECTION, CheckRule.SCREEN)
    union = {
        "type": "object",
        "required": ["reply"],
        "properties": {
            "reply": {
                "anyOf": [
                    {"title": "note", "type": "object", "properties": {"note": schema()["properties"]["summary"]}},
                    {"title": "flag", "type": "object", "properties": {"ok": {"type": "boolean", "description": "ok"}}},
                ]
            }
        },
    }
    ids = list(compile_schema(union, draft_screen=True).nodes)
    assert "/reply|c0/note#screen" in ids
    assert "/reply|c0/note#generate" in ids


def test_screen_rejects_v2_draft() -> None:
    backend = by_check(criterion=0.90, screen=0.90)
    result = resolve(backend, ScriptedLLM([V2_DRAFT]), config=screened(), redraft_budget=0)
    assert result.rejections == (Rejection("/summary", (SCREEN_REJECTION,), V2_DRAFT),)
    assert [u.reason for u in result.unresolved] == [UnresolvedReason.REDRAFT_EXHAUSTED]
    assert "summary" not in result.value
    assert result.decisions["/summary#screen@0"].selected is True
    assert result.decisions["/summary#criterion:0@0"].selected is True
    today = resolve(by_check(criterion=0.90, screen=0.90), ScriptedLLM([V2_DRAFT]), redraft_budget=0)
    assert today.value == {"summary": V2_DRAFT}  # without the screen, the self-claim is admitted


@pytest.mark.parametrize(
    ("criterion", "screen", "failing"),
    [
        (0.90, 0.10, ()),
        (0.90, 0.90, (SCREEN_REJECTION,)),
        (0.10, 0.10, tuple(CRITERIA)),
        (0.10, 0.90, (*CRITERIA, SCREEN_REJECTION)),
    ],
)
def test_screen_and_criteria_conjunction(criterion: float, screen: float, failing: tuple[str, ...]) -> None:
    result = resolve(by_check(criterion, screen), ScriptedLLM(["d"]), config=screened(), redraft_budget=0)
    assert ("summary" in result.value) is (failing == ())
    assert result.rejections == ((Rejection("/summary", failing, "d"),) if failing else ())


def test_redraft_prompt_names_screen() -> None:
    backend = by_check(criterion=0.90, screen=0.90)
    llm = ScriptedLLM([V2_DRAFT, "Refunds of $40 take 5 days."])
    resolve(backend, llm, config=screened())
    second = llm.calls[1][0]
    assert second[-1].content == redraft_prompt("summary", [SCREEN_REJECTION])
    assert second[-1].content == (
        "That draft does not meet these criteria: The draft speaks only about the source, not about itself or "
        "the requirements it meets. Write the summary again. Return only the value."
    )


def test_dry_run_with_options() -> None:
    declared = schema({"criteria": CRITERIA, "rubric": RUBRIC})
    run = asyncio.run(dry_run(declared, "/summary", "A refund of $40.", config=screened()))
    assert run.failing == ()
    assert run.questions[-1] == screen_question("/summary#generate")
    assert len(run.questions) == 4
    newer = asyncio.run(dry_run(declared, "/summary", "x", config=JevsonConfig(criterion_template="1.2.0")))
    assert newer.questions[0] == (
        "Judging only from the facts that `drafts./summary#generate` states about the source, does it meet this "
        "criterion: mentions the refund amount stated in the source?"
    )
    assert newer.failing == ()
    flagged = asyncio.run(dry_run(schema(), "/summary", "x", backend=by_check(0.9, 0.9), config=screened()))
    assert flagged.failing == (SCREEN_REJECTION,)


def test_screen_skips_ungated_field() -> None:
    graph = compile_schema(schema({}, note={"type": "string", "x-jevson": {"generate": {}}}), draft_screen=True)
    assert [n for n in graph.nodes if n.startswith("/note")] == ["/note#generate"]
    backend = passing()
    ungated = {"type": "object", "properties": {"note": {"type": "string", "x-jevson": {"generate": {}}}}}
    result = resolve(backend, ScriptedLLM(["anything"]), ungated, config=screened())
    assert result.value == {"note": "anything"}
    assert result.ungated == ("/note",)
    assert result.decided_by == {"/note": DecidedBy.LLM}
    assert backend.calls == []


@pytest.mark.parametrize("rule", list(CheckRule))
def test_each_rules_passing_answer_passes_its_own_check(rule: CheckRule) -> None:
    """The offline dry run answers each check with its rule's `passing`; that answer must pass the check,
    even when the rubric's minimum is its top level."""
    levels = tuple(Option(f"c{i}", f'"{name}"') for i, name in enumerate(["poor", "ok", "good"]))
    kind = DecisionKind.SCORE if rule is CheckRule.RUBRIC else DecisionKind.PREDICATE
    source = OptionSource.SCHEMA_RUBRIC if rule is CheckRule.RUBRIC else OptionSource.PREDICATE
    node = DecisionNode("/s#check", kind, "q", source, "/s", levels if rule is CheckRule.RUBRIC else ())
    question = Question("q7", kind, "q", node.options)
    answer = PASS_RULES[rule].passing(question)
    assert getattr(answer, "name", None) == "q7"
    drafting = Drafting("p", "s", checks=(Check(node.id, "c", rule),), rubric_minimum="c2")
    assert PASS_RULES[rule].passes(node, answer, drafting, 10)[1]
    expected = {
        CheckRule.CRITERION: PredicateAnswer("q7", 1.0),
        CheckRule.SCREEN: PredicateAnswer("q7", 0.0),
        CheckRule.RUBRIC: ScoreAnswer("q7", 2.0, {"c0": 0.0, "c1": 0.0, "c2": 1.0}),
    }
    assert answer == expected[rule]


def test_an_unanswered_check_does_not_stop_the_checks_after_it() -> None:
    first = DecisionNode("/s#criterion:0", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/s")
    second = DecisionNode("/s#criterion:1", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/s")
    checks = (Check(first.id, "a", CheckRule.CRITERION), Check(second.id, "b", CheckRule.CRITERION))
    nodes = {first.id: first, second.id: second}
    answers = {first.id: None, second.id: PredicateAnswer("q1", 0.1)}
    decisions, failing = judge(Drafting("p", "s", checks=checks), nodes, answers, 10)
    assert (list(decisions), failing) == ([second.id], ("a", "b"))


def test_dry_run_asks_its_field_only_with_the_configured_model() -> None:
    two = schema({"criteria": CRITERIA}, other={"type": "string", "x-jevson": {"generate": {"criteria": ["is short"]}}})
    backend = passing()
    run = asyncio.run(dry_run(two, "/summary", "d", backend=backend, config=JevsonConfig(model="m-test")))
    assert len(run.questions) == 2
    [call] = backend.calls
    assert call.model == "m-test"
    assert [q.instructions for q in call.questions] == list(run.questions)


def test_a_field_without_a_rubric_has_no_minimum_and_a_rubric_node_is_a_schema_rubric() -> None:
    plain = compile_schema(schema()).nodes["/summary#generate"]
    assert isinstance(plain, StepNode)
    assert plain.drafting is not None
    assert plain.drafting.rubric_minimum is None
    rubric = compile_schema(schema({"rubric": RUBRIC})).nodes["/summary#rubric"]
    assert isinstance(rubric, DecisionNode)
    assert rubric.option_source is OptionSource.SCHEMA_RUBRIC


# --- review round 1 (T48-6): pins the survivors PR-A's mutmut run had left in dry_run and _rubric --------


def test_the_dry_run_defaults_to_an_empty_source() -> None:
    run = asyncio.run(dry_run(schema(), "/summary", "d"))
    assert run.state == LevelState("", {"/summary#generate": "d"}).serialise()


def test_a_dry_run_of_an_ungated_field_returns_its_state_and_asks_nothing() -> None:
    run = asyncio.run(dry_run(schema({}), "/summary", "d", "s"))
    assert run == DryRun(LevelState("s", {"/summary#generate": "d"}).serialise(), (), ())


def test_a_dry_run_of_an_unknown_pointer_names_it() -> None:
    with pytest.raises(UsageError, match=r"^'/nope' is not a generative field of this schema$"):
        asyncio.run(dry_run(schema(), "/nope", "x"))


def test_a_rubric_without_a_declared_minimum_passes_from_its_lowest_level() -> None:
    node = rubric_node()
    drafting = Drafting("p", "summary", checks=(Check(node.id, "r", CheckRule.RUBRIC),))
    answer = ScoreAnswer("q0", 0.0, {"c0": 1.0, "c1": 0.0, "c2": 0.0})
    assert judge(drafting, {node.id: node}, {node.id: answer}, 10)[1] == ()
