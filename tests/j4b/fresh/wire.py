"""`PinnedWire`: the innermost transport of a phase's clients, which refuses a request off the pinned request
parameters before it is sent (RC3-1; design §2.6 "every decision rule frozen").

The amendable modules sit between the frozen request builders (`OpenAIChatLLM.body` and `.complete`,
`DecisionsBackend`) and the wire, so a fix to one of them could rewrite what is sent. This module is frozen, and
`phases.clients` (frozen) puts it under `MeteredTransport`, as the last step before the network. A drafting request
must equal, key for key, the body the pinned client builds for the messages it carries: the drafting model, the
reasoning effort, `max_completion_tokens`, the strict `submit` tool and `tool_choice`. A decision request must carry
exactly `model`, `input` and `questions`, with the model every configuration names. Any other request, or one to
another URL, is not sent: the ledger is stopped (so no unit is re-queued) and the attempt is a harness defect, which
the runner leaves incomplete for `void --reason harness_defect`. What is sent is a new request built from the exact
bytes checked, never the request object handed in, whose stream could differ from its cached body (RC4-1).
Message, input and question content is not checked here; it is set by the frozen builders above the amendable
wrappers (`inflight`, `requeue`, `MeteredTransport` and the client wiring are frozen items too).
"""

from __future__ import annotations

import json
from typing import Any, cast

import httpx

from jevson.execute.drafting import TOOL_SCHEMA
from jevson.types import Message
from tests.integration.openai_chat import URL as CHAT_URL
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b.fresh.arms import LIBRARY_ARMS
from tests.j4b.fresh.constants import MAX_COMPLETION_TOKENS
from tests.j4b.fresh.spend import SpendLedger

DECISIONS_URL = "https://api.openai.com/v1/decisions"
DECISION_KEYS = frozenset({"model", "input", "questions"})
MESSAGE_KEYS = frozenset({"role", "content"})
LENGTH_HEADERS = frozenset({"content-length", "transfer-encoding"})
OFF_PIN = "request off pin: "
"""The prefix of `SpendLedger.violation` when this transport refused a request."""


class RequestOffPin(Exception):
    """A request whose parameters are not the pinned ones: a harness defect; it was never sent."""


def decision_models() -> frozenset[str]:
    return frozenset(config.model for config in LIBRARY_ARMS.values())


def _chat_problem(body: dict[str, Any]) -> str | None:
    sent = cast("list[object] | object", body.get("messages"))
    items = cast("list[object]", sent) if isinstance(sent, list) else None
    if items is None or not all(isinstance(m, dict) and frozenset(cast("dict[str, Any]", m)) == MESSAGE_KEYS
                                for m in items):  # fmt: skip
        return "drafting messages are not a list of {role, content}"
    listed = [Message(m["role"], str(m["content"])) for m in cast("list[dict[str, Any]]", items)]
    pinned = OpenAIChatLLM("", max_completion_tokens=MAX_COMPLETION_TOKENS).body(listed, TOOL_SCHEMA)
    differing = sorted(k for k in set(pinned) | set(body) if pinned.get(k) != body.get(k))
    return f"drafting body differs from the pinned client's in {differing}" if differing else None


def _decision_problem(body: dict[str, Any]) -> str | None:
    if frozenset(body) != DECISION_KEYS:
        return f"decision body keys {sorted(body)}"
    if body["model"] not in decision_models():
        return f"decision model {body['model']!r}"
    return None


def problem(request: httpx.Request, content: bytes) -> str | None:
    """Why `request` is off the pin, or None."""
    try:
        loaded: object = json.loads(content)
    except ValueError:
        return "a body that is not JSON"
    if not isinstance(loaded, dict):
        return "a body that is not a JSON object"
    body = cast("dict[str, Any]", loaded)
    url = str(request.url)
    if request.method == "POST" and url == CHAT_URL:
        return _chat_problem(body)
    if request.method == "POST" and url == DECISIONS_URL:
        return _decision_problem(body)
    return f"{request.method} {url}"


class PinnedWire(httpx.AsyncBaseTransport):
    """Forward a request only if it is on the pin; otherwise stop the ledger and raise `RequestOffPin`."""

    def __init__(self, inner: httpx.AsyncBaseTransport, ledger: SpendLedger) -> None:
        self.inner, self.ledger = inner, ledger

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        checked = await request.aread()
        found = problem(request, checked)
        if found is not None:
            self.ledger.violation = OFF_PIN + found
            self.ledger.stopped = True
            raise RequestOffPin(found)
        return await self.inner.handle_async_request(sent_as_checked(request, checked))


def sent_as_checked(request: httpx.Request, checked: bytes) -> httpx.Request:
    """A new request carrying exactly the bytes `problem` checked (RC4-1): `aread()` returns the cached body, while a
    transport sends `request.stream`, which code outside this one could have swapped. The length headers are
    recomputed from `checked`; the method, URL, other headers and extensions (the timeouts) are kept."""
    headers = [(k, v) for k, v in request.headers.multi_items() if k.lower() not in LENGTH_HEADERS]
    return httpx.Request(request.method, request.url, headers=headers, content=checked,
                         extensions=request.extensions)  # fmt: skip


def off_pin(ledger: SpendLedger) -> str | None:
    """The refusal this transport recorded on `ledger`, if any."""
    violation = ledger.violation
    return violation if violation is not None and violation.startswith(OFF_PIN) else None
