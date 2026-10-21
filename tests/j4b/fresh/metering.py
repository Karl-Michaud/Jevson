"""`MeteredTransport`: every HTTP attempt reserved at its bound before it is sent, and settled after
(design §6.3 "the per-request bound"; plan §4.1, §11 D3).

It wraps the `httpx` transport of both clients (`DecisionsBackend(transport=...)` and
`OpenAIChatLLM(transport=...)`), so it sees every attempt, retries included. The bound of a request is computed
from the bytes it is about to send: input = UTF-8 bytes of the body + 64 tokens, + 160 per question and 8 per option
for a decision request (plan §11 D21: the API bills tokens per question that are not in the body), at the input
price; output, for a drafting call, = its `max_completion_tokens` at the output price; decisions have no output
charge. An attempt is settled at its reported usage when a 200 carried every usage count its endpoint reports (a
non-negative int each), and at its full bound otherwise (no usage or an incomplete one, a timeout, a connection
error, a 429, a 5xx, a cancellation): the settle is in a `finally`, so a `CancelledError` releases the reservation
too. Reported usage above the bound stops the run and voids the attempt.
"""

from __future__ import annotations

import json
from typing import cast

import httpx

from tests.j4b.fresh.constants import CHAT_FORMAT_TOKENS, DECISION_OPTION_TOKENS, DECISION_QUESTION_TOKENS, PRICE
from tests.j4b.fresh.spend import SpendLedger


class UsageOverBound(Exception):
    """A response reported more tokens than its reserved bound: the attempt is void (design §6.4)."""


def endpoint_of(request: httpx.Request) -> str:
    return "chat" if request.url.path.endswith("/chat/completions") else "decisions"


def _payload(body: bytes) -> dict[str, object]:
    loaded: object = json.loads(body)
    if not isinstance(loaded, dict):
        raise ValueError("a metered request body is not a JSON object")
    return cast("dict[str, object]", loaded)


def question_counts(body: bytes) -> tuple[int, int]:
    """(questions, options) of a decision body as `DecisionsBackend` encodes it: 2 options per predicate, each
    choice's `choices` and each score's `levels`."""
    questions = cast("list[dict[str, object]]", _payload(body).get("questions", []))
    options = 0
    for question in questions:
        listed = question.get("choices", question.get("levels"))
        options += 2 if question.get("type") == "predicate" else len(cast("list[object]", listed))
    return len(questions), options


def input_bound(body: bytes, endpoint: str) -> int:
    """The input tokens one attempt carrying `body` may bill: bytes + 64, and for decisions + 160 q + 8 o (D21)."""
    if endpoint != "decisions":
        return len(body) + CHAT_FORMAT_TOKENS
    questions, options = question_counts(body)
    return len(body) + CHAT_FORMAT_TOKENS + DECISION_QUESTION_TOKENS * questions + DECISION_OPTION_TOKENS * options


def output_cap(body: bytes) -> int:
    cap = _payload(body).get("max_completion_tokens")
    if not isinstance(cap, int):
        raise ValueError("a metered drafting call must carry max_completion_tokens")
    return cap


def request_bound(body: bytes, endpoint: str) -> int:
    """The bound, in nano-dollars, of one attempt carrying `body` to `endpoint`."""
    if endpoint == "decisions":
        return input_bound(body, endpoint) * PRICE["decision_in"]
    return input_bound(body, endpoint) * PRICE["chat_in"] + output_cap(body) * PRICE["chat_out"]


def retry_after_s(header: str | None) -> float | None:
    """`Retry-After` in seconds (the API sends seconds; an HTTP date is not used and reads as None)."""
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


def usage_of(content: bytes, endpoint: str) -> tuple[tuple[int, int] | None, str | None]:
    """((input tokens, output tokens), returned model) from a 200 body, or (None, model) unless every count its
    endpoint reports (decisions: `input_tokens`; chat: `prompt_tokens` and `completion_tokens`) is a non-negative
    int: a reply without complete usage is settled at its full bound."""
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
    names = ("input_tokens",) if endpoint == "decisions" else ("prompt_tokens", "completion_tokens")
    values = [counts.get(n) for n in names]
    tokens = [t for t in values if isinstance(t, int) and not isinstance(t, bool) and t >= 0]
    if len(tokens) != len(names):
        return None, model
    return (tokens[0], tokens[1] if len(tokens) == 2 else 0), model


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
        bound_in = input_bound(body, endpoint)
        if endpoint == "decisions":
            over = f"input_tokens {tokens_in} > bound {bound_in}" if tokens_in > bound_in else None
            return tokens_in * PRICE["decision_in"], over
        cap = output_cap(body)
        over = None
        if tokens_in > bound_in or tokens_out > cap:
            over = f"usage {tokens_in}/{tokens_out} > bound {bound_in}/{cap}"
        return tokens_in * PRICE["chat_in"] + tokens_out * PRICE["chat_out"], over
