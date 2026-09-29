"""Deterministic case sampling for probes 1-3 (docs/taxonomy.md §2.2 item 8).

Shuffle each pool with the seed; take cases in order, skipping a case whose document already has ``cap`` cases in
that probe; then, while the hard share of all probe 1-3 cases is below ``min_hard``, replace the last-taken non-hard
case of the probe with the lower hard share by the next untaken hard case of that probe (respecting the cap); then,
while fewer than ``min_repeated`` present cases are repeated-text, replace the last-taken non-repeated, non-hard present
case by the next untaken repeated-text case.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol, Sequence

from tests.phase0 import rules as R


class Case(Protocol):
    case_id: str
    doc_id: str
    hard: bool
    repeated: bool


@dataclass
class Draw:
    order: list          # the shuffled pool
    taken: list          # chosen cases, in the order taken
    cap: int
    per_doc: Counter = field(default_factory=Counter)

    def can_take(self, c) -> bool:
        return c not in self.taken and self.per_doc[c.doc_id] < self.cap

    def add(self, c) -> None:
        self.taken.append(c)
        self.per_doc[c.doc_id] += 1

    def remove(self, c) -> None:
        self.taken.remove(c)
        self.per_doc[c.doc_id] -= 1

    def swap(self, pred_out, pred_in) -> bool:
        """Replace the last-taken case matching pred_out by the next untaken case matching pred_in."""
        for out in reversed(self.taken):
            if not pred_out(out):
                continue
            self.remove(out)
            for c in self.order:
                if pred_in(c) and c is not out and self.can_take(c):
                    self.add(c)
                    return True
            self.add(out)
            return False
        return False


def _draw(pool: Sequence, n: int, rng: random.Random, cap: int) -> Draw:
    order = sorted(pool, key=lambda c: c.case_id)
    rng.shuffle(order)
    d = Draw(order, [], cap)
    for c in order:
        if len(d.taken) == n:
            break
        if d.can_take(c):
            d.add(c)
    return d


def _hard_share(*draws: Draw) -> float:
    n = sum(len(d.taken) for d in draws)
    return sum(c.hard for d in draws for c in d.taken) / n if n else 0.0


def sample(present: Sequence, absent: Sequence, n: int = R.N_TARGET, seed: int = R.SEED,
           cap: int = R.MAX_CASES_PER_DOC, min_hard: float = R.MIN_HARD_SHARE,
           min_repeated: int = R.MIN_REPEATED_PRESENT) -> tuple[list, list, dict]:
    rng = random.Random(seed)
    p = _draw(present, n, rng, cap)
    a = _draw(absent, n, rng, cap)
    notes = {"pool_present": len(present), "pool_absent": len(absent), "hard_swaps": 0, "repeated_swaps": 0}
    while _hard_share(p, a) < min_hard:
        share = lambda d: sum(c.hard for c in d.taken) / len(d.taken) if d.taken else 1.0  # noqa: E731
        first, second = sorted((p, a), key=share)
        if not (first.swap(lambda c: not c.hard, lambda c: c.hard)
                or second.swap(lambda c: not c.hard, lambda c: c.hard)):
            notes["hard_shortfall"] = True
            break
        notes["hard_swaps"] += 1
    while sum(c.repeated for c in p.taken) < min_repeated:
        if not p.swap(lambda c: not c.repeated and not c.hard, lambda c: c.repeated):
            notes["repeated_shortfall"] = True
            break
        notes["repeated_swaps"] += 1
    notes.update({"n_present": len(p.taken), "n_absent": len(a.taken), "hard_share": _hard_share(p, a),
                  "hard_present": sum(c.hard for c in p.taken), "hard_absent": sum(c.hard for c in a.taken),
                  "repeated_present": sum(c.repeated for c in p.taken)})
    key = lambda c: c.case_id  # noqa: E731
    return sorted(p.taken, key=key), sorted(a.taken, key=key), notes
