"""Hostile transport: the `transport` row of PLAN §4.2, as `httpx.MockTransport` handlers.

Timeouts, 429, 5xx, connection resets, unparseable HTTP responses, and context-limit rejections.
The error bodies are the ones Phase 0r recorded from `/v1/decisions`
(tests/probes/results/0r/probe_limits.json, probe_context_limit.json); `insufficient_quota` and the
401 body follow OpenAI's documented error shape and were not observed in Phase 0r.

Not shipped: the hostile doubles live in tests/ (PLAN §2).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from tests.adversarial.hostile_backend import SENTINEL_KEY, Handler, envelope, good_answers, respond


def _error(message: str | None, code: str | None, param: str | None = None) -> dict[str, Any]:
    return {"error": {"message": message, "type": "invalid_request_error", "param": param, "code": code}}


CONTEXT_LIMIT = _error("Decision input exceeds the token limit.", None)
QUESTION_LIMIT = _error(
    "Invalid 'questions': array too long. Expected an array with maximum length 200, "
    "but got an array with length 201 instead.",
    "array_above_max_length",
    "questions",
)
TOO_FEW_CHOICES = _error(
    "Invalid 'questions[0].choices': array too short. Expected an array with minimum length 2, "
    "but got an array with length 1 instead.",
    "array_below_min_length",
    "questions[0].choices",
)
BAD_KEY = _error(f"Incorrect API key provided: {SENTINEL_KEY}.", "invalid_api_key")
QUOTA = _error("You exceeded your current quota.", "insufficient_quota")
RATE = _error("Rate limit reached for requests.", "rate_limit_exceeded")
SERVER = {"error": {"message": "The server had an error.", "type": "server_error", "param": None, "code": None}}
ECHOING = _error(f"Invalid header value: Bearer {SENTINEL_KEY}", None)


def raising(error: Exception) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error

    return handle


# Retried, then surfaced as BackendError(code): (handler, code)
RETRYABLE: dict[str, tuple[Handler, str]] = {
    "read timeout": (raising(httpx.ReadTimeout("timed out")), "timeout"),
    "connect timeout": (raising(httpx.ConnectTimeout("timed out")), "timeout"),
    "connection reset": (raising(httpx.ReadError("[Errno 54] Connection reset by peer")), "connection"),
    "connection refused": (raising(httpx.ConnectError("[Errno 61] Connection refused")), "connection"),
    "server disconnected": (raising(httpx.RemoteProtocolError("Server disconnected")), "connection"),
    "429": (lambda request: respond(RATE, 429), "rate_limited"),
    "500": (lambda request: respond(SERVER, 500), "server_error"),
    "502 with an HTML body": (lambda request: respond(b"<html>Bad Gateway</html>", 502), "server_error"),
    "503": (lambda request: respond(SERVER, 503, {"retry-after": "1.5"}), "server_error"),
    # A malformed Retry-After is ignored and the backoff applies (DESIGN §6.1).
    "429 with Retry-After nan": (lambda request: respond(RATE, 429, {"retry-after": "nan"}), "rate_limited"),
    "429 with Retry-After -1": (lambda request: respond(RATE, 429, {"retry-after": "-1"}), "rate_limited"),
    "429 with Retry-After 1e309": (lambda request: respond(RATE, 429, {"retry-after": "1e309"}), "rate_limited"),
}

# Surfaced at once, never retried: (handler, code)
FINAL: dict[str, tuple[Handler, str]] = {
    "context-limit rejection": (lambda request: respond(CONTEXT_LIMIT, 400), "context_limit"),
    "question-count rejection": (lambda request: respond(QUESTION_LIMIT, 400), "question_limit"),
    "other 400": (lambda request: respond(TOO_FEW_CHOICES, 400), "invalid_request"),
    "400 without a body": (lambda request: respond(b"", 400), "invalid_request"),
    "401 echoing the key": (lambda request: respond(BAD_KEY, 401), "authentication"),
    "403": (lambda request: respond(BAD_KEY, 403), "permission"),
    "404": (lambda request: respond({"error": "not found"}, 404), "http_404"),
    "429 insufficient_quota": (lambda request: respond(QUOTA, 429), "quota"),
    # The server asks for longer than the 30 s cap: surfaced, never retried early (DESIGN §6.1).
    "429 with Retry-After beyond the cap": (lambda request: respond(RATE, 429, {"retry-after": "900"}), "rate_limited"),
    "undecodable content-encoding": (
        lambda request: httpx.Response(200, content=b"\x00garbage", headers={"content-encoding": "gzip"}),
        "unparseable_response",
    ),
    "400 echoing the key": (lambda request: respond(ECHOING, 400), "invalid_request"),
}


class Flaky:
    """Fails with `failure` for the first `failures` requests, then answers well. Records each request."""

    def __init__(self, failure: Handler, failures: int) -> None:
        self._failure = failure
        self._failures = failures
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if len(self.requests) <= self._failures:
            response = self._failure(request)  # a raising handler raises here
            response.headers["x-request-id"] = f"req-failed-{len(self.requests)}"
            return response
        return respond(envelope(good_answers()), headers={"x-request-id": "req-ok"})


def counting(handler: Handler) -> tuple[Handler, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return handle, seen


def all_behaviours() -> Iterator[tuple[str, Handler, str]]:
    for name, (handler, code) in {**RETRYABLE, **FINAL}.items():
        yield name, handler, code
