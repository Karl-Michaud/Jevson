"""Single-flight wrappers (design §2.3 item 3; plan §4.1 `inflight.py`, FEAS48-R5-1).

Concurrent identical calls share one inner call and one recorded response: drafting calls keyed by `replay_key`,
decision requests by `cache_key`. The wrapper owns the inner task: it is created once per key; a done-callback
removes the key and retrieves the task's exception; every waiter, the first included, awaits it through
`asyncio.shield`, so a waiter cancelled by its own `wait_for` never cancels the shared call. `drain()` awaits every
live inner task; the runner calls it before closing a phase, so no paid call is still in flight.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeVar

from jevson import BackendResponse, Question
from jevson.backends.caching import cache_key
from jevson.llm.replay import replay_key
from jevson.protocols import LLM, Backend
from jevson.types import JSONValue, LLMResponse, Message

T = TypeVar("T")


class _Flights:
    def __init__(self) -> None:
        self.live: dict[str, asyncio.Future[Any]] = {}
        self.inner_calls = 0

    async def run(self, key: str | None, call: Callable[[], Awaitable[T]]) -> T:
        if key is None:
            self.inner_calls += 1
            return await call()
        task = self.live.get(key)
        if task is None:
            self.inner_calls += 1
            task = asyncio.ensure_future(call())
            self.live[key] = task
            task.add_done_callback(lambda done, k=key: self._finished(k, done))
        return await asyncio.shield(task)

    def _finished(self, key: str, done: asyncio.Future[Any]) -> None:
        if self.live.get(key) is done:
            del self.live[key]
        if not done.cancelled():
            done.exception()  # retrieved, so an unawaited failure is never "never retrieved"

    async def drain(self) -> None:
        while self.live:
            await asyncio.gather(*self.live.values(), return_exceptions=True)


class SingleFlightLLM:
    """An `LLM` whose identical concurrent requests share one inner call."""

    def __init__(self, inner: LLM, llm_id: str) -> None:
        self.inner, self.llm_id = inner, llm_id
        self.flights = _Flights()

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        key = replay_key(self.llm_id, messages, tool_schema)
        return await self.flights.run(key, lambda: self.inner.complete(messages, tool_schema))

    async def drain(self) -> None:
        await self.flights.drain()


class SingleFlightBackend:
    """A `Backend` whose identical concurrent requests share one inner request."""

    def __init__(self, inner: Backend) -> None:
        self.inner = inner
        self.flights = _Flights()

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        key = cache_key(state, questions, model)
        return await self.flights.run(key, lambda: self.inner.ask(state, questions, model))

    async def drain(self) -> None:
        await self.flights.drain()
