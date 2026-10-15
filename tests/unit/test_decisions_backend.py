"""DecisionsBackend: wire shape, answer mapping, credentials, lifecycle, and the shared limiter."""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import httpx
import pytest

from jevson import (
    Backend,
    ChoiceAnswer,
    DecisionsBackend,
    MissingCredentials,
    PredicateAnswer,
    Refusal,
    ScoreAnswer,
    UsageError,
)
from tests.adversarial.hostile_backend import (
    MODEL,
    QUESTIONS,
    RETURNED_MODEL,
    SENTINEL_KEY,
    backend,
    envelope,
    good_answers,
    respond,
)


class Recorder:
    """A mock-transport handler that records every request and answers well."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return respond(envelope(good_answers()))

    def body(self, index: int = 0) -> dict[str, Any]:
        return json.loads(self.requests[index].content)


def ask(b: DecisionsBackend) -> Any:
    return asyncio.run(b.ask("the source text", QUESTIONS, MODEL))


def test_it_satisfies_the_backend_protocol() -> None:
    assert isinstance(backend(Recorder()), Backend)


def test_the_request_uses_opaque_names_and_the_declared_options() -> None:
    recorder = Recorder()
    ask(backend(recorder))
    request = recorder.requests[0]
    assert (request.method, str(request.url)) == ("POST", "https://api.openai.com/v1/decisions")
    assert request.headers["authorization"] == f"Bearer {SENTINEL_KEY}"
    assert recorder.body() == {
        "model": MODEL,
        "input": "the source text",
        "questions": [
            {"type": "predicate", "name": "q0", "instructions": "Is the invoice paid?"},
            {"type": "choice", "name": "q1", "instructions": "Which vendor issued it?",
             "choices": [{"value": "c0", "description": "Acme"}, {"value": "c1", "description": "Globex"}]},
            {"type": "score", "name": "q2", "instructions": "How legible is it?",
             "levels": [{"label": "l0", "description": "poor"}, {"label": "l1", "description": "fair"},
                        {"label": "l2", "description": "good"}]},
        ],
    }  # fmt: skip


def test_answers_are_mapped_back_to_the_callers_names_with_model_and_usage() -> None:
    response = ask(backend(Recorder()))
    paid, vendor, quality = response.answers
    assert paid == PredicateAnswer("paid", 0.9)
    assert vendor == ChoiceAnswer("vendor", "c1", {"c0": 0.2, "c1": 0.8}, 0.7)
    assert quality == ScoreAnswer("quality", 1.8, {"l0": 0.0, "l1": 0.2, "l2": 0.8}, 0.6)
    assert (response.model, response.input_tokens, response.request_id) == (RETURNED_MODEL, 321, "req-1")
    assert (response.transport_retries, response.retried_request_ids, response.cache_hit) == (0, (), False)


def test_a_refusal_becomes_a_refusal() -> None:
    answers = [*good_answers()[:2], {"type": "refusal", "name": "q2"}]
    response = asyncio.run(backend(lambda request: respond(envelope(answers))).ask("s", QUESTIONS, MODEL))
    assert response.answers[2] == Refusal("quality")


def test_the_url_and_a_missing_request_id_are_tolerated() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://proxy.test/v1/decisions"
        return httpx.Response(200, json=envelope(good_answers()))

    assert ask(backend(handler, url="https://proxy.test/v1/decisions")).request_id == ""


def test_asking_nothing_is_a_usage_error() -> None:
    with pytest.raises(UsageError):
        asyncio.run(backend(Recorder()).ask("s", (), MODEL))


# --- credentials (DESIGN §8.3) --------------------------------------------------------------


def test_an_explicit_key_wins_over_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environment")
    recorder = Recorder()
    ask(backend(recorder))
    assert recorder.requests[0].headers["authorization"] == f"Bearer {SENTINEL_KEY}"


def test_the_environment_is_the_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-environment")
    recorder = Recorder()
    ask(DecisionsBackend(transport=httpx.MockTransport(recorder)))
    assert recorder.requests[0].headers["authorization"] == "Bearer sk-from-environment"


@pytest.mark.parametrize(("argument", "environment"), [(None, None), ("", None), (None, ""), ("", "")])
def test_no_key_raises_missing_credentials_before_any_network_call(
    monkeypatch: pytest.MonkeyPatch, argument: str | None, environment: str | None
) -> None:
    if environment is None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    else:
        monkeypatch.setenv("OPENAI_API_KEY", environment)

    def never(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no request may be made")

    with pytest.raises(MissingCredentials, match="OPENAI_API_KEY") as raised:
        DecisionsBackend(api_key=argument, transport=httpx.MockTransport(never))
    assert "api_key" in str(raised.value)


def test_the_library_never_reads_a_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    (tmp_path / ".env").write_text("OPENAI_API_KEY=sk-in-dotenv\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(MissingCredentials):
        DecisionsBackend()


# --- lifecycle (DESIGN §8) ------------------------------------------------------------------


def test_each_call_outside_async_with_uses_and_closes_its_own_client() -> None:
    b = backend(Recorder())
    for _ in range(20):
        ask(b)  # a fresh asyncio.run, so a fresh event loop, each time
        assert b._live_clients == 0  # pyright: ignore[reportPrivateUsage]


def test_concurrent_calls_on_one_loop_succeed_and_leave_no_client() -> None:
    b = backend(Recorder())

    async def both() -> list[Any]:
        return await asyncio.gather(b.ask("a", QUESTIONS, MODEL), b.ask("b", QUESTIONS, MODEL))

    assert len(asyncio.run(both())) == 2
    assert b._live_clients == 0  # pyright: ignore[reportPrivateUsage]


def test_inside_async_with_calls_share_one_client_closed_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    b = backend(Recorder())
    made: list[httpx.AsyncClient] = []
    original = b._new_client  # pyright: ignore[reportPrivateUsage]

    def counting() -> httpx.AsyncClient:
        made.append(original())
        return made[-1]

    monkeypatch.setattr(b, "_new_client", counting)

    async def session() -> None:
        async with b:
            async with b:  # re-entry on the same loop shares the client
                await b.ask("a", QUESTIONS, MODEL)
            await asyncio.gather(b.ask("b", QUESTIONS, MODEL), b.ask("c", QUESTIONS, MODEL))
            assert not made[0].is_closed

    asyncio.run(session())
    assert len(made) == 1
    assert made[0].is_closed
    assert b._live_clients == 0  # pyright: ignore[reportPrivateUsage]
    ask(b)  # still usable after exit, on a per-call client
    assert len(made) == 2


def test_async_with_on_a_second_loop_is_a_usage_error() -> None:
    b = backend(Recorder())
    entered, release = threading.Event(), threading.Event()

    async def hold() -> None:
        async with b:
            entered.set()
            await asyncio.to_thread(release.wait)

    thread = threading.Thread(target=asyncio.run, args=(hold(),))
    thread.start()
    entered.wait()

    async def enter() -> None:
        async with b:
            pass

    try:
        with pytest.raises(UsageError, match="another event loop"):
            asyncio.run(enter())
        ask(b)  # a call from another loop still works, on its own client
    finally:
        release.set()
        thread.join()


def test_a_closed_backend_refuses_every_use() -> None:
    b = backend(Recorder())
    with b:
        ask(b)
    with pytest.raises(UsageError, match="closed"):
        ask(b)
    with pytest.raises(UsageError):
        b.__enter__()

    async def enter() -> None:
        async with b:
            pass

    with pytest.raises(UsageError):
        asyncio.run(enter())


def test_aclose_closes_the_shared_client() -> None:
    b = backend(Recorder())

    async def session() -> None:
        await b.__aenter__()
        await b.aclose()
        assert b._live_clients == 0  # pyright: ignore[reportPrivateUsage]
        with pytest.raises(UsageError):
            await b.ask("a", QUESTIONS, MODEL)
        await b.__aexit__(None, None, None)

    asyncio.run(session())
    asyncio.run(backend(Recorder()).aclose())  # closing an unused backend is fine


# --- the per-key limiter (DESIGN §8, [L20]) -------------------------------------------------


def test_two_backends_with_one_key_share_one_limiter() -> None:
    a, b = backend(Recorder()), backend(Recorder())
    other = DecisionsBackend(api_key="sk-another", transport=httpx.MockTransport(Recorder()))
    assert a._limiter is b._limiter  # pyright: ignore[reportPrivateUsage]
    assert a._limiter is not other._limiter  # pyright: ignore[reportPrivateUsage]


def test_the_lower_requested_rate_wins() -> None:
    a = backend(Recorder(), requests_per_minute=600)
    backend(Recorder(), requests_per_minute=60)
    backend(Recorder(), requests_per_minute=6000)
    assert a._limiter.rate_per_s == 1.0  # pyright: ignore[reportPrivateUsage]


def test_every_attempt_waits_on_the_limiter() -> None:
    sleeps: list[float] = []

    async def record(seconds: float) -> None:
        sleeps.append(seconds)

    clock = iter([0.0] * 100)
    b = DecisionsBackend(
        api_key="sk-limited", transport=httpx.MockTransport(Recorder()), requests_per_minute=60,
        sleep=record, clock=lambda: next(clock),
    )  # fmt: skip
    for _ in range(3):
        ask(b)
    assert sleeps == [1.0, 2.0]  # burst 1 at 1 request/s, the clock frozen
