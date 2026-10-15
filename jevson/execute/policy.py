"""Transport retry (DESIGN §6.1). Decision retries and the redraft loop arrive with the executor.

Transport retries are not decision retries: 429, 5xx, timeouts and dropped connections are retried
with exponential backoff (or the server's `Retry-After`) up to `retries` times, counted separately,
and exempt from the changed-input rule. Every other failure surfaces at once. A context-limit
rejection is never retried unchanged: it surfaces for the executor to split or bisect (DESIGN §8.2).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from jevson.execute.ratelimit import Sleep

T = TypeVar("T")

RETRYABLE = frozenset({"rate_limited", "server_error", "timeout", "connection"})


class TransportFailure(Exception):
    """One failed attempt. `code` is the `BackendError` code it becomes if it is not retried."""

    def __init__(self, code: str, detail: str, retry_after_s: float | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class TransportPolicy:
    retries: int = 2
    base_delay_s: float = 0.5
    max_delay_s: float = 30.0

    def delay(self, failures: int, retry_after_s: float | None) -> float:
        """Seconds to wait after the `failures`-th failed attempt (1-based)."""
        if retry_after_s is not None:
            return min(max(retry_after_s, 0.0), self.max_delay_s)
        return min(self.base_delay_s * 2 ** (failures - 1), self.max_delay_s)


def parse_retry_after(header: str | None) -> float | None:
    """`Retry-After` in seconds; the HTTP-date form is not used by this API and is ignored."""
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


async def retrying(attempt: Callable[[], Awaitable[T]], policy: TransportPolicy, sleep: Sleep) -> T:
    """Run `attempt` until it succeeds, fails with a non-retryable code, or retries run out."""
    failures = 0
    while True:
        try:
            return await attempt()
        except TransportFailure as failure:
            if failure.code not in RETRYABLE or failures >= policy.retries:
                raise
            failures += 1
            await sleep(policy.delay(failures, failure.retry_after_s))
