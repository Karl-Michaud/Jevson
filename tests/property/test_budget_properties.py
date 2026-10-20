"""Budget: every request that is sent fits both limits (DESIGN §8.2).

Preflight and splitting keep each request group, bounded and adjudication alike, within
`max_input_tokens` and `max_questions_per_request`, whatever a draft up to `max_draft_chars` holds
(control characters are the worst case for the JSON state). `budget.split` keeps order and limits.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from itertools import pairwise
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from jevson import FakeBackend, Jevson, JevsonConfig, LLMResponse, Message, compile_schema
from jevson.errors import PreflightError
from jevson.execute import budget
from jevson.execute.state import LevelState
from jevson.types import DecisionKind, DecisionNode, Question, StepNode

SETTINGS = settings(
    max_examples=300,
    deadline=None,
    derandomize=True,
    database=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)


def schema(bounded: int, generative: int, max_chars: int, criteria: int) -> dict[str, Any]:
    props: dict[str, Any] = {f"b{i}": {"type": "boolean", "description": f"flag {i} holds"} for i in range(bounded)}
    for i in range(generative):
        props[f"g{i}"] = {
            "type": "string",
            "x-jevson": {
                "generate": {"criteria": [f"criterion {i}.{c}" for c in range(criteria)], "max_draft_chars": max_chars}
            },
        }
    return {"type": "object", "properties": props, "required": sorted(props)}


class Worst:
    def __init__(self, ch: str, n: int) -> None:
        self.text = ch * n

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, object] | None) -> LLMResponse:
        return LLMResponse({"value": self.text}, "", 1, 1)


@SETTINGS
@given(
    bounded=st.integers(0, 4),
    generative=st.integers(1, 3),
    max_chars=st.sampled_from([1, 10, 50]),
    criteria=st.integers(1, 3),
    ch=st.sampled_from(["\x00", "a", "\U0001f600"]),
    source=st.text(max_size=40),
    slack=st.integers(0, 12),
    per=st.integers(1, 5),
)
def test_every_sent_request_fits_both_limits(
    *, bounded: int, generative: int, max_chars: int, criteria: int, ch: str, source: str, slack: int, per: int
) -> None:
    s = schema(bounded, generative, max_chars, criteria)
    graph = compile_schema(s)
    steps = {n.id: n for n in graph.nodes.values() if isinstance(n, StepNode)}
    checks = {
        n.id: steps[d]
        for n in graph.nodes.values()
        if isinstance(n, DecisionNode)
        for d in n.dependencies
        if d in steps
    }
    sized = budget.with_drafts(budget.declared_tokens, checks)
    biggest = max(sized(n) for n in graph.nodes.values() if isinstance(n, DecisionNode))
    limit = (
        budget.estimate_tokens(LevelState(source).serialise()) + biggest + slack
    )  # tight: the largest question just fits
    fake = FakeBackend(default=FakeBackend.predicate(0.9))
    config = JevsonConfig(max_input_tokens=limit, max_questions_per_request=per)
    try:
        asyncio.run(Jevson(fake, llm=Worst(ch, max_chars), config=config).aresolve(s, source, redraft_budget=0))
    except PreflightError:
        return
    for call in fake.calls:
        real = budget.estimate_tokens(call.state) + sum(budget.question_tokens(q) for q in call.questions)
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
