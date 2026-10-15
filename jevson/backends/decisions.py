"""`DecisionsBackend`: the OpenAI Decisions API over raw `httpx` (DESIGN §2, §8).

This is the only module that knows the vendor URL, headers, or wire format; the `openai` SDK is not
a dependency, so every request, retry, and token is visible to `Cost`.

- Questions go out named `q0…qN` whatever their `Question.name`; answers are matched back by name
  and checked against question order. A malformed entry in an HTTP 200 becomes an `InvalidAnswer`
  for that question; a 200 whose envelope cannot be read is `BackendError(unparseable_response)`.
- Error codes are mapped from the bodies Phase 0r recorded (tests/probes/results/0r/probe_limits.json,
  probe_context_limit.json). 429, 5xx, timeouts and dropped connections are retried
  (`execute/policy.py`); a context-limit or question-count rejection surfaces at once.
- The key comes from `api_key=`, else `OPENAI_API_KEY`; it is never logged, written or `repr`ed, and
  is redacted from every message Jevson raises (DESIGN §8.3).
- One token bucket per key paces every attempt, retries included (`execute/ratelimit.py`). The
  default, 3,000 requests a minute, is a guess (half the published Build tier; `/v1/decisions` has
  no measured rate, DESIGN §2.2); pass `requests_per_minute` to change it, and the lower rate wins.
- Without `async with`, each `ask` uses its own client and closes it before returning; inside
  `async with`, calls on that loop share one client until exit (DESIGN §8 lifecycle).
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any, cast

import httpx

from jevson.errors import BackendError, MissingCredentials, UsageError
from jevson.execute.policy import TransportFailure, TransportPolicy, parse_retry_after, retrying
from jevson.execute.ratelimit import Clock, Sleep, acquire, limiter_for
from jevson.result import Result
from jevson.types import (
    Answer,
    BackendResponse,
    ChoiceAnswer,
    Cost,
    DecisionKind,
    InvalidAnswer,
    PredicateAnswer,
    Question,
    Refusal,
    ScoreAnswer,
)

URL = "https://api.openai.com/v1/decisions"
ENV_VAR = "OPENAI_API_KEY"
REQUEST_ID_HEADER = "x-request-id"
_MESSAGE_CAP = 300


class _Unparseable(Exception):
    pass


class DecisionsBackend:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        url: str = URL,
        timeout_s: float = 120.0,
        transport_retries: int = 2,
        requests_per_minute: float = 3000,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        clock: Clock = time.monotonic,
    ) -> None:
        key = api_key or os.environ.get(ENV_VAR) or ""
        if not key:
            raise MissingCredentials(f"no API key: pass api_key=... or set the {ENV_VAR} environment variable")
        self.__key = key
        self._url = url
        self._timeout = timeout_s
        self._policy = TransportPolicy(retries=transport_retries)
        self._limiter = limiter_for(key, requests_per_minute, clock)
        self._transport = transport
        self._sleep = sleep
        self._closed = False
        self._shared: tuple[asyncio.AbstractEventLoop, httpx.AsyncClient] | None = None
        self._depth = 0
        self._live_clients = 0

    def __repr__(self) -> str:
        return f"DecisionsBackend(url={self._url!r}, closed={self._closed})"

    # --- lifecycle ------------------------------------------------------------------------

    def __enter__(self) -> DecisionsBackend:
        self._check_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    async def __aenter__(self) -> DecisionsBackend:
        self._check_open()
        loop = asyncio.get_running_loop()
        if self._shared is None:
            self._shared = (loop, self._new_client())
        elif self._shared[0] is not loop:
            raise UsageError("this DecisionsBackend is already entered with `async with` on another event loop")
        self._depth += 1
        return self

    async def __aexit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        self._depth -= 1
        if self._depth == 0 and self._shared is not None:
            _, client = self._shared
            self._shared = None
            await self._close_client(client)

    def close(self) -> None:
        """Refuse further calls. A shared client is closed by the `async with` that opened it."""
        self._closed = True

    async def aclose(self) -> None:
        self._closed = True
        if self._shared is not None and self._shared[0] is asyncio.get_running_loop():
            _, client = self._shared
            self._shared, self._depth = None, 0
            await self._close_client(client)

    def _check_open(self) -> None:
        if self._closed:
            raise UsageError("this DecisionsBackend is closed")

    def _new_client(self) -> httpx.AsyncClient:
        self._live_clients += 1
        headers = {"Authorization": f"Bearer {self.__key}", "Content-Type": "application/json"}
        return httpx.AsyncClient(transport=self._transport, timeout=self._timeout, headers=headers)

    async def _close_client(self, client: httpx.AsyncClient) -> None:
        await client.aclose()
        self._live_clients -= 1

    # --- Backend --------------------------------------------------------------------------

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        self._check_open()
        if not questions:
            raise UsageError("ask() needs at least one question")
        payload = {"model": model, "input": state, "questions": [_encode(i, q) for i, q in enumerate(questions)]}
        loop = asyncio.get_running_loop()
        if self._shared is not None and self._shared[0] is loop:
            return await self._ask_with(self._shared[1], payload, questions)
        client = self._new_client()
        try:
            return await self._ask_with(client, payload, questions)
        finally:
            await self._close_client(client)

    async def _ask_with(
        self, client: httpx.AsyncClient, payload: dict[str, Any], questions: Sequence[Question]
    ) -> BackendResponse:
        attempts = 0
        failed_ids: list[str] = []  # request ids of attempts that failed and were retried or raised

        async def attempt() -> httpx.Response:
            nonlocal attempts
            attempts += 1
            await acquire(self._limiter, self._sleep)
            response = await _post(client, self._url, payload)
            if response.status_code != 200:
                if rid := response.headers.get(REQUEST_ID_HEADER):
                    failed_ids.append(rid)
                raise _http_failure(response)
            return response

        request_id = ""
        try:
            response = await retrying(attempt, self._policy, self._sleep)
            request_id = response.headers.get(REQUEST_ID_HEADER, "")
            answers, input_tokens, model = _decode(response, questions)
        except TransportFailure as failure:
            raise self._error(failure.code, failure.detail, attempts, failed_ids) from None
        except _Unparseable as bad:
            raise self._error("unparseable_response", str(bad), attempts, [*failed_ids, request_id]) from None
        return BackendResponse(
            answers=answers,
            input_tokens=input_tokens,
            request_id=request_id,
            model=model,
            transport_retries=attempts - 1,
            retried_request_ids=tuple(failed_ids),
        )

    def _error(self, code: str, detail: str, attempts: int, request_ids: list[str]) -> BackendError:
        cost = Cost(
            decision_requests=attempts,
            decision_request_ids=tuple(rid for rid in request_ids if rid),
            transport_retries=max(attempts - 1, 0),
        )
        return BackendError(code, detail.replace(self.__key, "<redacted>"), Result({}, False, cost=cost))


# --- the wire -------------------------------------------------------------------------------


def _encode(index: int, question: Question) -> dict[str, Any]:
    wire: dict[str, Any] = {"type": question.kind.value, "name": f"q{index}", "instructions": question.instructions}
    if question.kind is DecisionKind.CHOICE:
        wire["choices"] = [{"value": o.id, "description": o.description} for o in question.options]
    elif question.kind is DecisionKind.SCORE:
        wire["levels"] = [{"label": o.id, "description": o.description} for o in question.options]
    return wire


async def _post(client: httpx.AsyncClient, url: str, payload: dict[str, Any]) -> httpx.Response:
    """One HTTP attempt; httpx failures become `TransportFailure`s naming only the exception class."""
    try:
        return await client.post(url, json=payload)
    except httpx.TimeoutException:
        raise TransportFailure("timeout", "the request timed out") from None
    except httpx.TransportError as error:
        raise TransportFailure("connection", type(error).__name__) from None
    except httpx.HTTPError as error:
        raise TransportFailure("unparseable_response", type(error).__name__) from None


def _http_failure(response: httpx.Response) -> TransportFailure:
    status = response.status_code
    error = _json_object(response).get("error")
    fields = cast("dict[str, Any]", error) if isinstance(error, dict) else {}
    code, param, message = fields.get("code"), fields.get("param"), fields.get("message")
    text = message[:_MESSAGE_CAP] if isinstance(message, str) else ""
    detail = f"HTTP {status}" + (f" {code}" if isinstance(code, str) else "")
    if status in (401, 403):  # OpenAI's 401 message echoes part of the key: drop it
        return TransportFailure("authentication" if status == 401 else "permission", detail)
    retry_after = parse_retry_after(response.headers.get("retry-after"))
    return TransportFailure(_error_code(status, code, param, text), detail + (f": {text}" if text else ""), retry_after)


def _error_code(status: int, code: object, param: object, message: str) -> str:
    """The `BackendError` code for one non-200 response, from the bodies Phase 0r recorded."""
    if status == 429:
        return "quota" if code == "insufficient_quota" else "rate_limited"
    if status >= 500:
        return "server_error"
    if status != 400:
        return f"http_{status}"
    if "exceeds the token limit" in message:
        return "context_limit"
    if code == "array_above_max_length" and param == "questions":
        return "question_limit"
    return "invalid_request"


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:  # json.JSONDecodeError and UnicodeDecodeError are both ValueErrors
        return {}
    return cast("dict[str, Any]", body) if isinstance(body, dict) else {}


def _decode(response: httpx.Response, questions: Sequence[Question]) -> tuple[tuple[Answer, ...], int, str]:
    try:
        body = response.json()
    except ValueError:
        raise _Unparseable("the response body is not JSON") from None
    if not isinstance(body, dict):
        raise _Unparseable("the response body is not a JSON object")
    envelope = cast("dict[str, Any]", body)
    raw, model, usage = envelope.get("answers"), envelope.get("model"), envelope.get("usage")
    tokens = cast("dict[str, Any]", usage).get("input_tokens") if isinstance(usage, dict) else None
    if not isinstance(raw, list) or not isinstance(model, str) or not _is_count(tokens):
        raise _Unparseable("the response lacks an answers list, a model string, or usage.input_tokens")
    by_name: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for position, item in enumerate(cast("list[Any]", raw)):
        entry = cast("dict[str, Any]", item) if isinstance(item, dict) else {}
        if isinstance(name := entry.get("name"), str):
            by_name.setdefault(name, []).append((position, entry))
    answers = tuple(_match(index, question, by_name.get(f"q{index}", [])) for index, question in enumerate(questions))
    return answers, cast("int", tokens), model


class _BadAnswer(Exception):
    pass


def _match(index: int, question: Question, entries: list[tuple[int, dict[str, Any]]]) -> Answer:
    try:
        if len(entries) != 1:
            raise _BadAnswer(f"{len(entries)} answers with this question's name")
        position, entry = entries[0]
        if position != index:
            raise _BadAnswer(f"answer at position {position}, question at {index}")
        return _answer(question, entry)
    except _BadAnswer as bad:
        return InvalidAnswer(question.name, str(bad))


def _answer(question: Question, entry: Mapping[str, Any]) -> Answer:
    kind = entry.get("type")
    if kind == "refusal":
        return Refusal(question.name)
    if kind != question.kind.value:
        raise _BadAnswer(f"answer type {kind!r} for a {question.kind.value} question")
    if question.kind is DecisionKind.PREDICATE:
        return PredicateAnswer(question.name, _number(entry, "probability"))
    confidence = None if entry.get("confidence") is None else _number(entry, "confidence")
    if question.kind is DecisionKind.CHOICE:
        choice = entry.get("choice")
        if not isinstance(choice, str):
            raise _BadAnswer("choice is not a string")
        return ChoiceAnswer(question.name, choice, _distribution(entry, "value"), confidence)
    return ScoreAnswer(question.name, _number(entry, "score"), _distribution(entry, "label"), confidence)


def _distribution(entry: Mapping[str, Any], key: str) -> dict[str, float]:
    raw = entry.get("probabilities")
    if not isinstance(raw, list):
        raise _BadAnswer("probabilities is not a list")
    distribution: dict[str, float] = {}
    for item in cast("list[Any]", raw):
        item_fields = cast("dict[str, Any]", item) if isinstance(item, dict) else {}
        option = item_fields.get(key)
        if not isinstance(option, str) or option in distribution:
            raise _BadAnswer(f"probabilities has a missing, non-string or repeated {key}")
        distribution[option] = _number(item_fields, "probability")
    return distribution


def _number(fields: Mapping[str, Any], key: str) -> float:
    value = fields.get(key)
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise _BadAnswer(f"{key} is not a number")
    return float(value)


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
