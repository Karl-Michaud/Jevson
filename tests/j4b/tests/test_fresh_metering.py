"""`MeteredTransport`: every HTTP attempt reserved at its bound and settled at usage or at the bound (design §6.3;
FEAS48-3, FEAS48-5, FEAS48-R5-1; H18 items 4-6 and 9 at the transport)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from tests.j4b.fresh import metering
from tests.j4b.fresh.constants import CAP, PRICE
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
    assert [(r["type"], r.get("status"), r.get("billed")) for r in ledger.records] == [
        ("reserve", None, None),
        ("settle", None, request_bound(BODY.encode(), "chat")),
    ]


# --- review round 1: the decision bound counts its questions (FEAS48-C1-1), every usage path (T48-3, FEAS48-C1-3) ---

QUESTIONS = [
    {"type": "predicate", "name": "q0", "instructions": "Is it?"},
    {"type": "choice", "name": "q1", "instructions": "Which?", "choices": [{"value": v} for v in "abc"]},
    {"type": "score", "name": "q2", "instructions": "How?", "levels": [{"label": v} for v in "wxyz"]},
]
DECISION_BODY = json.dumps({"model": "gpt-6-luna", "input": "s", "questions": QUESTIONS})


def test_a_decision_bound_adds_160_per_question_and_8_per_option_to_its_bytes_plus_64() -> None:
    raw = DECISION_BODY.encode()
    assert metering.question_counts(raw) == (3, 2 + 3 + 4)
    assert metering.input_bound(raw, "decisions") == len(raw) + 64 + 160 * 3 + 8 * 9
    assert request_bound(raw, "decisions") == (len(raw) + 64 + 160 * 3 + 8 * 9) * PRICE["decision_in"]
    assert metering.input_bound(b"{}", "decisions") == 2 + 64
    with pytest.raises(ValueError, match="not a JSON object"):
        metering.input_bound(b"[]", "decisions")


def settle_of(tmp_path: Path, reply_: httpx.MockTransport, url: str = CHAT, body: str = BODY) -> SpendLedger:
    ledger = SpendLedger(tmp_path)
    post(MeteredTransport(reply_, ledger, run_attempt=1), url, body)
    return ledger


def test_a_200_decisions_reply_is_billed_at_its_input_tokens_exactly(tmp_path: Path) -> None:
    ledger = settle_of(tmp_path, reply({"input_tokens": 900}), DECISIONS, DECISION_BODY)
    assert ledger.billed == 900 * PRICE["decision_in"]
    assert ledger.violation is None


def test_usage_exactly_at_the_bound_is_billed_and_is_not_a_violation(tmp_path: Path) -> None:
    chat_in = metering.input_bound(BODY.encode(), "chat")
    ledger = settle_of(tmp_path / "c", reply({"prompt_tokens": chat_in, "completion_tokens": 2048}))
    assert ledger.billed == chat_in * PRICE["chat_in"] + 2048 * PRICE["chat_out"]
    assert (ledger.violation, ledger.stopped) == (None, False)
    dec_in = metering.input_bound(DECISION_BODY.encode(), "decisions")
    ledger = settle_of(tmp_path / "d", reply({"input_tokens": dec_in}), DECISIONS, DECISION_BODY)
    assert ledger.billed == dec_in * PRICE["decision_in"]
    assert (ledger.violation, ledger.stopped) == (None, False)


@pytest.mark.parametrize(
    ("usage", "url", "body"),
    [
        ({"prompt_tokens": 10, "completion_tokens": 2049}, CHAT, BODY),
        ({"input_tokens": "in-bound+1"}, DECISIONS, DECISION_BODY),
        ({"prompt_tokens": "in-bound+1", "completion_tokens": 0}, CHAT, BODY),
    ],
)
def test_usage_one_token_over_either_bound_voids_and_still_settles(
    tmp_path: Path, usage: dict[str, object], url: str, body: str
) -> None:
    over = metering.input_bound(body.encode(), metering.endpoint_of(httpx.Request("POST", url))) + 1
    planted = {k: over if v == "in-bound+1" else v for k, v in usage.items()}
    ledger = SpendLedger(tmp_path)
    with pytest.raises(UsageOverBound):
        post(MeteredTransport(httpx.MockTransport(lambda r: httpx.Response(200, json={"usage": planted})), ledger,
                              run_attempt=1), url, body)  # fmt: skip
    assert ledger.violation is not None
    assert ledger.stopped
    assert [r["type"] for r in ledger.records] == ["reserve", "settle"]
    assert ledger.open == {}


@pytest.mark.parametrize(
    ("content", "url", "body"),
    [
        (b"not json", CHAT, BODY),
        (b"[1, 2]", CHAT, BODY),
        (b'{"usage": [10, 5]}', CHAT, BODY),
        (b'{"usage": {"prompt_tokens": 10}}', CHAT, BODY),
        (b'{"usage": {"completion_tokens": 5}}', CHAT, BODY),
        (b'{"usage": {"prompt_tokens": -1, "completion_tokens": 5}}', CHAT, BODY),
        (b'{"usage": {"prompt_tokens": true, "completion_tokens": 5}}', CHAT, BODY),
        (b'{"usage": {"prompt_tokens": 1.5, "completion_tokens": 5}}', CHAT, BODY),
        (b'{"usage": {}}', DECISIONS, DECISION_BODY),
        (b'{"usage": {"total_tokens": 999}}', DECISIONS, DECISION_BODY),
        (b'{"usage": {"input_tokens": false}}', DECISIONS, DECISION_BODY),
    ],
)
def test_a_200_without_complete_usage_is_settled_at_its_full_bound(
    tmp_path: Path, content: bytes, url: str, body: str
) -> None:
    ledger = settle_of(tmp_path, httpx.MockTransport(lambda r: httpx.Response(200, content=content)), url, body)
    endpoint = metering.endpoint_of(httpx.Request("POST", url))
    assert ledger.billed == request_bound(body.encode(), endpoint)
    assert ledger.violation is None


def test_usage_of_reads_each_endpoints_keys_and_the_model() -> None:
    chat = b'{"model": "m", "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7}}'
    assert metering.usage_of(chat, "chat") == ((3, 4), "m")
    assert metering.usage_of(b'{"model": 5, "usage": {"input_tokens": 9}}', "decisions") == ((9, 0), None)
    assert metering.usage_of(b'{"model": "m"}', "chat") == (None, "m")
    assert metering.usage_of(b"[]", "chat") == (None, None)


@pytest.mark.parametrize(
    ("header", "seconds"), [(None, None), ("7", 7.0), ("0.5", 0.5), ("Wed, 21 Oct 2026 07:28:00 GMT", None)]
)
def test_retry_after_reads_seconds_and_an_http_date_as_none(header: str | None, seconds: float | None) -> None:
    assert metering.retry_after_s(header) == seconds
