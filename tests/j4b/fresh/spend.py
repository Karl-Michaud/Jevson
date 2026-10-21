"""The spend ledger: the $15 cap over every attempt, reserved before and settled after each HTTP attempt
(design §6.3; plan §4.1 `spend.py`, FEAS48-3, ARCH48-R6-8).

`spend.jsonl` under the run root is append-only, each record `fsync`ed: a `reserve` (the attempt's bound) before
the POST and a `settle` (what it billed, its status, its `Retry-After`, the returned `model`) after it. On opening,
a `reserve` with no `settle` (a crash with a call in flight) is charged at its full bound, as a failed attempt is.
Amounts are integer nano-dollars, so the cap arithmetic is exact. The cap arithmetic lives here once: `fits`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tests.j4b.fresh.constants import CAP, NANO


class SpendCapReached(Exception):
    """An HTTP attempt that would take spend past the cap is refused before it is sent."""


@dataclass(frozen=True)
class Settled:
    seq: int
    attempt_id: str
    endpoint: str
    billed: int
    status: int | None
    retry_after: float | None
    model: str | None
    run_attempt: int


class SpendLedger:
    """Spend so far over every attempt, plus the reservations of HTTP attempts in flight."""

    def __init__(self, root: Path, cap: int = CAP) -> None:
        self.path = root / "spend.jsonl"
        self.cap = cap
        self.records: list[dict[str, Any]] = []
        if self.path.exists():
            self.records = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]
        settled = {r["attempt_id"] for r in self.records if r["type"] == "settle"}
        self.billed = sum(r["billed"] for r in self.records if r["type"] == "settle")
        self.billed += sum(
            r["bound"] for r in self.records if r["type"] == "reserve" and r["attempt_id"] not in settled
        )
        self.open: dict[str, int] = {}
        self.stopped = False
        """Set when a reservation is refused at the cap: how the runner tells a cap stop from a network failure."""
        self.violation: str | None = None
        """Set when a response's reported usage exceeds its reserved bound: the attempt is void."""

    def fits(self, bound: int) -> bool:
        """Spend billed so far + every open reservation + `bound` <= the cap."""
        return self.billed + sum(self.open.values()) + bound <= self.cap

    def reserve(self, bound: int, *, endpoint: str, run_attempt: int) -> str:
        """Reserve `bound` for one HTTP attempt, only if it fits; otherwise stop and raise `SpendCapReached`."""
        if not self.fits(bound):
            self.stopped = True
            raise SpendCapReached(
                f"an attempt bounded at ${bound / NANO:.4f} would pass the ${self.cap / NANO:.2f} cap"
            )
        attempt_id = f"a{len(self.records)}"
        self._append(
            {
                "type": "reserve",
                "attempt_id": attempt_id,
                "bound": bound,
                "endpoint": endpoint,
                "run_attempt": run_attempt,
            }
        )
        self.open[attempt_id] = bound
        return attempt_id

    def settle(
        self, attempt_id: str, billed: int, *, status: int | None, retry_after: float | None, model: str | None
    ) -> None:
        reserved = next(r for r in self.records if r["type"] == "reserve" and r["attempt_id"] == attempt_id)
        self._append(
            {
                "type": "settle",
                "attempt_id": attempt_id,
                "billed": billed,
                "status": status,
                "retry_after": retry_after,
                "model": model,
                "endpoint": reserved["endpoint"],
                "run_attempt": reserved["run_attempt"],
            }
        )
        self.open.pop(attempt_id, None)
        self.billed += billed

    def position(self) -> int:
        """The next record's sequence number: a unit's start position for the re-queue window."""
        return len(self.records)

    def settles(self, since: int = 0) -> Iterator[Settled]:
        for record in self.records[since:]:
            if record["type"] == "settle":
                yield Settled(
                    record["seq"],
                    record["attempt_id"],
                    record["endpoint"],
                    record["billed"],
                    record["status"],
                    record["retry_after"],
                    record["model"],
                    record["run_attempt"],
                )

    def _append(self, record: dict[str, Any]) -> None:
        record = {"seq": len(self.records), **record}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self.records.append(record)
