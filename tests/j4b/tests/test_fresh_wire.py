"""RC3-1: `PinnedWire` refuses a request off the pinned parameters before it is sent, and `phases.clients` puts it
under the metered transport, so an amended wrapper cannot change what reaches the network."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jevson import DecisionKind, DecisionsBackend, Question
from jevson.execute.drafting import TOOL_SCHEMA
from jevson.types import Message
from tests.integration.openai_chat import URL as CHAT_URL
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b.fresh import phases, wire
from tests.j4b.fresh.constants import MAX_COMPLETION_TOKENS
from tests.j4b.fresh.metering import MeteredTransport
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.tests import fake_api

MESSAGES = [Message("system", "Draft the field."), Message("user", "A document.")]


def pinned_chat() -> dict[str, Any]:
    return OpenAIChatLLM("", max_completion_tokens=MAX_COMPLETION_TOKENS).body(MESSAGES, TOOL_SCHEMA)


def post(url: str, body: object) -> httpx.Request:
    return httpx.Request("POST", url, content=json.dumps(body).encode())


def decision(**changes: Any) -> dict[str, Any]:
    return {"model": "gpt-6-luna", "input": "x", "questions": [], **changes}


def test_the_pinned_bodies_are_on_the_pin() -> None:
    assert wire.problem(post(CHAT_URL, pinned_chat()), json.dumps(pinned_chat()).encode()) is None
    assert wire.problem(post(wire.DECISIONS_URL, decision()), json.dumps(decision()).encode()) is None


OFF = {
    "effort": (CHAT_URL, {**pinned_chat(), "reasoning_effort": "high"}, "['reasoning_effort']"),
    "drafting model": (CHAT_URL, {**pinned_chat(), "model": "gpt-other"}, "['model']"),
    "output cap": (CHAT_URL, {**pinned_chat(), "max_completion_tokens": 4096}, "['max_completion_tokens']"),
    "no tool": (CHAT_URL, {k: v for k, v in pinned_chat().items() if k not in ("tools", "tool_choice")},
                "['tool_choice', 'tools']"),
    "an extra key": (CHAT_URL, {**pinned_chat(), "temperature": 0}, "['temperature']"),
    "messages": (CHAT_URL, {**pinned_chat(), "messages": [{"role": "user"}]}, "not a list of {role, content}"),
    "decision model": (wire.DECISIONS_URL, decision(model="gpt-other"), "decision model 'gpt-other'"),
    "decision key": (wire.DECISIONS_URL, decision(seed=1), "decision body keys"),
    "another url": ("https://api.openai.com/v1/responses", pinned_chat(), "POST https://api.openai.com/v1/responses"),
}  # fmt: skip


@pytest.mark.parametrize("name", sorted(OFF))
def test_each_off_pin_request_is_named(name: str) -> None:
    url, body, named = OFF[name]
    found = wire.problem(post(url, body), json.dumps(body).encode())
    assert found is not None
    assert named in found


def test_a_body_that_is_not_a_json_object_is_off_pin() -> None:
    assert wire.problem(post(CHAT_URL, []), b"[]") == "a body that is not a JSON object"
    assert wire.problem(httpx.Request("POST", CHAT_URL, content=b"{"), b"{") == "a body that is not JSON"


class Seen(httpx.AsyncBaseTransport):
    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(json.loads(await request.aread()))
        return httpx.Response(200, json=fake_api.completion("a draft"))


def test_an_off_pin_request_is_not_sent_and_stops_the_ledger(tmp_path: Path) -> None:
    seen, ledger = Seen(), SpendLedger(tmp_path)
    guard = wire.PinnedWire(seen, ledger)
    body = {**pinned_chat(), "reasoning_effort": "high"}
    with pytest.raises(wire.RequestOffPin):
        asyncio.run(guard.handle_async_request(post(CHAT_URL, body)))
    assert seen.bodies == []
    assert ledger.stopped
    assert (
        wire.off_pin(ledger) == "request off pin: drafting body differs from the pinned client's in "
        "['reasoning_effort']"
    )
    asyncio.run(guard.handle_async_request(post(CHAT_URL, pinned_chat())))
    assert seen.bodies == [pinned_chat()]


def test_off_pin_reads_only_this_transports_refusal(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    assert wire.off_pin(ledger) is None
    ledger.violation = "usage 10/10 > bound 1/1"
    assert wire.off_pin(ledger) is None


class Rewriting(MeteredTransport):
    """An amended metering wrapper (the RC3-1 probe): raises the effort after `body()` built the request."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(await request.aread())
        if "reasoning_effort" in body:
            body["reasoning_effort"] = "high"
        rewritten = httpx.Request(request.method, request.url, headers={"content-type": "application/json"},
                                  content=json.dumps(body).encode())  # fmt: skip
        return await super().handle_async_request(rewritten)


def test_rc3_1_a_rewrite_inside_the_client_chain_never_reaches_the_wire(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen, ledger = Seen(), SpendLedger(tmp_path)
    monkeypatch.setattr(phases, "MeteredTransport", Rewriting)
    c = phases.clients(tmp_path, ledger, key="dummy-wire", transport=seen, run_attempt=1, sleep=fake_api.no_sleep)
    with pytest.raises(wire.RequestOffPin):
        asyncio.run(c.drafting.complete(MESSAGES, TOOL_SCHEMA))
    assert seen.bodies == []
    assert wire.off_pin(ledger) is not None


def test_the_clients_send_pinned_requests_through(tmp_path: Path) -> None:
    api, ledger = fake_api.FakeAPI(), SpendLedger(tmp_path)
    c = phases.clients(tmp_path, ledger, key="dummy-wire", transport=httpx.MockTransport(api), run_attempt=1,
                       sleep=fake_api.no_sleep)  # fmt: skip
    asyncio.run(c.drafting.complete(MESSAGES, TOOL_SCHEMA))
    backend = DecisionsBackend(api_key="dummy-wire", transport=wire.PinnedWire(httpx.MockTransport(api), ledger))
    with pytest.raises(wire.RequestOffPin):
        asyncio.run(backend.ask("x", [Question("q", DecisionKind.PREDICATE, "The text is short.")], "gpt-other"))
    assert [e for e, _ in api.bodies] == ["chat"]
    assert api.bodies[0][1] == pinned_chat()
