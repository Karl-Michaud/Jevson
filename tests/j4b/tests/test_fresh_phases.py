"""H16: the configuration phase's first-draft gate (design §2.3 items 1-2; FEAS48-11)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from jevson import Rejection, compile_schema
from jevson.execute.drafting import TOOL_SCHEMA, malformed, messages
from jevson.llm.replay import ReplayLLM, replay_key
from jevson.types import Drafting, JSONValue, LLMResponse, Message, StepNode
from tests.j4b.fresh import judging
from tests.j4b.fresh.phases import FirstDraftGate, GateViolation, redraft_prompts
from tests.j4b.tests import fresh_data

SOURCE = "A document."


class Counting:
    def __init__(self) -> None:
        self.calls: list[tuple[Message, ...]] = []

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        self.calls.append(tuple(messages))
        return LLMResponse({"value": f"draft {len(self.calls)}"}, "", 1, 1)


def draftings(screen: bool = False) -> list[Drafting]:
    fields = [r for k, r in fresh_data.authored()["rset_fields.json"].items() if k.startswith("receipt.")]
    graph = compile_schema(judging.rset_schema(fields, "F0"), draft_screen=screen)
    return [n.drafting for n in graph.nodes.values() if isinstance(n, StepNode) and n.drafting is not None]


def gate(tmp_path: Path, screen: bool = False) -> tuple[FirstDraftGate, Counting, Drafting]:
    inner = Counting()
    first = draftings(screen)[0]
    recorder = ReplayLLM(inner, tmp_path, llm_id="m")
    asyncio.run(recorder.complete(messages(first, SOURCE, None), TOOL_SCHEMA))
    key = replay_key("m", messages(first, SOURCE, None), TOOL_SCHEMA)
    assert key is not None
    replayed = ReplayLLM(None, tmp_path, llm_id="m", replay_only=True)
    return FirstDraftGate(inner, replayed, [key], draftings(screen), llm_id="m"), inner, first


def test_h16_a_recorded_first_draft_replays_and_a_changed_source_raises(tmp_path: Path) -> None:
    g, inner, first = gate(tmp_path)
    calls = len(inner.calls)
    assert asyncio.run(g.complete(messages(first, SOURCE, None), TOOL_SCHEMA)).raw == ""
    assert len(inner.calls) == calls
    with pytest.raises(GateViolation):
        asyncio.run(g.complete(messages(first, SOURCE + " Changed.", None), TOOL_SCHEMA))


def test_h16_a_redraft_of_any_failing_subset_passes_to_the_inner_llm(tmp_path: Path) -> None:
    g, inner, first = gate(tmp_path, screen=True)
    for failing in (
        [c.text for c in first.checks][:1],
        [c.text for c in first.checks][-1:],
        [c.text for c in first.checks],
    ):
        rejection = Rejection("/total", tuple(failing), "draft 1")
        asyncio.run(g.complete(messages(first, SOURCE, rejection), TOOL_SCHEMA))
    assert len(inner.calls) == 1 + 3


def test_h16_a_malformed_first_drafts_redraft_passes(tmp_path: Path) -> None:
    g, inner, first = gate(tmp_path)
    rejection = Rejection("/total", (malformed(first.max_draft_chars),), "{")
    asyncio.run(g.complete(messages(first, SOURCE, rejection), TOOL_SCHEMA))
    assert len(inner.calls) == 2


def test_h16_a_redraft_naming_a_text_that_is_not_one_of_the_fields_checks_raises(tmp_path: Path) -> None:
    g, _, first = gate(tmp_path)
    rejection = Rejection("/total", ("Some other requirement",), "draft 1")
    with pytest.raises(GateViolation):
        asyncio.run(g.complete(messages(first, SOURCE, rejection), TOOL_SCHEMA))
    assert len(redraft_prompts(first)) == 2 ** len(first.checks) - 1 + 1
