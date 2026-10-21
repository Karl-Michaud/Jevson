"""`MeteredTransport`: every HTTP attempt reserved at its bound and settled at usage or at the bound (design §6.3;
FEAS48-3, FEAS48-5, FEAS48-R5-1; H18 items 4-6 and 9 at the transport)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tests.j4b.fresh.constants import CAP, NANO, PRICE
from tests.j4b.fresh.metering import MeteredTransport, UsageOverBound, request_bound
from tests.j4b.fresh.spend import SpendCapReached, SpendLedger

CHAT = "https://api.openai.com/v1/chat/completions"
DECISIONS = "https://api.openai.com/v1/decisions"
BODY = json.dumps({"model": "m", "messages": [{"role": "user", "content": "Write it."}], "max_completion_tokens": 2048})


def post(transport: httpx.AsyncBaseTransport, url: str = CHAT, body: str = BODY) -> httpx.Response:
    async def go() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport) as client:
            return await client.post(url, content=body.encode())

    return asyncio.run(go())


def reply(usage: dict[str, int] | None, status: int = 200, **headers: str) -> httpx.MockTransport:
    payload = {"model": "gpt-5.4-mini-2026-03-17", **({"usage": usage} if usage is not None else {})}
    return httpx.MockTransport(lambda request: httpx.Response(status, json=payload, headers=headers))


def test_the_bound_of_a_fixed_body_is_its_bytes_plus_64_and_the_output_cap() -> None:
    raw = BODY.encode()
    assert request_bound(raw, "chat") == (len(raw) + 64) * PRICE["chat_in"] + 2048 * PRICE["chat_out"]
    assert request_bound(raw, "decisions") == (len(raw) + 64) * PRICE["decision_in"]
    with pytest.raises(ValueError, match="max_completion_tokens"):
        request_bound(b"{}", "chat")


def test_a_200_is_settled_at_its_usage_and_a_failure_at_its_bound(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    post(MeteredTransport(reply({"prompt_tokens": 10, "completion_tokens": 5}), ledger, run_attempt=1))
    assert ledger.billed == 10 * PRICE["chat_in"] + 5 * PRICE["chat_out"]
    post(MeteredTransport(reply(None, 500, **{"retry-after": "60"}), ledger, run_attempt=1))
    bound = request_bound(BODY.encode(), "chat")
    assert ledger.billed == 10 * PRICE["chat_in"] + 5 * PRICE["chat_out"] + bound
    settled = list(ledger.settles())
    assert [(s.status, s.retry_after, s.model) for s in settled] == [
        (200, None, "gpt-5.4-mini-2026-03-17"),
        (500, 60.0, None),
    ]


def test_a_transport_error_after_sending_is_charged_its_full_bound(tmp_path: Path) -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("billed, no reply", request=request)

    ledger = SpendLedger(tmp_path)
    with pytest.raises(httpx.ReadTimeout):
        post(MeteredTransport(httpx.MockTransport(fail), ledger, run_attempt=1))
    assert ledger.billed == request_bound(BODY.encode(), "chat")
    assert ledger.open == {}


def test_usage_over_the_bound_stops_the_run_and_voids_the_attempt(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    with pytest.raises(UsageOverBound):
        post(MeteredTransport(reply({"input_tokens": 10_000}), ledger, run_attempt=1), DECISIONS, "{}")
    assert ledger.violation is not None
    assert ledger.stopped


def test_nothing_is_sent_when_open_reservations_leave_no_room(tmp_path: Path) -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"model": "m", "usage": {"prompt_tokens": 1, "completion_tokens": 1}})

    ledger = SpendLedger(tmp_path)
    bound = request_bound(BODY.encode(), "chat")
    for _ in range(30):
        ledger.reserve((CAP - bound) // 30, endpoint="chat", run_attempt=1)
    ledger.reserve(bound - 1 if bound > 1 else 0, endpoint="chat", run_attempt=1)
    with pytest.raises(SpendCapReached):
        post(MeteredTransport(httpx.MockTransport(answer), ledger, run_attempt=1))
    assert sent == []


def test_a_cancelled_attempt_is_settled_at_its_bound_and_releases_its_reservation(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        await gate.wait()
        return httpx.Response(200)

    async def scenario() -> SpendLedger:
        ledger = SpendLedger(tmp_path)
        async with httpx.AsyncClient(transport=MeteredTransport(httpx.MockTransport(hang), ledger, run_attempt=1)) as c:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(c.post(CHAT, content=BODY.encode()), 0.01)
        return ledger

    ledger = asyncio.run(scenario())
    assert ledger.open == {}
    assert ledger.billed == request_bound(BODY.encode(), "chat")
    assert [r["type"] for r in ledger.records] == ["reserve", "settle"]
    assert NANO > 0
