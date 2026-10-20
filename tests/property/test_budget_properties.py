"""Budget: every request that is sent fits both limits (DESIGN §8.2).

Preflight and splitting keep each request group, bounded and adjudication alike, within
`max_input_tokens` and `max_questions_per_request`, whatever a draft up to `max_draft_chars` holds
(control characters are the worst case for the JSON state). The property draws boolean, enum, ordinal
and multi-label array fields, generative fields with criteria and an optional rubric, an optional
union whose branch holds a bounded and a generative field (fan-out or level by level), and redraft
rounds, each redraft new text that is adjudicated again. `budget.split` keeps order and limits.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from itertools import pairwise
from typing import Any

from hypothesis import HealthCheck, event, given, settings
from hypothesis import strategies as st

from jevson import FakeBackend, Jevson, JevsonConfig, LLMResponse, Message, compile_schema
from jevson.errors import PreflightError
from jevson.execute import budget
from jevson.execute.state import LevelState
from jevson.types import Answer, DecisionKind, DecisionNode, Question, StepNode

SETTINGS = settings(
    max_examples=300,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


BOUNDED = (
    lambda i: {"type": "boolean", "description": f"flag {i} holds"},
    lambda i: {"enum": ["alpha", "beta", "gamma"], "description": f"kind {i}"},
    lambda i: {
        "type": "integer",
        "minimum": 1,
        "maximum": 4,
        "x-jevson": {"ordinal": True},
        "description": f"level {i}",
    },
    lambda i: {"type": "array", "items": {"enum": ["x", "y", "z"]}, "description": f"tags {i}"},
)
RUBRIC = {"description": "how faithful it is", "levels": ["poor", "fair", "good"], "minimum": "good"}


def generative(name: str, max_chars: int, criteria: int, rubric: bool) -> dict[str, Any]:
    generate: dict[str, Any] = {
        "criteria": [f"{name} meets {c}" for c in range(criteria)],
        "max_draft_chars": max_chars,
    }
    return {"type": "string", "x-jevson": {"generate": generate | ({"rubric": RUBRIC} if rubric else {})}}


@st.composite
def schemas(draw: st.DrawFn, max_chars: int) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for i, kind in enumerate(draw(st.lists(st.integers(0, len(BOUNDED) - 1), max_size=4))):
        props[f"b{i}"] = BOUNDED[kind](i)
    for i in range(draw(st.integers(1, 3))):
        props[f"g{i}"] = generative(f"g{i}", max_chars, draw(st.integers(1, 3)), draw(st.booleans()))
    if draw(st.booleans()):
        left = {"kind": {"const": "l"}, "lb": {"type": "boolean", "description": "left holds"},
                "lg": generative("lg", max_chars, draw(st.integers(1, 2)), draw(st.booleans()))}  # fmt: skip
        right = {"kind": {"const": "r"}, "rb": {"enum": ["p", "q"], "description": "right kind"}}
        props["u"] = {"anyOf": [obj(left, "L"), obj(right, "R")], "description": "the shape"}
    return obj(props)


def obj(props: Mapping[str, Any], title: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "object", "properties": dict(props), "required": sorted(props)}
    return out | ({"title": title} if title else {})


class Worst:
    """Drafts at `max_draft_chars` of `ch`; each redraft swaps one character for its neighbour, so it is
    new text of the same worst-case size."""

    def __init__(self, ch: str, n: int) -> None:
        self.ch, self.n, self.calls = ch, n, 0

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, object] | None) -> LLMResponse:
        self.calls += 1
        text = list(self.ch * self.n)
        text[self.calls % self.n] = chr(ord(self.ch) + self.calls % 2)
        return LLMResponse({"value": "".join(text)}, "", 1, 1)


def answers(probability: float) -> Callable[[Question], Answer]:
    """`probability` for every predicate, and the first option of every choice and rubric score."""

    def answer(question: Question) -> Answer:
        if question.options:
            return FakeBackend.select(question.options[0].id, 0.9)(question)
        return FakeBackend.predicate(probability)(question)

    return answer


def tight(schema: dict[str, Any], fanout: bool, source: str, slack: int) -> int:
    """`max_input_tokens` at which the largest question, its draft included, just fits beside the source."""
    graph = compile_schema(schema, union_fanout=fanout)
    steps = {n.id: n for n in graph.nodes.values() if isinstance(n, StepNode)}
    nodes = [n for n in graph.nodes.values() if isinstance(n, DecisionNode)]
    sized = budget.with_drafts(
        budget.declared_tokens, {n.id: steps[d] for n in nodes for d in n.dependencies if d in steps}
    )
    return budget.estimate_tokens(LevelState(source).serialise()) + max(sized(n) for n in nodes) + slack


@SETTINGS
@given(
    data=st.data(),
    max_chars=st.sampled_from([1, 10, 50]),
    ch=st.sampled_from(["\x00", "a", "\U0001f600"]),
    source=st.text(max_size=40),
    slack=st.integers(0, 12),
    per=st.integers(1, 5),
    fanout=st.booleans(),
    redrafts=st.integers(0, 2),
    probability=st.sampled_from([0.1, 0.9]),
)
def test_every_sent_request_fits_both_limits(
    *, data: st.DataObject, max_chars: int, ch: str, source: str, slack: int, per: int, fanout: bool,
    redrafts: int, probability: float,
) -> None:  # fmt: skip
    s = data.draw(schemas(max_chars))
    limit = tight(s, fanout, source, slack)
    fake = FakeBackend(default=answers(probability))
    config = JevsonConfig(max_input_tokens=limit, max_questions_per_request=per, union_fanout=fanout)
    try:
        result = asyncio.run(
            Jevson(fake, llm=Worst(ch, max_chars), config=config).aresolve(s, source, redraft_budget=redrafts)
        )
    except PreflightError:
        return
    event(f"redraft rounds ran: {result.cost.redrafts > 0}")
    for call in fake.calls:
        real = budget.estimate_tokens(call.state) + sum(budget.question_tokens(q) for q in call.questions)
        event(f"gap to the limit: {min(limit - real, 2)}")
        assert len(call.questions) <= per
        assert real <= limit, f"a request of {real} estimated tokens went out under max_input_tokens={limit}"


@SETTINGS
@given(
    sizes=st.lists(st.integers(1, 50), max_size=12),
    room=st.integers(50, 200),
    per=st.integers(1, 5),
    source=st.text(max_size=20),
)
def test_split_keeps_order_and_both_limits_and_packs_greedily(
    *, sizes: list[int], room: int, per: int, source: str
) -> None:
    state = LevelState(source).serialise()
    config = JevsonConfig(max_input_tokens=budget.estimate_tokens(state) + room, max_questions_per_request=per)
    questions = [Question(f"q{i}", DecisionKind.PREDICATE, f"statement {i}") for i in range(len(sizes))]
    cost = {q.name: size for q, size in zip(questions, sizes, strict=True)}
    chunks = budget.split(state, questions, cost, config)
    assert [q for chunk in chunks for q in chunk] == questions  # order kept, nothing lost or repeated
    assert all(chunks), "an empty chunk"
    for chunk in chunks:
        assert len(chunk) <= per
        assert sum(cost[q.name] for q in chunk) <= room
    for chunk, after in pairwise(chunks):  # a new chunk starts only when one limit is hit
        assert len(chunk) == per or sum(cost[q.name] for q in chunk) + cost[after[0].name] > room
