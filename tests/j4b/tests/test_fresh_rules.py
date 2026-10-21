"""H2-H8, H32, H33: the bars of the ASTERION-48/-58 pre-registration (design §4.1-§4.2), as `rules.py` builds them.

Every expected boundary comes from the design or from the plan's probes (`S/exp/r48-stats/r10/bounds.out`,
`offsets.out`), never from this module's own arithmetic.
"""

from __future__ import annotations

import math
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.j4b.fresh import rules as R
from tests.j4b.fresh.clustering import deff_paired, deff_single, icc_anova
from tests.j4b.labelling.intervals import Interval, newcombe_paired, wilson

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=200, deadline=None)


def matrices(k: int, m: int, *, worse: int = 0, better: int = 0, worse_size: int | None = None) -> tuple[list, list]:
    """K clusters of m drafts: `worse` clusters where the configuration alone fails `worse_size` drafts (all m by
    default) and `better` clusters where the reference alone fails all m."""
    x = [[0] * m for _ in range(k)]
    b = [[0] * m for _ in range(k)]
    for c in range(worse):
        for j in range(worse_size if worse_size is not None else m):
            x[c][j] = 1
    for c in range(k - better, k):
        b[c] = [1] * m
    return x, b


# --- z values (design §4) ----------------------------------------------------------------------------


def test_z_values_are_computed_one_sided_bonferroni_levels() -> None:
    assert pytest.approx(2.39397979981851, abs=1e-12) == R.Z_48
    assert pytest.approx(2.4977054744123737, abs=1e-12) == R.Z_58T
    assert R.Z_STRATA == R.Z_48
    assert pytest.approx(1.9599639845400534, abs=1e-12) == R.Z_ONE
    assert pytest.approx(2.8727757597822117, abs=1e-12) == R.NI_MULTIPLIER * R.Z_48
    assert pytest.approx(2.351956781448064, abs=1e-12) == R.NI_MULTIPLIER * R.Z_ONE


# --- H2: bar I and the positive control --------------------------------------------------------------


def test_h2_bar_i_passes_only_at_zero_flipped_cells_and_pc_needs_8_of_16() -> None:
    zero, one = R.bar_i(0), R.bar_i(1)
    assert (zero[1], one[1]) == (True, False)
    assert zero[0].high == pytest.approx(0.04522281827822121, abs=1e-12)
    assert one[0].high == pytest.approx(0.059915856834621556, abs=1e-12)
    eight, seven = R.bar_pc(8), R.bar_pc(7)
    assert (eight[1], seven[1]) == (True, False)
    assert eight[0].low == pytest.approx(0.2799956361032602, abs=1e-12)  # reported at z = 1.96, design's 0.280


# --- H3: the cell rule's boundaries with no better pair ----------------------------------------------


@pytest.mark.parametrize(
    ("k", "z", "passing", "failing"),
    [(128, R.Z_48, 0, 1), (128, R.Z_ONE, 1, 2), (96, R.Z_ONE, 0, 1)],
)
def test_h3_cell_rule_boundaries(k: int, z: float, passing: int, failing: int) -> None:
    m = 6 if k == 128 else 4
    assert R.net_cell(*matrices(k, m, worse=passing), z)[2] <= 0.05
    assert R.net_cell(*matrices(k, m, worse=failing), z)[2] > 0.05


# --- H4: the net cell rule (design §4.2, owner answer item 8) ----------------------------------------


@pytest.mark.parametrize(("k", "m"), [(96, 4), (128, 6)])
@pytest.mark.parametrize("z", [R.Z_48, R.Z_ONE])
def test_h4_with_no_better_pair_the_net_rule_is_the_strict_rule(k: int, m: int, z: float) -> None:
    for w in range(k + 1):
        assert R.net_cell(*matrices(k, m, worse=w), z)[2] == pytest.approx(wilson(w, k, z).high, abs=1e-15)


@pytest.mark.parametrize(
    ("w", "v", "passes", "upper"),
    [(3, 5, True, 0.04806), (4, 5, False, 0.05923), (1, 1, True, 0.04949), (6, 10, True, 0.04941),
     (7, 10, False, 0.05966)],
)  # fmt: skip
def test_h4_net_rule_points_at_k128_z_48(w: int, v: int, passes: bool, upper: float) -> None:
    worse, better, bound = R.net_cell(*matrices(128, 6, worse=w, better=v), R.Z_48)
    assert (worse, better) == (w, v)
    assert bound == pytest.approx(upper, abs=5e-6)
    assert (bound <= 0.05) is passes


def test_h4_net_rule_points_at_k96_z_one() -> None:
    assert R.net_cell(*matrices(96, 4, worse=1, better=1), R.Z_ONE)[2] == pytest.approx(0.04713, abs=5e-6)
    assert R.net_cell(*matrices(96, 4, worse=2, better=1), R.Z_ONE)[2] == pytest.approx(0.06322, abs=5e-6)


@pytest.mark.parametrize(
    ("k", "m", "z", "table"),
    [
        (128, 6, R.Z_48, {0: 0, 1: 1, 5: 3, 10: 6}),
        (128, 6, R.Z_ONE, {0: 1, 1: 2, 5: 4, 10: 7}),
        (96, 4, R.Z_ONE, {0: 0, 1: 1, 5: 3, 10: 6}),
    ],
)
def test_h4_the_largest_worse_count_that_passes_for_each_better_count(
    k: int, m: int, z: float, table: dict[int, int]
) -> None:
    for v, largest in table.items():
        passing = [w for w in range(k - v + 1) if R.net_cell(*matrices(k, m, worse=w, better=v), z)[2] <= 0.05]
        assert max(passing) == largest


@pytest.mark.parametrize("m", [6, 4])
def test_h4_half_a_cluster_is_worse_and_minus_half_is_better(m: int) -> None:
    x, b = matrices(10, m, worse=1, worse_size=m // 2)
    assert R.net_cell(x, b, R.Z_48)[:2] == (1, 0)
    x, b = matrices(10, m, worse=1, worse_size=m // 2 - 1)
    assert R.net_cell(x, b, R.Z_48)[:2] == (0, 0)
    x, b = matrices(10, m)
    for j in range(m // 2):
        b[3][j] = 1
    assert R.net_cell(x, b, R.Z_48)[:2] == (0, 1)


# --- H5: the NI-bound multiplier ---------------------------------------------------------------------

FIXTURE_48 = matrices(128, 6, worse=1, worse_size=3, better=1)
"""NI upper 0.04276 at z = 2.394 and 0.06031 at 1.2 z; one worse and one better pair, so the cell rule passes."""
FIXTURE_ONE = matrices(128, 6, worse=2, worse_size=4, better=1)
"""NI upper 0.03993 at z = 1.96 and 0.05236 at 1.2 z; two worse pairs and one better, so the cell rule passes."""


def test_h5_the_five_net_rule_bars_read_their_ni_upper_at_1_2_z() -> None:
    for (x, b), z in ((FIXTURE_48, R.Z_48), (FIXTURE_ONE, R.Z_ONE)):
        at_z = R.ni_paired(x, b, z, ni_z=z, cell=True)
        assert at_z.passed  # the fixture lies between the two bounds
        assert at_z.cell_upper is not None
        assert at_z.cell_upper <= 0.05
        assert R.ni_paired(x, b, z, ni_z=R.NI_MULTIPLIER * z, cell=True).upper_adjusted > 0.05
    assert not R.bar_frr_ni(*FIXTURE_48).passed
    assert not R.bar_fa_ni(*FIXTURE_48, R.Z_48).passed
    for bar in (R.bar_sc_fa, R.bar_fa_s, R.bar_sc_s):
        reading = bar(*FIXTURE_ONE)
        assert not reading.passed
        assert reading.cell_upper == pytest.approx(R.net_cell(*FIXTURE_ONE, R.Z_ONE)[2])  # cell rule at the bar's z
    assert not R.bar_fa_ni(*FIXTURE_ONE, R.Z_ONE).passed


def test_h5_c_ni_b_ni_and_frr_fi_keep_their_own_z() -> None:
    x, b = FIXTURE_48
    for bar in (R.bar_c_ni, R.bar_b_ni):
        reading = bar(x, b, R.Z_48)
        assert reading.passed
        assert reading.cell_upper is None
    both, o1, o2, nei = 0, 3, 6, 768 - 9
    deff = deff_paired(x, b)
    upper, _ = R.bar_frr_fi(x, b)
    assert upper == pytest.approx(newcombe_paired(both / deff, o1 / deff, o2 / deff, nei / deff, z=R.Z_STRATA).high)


# --- H6: design effects ------------------------------------------------------------------------------


def test_h6_term_ii_exceeds_term_i_on_a_whole_cluster_fixture() -> None:
    x, b = matrices(128, 6, worse=4)
    term_i = 1 + 5 * max(icc_anova(x), icc_anova(b))
    assert deff_paired(x, b) > term_i
    assert deff_paired(x, b) == pytest.approx(6.0, rel=0.02)


@DETERMINISTIC
@given(st.integers(1, 400), st.data())
def test_h6_at_deff_1_frr_t_is_the_plain_wilson_bound(n: int, data: st.DataObject) -> None:
    k = data.draw(st.integers(0, n))
    clusters = [[1] * k + [0] * (n - k)]  # one cluster: no between-cluster variance, DEFF = 1 + (n - 1) * 0
    interval, deff, _ = R.bar_frr_t(clusters)
    assert deff == 1.0
    assert interval == wilson(k, n, R.Z_58T)


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        ([[1, 1, 0], [0, 0, 0], [1, 1, 1], [0, 1, 0]], 0.4375),
        ([[1, 0, 1, 0], [0, 1, 0, 1], [1, 0, 0, 1]], 0.0),
        ([[1, 1], [0, 0], [1, 1], [0, 0], [1, 0]], 0.6666666666666667),
        ([[0, 0, 0], [0, 0, 0]], 0.0),
    ],
)
def test_h6_icc_equals_joint_lib_at_equal_sizes_and_is_floored(groups: list[list[int]], expected: float) -> None:
    """`expected` is `joint_lib.icc(groups)` (S/exp/design-ASTERION-48-58/r4/joint_lib.py), hard-coded from
    `B/b2/joint_icc.out`."""
    assert icc_anova(groups) == pytest.approx(expected, abs=1e-12)


def test_h6_unequal_sizes_use_m0_and_single_deff_uses_mean_size() -> None:
    groups = [[1, 1, 1], [0], [1, 0], [0, 0, 0, 0]]
    n, k = 10, 4
    m0 = (n - sum(len(g) ** 2 for g in groups) / n) / (k - 1)
    grand = 4 / n
    msb = sum(len(g) * (sum(g) / len(g) - grand) ** 2 for g in groups) / (k - 1)
    msw = sum(sum((v - sum(g) / len(g)) ** 2 for v in g) for g in groups) / (n - k)
    assert icc_anova(groups) == pytest.approx((msb - msw) / (msb + (m0 - 1) * msw))
    assert deff_single(groups) == pytest.approx(1 + (n / k - 1) * icc_anova(groups))
    assert icc_anova([[1, 0]]) == 0.0


# --- H7: the redraft bar, B-NI and the run-level precondition ---------------------------------------


def rows(*, n: int, rejected: int, a: int, b: int, c: int) -> list[R.RbRow]:
    """`n` first drafts: `rejected` of them rejected, `a` redrafts admitted and true, `b` admitted and violating;
    `c` admitted first drafts violating."""
    out = [R.RbRow(False, False, i < a + b, i < a) for i in range(rejected)]
    out += [R.RbRow(True, i >= c) for i in range(n - rejected)]
    return out


def test_h7_rb_points_and_a_configuration_with_no_rejection_fails_as_not_measurable() -> None:
    assert R.rb_points(rows(n=300, rejected=100, a=10, b=2, c=0)).passed
    assert not R.rb_points(rows(n=300, rejected=100, a=9, b=0, c=0)).passed  # A = 9% < 10%
    nothing = R.rb_points(rows(n=300, rejected=0, a=0, b=0, c=0))
    assert (nothing.passed, nothing.reason, nothing.a) == (False, "A not measurable", None)
    assert (R.rb_run_level(100), R.rb_run_level(99)) == (True, False)


def test_h7_b_ni_reads_documents_at_the_bars_z() -> None:
    x, b = matrices(100, 3)
    assert R.bar_b_ni(x, b, R.Z_48).passed
    x, b = matrices(100, 3, worse=8)
    assert not R.bar_b_ni(x, b, R.Z_48).passed  # 8 of 300 more, d = 0.0267 > 0.02


# --- H8: the shipped-cell gates ----------------------------------------------------------------------


def test_h8_fa_s_reads_one_and_two_worse_pairs_at_z_one() -> None:
    one = R.bar_fa_s(*matrices(128, 6, worse=1, worse_size=3))
    two = R.bar_fa_s(*matrices(128, 6, worse=2, worse_size=3))
    assert one.cell_upper == pytest.approx(0.04293, abs=5e-6)
    assert two.cell_upper == pytest.approx(0.05518, abs=5e-6)
    assert (one.passed, two.passed) == (True, False)


# --- H32: exact point rules --------------------------------------------------------------------------


def test_h32_a_two_point_b_minus_c_passes_exactly() -> None:
    reading = R.rb_points(rows(n=300, rejected=100, a=10, b=5, c=9))
    assert reading.b_minus_c == Fraction(2, 100)
    assert reading.passed
    assert not (0.08 - 0.06 <= 0.02)  # the float comparison the Fraction avoids
    assert R.ni_condition(0, 6, 0, 294, deff=1.0, ni_z=R.Z_ONE) is (
        newcombe_paired(0, 6, 0, 294, z=R.Z_ONE).high <= 0.05
    )
    assert not R.ni_condition(0, 7, 0, 293, deff=1.0, ni_z=1.0)


# --- H33: no complete attempt ------------------------------------------------------------------------


def test_h33_inconclusive_outcomes_name_their_cause() -> None:
    assert R.no_attempt_outcome(["cap stop"], cap_stopped=True) == "inconclusive (spend cap)"
    reasons = ["harness defect: interrupted: no completion marker", "harness defect: replay_miss"]
    assert R.no_attempt_outcome(reasons, cap_stopped=False) == (
        "inconclusive (no complete attempt: harness defect: interrupted: no completion marker; "
        "harness defect: replay_miss)"
    )


def test_r_frr_is_a_deff_adjusted_wilson_at_z_one() -> None:
    clusters = [[1, 0, 0], [0, 0], [1, 1, 0, 0]]
    interval, deff = R.r_frr(clusters)
    assert interval == wilson(3 / deff, 9 / deff, R.Z_ONE)
    assert math.isfinite(deff)


# --- review round 1 (T48-2): DEFF > 1, the pass bits, the point sign, A's numerator and every `<=` boundary ----


def clustered(full: int, single: int, k: int = 128, m: int = 6) -> list[list[int]]:
    """`full` clusters failing all m drafts, `single` failing one draft, the rest none."""
    return [[1] * m if c < full else ([1] + [0] * (m - 1) if c < full + single else [0] * m) for c in range(k)]


def test_frr_t_divides_both_counts_by_a_deff_above_1_and_fails_above_0_25() -> None:
    clusters = clustered(24, 16)
    interval, deff, passed = R.bar_frr_t(clusters)
    assert deff == pytest.approx(5.372839506172839, rel=1e-12)
    assert interval.high == pytest.approx(wilson(160 / deff, 768 / deff, R.Z_58T).high, rel=1e-12)
    assert interval.high == pytest.approx(0.3044708932168011, rel=1e-9)
    assert passed is False


def test_r_frr_divides_both_counts_by_a_deff_above_1() -> None:
    clusters = clustered(12, 0)
    interval, deff = R.r_frr(clusters)
    assert deff == pytest.approx(6.0)
    assert interval.high == pytest.approx(wilson(72 / 6.0, 768 / 6.0, R.Z_ONE).high, rel=1e-12)
    assert interval.high == pytest.approx(0.15672997257307852, rel=1e-9)


def frr_fi_matrices(better: int, both: int, k: int = 32, m: int = 6) -> tuple[list[list[int]], list[list[int]]]:
    """F1 fixes `better` clusters F0 rejects whole; `both` clusters are rejected whole under both forms."""
    x = [[0] * m for _ in range(k)]
    b = [[0] * m for _ in range(k)]
    for c in range(better):
        b[c] = [1] * m
    for c in range(k - both, k):
        x[c] = [1] * m
        b[c] = [1] * m
    return x, b


@pytest.mark.parametrize(
    ("better", "both", "upper", "passed"),
    [(6, 4, -0.0150, True), (6, 0, 0.0051, False), (7, 0, -0.0187, True)],
)
def test_frr_fi_passes_only_below_zero_with_both_rejected_divided_by_deff(
    better: int, both: int, upper: float, passed: bool
) -> None:
    got, ok = R.bar_frr_fi(*frr_fi_matrices(better, both))
    assert got == pytest.approx(upper, abs=1e-4)
    assert ok is passed


def test_the_point_condition_is_the_net_difference_not_the_discordant_total() -> None:
    """(o1 - o2) / n = 0 passes the point; (o1 + o2) / n = 62 / 3000 > 0.02 would not."""
    assert R.ni_condition(0, 31, 31, 2938, deff=1.0, ni_z=R.NI_MULTIPLIER * R.Z_48) is True


def test_rb_a_counts_only_redrafts_both_admitted_and_true() -> None:
    rows = [R.RbRow(False, False, True, False)] * 10 + [R.RbRow(True, True)] * 90
    points = R.rb_points(rows)
    assert points.a == 0
    assert points.passed is False


def test_the_iid_bound_is_reported_at_the_bars_ni_z() -> None:
    x, b = matrices(100, 3, worse=2)
    ni_z = R.NI_MULTIPLIER * R.Z_48
    reading = R.ni_paired(x, b, R.Z_48, ni_z=ni_z, cell=False)
    assert reading.upper_iid == newcombe_paired(*reading.counts, z=ni_z).high
    assert reading.upper_iid != newcombe_paired(*reading.counts).high


def at(high: float) -> Interval:
    return Interval(0.0, 0.0, high)


def test_each_pre_registered_bound_passes_at_equality(monkeypatch: pytest.MonkeyPatch) -> None:
    """The design's `<=` (NI 0.05, the net cell 0.05, bar I 0.05, FRR-T 0.25): a bound exactly at its threshold
    passes. Float counts cannot land on it, so the interval is injected."""
    monkeypatch.setattr(R, "newcombe_paired", lambda *a, **k: at(R.NI_MARGIN))
    assert R.ni_condition(0, 0, 0, 100, deff=1.0, ni_z=1.0) is True
    x, b = matrices(10, 2)
    assert R.ni_paired(x, b, 1.0, ni_z=1.0, cell=True).passed is True
    monkeypatch.setattr(R, "wilson", lambda *a, **k: at(R.NI_MARGIN))
    assert R.bar_i(0)[1] is True
    monkeypatch.setattr(R, "wilson", lambda *a, **k: at(R.FRR_TARGET))
    assert R.bar_frr_t(clustered(0, 1))[2] is True


def test_frr_fi_fails_at_an_upper_of_exactly_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Design §4.1: FRR-Fi passes only when the upper bound is below 0 (strict)."""
    monkeypatch.setattr(R, "newcombe_paired", lambda *a, **k: at(0.0))
    assert R.bar_frr_fi(*frr_fi_matrices(7, 0))[1] is False
