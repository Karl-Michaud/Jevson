from __future__ import annotations

from fractions import Fraction

import pytest

from tests.phase0 import floor as F


def test_grid_is_plan_grid():
    assert F.FLOOR_GRID == (5, 10, 15, 20, 25, 30, 35, 40, 45)


def test_grid_top_binds_when_everything_qualifies():
    sel = F.select_floor([90] * 100)
    assert sel.floor == 45 and sel.grid_top_binds and not sel.stop
    assert sel.qualifying == F.FLOOR_GRID


def test_no_value_qualifies_gives_005_and_stop():
    sel = F.select_floor([3] * 3 + [90] * 97)      # 3% of same pairs at or below 0.05
    assert sel.floor == 5 and sel.stop and not sel.grid_top_binds and sel.qualifying == ()


def test_exactly_two_percent_qualifies_and_just_above_does_not():
    same = [20, 20] + [90] * 98                    # 2/100 at or below 0.20..0.45
    sel = F.select_floor(same)
    assert sel.share_at_or_below[20] == Fraction(2, 100)
    assert sel.floor == 45 and sel.qualifying == F.FLOOR_GRID
    same2 = [20, 20, 40] + [90] * 97               # 3/100 at or below 0.40 -> 0.40 and 0.45 fail
    sel2 = F.select_floor(same2)
    assert sel2.floor == 35 and not sel2.grid_top_binds
    assert sel2.share_at_or_below[40] == Fraction(3, 100)


def test_boundary_inclusive_at_or_below():
    # a pair exactly at a grid value counts as at-or-below that value
    same = [25, 25, 25] + [90] * 97
    sel = F.select_floor(same)
    assert sel.floor == 20 and sel.share_at_or_below[25] == Fraction(3, 100)


def test_rule_takes_largest_even_if_non_contiguous():
    # the share is monotone in the floor, so the qualifying set is always a prefix of the grid
    same = [12] * 2 + [33] * 1 + [90] * 97
    sel = F.select_floor(same)
    assert sel.qualifying == (5, 10, 15, 20, 25, 30) and sel.floor == 30


def test_empty_rejected():
    with pytest.raises(ValueError):
        F.select_floor([])


def test_variant_lower_wrong_wins():
    assert F.choose_variant(F.VariantScore(100, 90, 3), F.VariantScore(100, 85, 1)) == "cross"
    assert F.choose_variant(F.VariantScore(100, 90, 1), F.VariantScore(100, 85, 3)) == "internal"


def test_variant_equal_wrong_breaks_on_correct():
    assert F.choose_variant(F.VariantScore(100, 90, 1), F.VariantScore(100, 85, 1)) == "internal"
    assert F.choose_variant(F.VariantScore(100, 80, 1), F.VariantScore(100, 85, 1)) == "cross"


def test_variant_full_tie_keeps_internal_and_rates_not_counts():
    assert F.choose_variant(F.VariantScore(100, 90, 1), F.VariantScore(100, 90, 1)) == "internal"
    # equal rates with different denominators are equal
    assert F.choose_variant(F.VariantScore(100, 90, 2), F.VariantScore(50, 45, 1)) == "internal"


def test_variant_rejects_empty():
    with pytest.raises(ValueError):
        F.choose_variant(F.VariantScore(0, 0, 0), F.VariantScore(1, 1, 0))
