"""execute/ratelimit.py and execute/policy.py."""

from __future__ import annotations

import asyncio
import threading

import pytest

from jevson.execute import ratelimit
from jevson.execute.policy import TransportFailure, TransportPolicy, parse_retry_after, retrying
from jevson.execute.ratelimit import TokenBucket, acquire, key_id, limiter_for


class FrozenClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_bucket_spends_its_burst_then_reserves_slots_at_the_rate() -> None:
    clock = FrozenClock()
    bucket = TokenBucket(rate_per_s=2, burst=2, clock=clock)
    assert [bucket.reserve() for _ in range(5)] == [0.0, 0.0, 0.5, 1.0, 1.5]
    clock.now = 10.0  # refills, but never above the burst
    assert [bucket.reserve() for _ in range(3)] == [0.0, 0.0, 0.5]


def test_the_bucket_rejects_a_bad_rate() -> None:
    with pytest.raises(ValueError, match="rate_per_s"):
        TokenBucket(0, 1)
    with pytest.raises(ValueError, match="burst"):
        TokenBucket(1, 0.5)


def test_threads_and_loops_share_one_rate() -> None:
    """4 threads, each on its own event loop, take 100 slots from one frozen-clock bucket."""
    bucket = limiter_for("sk-shared", requests_per_minute=600, clock=FrozenClock())  # 10/s, burst 10
    waits: list[float] = []
    lock = threading.Lock()

    async def record(seconds: float) -> None:
        with lock:
            waits.append(seconds)

    async def take(n: int) -> None:
        for _ in range(n):
            await acquire(bucket, record)

    threads = [threading.Thread(target=asyncio.run, args=(take(25),)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # 10 free slots, then one every 0.1 s: every reservation distinct, none lost to a race
    assert sorted(round(w, 6) for w in waits) == [round(0.1 * k, 6) for k in range(1, 91)]


def test_the_registry_is_keyed_by_a_hash_of_the_key() -> None:
    limiter_for("sk-secret-value", 60)
    assert list(ratelimit._registry.buckets) == [key_id("sk-secret-value")]  # pyright: ignore[reportPrivateUsage]
    assert "sk-secret-value" not in key_id("sk-secret-value")


def test_after_fork_every_lock_is_new() -> None:
    bucket = limiter_for("sk-fork", 60)
    old_bucket_lock, old_registry_lock = bucket._lock, ratelimit._registry.lock  # pyright: ignore[reportPrivateUsage]
    old_bucket_lock.acquire()  # as if the parent forked while holding it
    try:
        ratelimit._reinit_after_fork()  # pyright: ignore[reportPrivateUsage]
        assert bucket._lock is not old_bucket_lock  # pyright: ignore[reportPrivateUsage]
        assert ratelimit._registry.lock is not old_registry_lock  # pyright: ignore[reportPrivateUsage]
        assert bucket.reserve() == 0.0  # does not deadlock
    finally:
        old_bucket_lock.release()


def test_backoff_doubles_and_retry_after_wins_within_the_cap() -> None:
    policy = TransportPolicy()
    assert [policy.delay(n, None) for n in (1, 2, 3, 10)] == [0.5, 1.0, 2.0, 30.0]
    assert (policy.delay(1, 4.0), policy.delay(1, 999.0), policy.delay(1, -3.0)) == (4.0, 30.0, 0.0)


@pytest.mark.parametrize(("header", "seconds"), [(None, None), ("2", 2.0), ("0.25", 0.25), ("Wed, 21 Oct", None)])
def test_retry_after_parsing(header: str | None, seconds: float | None) -> None:
    assert parse_retry_after(header) == seconds


def test_a_non_retryable_failure_is_raised_on_the_first_attempt() -> None:
    attempts: list[int] = []

    async def attempt() -> str:
        attempts.append(1)
        raise TransportFailure("context_limit", "too big")

    async def sleep(seconds: float) -> None:
        raise AssertionError("never sleeps")

    with pytest.raises(TransportFailure, match="context_limit"):
        asyncio.run(retrying(attempt, TransportPolicy(retries=5), sleep))
    assert len(attempts) == 1
