"""Per-unit reservations and the requests behind them, built offline (design §6.3; plan §7 "dryrun", §11 D10;
FEAS48-7, FEAS48-8, FEAS48-R10-3).

Every unit is run once through Jevson against a recording `FakeBackend`, so its requests are the ones the run
will send, built by the library itself; each is encoded as `DecisionsBackend` encodes it and measured as `httpx`
sends it, and `metering.request_bound` prices it exactly as `MeteredTransport` will. The I-set, [P7] and P-set
send fixed drafts with no redraft, so their bounds are exact. An R-set unit is run with every draft rejected (the
most requests) and every draft a placeholder of a few characters; each draft it carries is then reserved at
`max_draft_chars` x 7 bytes (decision side) and each prior draft a redraft quotes at `max_draft_chars` x 6 (chat
side), or at the design's 4 bytes for R_max as the design states it. A drafting unit is one document's three
first drafts, known exactly.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx

from jevson import BackendResponse, DecisionKind, FakeBackend, LLMResponse, Message, Question
from jevson.execute.drafting import TOOL_SCHEMA
from jevson.types import JSONValue
from tests.integration.openai_chat import URL as CHAT_URL
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b.fresh import arms, costs, judging, metering, phases
from tests.j4b.fresh.constants import MAX_COMPLETION_TOKENS, PRICE
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.workload import Workload

DECISIONS_URL = "https://api.openai.com/v1/decisions"
MAX_DRAFT_CHARS = 4000
"""`Drafting.max_draft_chars` at the default every R-set field uses (checked against each field's drafting)."""


def wire_question(index: int, question: Question) -> dict[str, Any]:
    """A question as `DecisionsBackend` sends it."""
    wire: dict[str, Any] = {"type": question.kind.value, "name": f"q{index}", "instructions": question.instructions}
    if question.kind is DecisionKind.CHOICE:
        wire["choices"] = [{"value": o.id, "description": o.description} for o in question.options]
    elif question.kind is DecisionKind.SCORE:
        wire["levels"] = [{"label": o.id, "description": o.description} for o in question.options]
    return wire


def wire_body(url: str, payload: Mapping[str, Any]) -> bytes:
    """The bytes `httpx` sends for `payload` (its own JSON encoding)."""
    return httpx.Request("POST", url, json=payload).content


@dataclass(frozen=True)
class DecisionRequest:
    body: bytes
    questions: tuple[tuple[str, str], ...]
    """(kind, instructions) per question, for the layout check (H23)."""
    options: int
    drafts: int
    """The drafts the request's state carries (each reserved at its maximum for an R-set unit)."""

    @property
    def key(self) -> bytes:
        return self.body


@dataclass
class Recorder:
    """A `Backend` that records each request's wire body and answers every predicate at `probability`."""

    probability: float
    requests: list[DecisionRequest] = field(default_factory=list[DecisionRequest])

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        payload = {"model": model, "input": state, "questions": [wire_question(i, q) for i, q in enumerate(questions)]}
        options = sum(2 if q.kind is DecisionKind.PREDICATE else len(q.options) for q in questions)
        drafts = len(json.loads(state).get("drafts", {}))
        kinds = tuple((q.kind.value, q.instructions) for q in questions)
        self.requests.append(DecisionRequest(wire_body(DECISIONS_URL, payload), kinds, options, drafts))
        return await FakeBackend(default=FakeBackend.predicate(self.probability)).ask(state, questions, model)


@dataclass
class PlaceholderDrafts:
    """An `LLM` that drafts a short distinct placeholder (`d1`, `d2`, ...; distinct, because a draft identical to
    one already adjudicated is not adjudicated again) and records each request's messages."""

    calls: list[tuple[Message, ...]] = field(default_factory=list[tuple[Message, ...]])

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        self.calls.append(tuple(messages))
        return LLMResponse({"value": f"d{len(self.calls)}"}, "", 0, 0)


def chat_body(messages: Sequence[Message]) -> bytes:
    body = OpenAIChatLLM("k", max_completion_tokens=MAX_COMPLETION_TOKENS).body(messages, TOOL_SCHEMA)
    return wire_body(CHAT_URL, body)


@dataclass(frozen=True)
class UnitRequests:
    decisions: tuple[DecisionRequest, ...]
    redrafts: tuple[bytes, ...]
    """Chat bodies of the unit's redrafts, each quoting a placeholder prior draft."""


def unit_requests(w: Workload, unit: Unit) -> UnitRequests:
    """The requests one unit sends: exact for the first-draft sets; for an R-set unit, every draft rejected."""
    config = arms.LIBRARY_ARMS[unit.arm]
    if unit.set_name == "rset":
        doc = w.documents[unit.key]
        fields = w.fields[doc.domain]
        if any(d.max_draft_chars != MAX_DRAFT_CHARS for d in phases.draftings(fields, unit.config)):
            raise ValueError("an R-set field's max_draft_chars differs from the reserved maximum")
        recorder, llm = Recorder(0.0), PlaceholderDrafts()
        asyncio.run(judging.judge_document(recorder, llm, doc.text, fields=fields, config=config, form=unit.form))
        redrafts = tuple(chat_body(m) for m in llm.calls if len(m) == 3)
        return UnitRequests(tuple(recorder.requests), redrafts)
    case = w.cases[unit.set_name][unit.key]
    if unit.set_name == "pset":
        case = judging.pset_case(case, unit.form)
    recorder = Recorder(0.9)
    asyncio.run(judging.judge_case(recorder, case, config, unit.set_name))
    return UnitRequests(tuple(recorder.requests), ())


def unit_bound(requests: UnitRequests, *, decision_bpc: int, chat_bpc: int) -> int:
    """The unit's reservation in nano-dollars: every request at its metered bound, unseen drafts at their maximum."""
    total = 0
    for r in requests.decisions:
        total += metering.request_bound(r.body, "decisions") + r.drafts * MAX_DRAFT_CHARS * decision_bpc * PRICE[
            "decision_in"]  # fmt: skip
    for body in requests.redrafts:
        total += metering.request_bound(body, "chat") + MAX_DRAFT_CHARS * chat_bpc * PRICE["chat_in"]
    return total


def first_draft_bodies(w: Workload, doc_id: str) -> list[bytes]:
    doc = w.documents[doc_id]
    return [chat_body(m) for m in phases.first_draft_requests(doc, w.fields[doc.domain])]


def drafting_bound(w: Workload, doc_id: str) -> int:
    """A drafting unit: one document's three first drafts, each at its exact metered bound."""
    return sum(metering.request_bound(body, "chat") for body in first_draft_bodies(w, doc_id))


def margins(requests: Sequence[DecisionRequest]) -> list[int]:
    """The metered input bound (bytes + 64 + 160 q + 8 o, D21) - (ceil(bytes / 3) + 160 q + 8 o) for each request
    (FEAS48-7, FEAS48-C1-1), q and o counted as the request was built: the harness formula, never the library's
    `+dw` estimate (FEAS48-R10-3)."""
    return [
        costs.margin(metering.input_bound(r.body, "decisions"), len(r.body), len(r.questions), r.options)
        for r in requests
    ]
