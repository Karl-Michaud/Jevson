"""PLAN §4.2 `transport`, and the key-never-leaks criterion, against DecisionsBackend."""

from __future__ import annotations

import asyncio
import logging
import traceback

import httpx
import pytest

from jevson import BackendError, BackendResponse
from tests.adversarial.hostile_backend import (
    MODEL,
    QUESTIONS,
    SENTINEL_KEY,
    Handler,
    backend,
    envelope,
    good_answers,
    respond,
)
from tests.adversarial.hostile_transport import FINAL, RETRYABLE, Flaky, all_behaviours, counting


def run(handler: Handler, *, transport_retries: int = 2, sleeps: list[float] | None = None) -> BackendResponse:
    async def record(seconds: float) -> None:
        (sleeps if sleeps is not None else []).append(seconds)

    b = backend(handler, transport_retries=transport_retries, sleep=record)
    return asyncio.run(b.ask("source", QUESTIONS, MODEL))


@pytest.mark.parametrize("behaviour", RETRYABLE)
def test_retryable_failures_are_retried_then_surface_with_their_cost(behaviour: str) -> None:
    handler, code = RETRYABLE[behaviour]
    handler, seen = counting(handler)
    sleeps: list[float] = []
    with pytest.raises(BackendError) as raised:
        run(handler, sleeps=sleeps)
    assert raised.value.code == code
    assert len(seen) == 3
    cost = raised.value.cost
    assert (cost.decision_requests, cost.transport_retries) == (3, 2)
    assert raised.value.result.cost is cost
    assert raised.value.result.value == {}
    assert sleeps == ([1.5, 1.5] if behaviour == "503" else [0.5, 1.0])


@pytest.mark.parametrize("behaviour", FINAL)
def test_other_failures_surface_at_once(behaviour: str) -> None:
    handler, code = FINAL[behaviour]
    handler, seen = counting(handler)
    with pytest.raises(BackendError) as raised:
        run(handler)
    assert raised.value.code == code
    assert len(seen) == 1
    assert (raised.value.cost.decision_requests, raised.value.cost.transport_retries) == (1, 0)


def test_a_context_limit_rejection_is_surfaced_for_the_executor_to_split() -> None:
    handler, _ = FINAL["context-limit rejection"]
    with pytest.raises(BackendError) as raised:
        run(handler)
    assert raised.value.code == "context_limit"
    assert "exceeds the token limit" in str(raised.value)


def test_a_recovered_request_reports_its_retries_and_their_request_ids() -> None:
    flaky = Flaky(RETRYABLE["500"][0], failures=2)
    response = run(flaky)
    assert len(flaky.requests) == 3
    assert response.transport_retries == 2
    assert response.retried_request_ids == ("req-failed-1", "req-failed-2")
    assert response.request_id == "req-ok"


def test_a_failure_without_a_request_id_is_still_counted() -> None:
    with pytest.raises(BackendError) as raised:
        run(lambda request: httpx.Response(500), transport_retries=1)
    assert (raised.value.cost.decision_requests, raised.value.cost.decision_request_ids) == (2, ())


def test_transport_retries_zero_means_one_attempt() -> None:
    handler, seen = counting(RETRYABLE["429"][0])
    with pytest.raises(BackendError):
        run(handler, transport_retries=0)
    assert len(seen) == 1


def test_a_retry_after_header_is_honoured_within_the_cap() -> None:
    sleeps: list[float] = []
    flaky = Flaky(lambda request: respond({}, 429, {"retry-after": "30"}), failures=1)
    run(flaky, sleeps=sleeps)
    assert sleeps == [30.0]


def test_a_retry_after_beyond_the_cap_surfaces_at_once_with_its_attempt_counted() -> None:
    sleeps: list[float] = []
    handler, seen = counting(lambda request: respond({}, 429, {"retry-after": "900", "x-request-id": "req-1"}))
    with pytest.raises(BackendError) as raised:
        run(handler, sleeps=sleeps)
    assert (raised.value.code, len(seen), sleeps) == ("rate_limited", 1, [])
    assert "Retry-After 900 s exceeds the 30 s cap" in str(raised.value)
    cost = raised.value.cost
    assert (cost.decision_requests, cost.transport_retries, cost.decision_request_ids) == (1, 0, ("req-1",))


@pytest.mark.parametrize("header", ["nan", "-1", "1e309", "inf"])
def test_a_malformed_retry_after_falls_back_to_the_backoff(header: str) -> None:
    sleeps: list[float] = []
    handler, seen = counting(lambda request: respond({}, 429, {"retry-after": header}))
    with pytest.raises(BackendError) as raised:
        run(handler, sleeps=sleeps)
    assert (raised.value.code, len(seen), sleeps) == ("rate_limited", 3, [0.5, 1.0])
    assert (raised.value.cost.decision_requests, raised.value.cost.transport_retries) == (3, 2)


# --- the key never leaks (DESIGN §8.3) ------------------------------------------------------

LEAK_PATHS: dict[str, Handler] = {
    "success": lambda request: respond(envelope(good_answers())),
    **{name: handler for name, handler, _ in all_behaviours()},
}


@pytest.mark.parametrize("path", LEAK_PATHS)
def test_the_key_appears_in_no_exception_repr_or_log(path: str, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    seen_authorization: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_authorization.append(request.headers["authorization"])
        return LEAK_PATHS[path](request)

    b = backend(handler)
    texts = [repr(b), str(b)]
    try:
        texts.append(repr(asyncio.run(b.ask("source", QUESTIONS, MODEL))))
    except BackendError as error:
        texts += [str(error), repr(error), repr(error.args), repr(error.result)]
        texts.append("".join(traceback.format_exception(error)))
    texts += [record.getMessage() for record in caplog.records] + [repr(r.args) for r in caplog.records]
    assert seen_authorization[0] == f"Bearer {SENTINEL_KEY}"  # the key was really used
    assert not [t for t in texts if SENTINEL_KEY in t]
