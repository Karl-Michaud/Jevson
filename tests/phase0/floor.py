"""The two probe 4 selection rules, exactly as PLAN Phase 0 fixes them before the data is seen.

conflict_floor: "the largest value in {0.05, 0.10, …, 0.45} such that same-entity pairs at or below it are
<= 2% of all same-entity pairs; if no value qualifies, the floor is 0.05 and probe 4 is recorded as stop;
whether the grid top binds is recorded."

Variant: "the one with the lower silently-wrong point estimate; if equal, the one with more correct
components." A further tie (possible only when both counts are equal) keeps the internal rule, which is
always on (DESIGN §5.7); this tie-break was fixed with the rules, before any probe ran.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, Sequence

FLOOR_GRID: tuple[int, ...] = (5, 10, 15, 20, 25, 30, 35, 40, 45)   # hundredths
MAX_SAME_AT_OR_BELOW = Fraction(2, 100)
FALLBACK_FLOOR = 5

Variant = Literal["internal", "cross"]


@dataclass(frozen=True)
class FloorSelection:
    floor: int                      # hundredths
    qualifying: tuple[int, ...]     # every grid value meeting the 2% condition
    share_at_or_below: dict[int, Fraction]
    grid_top_binds: bool            # the rule selected the top of the grid
    stop: bool                      # no value qualified: floor 0.05 and probe 4 is stop


def select_floor(same_entity_pairs: Sequence[int]) -> FloorSelection:
    """same_entity_pairs: p(same) in hundredths for every gold same-entity pair (both runs pooled)."""
    if not same_entity_pairs:
        raise ValueError("no same-entity pairs")
    n = len(same_entity_pairs)
    share = {g: Fraction(sum(p <= g for p in same_entity_pairs), n) for g in FLOOR_GRID}
    ok = tuple(g for g in FLOOR_GRID if share[g] <= MAX_SAME_AT_OR_BELOW)
    if not ok:
        return FloorSelection(FALLBACK_FLOOR, ok, share, False, True)
    chosen = max(ok)
    return FloorSelection(chosen, ok, share, chosen == FLOOR_GRID[-1], False)


@dataclass(frozen=True)
class VariantScore:
    components: int
    correct: int
    silently_wrong: int

    def wrong_rate(self) -> Fraction:
        return Fraction(self.silently_wrong, self.components)

    def correct_rate(self) -> Fraction:
        return Fraction(self.correct, self.components)


def choose_variant(internal: VariantScore, cross: VariantScore) -> Variant:
    if internal.components <= 0 or cross.components <= 0:
        raise ValueError("no components scored")
    if internal.wrong_rate() != cross.wrong_rate():
        return "internal" if internal.wrong_rate() < cross.wrong_rate() else "cross"
    if internal.correct_rate() != cross.correct_rate():
        return "internal" if internal.correct_rate() > cross.correct_rate() else "cross"
    return "internal"
