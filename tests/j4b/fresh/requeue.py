"""Unit recovery: a unit whose request still fails after the clients' own retries is re-queued in the same
attempt, at most twice (plan §11 D11; FEAS48-4, FEAS48-R5-5, NEW-R6-3).

Before each re-queue it waits max(30 s, the largest `Retry-After` among every failed settle record written since
the failing unit started). Nothing attributes an HTTP attempt to a unit (a single-flight task serves several), so
the window rule is used: it can only wait longer than the unit's own `Retry-After`, never shorter. A cap stop and a
replay miss are never re-queued. `sleep` is injected, so no test waits on the wall clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from jevson import BackendError, LLMError
from tests.j4b.fresh.constants import UNIT_REQUEUE_WAIT_S, UNIT_REQUEUES
from tests.j4b.fresh.spend import SpendLedger

T = TypeVar("T")
Sleep = Callable[[float], Awaitable[object]]


class CapStop(Exception):
    """The spend cap stopped a unit: the attempt stops and is void (design §6.3)."""


class RequeuesExhausted(Exception):
    """A unit still failed after its re-queues: a documented harness defect that voids the attempt."""


class ReplayMiss(Exception):
    """A request that had to be served from the records was not: the attempt is void (design §6.4)."""


def wait_s(ledger: SpendLedger, since: int) -> float:
    """The wait before a re-queue: the largest failed `Retry-After` since `since`, at least 30 s."""
    after = [s.retry_after for s in ledger.settles(since) if s.status != 200 and s.retry_after is not None]
    return max([UNIT_REQUEUE_WAIT_S, *after])


async def run_unit(name: str, unit: Callable[[], Awaitable[T]], ledger: SpendLedger, sleep: Sleep) -> T:
    """Run `unit`, re-queueing it after a transport failure; a cap stop or a usage violation is never retried."""
    started = ledger.position()
    requeues = 0
    while True:
        try:
            return await unit()
        except (BackendError, LLMError) as error:
            if ledger.stopped:
                raise CapStop(f"{name}: {ledger.violation or 'the spend cap'}") from error
            if error.code == "replay_miss":
                raise ReplayMiss(f"{name}: {error}") from error
            if requeues == UNIT_REQUEUES:
                raise RequeuesExhausted(f"{name}: failed after {UNIT_REQUEUES} re-queues ({error})") from error
            await sleep(wait_s(ledger, started))
            requeues += 1
