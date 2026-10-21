"""The spend gates before an attempt and before each batch (design §6.3; plan §4.1 `gates.py`).

Both call `SpendLedger.fits` and hold no arithmetic of their own: the start gate with the attempt's estimate at a
60% rejection share, the per-batch check with the sum of the batch's per-request bounds, before every batch of
both phases. `MeteredTransport` still checks every HTTP attempt.
"""

from __future__ import annotations

from collections.abc import Iterable

from tests.j4b.fresh.spend import SpendLedger


def start_gate(ledger: SpendLedger, estimate_at_60_percent: int) -> bool:
    """Whether an attempt may start: spend so far + its 60% estimate fits under the cap."""
    return ledger.fits(estimate_at_60_percent)


def batch_fits(ledger: SpendLedger, bounds: Iterable[int]) -> bool:
    """Whether a batch may be sent: spend so far + open reservations + the sum of its request bounds fits."""
    return ledger.fits(sum(bounds))
