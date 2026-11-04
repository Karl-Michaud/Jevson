"""The per-key rate limiter (DESIGN §8, [L20]).

One token bucket per API key, shared by every `DecisionsBackend` in the process through a registry
keyed by a hash of the key. The bucket is guarded by a `threading.Lock`, never an asyncio primitive:
a caller reserves a slot under the lock and then sleeps on its own loop, so threads and event loops
share one rate. After `os.fork()` the child gets fresh locks.
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
from collections.abc import Awaitable, Callable

Clock = Callable[[], float]
Sleep = Callable[[float], Awaitable[object]]


class TokenBucket:
    """`rate_per_s` requests per second on average, bursts of up to `burst`."""

    def __init__(self, rate_per_s: float, burst: float, clock: Clock = time.monotonic) -> None:
        if not rate_per_s > 0 or not burst >= 1:
            raise ValueError("rate_per_s must be > 0 and burst >= 1")
        self._lock = threading.Lock()
        self._clock = clock
        self.rate_per_s = rate_per_s
        self.burst = burst
        self._tokens = burst
        self._stamp = clock()

    def reserve(self) -> float:
        """Take one slot now; return how long the caller must wait before using it."""
        with self._lock:
            now = self._clock()
            self._tokens = min(self.burst, self._tokens + (now - self._stamp) * self.rate_per_s)
            self._stamp = now
            self._tokens -= 1
            return max(0.0, -self._tokens / self.rate_per_s)

    def tighten(self, rate_per_s: float, burst: float) -> None:
        """Keep the lower of two requested rates (and bursts) for one key."""
        with self._lock:
            self.rate_per_s = min(self.rate_per_s, rate_per_s)
            self.burst = min(self.burst, burst)
            self._tokens = min(self._tokens, self.burst)

    def _after_fork(self) -> None:
        self._lock = threading.Lock()


async def acquire(bucket: TokenBucket, sleep: Sleep) -> None:
    wait = bucket.reserve()
    if wait > 0:
        await sleep(wait)


class _Registry:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.buckets: dict[str, TokenBucket] = {}


_registry = _Registry()


def key_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def limiter_for(api_key: str, requests_per_minute: float, clock: Clock = time.monotonic) -> TokenBucket:
    """The process-wide bucket for this key; a second caller asking a lower rate tightens it."""
    rate = requests_per_minute / 60
    burst = max(1.0, rate)
    with _registry.lock:
        bucket = _registry.buckets.get(key_id(api_key))
        if bucket is None:
            bucket = _registry.buckets[key_id(api_key)] = TokenBucket(rate, burst, clock)
        else:
            bucket.tighten(rate, burst)
        return bucket


def _reinit_after_fork() -> None:
    _registry.lock = threading.Lock()
    for bucket in _registry.buckets.values():
        bucket._after_fork()  # pyright: ignore[reportPrivateUsage]


os.register_at_fork(after_in_child=_reinit_after_fork)
