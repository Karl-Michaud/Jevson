"""Unit recovery (plan §11 D11; FEAS48-4, FEAS48-R5-5, NEW-R6-3), with injected sleeps."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from jevson import BackendError, LLMError, Result
from tests.j4b.fresh.constants import UNIT_REQUEUE_WAIT_S, UNIT_REQUEUES
from tests.j4b.fresh.requeue import CapStop, ReplayMiss, RequeuesExhausted, run_unit, wait_s
from tests.j4b.fresh.spend import SpendLedger


class Sleeps:
    def __init__(self) -> None:
        self.waits: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def failing(times: int, ledger: SpendLedger, retry_after: float | None = None):
    calls = {"n": 0}

    async def unit() -> str:
        calls["n"] += 1
        if calls["n"] <= times:
            attempt = ledger.reserve(1, endpoint="decisions", run_attempt=1)
            ledger.settle(attempt, 1, status=429, retry_after=retry_after, model=None)
            raise BackendError("rate_limited", "429", Result({}, False))
        return "done"

    return unit, calls


def test_a_unit_is_requeued_at_most_twice_after_waiting_the_window(tmp_path: Path) -> None:
    ledger, sleeps = SpendLedger(tmp_path), Sleeps()
    unit, calls = failing(2, ledger)
    assert asyncio.run(run_unit("u", unit, ledger, sleeps)) == "done"
    assert (calls["n"], sleeps.waits) == (3, [UNIT_REQUEUE_WAIT_S] * 2)
    unit, _ = failing(3, ledger)
    with pytest.raises(RequeuesExhausted):
        asyncio.run(run_unit("u", unit, ledger, Sleeps()))
    assert UNIT_REQUEUES == 2


def test_the_wait_is_the_largest_retry_after_since_the_unit_started(tmp_path: Path) -> None:
    ledger, sleeps = SpendLedger(tmp_path), Sleeps()
    earlier = ledger.reserve(1, endpoint="decisions", run_attempt=1)
    ledger.settle(earlier, 1, status=429, retry_after=500.0, model=None)  # before the unit: not counted
    unit, _ = failing(1, ledger, retry_after=60.0)
    asyncio.run(run_unit("u", unit, ledger, sleeps))
    assert sleeps.waits == [60.0]
    assert wait_s(ledger, 0) == 500.0


def test_a_cap_stop_is_never_requeued(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    ledger.stopped = True

    async def unit() -> str:
        raise LLMError("llm_exception", "SpendCapReached", Result({}, False))

    with pytest.raises(CapStop):
        asyncio.run(run_unit("u", unit, ledger, Sleeps()))


def test_a_replay_miss_is_never_requeued(tmp_path: Path) -> None:
    async def unit() -> str:
        raise LLMError("replay_miss", "no recorded response", Result({}, False))

    with pytest.raises(ReplayMiss):
        asyncio.run(run_unit("u", unit, SpendLedger(tmp_path), Sleeps()))
