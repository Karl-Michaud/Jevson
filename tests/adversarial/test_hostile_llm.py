"""PLAN §4.1 with Phase 4's owner: the central property over generated schemas x every hostile LLM.

Generated schemas from the supported subset gain generative fields (0-3 criteria, an optional
rubric, a small `max_draft_chars`); the LLM draws a behaviour per call from every hostile LLM
behaviour of PLAN §4.2, valid drafts, repeats, and the [P7] injected drafts; the backend is the
hostile Decisions transport of `test_central_property`. DESIGN §6.1: a complete valid `Result`, a
`Result` naming every hole, or a typed exception. Never a fourth outcome.

The [P7] variants are also checked structurally on the fake backend: an injected draft sits beside a
clean one in the keyed multi-draft layout, as an opaque string value under its own key, and each
field's verdict follows only the backend's answers to that field's questions. How far a live model is
steered by them is the J4b injection regression.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from jevson import FakeBackend, Jevson, JevsonConfig, Result, Unresolved, UnresolvedReason
from jevson.types import LLMResponse, PredicateAnswer, Question
from tests.adversarial.hostile_backend import backend
from tests.adversarial.hostile_llm import HOSTILE, INJECTED_DRAFTS, ScriptedLLM, tool
from tests.adversarial.test_central_property import check, hostile, sources
from tests.property.test_compiler_properties import supported
from tests.unit.recording_backend import check_isolation, draft_reads, key

VALID = ["Refunds take 5 days.", "A refund of $40 was issued.", ""]


@st.composite
def generative_schemas(draw: st.DrawFn) -> dict[str, Any]:
    schema, _ = draw(supported())
    properties = dict(schema["properties"])
    for i in range(draw(st.integers(1, 3))):
        generate: dict[str, Any] = {"criteria": [f"criterion {i}.{c}" for c in range(draw(st.integers(0, 3)))]}
        if draw(st.booleans()):
            generate["rubric"] = {"description": f"quality {i}", "levels": ["poor", "ok", "good"], "minimum": "ok"}
        if draw(st.booleans()):
            generate["max_draft_chars"] = draw(st.sampled_from([1, 30, 4000]))
        properties[f"gen{i}"] = {"type": "string", "x-jevson": {"generate": generate}}
    required = list(properties) if draw(st.booleans()) else []
    return {"type": "object", "properties": properties, "required": required}


class DrawnLLM:
    """Draws a fresh behaviour for every call."""

    def __init__(self, data: st.DataObject) -> None:
        self.data = data
        self.last: Any = tool(VALID[0])

    async def complete(self, messages: Any, tool_schema: Any) -> LLMResponse:
        kind = self.data.draw(st.sampled_from(["hostile", "valid", "repeat", "injected"]))
        if kind == "hostile":
            behaviour = HOSTILE[self.data.draw(st.sampled_from(sorted(HOSTILE)))]
        elif kind == "valid":
            behaviour = tool(self.data.draw(st.sampled_from(VALID)))
        elif kind == "injected":
            behaviour = tool(INJECTED_DRAFTS[self.data.draw(st.sampled_from(sorted(INJECTED_DRAFTS)))])
        else:
            behaviour = self.last
        self.last = behaviour
        return await ScriptedLLM([behaviour]).complete(messages, tool_schema)


@settings(derandomize=True, database=None, max_examples=200, deadline=None,
          suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])  # fmt: skip
@given(generative_schemas(), sources, st.data(), st.integers(0, 2), st.booleans())
def test_the_central_property_holds_over_generated_schemas_and_hostile_llms(
    schema: dict[str, Any], source: str, data: st.DataObject, redrafts: int, raising: bool
) -> None:
    config = JevsonConfig(step_timeout_s=0.01, raise_on_unresolved_required=raising, max_questions_per_request=3)
    jevson = Jevson(backend(hostile(data), transport_retries=0), llm=DrawnLLM(data), config=config)
    outcome: Result | Exception
    try:
        outcome = asyncio.run(jevson.aresolve(schema, source, redraft_budget=redrafts))
    except Exception as error:  # the property: every exception is one of the hierarchy's
        outcome = error
    event(getattr(outcome, "code", type(outcome).__name__))
    check(schema, outcome)
    if isinstance(outcome, Result):
        for pointer, value in outcome.value.items():
            if pointer.startswith("gen"):
                assert isinstance(value, str), "an admitted draft is always a string"
        for rejection in outcome.rejections:
            assert isinstance(rejection.draft, str)
            assert rejection.criteria


def test_injected_drafts_stay_opaque_values_beside_a_clean_draft_and_verdicts_follow_the_backend() -> None:
    criteria = {"type": "string", "x-jevson": {"generate": {"criteria": ["mentions the refund amount"]}}}
    schema = {"type": "object", "properties": {"injected": criteria, "clean": criteria}}
    for name, text in INJECTED_DRAFTS.items():
        llm = ScriptedLLM([text, "Nothing about money."])

        def verdict(question: Question) -> PredicateAnswer:
            return PredicateAnswer(question.name, 0.1)  # both drafts fail their criterion, whatever they say

        fake = FakeBackend(default=verdict)
        result = asyncio.run(Jevson(fake, llm=llm).aresolve(schema, "Refund: $40.", redraft_budget=0))
        state = json.loads(fake.calls[0].state)
        assert state["drafts"] == {"/injected#generate": text, "/clean#generate": "Nothing about money."}, name
        assert len(fake.calls[0].questions) == 2
        reads = draft_reads(schema)
        assert all(reads[key(q)] is not None for q in fake.calls[0].questions), name  # per the compiled graph
        assert result.unresolved == (
            Unresolved("/clean", UnresolvedReason.REDRAFT_EXHAUSTED, detail="0 redraft(s)"),
            Unresolved("/injected", UnresolvedReason.REDRAFT_EXHAUSTED, detail="0 redraft(s)"),
        ), name
        assert [r.draft for r in result.rejections] == [text, "Nothing about money."]


def test_injected_drafts_never_reach_a_bounded_field_of_the_same_level() -> None:
    """DESIGN §5.2: a bounded field beside the [P7] drafts is asked over the source-only state."""
    criteria = {"type": "string", "x-jevson": {"generate": {"criteria": ["mentions the refund amount"]}}}
    refunded = {"type": "boolean", "description": "a refund was issued"}
    schema = {"type": "object", "properties": {"injected": criteria, "clean": criteria, "refunded": refunded}}
    for name, text in INJECTED_DRAFTS.items():
        llm = ScriptedLLM([text, "Nothing about money."])
        fake = FakeBackend(default=FakeBackend.predicate(0.1))
        result = asyncio.run(Jevson(fake, llm=llm).aresolve(schema, "Refund: $40.", redraft_budget=0))
        reads = draft_reads(schema)
        check_isolation([(c.state, c.questions) for c in fake.calls], reads)
        bounded = [c for c in fake.calls if any(reads[key(q)] is None for q in c.questions)]
        assert [json.loads(c.state) for c in bounded] == [{"source": "Refund: $40."}], name
        assert [len(c.questions) for c in bounded] == [1], name
        assert result.value["refunded"] is False, name  # the backend's answer, whatever the drafts say


def test_every_hostile_behaviour_alone_ends_in_one_of_the_three_outcomes() -> None:
    criteria = {"type": "string", "x-jevson": {"generate": {"criteria": ["c"], "max_draft_chars": 50}}}
    schema = {"type": "object", "properties": {"s": criteria}, "required": ["s"]}
    for name, behaviour in HOSTILE.items():
        llm = ScriptedLLM([behaviour])
        jevson = Jevson(FakeBackend(default=FakeBackend.predicate(0.9)), llm=llm,
                        config=JevsonConfig(step_timeout_s=0.01))  # fmt: skip
        outcome: Result | Exception
        try:
            outcome = asyncio.run(jevson.aresolve(schema, "src"))
        except Exception as error:
            outcome = error
        check(schema, outcome)
        if name.startswith(("raises", "never")):
            assert not isinstance(outcome, Result), name
        elif name == "nonsense token counts":
            assert isinstance(outcome, Result)
            assert outcome.value == {"s": "refunds take 5 days"}
        else:
            assert isinstance(outcome, Result), name
            assert outcome.unresolved[0].reason is UnresolvedReason.REDRAFT_EXHAUSTED, name
            assert all(len(r.draft) <= 50 for r in outcome.rejections), name
