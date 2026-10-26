"""The two phases of an attempt and the configuration phase's first-draft gate (design §2.3, §6.2-§6.3;
plan §4.1 `phases.py`, §7 "Phases"; FEAS48-11, FEAS48-R8-1).

**Clients.** Decisions go through `SingleFlightBackend(CachingBackend(DecisionsBackend(transport=metered)))` and
drafting through `SingleFlightLLM(ReplayLLM(OpenAIChatLLM(max_completion_tokens=2048, transport=metered)))`, both over
one `MeteredTransport(PinnedWire(transport))` and recording under the phase directory. **Drafting phase.** Every R-set
first draft is drawn once, built exactly as the executor builds it (`messages(step.drafting, doc.text, None)`,
`TOOL_SCHEMA`), in batches of 10 documents, each batch checked against the cap first. **Configuration phase.** Units in
the pinned batches; each unit re-queued under `requeue.run_unit`, and returned as judged (`admission.Judged`): what a
unit's outcome is (a flip, an admission, an R-set draft) is `admission.record`'s, frozen, never this module's.

**The first-draft gate.** A drafting request whose `replay_key` is one of the drafting phase's recorded keys is
served from that recording with `replay_only=True`, so a missing first draft raises `replay_miss` and never
draws a new one. Any other request must be a redraft: three messages, the last being the executor's own redraft
prompt (`redraft_prompt`) over a failing list that is a subset of the field's checks or exactly
`[malformed(max_draft_chars)]`; anything else raises. The strings are the library's own, imported, never
copied (plan §11 D18).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from jevson import CachingBackend, DecisionsBackend, LLMError, Result, compile_schema
from jevson.compile.questions import redraft_prompt
from jevson.execute.drafting import TOOL_SCHEMA, malformed, messages
from jevson.llm.replay import ReplayLLM, replay_key
from jevson.protocols import LLM
from jevson.types import Drafting, JSONValue, LLMResponse, Message, StepNode
from tests.integration.openai_chat import MODEL, OpenAIChatLLM
from tests.j4b import redraft
from tests.j4b.fresh import admission, arms, gates, judging, packing, requeue
from tests.j4b.fresh.constants import MAX_COMPLETION_TOKENS
from tests.j4b.fresh.inflight import SingleFlightBackend, SingleFlightLLM
from tests.j4b.fresh.metering import MeteredTransport
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.fresh.wire import PinnedWire
from tests.j4b.fresh.workload import Workload

Sleep = Callable[[float], Awaitable[object]]


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


# --- clients -------------------------------------------------------------------------------------------


@dataclass
class Clients:
    backend: SingleFlightBackend
    drafting: SingleFlightLLM
    llm_dir: Path


def clients(
    phase_dir: Path, ledger: SpendLedger, *, key: str, transport: httpx.AsyncBaseTransport, run_attempt: int,
    sleep: Sleep,
) -> Clients:  # fmt: skip
    """The metered, recorded, single-flight clients of one phase; `PinnedWire` is innermost, so no request off the
    pinned parameters is sent (RC3-1)."""
    metered = MeteredTransport(PinnedWire(transport, ledger), ledger, run_attempt=run_attempt)
    decisions = DecisionsBackend(api_key=key, transport=metered, sleep=sleep)
    cached = CachingBackend(decisions, phase_dir / "decisions")
    chat = OpenAIChatLLM(key, max_completion_tokens=MAX_COMPLETION_TOKENS, transport=metered, sleep=sleep)
    recorded = ReplayLLM(chat, phase_dir / "llm", llm_id=MODEL)
    return Clients(SingleFlightBackend(cached), SingleFlightLLM(recorded, MODEL), phase_dir / "llm")


def _no_network(request: httpx.Request) -> httpx.Response:
    raise AssertionError(f"a replay sent a request to {request.url}")


def replay_clients(phase_dir: Path) -> Clients:
    """The clients of a replay: records only (`replay_only=True`), so a miss raises and nothing is ever sent."""
    decisions = DecisionsBackend(api_key="replay-only", transport=httpx.MockTransport(_no_network))
    cached = CachingBackend(decisions, phase_dir / "decisions", replay_only=True)
    recorded = ReplayLLM(None, phase_dir / "llm", llm_id=MODEL, replay_only=True)
    return Clients(SingleFlightBackend(cached), SingleFlightLLM(recorded, MODEL), phase_dir / "llm")


def draftings(fields: Sequence[Mapping[str, Any]], config: tuple[str, str] = ("L0", "F0")) -> list[Drafting]:
    """Each field's compiled drafting under `config` (its checks carry the configuration's screen)."""
    options = arms.LIBRARY_ARMS[config[0]]
    graph = compile_schema(judging.rset_schema(fields, config[1]), criterion_template=options.criterion_template,
                           draft_screen=options.draft_screen)  # fmt: skip
    return [n.drafting for n in graph.nodes.values() if isinstance(n, StepNode) and n.drafting is not None]


# --- the drafting phase ---------------------------------------------------------------------------------


def first_draft_requests(doc: redraft.Document, fields: Sequence[Mapping[str, Any]]) -> list[tuple[Message, ...]]:
    return [messages(d, doc.text, None) for d in draftings(fields)]


def first_keys(w: Workload) -> frozenset[str]:
    """The `replay_key` of every first draft of the phase: what the drafting phase records."""
    requests = (m for d in w.documents.values() for m in first_draft_requests(d, w.fields[d.domain]))
    return frozenset(k for m in requests if (k := replay_key(MODEL, m, TOOL_SCHEMA)) is not None)


async def drafting_phase(
    c: Clients, ledger: SpendLedger, w: Workload,
    *, bound: Callable[[str], int], sleep: Sleep, after_batch: Callable[[], None] = lambda: None,
) -> frozenset[str]:  # fmt: skip
    """Draw every first draft once, a batch of 10 documents at a time, each batch checked against the cap first;
    return the recorded keys."""
    batches = packing.drafting_batches(list(w.documents))
    for index, batch in enumerate(batches):
        requests = {d: first_draft_requests(w.documents[d], w.fields[w.documents[d].domain]) for d in batch}
        if not gates.batch_fits(ledger, [bound(d) for d in batch]):
            raise requeue.CapStop(f"drafting batch {index} of {len(batches)} does not fit under the cap")

        async def draw(doc_id: str, requests: dict[str, list[tuple[Message, ...]]] = requests) -> None:
            try:
                await asyncio.gather(*(c.drafting.complete(m, TOOL_SCHEMA) for m in requests[doc_id]))
            except LLMError:
                raise
            except Exception as failure:  # as the executor wraps a drafting failure (`executor.py` `_draft`)
                raise LLMError("llm_exception", f"{doc_id}: {type(failure).__name__}", Result({}, False)) from failure

        await asyncio.gather(*(requeue.run_unit(d, lambda d=d: draw(d), ledger, sleep) for d in batch))
        after_batch()
    await c.drafting.drain()
    return first_keys(w)


# --- the configuration phase ----------------------------------------------------------------------------


async def run_unit(c: Clients, w: Workload, first_keys: frozenset[str], unit: Unit) -> admission.Judged:
    """One (case, configuration) pair, judged; `admission.record` (frozen) turns it into the recorded outcome."""
    config = arms.LIBRARY_ARMS[unit.arm]
    if unit.set_name == "rset":
        doc = w.documents[unit.key]
        fields = w.fields[doc.domain]
        steps = draftings(fields, unit.config)
        recorded = ReplayLLM(None, c.llm_dir, llm_id=MODEL, replay_only=True)
        gate = FirstDraftGate(c.drafting, recorded, first_keys, steps, llm_id=MODEL)
        result = await judging.judge_document(c.backend, gate, doc.text, fields=fields, config=config, form=unit.form)
        return admission.Judged("rset", result, None, steps, [str(f["pointer"]) for f in fields])
    case = w.cases[unit.set_name][unit.key]
    if unit.set_name == "pset":
        case = judging.pset_case(case, unit.form)
    return admission.Judged(unit.set_name, await judging.judge_case(c.backend, case, config, unit.set_name), case)


async def configuration_phase(
    c: Clients, ledger: SpendLedger, w: Workload, first_keys: frozenset[str],
    *, bound: Callable[[Unit], int], sleep: Sleep, after_batch: Callable[[], None] = lambda: None,
) -> dict[Unit, admission.Judged]:  # fmt: skip
    """Every unit, one batch of at most 10 in flight, each batch checked against the cap first; `after_batch`
    runs the guards (the model-string check) between batches."""
    outcomes: dict[Unit, admission.Judged] = {}
    batches = packing.configuration_batches(w.units)
    for index, batch in enumerate(batches):
        if not gates.batch_fits(ledger, [bound(u) for u in batch]):
            raise requeue.CapStop(f"configuration batch {index} of {len(batches)} does not fit under the cap")
        done = await asyncio.gather(
            *(requeue.run_unit(f"{u}", lambda u=u: run_unit(c, w, first_keys, u), ledger, sleep) for u in batch)
        )
        outcomes.update(zip(batch, done, strict=True))
        after_batch()
    await c.backend.drain()
    await c.drafting.drain()
    return outcomes


def model_strings(ledger: SpendLedger, run_attempt: int) -> dict[str, set[str]]:
    """Each endpoint's returned `model` strings in this attempt, from the settle records (plan §11 D6)."""
    found: dict[str, set[str]] = {"decisions": set(), "chat": set()}
    for s in ledger.settles():
        if s.run_attempt == run_attempt and s.status == 200 and s.model is not None:
            found[s.endpoint].add(s.model)
    return found
