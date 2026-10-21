"""The configuration phase's first-draft gate (design §2.3 items 1-2; plan §4.1 `phases.py`, FEAS48-11).

A drafting request whose `replay_key` is one of the drafting phase's recorded keys is served from that recording
with `replay_only=True`, so a missing first draft raises `replay_miss` and never draws a new one. Any other request
must be a redraft: three messages, the last being the executor's own redraft prompt (`redraft_prompt`) over a
failing list that is a subset of the field's checks or exactly `[malformed(max_draft_chars)]`; anything else
raises. The strings are the library's own, imported, never copied (plan §11 D18).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

from jevson.compile.questions import redraft_prompt
from jevson.execute.drafting import malformed
from jevson.llm.replay import ReplayLLM, replay_key
from jevson.protocols import LLM
from jevson.types import Drafting, JSONValue, LLMResponse, Message


class GateViolation(Exception):
    """A drafting request that is neither a recorded first draft nor a redraft the executor would send."""


def _subsets(items: Sequence[str]) -> Iterable[tuple[str, ...]]:
    for mask in range(1, 2 ** len(items)):
        yield tuple(text for i, text in enumerate(items) if mask >> i & 1)


def redraft_prompts(drafting: Drafting) -> set[str]:
    """Every redraft prompt the executor can send for this field: any non-empty subset of its checks, in
    declared order, or the malformed-draft text."""
    checks = [c.text for c in drafting.checks]
    prompts = {redraft_prompt(drafting.label, failing) for failing in _subsets(checks)}
    return prompts | {redraft_prompt(drafting.label, [malformed(drafting.max_draft_chars)])}


class FirstDraftGate:
    """First drafts replayed from the drafting phase; redrafts passed to `inner`; anything else refused."""

    def __init__(
        self, inner: LLM, recorded: ReplayLLM, first_keys: Iterable[str], draftings: Iterable[Drafting], *, llm_id: str
    ) -> None:
        self.inner, self.recorded, self.llm_id = inner, recorded, llm_id
        self.first_keys = frozenset(first_keys)
        self.redrafts: set[str] = set()
        for drafting in draftings:
            self.redrafts |= redraft_prompts(drafting)

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        key = replay_key(self.llm_id, messages, tool_schema)
        if key in self.first_keys:
            return await self.recorded.complete(messages, tool_schema)
        if len(messages) == 3 and messages[2].content in self.redrafts:
            return await self.inner.complete(messages, tool_schema)
        raise GateViolation("a drafting request that is neither a recorded first draft nor a redraft")
