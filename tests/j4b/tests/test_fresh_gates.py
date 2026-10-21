"""The start gate and the per-batch check ask the ledger and nothing else (design §6.3; ARCH48-R6-8)."""

from __future__ import annotations

from pathlib import Path

from tests.j4b.fresh.constants import NANO
from tests.j4b.fresh.gates import batch_fits, start_gate
from tests.j4b.fresh.spend import SpendLedger


def test_the_gates_only_ask_the_ledger(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    ledger.reserve(8 * NANO, endpoint="chat", run_attempt=1)
    assert start_gate(ledger, 7 * NANO)
    assert not start_gate(ledger, 7 * NANO + 1)
    assert batch_fits(ledger, [NANO] * 7)
    assert not batch_fits(ledger, [NANO] * 7 + [1])
    assert ledger.open  # neither gate reserves anything
    assert len(ledger.records) == 1
