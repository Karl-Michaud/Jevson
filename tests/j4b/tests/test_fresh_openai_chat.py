"""H18: the drafting client's changes for the metered run (design §6.3 items 1-3; FEAS48-5, FEAS48-6,
FEAS48-R5-1, FEAS48-R5-3, FEAS48-R8-4; plan §11 D17). Every request goes to an `httpx.MockTransport`."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from jevson import BackendError, DecisionsBackend, FakeBackend, Jevson, JevsonConfig, LLMError, ReplayLLM
from jevson.compile.questions import redraft_prompt
from jevson.execute.drafting import malformed
from jevson.llm.replay import replay_key
from jevson.types import Message
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b.fresh.constants import NANO, PRICE
from tests.j4b.fresh.metering import MeteredTransport, request_bound
from tests.j4b.fresh.spend import SpendCapReached, SpendLedger

MESSAGES = [Message("user", "Write the summary for the source below. Return only the value.\n\nRefund: $40.")]
TOOL = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}
TODAY = (
    '{"messages": [{"content": "Write the summary for the source below. Return only the value.\\n\\nRefund: $40.", '
    '"role": "user"}], "model": "gpt-5.4-mini-2026-03-17", "reasoning_effort": "none", "tool_choice": '
    '{"function": {"name": "submit"}, "type": "function"}, "tools": [{"function": {"name": "submit", "parameters": '
    '{"additionalProperties": false, "properties": {"value": {"type": "string"}}, "required": ["value"], "type": '
    '"object"}, "strict": true}, "type": "function"}]}'
)
"""`json.dumps(OpenAIChatLLM("k").body(MESSAGES, TOOL), sort_keys=True)` at e239c2f."""


def completion(
    arguments: str = '{"value": "A refund of $40."}',
    *,
    finish: str = "stop",
    usage: tuple[int, int] = (20, 8),
    model: str = "gpt-5.4-mini-2026-03-17",
) -> dict[str, Any]:
    return {
        "model": model,
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
        "choices": [{"finish_reason": finish, "message": {"tool_calls": [{"function": {"arguments": arguments}}]}}],
    }


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def wire(client: OpenAIChatLLM) -> bytes:
    """The bytes httpx sends for the client's body (its own JSON encoding)."""
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions", json=client.body(MESSAGES, TOOL)).content


def llm(
    handler: Callable[[httpx.Request], httpx.Response], ledger: SpendLedger | None = None, **kw: Any
) -> OpenAIChatLLM:
    transport: httpx.AsyncBaseTransport = httpx.MockTransport(handler)
    if ledger is not None:
        transport = MeteredTransport(transport, ledger, run_attempt=1)
    return OpenAIChatLLM("dummy", transport=transport, sleep=Sleeps(), **kw)


# (1) the output cap is sent only when set ------------------------------------------------------------


def test_h18_1_the_cap_is_in_the_body_only_when_set_and_otherwise_the_body_is_todays() -> None:
    assert json.dumps(OpenAIChatLLM("k").body(MESSAGES, TOOL), sort_keys=True) == TODAY
    capped = OpenAIChatLLM("k", max_completion_tokens=2048).body(MESSAGES, TOOL)
    assert capped.pop("max_completion_tokens") == 2048
    assert json.dumps(capped, sort_keys=True) == TODAY


# (2) a truncated reply is a failed draft -------------------------------------------------------------


def test_h18_2_finish_reason_length_gives_no_arguments() -> None:
    parsed = OpenAIChatLLM("k").parse(completion(finish="length"))
    assert parsed.arguments is None
    assert parsed.raw == '{"value": "A refund of $40."}'


# (3), (4): a failed attempt is charged its bound; headroom is checked on the retry -----------------------


def test_h18_3_a_read_timeout_after_billing_is_charged_its_bound_and_the_retry_its_usage(tmp_path: Path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("billed, no reply", request=request)
        return httpx.Response(200, json=completion())

    ledger = SpendLedger(tmp_path)
    client = llm(handler, ledger, max_completion_tokens=2048)
    assert asyncio.run(client.complete(MESSAGES, TOOL)).arguments == {"value": "A refund of $40."}
    body = wire(client)
    bound = request_bound(body, "chat")
    assert bound == (len(body) + 64) * PRICE["chat_in"] + 2048 * PRICE["chat_out"]
    assert ledger.billed == bound + 20 * PRICE["chat_in"] + 8 * PRICE["chat_out"]


def test_h18_3_with_one_cent_of_headroom_the_retry_is_refused(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("billed, no reply", request=request)

    ledger = SpendLedger(tmp_path)
    client = llm(handler, ledger, max_completion_tokens=2048)
    long = [Message("user", MESSAGES[0].content + " The customer wrote at length." * 60)]
    body = httpx.Request("POST", "https://api.openai.com/v1/chat/completions", json=client.body(long, TOOL)).content
    bound = request_bound(body, "chat")
    assert bound > NANO // 100  # one attempt of this request costs more than a cent at its bound
    ledger.billed = ledger.cap - bound - NANO // 100  # the first attempt fits; then $0.01 is left
    with pytest.raises(SpendCapReached):
        asyncio.run(client.complete(long, TOOL))
    assert len([r for r in ledger.records if r["type"] == "reserve"]) == 1
    assert ledger.stopped


# (5), (7): usage over the bound, and a refusal surfacing through Jevson ------------------------------------


def test_h18_5_prompt_tokens_over_the_bound_stops_the_run(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    client = llm(lambda r: httpx.Response(200, json=completion(usage=(10**6, 1))), ledger, max_completion_tokens=2048)
    with pytest.raises(Exception, match="usage"):
        asyncio.run(client.complete(MESSAGES, TOOL))
    assert ledger.violation is not None


SCHEMA = {
    "type": "object",
    "required": ["summary"],
    "properties": {"summary": {"type": "string", "x-jevson": {"generate": {"criteria": ["is short"]}}}},
}


def test_h18_7_a_refusal_sends_nothing_more_and_surfaces_as_llm_error_with_the_ledger_stopped(tmp_path: Path) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json=completion())

    ledger = SpendLedger(tmp_path)
    ledger.billed = ledger.cap
    client = llm(handler, ledger, max_completion_tokens=2048)
    with pytest.raises(LLMError) as raised:
        asyncio.run(
            Jevson(FakeBackend(default=FakeBackend.predicate(0.9)), llm=client).aresolve(SCHEMA, "Refund: $40.")
        )
    assert raised.value.code == "llm_exception"
    assert (sent, ledger.stopped) == ([], True)


def test_h18_7_a_decision_refusal_surfaces_as_backend_error_with_the_ledger_stopped(tmp_path: Path) -> None:
    sent: list[httpx.Request] = []
    ledger = SpendLedger(tmp_path)
    ledger.billed = ledger.cap
    transport = MeteredTransport(
        httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(500)), ledger, run_attempt=1
    )
    backend = DecisionsBackend(api_key="dummy-h18-7", transport=transport, requests_per_minute=10**9, sleep=Sleeps())
    chat = llm(lambda r: httpx.Response(200, json=completion()))
    with pytest.raises(BackendError) as raised:
        asyncio.run(Jevson(backend, llm=chat).aresolve(SCHEMA, "Refund: $40."))
    assert raised.value.code == "backend_exception"
    assert (sent, ledger.stopped) == ([], True)


# (8): the returned model reaches the response, the ReplayLLM record and Result.versions (R15) -------------


def test_h18_8_the_returned_model_fills_llm_response_model_the_replay_record_and_versions(tmp_path: Path) -> None:
    parsed = OpenAIChatLLM("k").parse(completion(model="gpt-5.4-mini-2026-03-17"))
    assert parsed.model == "gpt-5.4-mini-2026-03-17"
    client = llm(lambda request: httpx.Response(200, json=completion(model="gpt-5.4-mini-2026-03-17")))
    replay = ReplayLLM(client, tmp_path, llm_id="chat")
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    result = asyncio.run(Jevson(backend, llm=replay).aresolve(SCHEMA, "Refund: $40."))
    assert result.versions["llm_model"] == "gpt-5.4-mini-2026-03-17"
    [record] = tmp_path.iterdir()
    assert json.loads(record.read_text(encoding="utf-8"))["model"] == "gpt-5.4-mini-2026-03-17"


# (9): a cancelled attempt ---------------------------------------------------------------------------------


def test_h18_9_a_cancelled_post_is_settled_at_its_bound_and_holds_no_reservation(tmp_path: Path) -> None:
    gate = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        await gate.wait()
        return httpx.Response(200, json=completion())

    async def scenario() -> SpendLedger:
        ledger = SpendLedger(tmp_path)
        transport = MeteredTransport(httpx.MockTransport(hang), ledger, run_attempt=1)
        client = OpenAIChatLLM("dummy", transport=transport, max_completion_tokens=2048, sleep=Sleeps())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(client.complete(MESSAGES, TOOL), 0.01)
        return ledger

    ledger = asyncio.run(scenario())
    assert ledger.open == {}
    assert [r["type"] for r in SpendLedger(tmp_path).records] == ["reserve", "settle"]
    assert ledger.billed > 0


# (10): the injected sleep -----------------------------------------------------------------------------------


def test_h18_10_an_exhausted_request_sleeps_through_the_injected_sleep_only() -> None:
    sleeps = Sleeps()
    client = OpenAIChatLLM(
        "dummy", transport=httpx.MockTransport(lambda r: httpx.Response(500, text="busy")), sleep=sleeps
    )
    with pytest.raises(RuntimeError, match="HTTP 500"):
        asyncio.run(client.complete(MESSAGES, TOOL))
    assert sleeps.waits == [1, 2, 4, 8]


# (11): an unencodable draft is malformed -----------------------------------------------------------------


def test_h18_11_a_lone_surrogate_is_a_malformed_draft_whose_redraft_is_keyable_and_sent() -> None:
    raw = '{"value": "refund \\ud83d issued"}'
    assert OpenAIChatLLM("k").parse(completion(raw)).arguments is None
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=completion(raw if len(sent) == 1 else '{"value": "A refund."}'))

    client = llm(handler)
    result = asyncio.run(
        Jevson(FakeBackend(default=FakeBackend.predicate(0.9)), llm=client, config=JevsonConfig()).aresolve(
            SCHEMA, "Refund: $40."
        )
    )
    assert result.value == {"summary": "A refund."}
    assert len(sent) == 2
    redraft = [Message(m["role"], m["content"]) for m in sent[1]["messages"]]
    assert replay_key("m", redraft, TOOL) is not None
    assert redraft[-1].content == redraft_prompt("summary", [malformed(4000)])
