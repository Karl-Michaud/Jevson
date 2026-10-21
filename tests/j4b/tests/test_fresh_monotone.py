"""H10: monotonicity where it holds, and the two pinned counter-examples where it does not (plan §11 D9).

The pre-registered DEFF-adjusted rule is applied exactly as written; these tests record that it is not monotone in
counts, rather than "fixing" it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.j4b.fresh import rules as R
from tests.j4b.fresh.clustering import deff_paired
from tests.j4b.labelling.intervals import newcombe_paired, wilson

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=300, deadline=None)
KNOWN = json.loads((Path(__file__).parent / "data" / "h10_known.json").read_text(encoding="utf-8"))


@DETERMINISTIC
@given(st.sampled_from([(96, R.Z_ONE), (128, R.Z_48), (128, R.Z_ONE)]), st.data())
def test_h10a_the_net_cell_bound_rises_with_worse_pairs_and_falls_with_better_ones(
    case: tuple[int, float], data: st.DataObject
) -> None:
    k, z = case
    w = data.draw(st.integers(0, k - 1))
    v = data.draw(st.integers(0, k - 1 - w))

    def upper(w: int, v: int) -> float:
        return newcombe_paired(0, w, v, k - w - v, z=z).high

    assert upper(w + 1, v) >= upper(w, v) - 1e-15
    if w + v + 1 <= k:
        assert upper(w, v + 1) <= upper(w, v) + 1e-15


@DETERMINISTIC
@given(st.integers(0, 120), st.integers(0, 15), st.floats(1.0, 8.0), st.integers(0, 767))
def test_h10b_bar_i_pc_and_frr_t_at_a_fixed_deff_are_monotone(flipped: int, pc: int, deff: float, k: int) -> None:
    assert R.bar_i(flipped + 1)[0].high >= R.bar_i(flipped)[0].high
    assert R.bar_pc(pc + 1)[1] >= R.bar_pc(pc)[1]
    assert wilson((k + 1) / deff, 768 / deff, R.Z_58T).high >= wilson(k / deff, 768 / deff, R.Z_58T).high


@DETERMINISTIC
@given(
    st.integers(0, 60), st.integers(0, 20), st.integers(0, 20), st.floats(1.0, 8.0),
    st.sampled_from([R.Z_ONE, R.Z_48, R.NI_MULTIPLIER * R.Z_ONE, R.NI_MULTIPLIER * R.Z_48]),
)  # fmt: skip
def test_h10c_moving_a_draft_from_neither_to_config_only_never_turns_ni_fail_into_pass(
    both: int, o1: int, o2: int, deff: float, ni_z: float
) -> None:
    nei = 768 - both - o1 - o2
    before = R.ni_condition(both, o1, o2, nei, deff=deff, ni_z=ni_z)
    after = R.ni_condition(both, o1 + 1, o2, nei - 1, deff=deff, ni_z=ni_z)
    assert not (after and not before)


def test_h10_known_2_the_o2_to_both_move_can_shrink_the_bound_at_a_fixed_deff() -> None:
    ni_z = R.NI_MULTIPLIER * R.Z_48
    before = newcombe_paired(0 / 6, 0 / 6, 8 / 6, 760 / 6, z=ni_z).high
    after = newcombe_paired(1 / 6, 0 / 6, 7 / 6, 760 / 6, z=ni_z).high
    assert before == pytest.approx(0.050837, abs=5e-7)
    assert after == pytest.approx(0.049984, abs=5e-7)
    assert not R.ni_condition(0, 0, 8, 760, deff=6.0, ni_z=ni_z)
    assert R.ni_condition(1, 0, 7, 760, deff=6.0, ni_z=ni_z)


def test_h10_known_one_added_failure_lowers_deff_and_turns_frr_ni_from_fail_to_pass() -> None:
    x, b = KNOWN["x"], KNOWN["b"]
    assert KNOWN["z"] == pytest.approx(R.Z_48, abs=1e-12)
    after = [row[:] for row in x]
    assert after[KNOWN["cluster"]][KNOWN["draft"]] == 0
    after[KNOWN["cluster"]][KNOWN["draft"]] = 1
    assert (deff_paired(x, b), deff_paired(after, b)) == pytest.approx(KNOWN["deff_before_after"])
    before_reading, after_reading = R.bar_frr_ni(x, b), R.bar_frr_ni(after, b)
    assert before_reading.upper_adjusted == pytest.approx(0.05383, abs=5e-6)
    assert after_reading.upper_adjusted == pytest.approx(0.04819, abs=5e-6)
    assert not before_reading.passed
    assert after_reading.passed
    at_bar_z = [R.ni_paired(m, b, R.Z_48, ni_z=R.Z_48, cell=True) for m in (x, after)]
    assert [r.passed for r in at_bar_z] == [True, True]  # at z = 2.394 the same fixture passes both times
