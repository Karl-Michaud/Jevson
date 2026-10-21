"""The spend ledger (design §6.3; FEAS48-3, FEAS48-5, ARCH48-R6-8): reserve-then-settle, the cap in one place."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from tests.j4b.fresh.constants import CAP, NANO
from tests.j4b.fresh.spend import Settled, SpendCapReached, SpendLedger


def test_reserve_and_settle_are_written_and_fsynced_in_order(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    a = ledger.reserve(5 * NANO, endpoint="chat", run_attempt=1)
    assert ledger.open == {a: 5 * NANO}
    ledger.settle(a, 2 * NANO, status=200, retry_after=None, model="gpt-5.4-mini-2026-03-17")
    records = [json.loads(line) for line in (tmp_path / "spend.jsonl").read_text().splitlines()]
    assert [(r["seq"], r["type"]) for r in records] == [(0, "reserve"), (1, "settle")]
    assert (ledger.billed, ledger.open) == (2 * NANO, {})
    assert [s.model for s in ledger.settles()] == ["gpt-5.4-mini-2026-03-17"]
    assert list(ledger.settles(since=2)) == []


def test_fits_counts_billed_open_reservations_and_the_new_bound_against_15_dollars(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    ledger.reserve(10 * NANO, endpoint="decisions", run_attempt=1)
    assert ledger.fits(5 * NANO)
    assert not ledger.fits(5 * NANO + 1)
    assert CAP == 15 * NANO


def test_a_refused_reservation_stops_the_run_and_is_not_an_httpx_error(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    ledger.reserve(CAP - NANO // 100, endpoint="chat", run_attempt=1)
    with pytest.raises(SpendCapReached) as raised:
        ledger.reserve(NANO // 100 + 1, endpoint="chat", run_attempt=1)
    assert not isinstance(raised.value, httpx.HTTPError)
    assert ledger.stopped


def test_after_a_crash_an_open_reservation_is_charged_at_its_full_bound(tmp_path: Path) -> None:
    crashed = SpendLedger(tmp_path)
    crashed.reserve(3 * NANO, endpoint="chat", run_attempt=1)
    settled = crashed.reserve(2 * NANO, endpoint="chat", run_attempt=1)
    crashed.settle(settled, NANO // 2, status=200, retry_after=None, model="m")
    reopened = SpendLedger(tmp_path)
    assert reopened.billed == 3 * NANO + NANO // 2
    assert reopened.open == {}


# --- review round 2 (T48-9): the file's name and format, the refusal's text, every settled field ------------


def test_the_ledger_is_spend_jsonl_one_sorted_json_object_per_line(tmp_path: Path) -> None:
    root = tmp_path / "run" / "attempt-1"
    ledger = SpendLedger(root)
    a = ledger.reserve(5 * NANO, endpoint="chat", run_attempt=1)
    ledger.settle(a, 2 * NANO, status=429, retry_after=3.0, model="m")
    assert [p.name for p in root.iterdir()] == ["spend.jsonl"]
    lines = (root / "spend.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines == [json.dumps(r, sort_keys=True) for r in ledger.records]
    assert lines[0] == (
        f'{{"attempt_id": "{a}", "bound": {5 * NANO}, "endpoint": "chat", "run_attempt": 1, "seq": 0, '
        '"type": "reserve"}'
    )
    assert list(ledger.settles()) == [Settled(1, a, "chat", 2 * NANO, 429, 3.0, "m", 1)]


def test_a_refused_reservation_states_its_bound_and_the_cap(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    ledger.reserve(CAP - NANO // 100, endpoint="chat", run_attempt=1)
    with pytest.raises(SpendCapReached, match=r"^an attempt bounded at \$0\.0123 would pass the \$15\.00 cap$"):
        ledger.reserve(123 * NANO // 10_000, endpoint="chat", run_attempt=1)
