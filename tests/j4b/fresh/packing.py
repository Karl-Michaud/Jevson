"""The pinned packing of both phases into batches (design §6.3 batch rule; STATS48-R6-4, FEAS48-R8-1).

Configuration phase: the I-set, [P7], P-set and R-set units are listed in that order; each set's (case,
configuration) list is first shuffled by its own `random.Random(20261019)`; the concatenation is then shuffled by
`random.Random(4858)` and cut into consecutive batches of at most 10 units. Drafting phase: the phase's documents
in `picked.json` order, shuffled by `random.Random(4858)`, cut into batches of at most 10 documents (one document's
three first drafts are one unit). One batch is in flight at a time.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tests.j4b.fresh.constants import BATCH_UNITS, PACKING_SEEDS

SET_ORDER = ("iset", "p7", "pset", "rset")


@dataclass(frozen=True)
class Unit:
    """One (case, configuration) pair: an I-set case, a [P7] case, a P-set draft or an R-set document."""

    set_name: str
    key: str
    arm: str
    form: str

    @property
    def config(self) -> tuple[str, str]:
        return (self.arm, self.form)


def configuration_batches(units: Mapping[str, Sequence[Unit]]) -> list[list[Unit]]:
    """The configuration phase's batches, by the pinned two-seed algorithm."""
    per_set, pooled_seed = PACKING_SEEDS
    pooled: list[Unit] = []
    for name in SET_ORDER:
        shuffled = list(units.get(name, ()))
        random.Random(per_set).shuffle(shuffled)
        pooled += shuffled
    random.Random(pooled_seed).shuffle(pooled)
    return [pooled[i : i + BATCH_UNITS] for i in range(0, len(pooled), BATCH_UNITS)]


def drafting_batches(doc_ids: Sequence[str]) -> list[list[str]]:
    """The drafting phase's batches: documents in file order, shuffled by `random.Random(4858)`, cut by 10."""
    docs = list(doc_ids)
    random.Random(PACKING_SEEDS[1]).shuffle(docs)
    return [docs[i : i + BATCH_UNITS] for i in range(0, len(docs), BATCH_UNITS)]
