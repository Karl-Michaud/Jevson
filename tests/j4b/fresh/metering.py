"""`MeteredTransport`: every HTTP attempt reserved at its bound before it is sent, and settled after
(design §6.3 "the per-request bound"; plan §4.1, §11 D3).

It wraps the `httpx` transport of both clients (`DecisionsBackend(transport=...)` and
`OpenAIChatLLM(transport=...)`), so it sees every attempt, retries included. The bound of a request is computed
from the bytes it is about to send: input = UTF-8 bytes of the body + 64 tokens, at the input price; output, for a
drafting call, = its `max_completion_tokens` at the output price; decisions have no output charge. An attempt is
settled at its reported usage when a 200 with usage came back, and at its full bound otherwise (a timeout, a
connection error, a 429, a 5xx, a cancellation): the settle is in a `finally`, so a `CancelledError` releases the
reservation too. Reported usage above the bound stops the run and voids the attempt.
"""

from __future__ import annotations

import json
from typing import cast

import httpx

from tests.j4b.fresh.constants import CHAT_FORMAT_TOKENS, PRICE
from tests.j4b.fresh.spend import SpendLedger


class UsageOverBound(Exception):
    """A response reported more tokens than its reserved bound: the attempt is void (design §6.4)."""


def endpoint_of(request: httpx.Request) -> str:
    return "chat" if request.url.path.endswith("/chat/completions") else "decisions"


def request_bound(body: bytes, endpoint: str) -> int:
    """The bound, in nano-dollars, of one attempt carrying `body` to `endpoint`."""
    input_bound = len(body) + CHAT_FORMAT_TOKENS
    if endpoint == "decisions":
        return input_bound * PRICE["decision_in"]
    cap = json.loads(body).get("max_completion_tokens")
    if not isinstance(cap, int):
        raise ValueError("a metered drafting call must carry max_completion_tokens")
    return input_bound * PRICE["chat_in"] + cap * PRICE["chat_out"]


def retry_after_s(header: str | None) -> float | None:
    """`Retry-After` in seconds (the API sends seconds; an HTTP date is not used and reads as None)."""
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


def usage_of(content: bytes, endpoint: str) -> tuple[tuple[int, int] | None, str | None]:
    """((input tokens, output tokens), returned model) from a 200 body, or (None, model) without usage."""
    try:
        loaded: object = json.loads(content)
    except ValueError:
        return None, None
    if not isinstance(loaded, dict):
        return None, None
    payload = cast("dict[str, object]", loaded)
    usage, model = payload.get("usage"), payload.get("model")
    model = model if isinstance(model, str) else None
    if not isinstance(usage, dict):
        return None, model
    counts = cast("dict[str, object]", usage)
    names = ("input_tokens", None) if endpoint == "decisions" else ("prompt_tokens", "completion_tokens")
    tokens = [counts.get(n, 0) if n else 0 for n in names]
    values = [t for t in tokens if isinstance(t, int) and not isinstance(t, bool) and t >= 0]
    if len(values) != len(tokens):
        return None, model
    return (values[0], values[1]), model


class MeteredTransport(httpx.AsyncBaseTransport):
    """Reserve, forward, settle; one ledger for both endpoints and every attempt."""

    def __init__(self, inner: httpx.AsyncBaseTransport, ledger: SpendLedger, *, run_attempt: int) -> None:
        self.inner, self.ledger, self.run_attempt = inner, ledger, run_attempt

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        body = await request.aread()
        endpoint = endpoint_of(request)
        bound = request_bound(body, endpoint)
        attempt_id = self.ledger.reserve(bound, endpoint=endpoint, run_attempt=self.run_attempt)
        billed, status, retry_after, model, over = bound, None, None, None, None
        try:
            response = await self.inner.handle_async_request(request)
            content = await response.aread()
            status, retry_after = response.status_code, retry_after_s(response.headers.get("retry-after"))
            if status == 200:
                usage, model = usage_of(content, endpoint)
                if usage is not None:
                    billed, over = self._billed(body, endpoint, usage)
            return httpx.Response(status, headers=response.headers, content=content, request=request)
        finally:
            self.ledger.settle(attempt_id, billed, status=status, retry_after=retry_after, model=model)
            if over is not None:
                self.ledger.violation = over
                self.ledger.stopped = True
                raise UsageOverBound(over)

    def _billed(self, body: bytes, endpoint: str, usage: tuple[int, int]) -> tuple[int, str | None]:
        tokens_in, tokens_out = usage
        input_bound = len(body) + CHAT_FORMAT_TOKENS
        if endpoint == "decisions":
            over = f"input_tokens {tokens_in} > bound {input_bound}" if tokens_in > input_bound else None
            return tokens_in * PRICE["decision_in"], over
        cap = int(json.loads(body)["max_completion_tokens"])
        over = None
        if tokens_in > input_bound or tokens_out > cap:
            over = f"usage {tokens_in}/{tokens_out} > bound {input_bound}/{cap}"
        return tokens_in * PRICE["chat_in"] + tokens_out * PRICE["chat_out"], over
