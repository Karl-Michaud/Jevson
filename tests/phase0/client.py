"""Minimal decision-model client for the Phase 0 probes: raw ``httpx``, no vendor SDK (DESIGN §8).

Two backends: ``jev`` (Phase 0, as run on `jev-1.13.0`) and ``decisions`` (Phase 0r, the OpenAI Decisions API on
`gpt-6-luna`). With ``decisions`` the request and response are translated at the wire (``tests/phase0/decisions.py``),
so the probes, templates and scoring are unchanged.

- The key is read from the repository's gitignored ``.env`` only when a live client is built, and is never
  printed, logged, or written; every response text that is kept passes through ``redact``.
- A transport can be injected (``httpx.MockTransport`` in tests and dry runs); tests never reach the network.
- A hard request budget, a start-rate limit below the vendor's ~1,200/min, and backoff on 429 / 5xx / network
  errors (honouring ``retry-after``).
- R13 is enforced on every request: no question may reference state by position.
"""
from __future__ import annotations

import asyncio
import pathlib
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx

from tests.phase0 import decisions as D
from tests.phase0 import rules as R
from tests.phase0.templates import assert_no_positional_references

URL = "https://api.typesafe.ai/v1/systemone"
ROOT = pathlib.Path(__file__).resolve().parents[2]


class BudgetExceeded(RuntimeError):
    pass


BACKENDS = {"jev": (URL, R.MODEL, "TYPESAFE_API_KEY", "x-typesafe-request-id"),
            "decisions": (D.URL, D.MODEL, D.KEY_NAME, "x-request-id")}


def load_key(env_path: pathlib.Path = ROOT / ".env", name: str = "TYPESAFE_API_KEY") -> str:
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{name}="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError(f"{name} not set in .env")


@dataclass
class Budget:
    limit: int = R.MAX_REQUESTS
    used: int = 0

    def take(self) -> None:
        if self.used >= self.limit:
            raise BudgetExceeded(f"request budget of {self.limit} exhausted")
        self.used += 1


@dataclass
class RateLimiter:
    per_min: int = R.RATE_PER_MIN
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    _next: float = field(default=0.0, init=False)
    _lock: asyncio.Lock | None = field(default=None, init=False)

    async def wait(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = self.clock()
            if now < self._next:
                await self.sleep(self._next - now)
                now = self._next
            self._next = now + 60.0 / self.per_min


class JevClient:
    def __init__(self, api_key: str, *, transport: httpx.AsyncBaseTransport | None = None, model: str | None = None,
                 concurrency: int = 8, budget: Budget | None = None, limiter: RateLimiter | None = None,
                 max_retries: int = 6, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 timeout: float = 120.0, allow_positional: bool = False, backend: str = "jev") -> None:
        if backend not in BACKENDS:
            raise ValueError(f"unknown backend {backend!r}")
        self.backend = backend
        self._url, default_model, _, self._rid_header = BACKENDS[backend]
        model = model or default_model
        self._key = api_key
        self.allow_positional = allow_positional   # only probe 5, which measures positional references on purpose
        self.model = model
        self.budget = budget or Budget()
        self.limiter = limiter or RateLimiter(sleep=sleep)
        self.max_retries = max_retries
        self._sleep = sleep
        self._sem = asyncio.Semaphore(concurrency)
        self._client = httpx.AsyncClient(transport=transport, timeout=timeout,
                                         headers={"Authorization": f"Bearer {api_key}",
                                                  "Content-Type": "application/json"})

    def __repr__(self) -> str:
        return f"JevClient(model={self.model!r}, used={self.budget.used})"

    def redact(self, s: str) -> str:
        return s.replace(self._key, "<REDACTED>") if self._key else s

    async def aclose(self) -> None:
        await self._client.aclose()

    async def ask(self, state: dict | str, questions: dict) -> dict:
        """One request. Returns {status, body, request_id, input_tokens, model, attempts, latency_s, error}."""
        if not self.allow_positional:
            assert_no_positional_references(questions)
        payload = (D.to_request(state, questions, self.model) if self.backend == "decisions"
                   else {"model": self.model, "state": state, "questions": questions})
        async with self._sem:
            for attempt in range(1, self.max_retries + 2):
                self.budget.take()
                await self.limiter.wait()
                t0 = time.perf_counter()
                try:
                    r = await self._client.post(self._url, json=payload)
                except httpx.HTTPError as e:
                    if attempt > self.max_retries:
                        return {"status": -1, "body": None, "error": self.redact(repr(e)), "attempts": attempt,
                                "request_id": None, "input_tokens": None, "model": None, "latency_s": None}
                    await self._sleep(min(2 ** attempt, 60))
                    continue
                dt = time.perf_counter() - t0
                if (r.status_code == 429 or r.status_code >= 500) and attempt <= self.max_retries:
                    ra = r.headers.get("retry-after", "")
                    try:
                        wait = float(ra)
                    except ValueError:
                        wait = float(min(2 ** attempt, 60))
                    await self._sleep(wait)
                    continue
                try:
                    body = r.json()
                except ValueError:
                    body = self.redact(r.text)
                if self.backend == "decisions":
                    body = D.from_response(body)
                usage = body.get("usage") if isinstance(body, dict) else None
                return {"status": r.status_code, "body": body, "error": None, "attempts": attempt,
                        "request_id": r.headers.get(self._rid_header),
                        "input_tokens": usage.get("input_tokens") if isinstance(usage, dict) else None,
                        "model": body.get("model") if isinstance(body, dict) else None, "latency_s": dt}
        raise AssertionError("unreachable")  # pragma: no cover
