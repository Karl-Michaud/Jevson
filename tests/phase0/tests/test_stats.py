from __future__ import annotations

import math
import random
from fractions import Fraction

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.phase0 import stats as S


# ---------------------------------------------------------------- Wilson

@pytest.mark.parametrize("k,n,lo,hi", [
    (0, 10, 0.0, 0.27753),
    (5, 10, 0.23659, 0.76341),
    (10, 10, 0.72247, 1.0),
    (1, 1, 0.20654, 1.0),
    (0, 1, 0.0, 0.79346),
    (128, 150, 0.78791, 0.90110),     # check_phase0_bands_n150.py, p = 0.85 row [L12]
    (30, 150, 0.14383, 0.27108),      # p = 0.20 row
    (90, 150, 0.52003, 0.67497),      # p = 0.60 row
    (15, 150, 0.06151, 0.15836),      # p = 0.10 row
    (32, 36, 0.74686, 0.95593),       # EVIDENCE P5: 32/36 = 0.89 (0.75-0.96)
])
def test_wilson_reference_values(k, n, lo, hi):
    a, b = S.wilson(k, n)
    assert a == pytest.approx(lo, abs=1e-4)
    assert b == pytest.approx(hi, abs=1e-4)


def test_wilson_half_width_near_085_matches_L12():
    lo, hi = S.wilson(128, 150)
    assert 100 * (hi - lo) / 2 == pytest.approx(5.66, abs=0.005)
    assert 100 * (0.85 - lo) == pytest.approx(6.2, abs=0.05)
    assert 100 * (hi - 0.85) == pytest.approx(5.1, abs=0.05)


def test_wilson_edges_exact():
    assert S.wilson(0, 150)[0] == 0.0
    assert S.wilson(150, 150)[1] == 1.0


@pytest.mark.parametrize("k,n", [(0, 0), (1, 0), (-1, 5), (6, 5)])
def test_wilson_rejects_bad_input(k, n):
    with pytest.raises(ValueError):
        S.wilson(k, n)


@settings(max_examples=400)
@given(st.integers(1, 2000).flatmap(lambda n: st.tuples(st.integers(0, n), st.just(n))))
def test_wilson_property_bounds_and_containment(kn):
    k, n = kn
    lo, hi = S.wilson(k, n)
    assert 0.0 <= lo <= k / n <= hi <= 1.0


# ---------------------------------------------------------------- bands

EDGES = [
    (S.PROBE1, "0.85", "go"), (S.PROBE1, "0.84", "conditional"), (S.PROBE1, "0.86", "go"),
    (S.PROBE1, "0.70", "conditional"), (S.PROBE1, "0.69", "stop"), (S.PROBE1, "0.71", "conditional"),
    (S.PROBE2, "0.80", "go"), (S.PROBE2, "0.79", "conditional"), (S.PROBE2, "0.81", "go"),
    (S.PROBE2, "0.60", "conditional"), (S.PROBE2, "0.59", "stop"), (S.PROBE2, "0.61", "conditional"),
    (S.PROBE3, "0.10", "go"), (S.PROBE3, "0.09", "go"), (S.PROBE3, "0.11", "conditional"),
    (S.PROBE3, "0.20", "conditional"), (S.PROBE3, "0.19", "conditional"), (S.PROBE3, "0.21", "stop"),
]


@pytest.mark.parametrize("band,rate,expected", EDGES)
def test_band_edges_exact_and_one_hundredth_either_side(band, rate, expected):
    assert band.verdict_of(Fraction(rate)) == expected
    assert band.verdict_of(rate) == expected
    assert band.verdict_of(float(rate)) == expected          # 0.85 as a float is not 85/100 in binary
    num = int(Fraction(rate) * 100)
    assert band.verdict(num, 100) == expected
    assert band.verdict(num * 3, 300) == expected


def test_band_extremes():
    assert S.PROBE1.verdict(0, 150) == "stop" and S.PROBE1.verdict(150, 150) == "go"
    assert S.PROBE3.verdict(0, 150) == "go" and S.PROBE3.verdict(150, 150) == "stop"


def test_band_rejects_bad_counts():
    with pytest.raises(ValueError):
        S.PROBE1.verdict(1, 0)
    with pytest.raises(ValueError):
        S.PROBE1.verdict(151, 150)


def test_cutpoints_match_check_phase0_bands_n150():
    c1, c2, c3 = S.PROBE1.cutpoints(150), S.PROBE2.cutpoints(150), S.PROBE3.cutpoints(150)
    assert min(c1["go"]) == 128 and max(c1["stop"]) == 104
    assert min(c2["go"]) == 120 and max(c2["stop"]) == 89
    assert max(c3["go"]) == 15 and min(c3["stop"]) == 31
    for c in (c1, c2, c3):
        assert sorted(sum(c.values(), [])) == list(range(151))


@settings(max_examples=300)
@given(st.integers(1, 400).flatmap(lambda n: st.tuples(st.integers(0, n), st.integers(0, n), st.just(n))))
def test_verdicts_monotone_in_estimate(abn):
    a, b, n = abn
    lo, hi = min(a, b), max(a, b)
    order = {"stop": 0, "conditional": 1, "go": 2}
    for band in (S.PROBE1, S.PROBE2):
        assert order[band.verdict(lo, n)] <= order[band.verdict(hi, n)]
    assert order[S.PROBE3.verdict(lo, n)] >= order[S.PROBE3.verdict(hi, n)]


@pytest.mark.parametrize("c,w,n,expected", [
    (85, 5, 100, "go"), (85, 6, 100, "stop"), (84, 5, 100, "conditional"), (86, 4, 100, "go"),
    (70, 5, 100, "conditional"), (69, 0, 100, "stop"), (71, 5, 100, "conditional"), (100, 0, 100, "go"),
    (90, 4, 100, "go"), (90, 6, 100, "stop"), (0, 0, 100, "stop"),
])
def test_probe4_verdict_edges(c, w, n, expected):
    assert S.probe4_verdict(c, w, n) == expected


@pytest.mark.parametrize("c,w,n", [(1, 1, 0), (-1, 0, 5), (3, 3, 5)])
def test_probe4_verdict_rejects(c, w, n):
    with pytest.raises(ValueError):
        S.probe4_verdict(c, w, n)


# ---------------------------------------------------------------- operating characteristic

L12_OC = [  # (band, true p, go, cond, stop) from check_phase0_bands_n150.py section (3)
    (S.PROBE1, 0.70, 0.000, 0.540, 0.460), (S.PROBE1, 0.75, 0.001, 0.931, 0.068),
    (S.PROBE1, 0.85, 0.511, 0.489, 0.000), (S.PROBE1, 0.90, 0.974, 0.026, 0.000),
    (S.PROBE2, 0.60, 0.000, 0.535, 0.465), (S.PROBE2, 0.80, 0.549, 0.451, 0.000),
    (S.PROBE2, 0.65, 0.000, 0.914, 0.086),
    (S.PROBE3, 0.10, 0.568, 0.432, 0.000), (S.PROBE3, 0.20, 0.001, 0.548, 0.451),
    (S.PROBE3, 0.15, 0.049, 0.913, 0.038),
]


@pytest.mark.parametrize("band,p,go,cond,stop", L12_OC)
def test_oc_reproduces_L12(band, p, go, cond, stop):
    oc = S.operating_characteristic(band, p, 150)
    assert oc["go"] == pytest.approx(go, abs=6e-4)
    assert oc["conditional"] == pytest.approx(cond, abs=6e-4)
    assert oc["stop"] == pytest.approx(stop, abs=6e-4)
    assert sum(oc.values()) == pytest.approx(1.0, abs=1e-9)


def _mc_oc(band, p, n, reps, rng):
    c = {"go": 0, "conditional": 0, "stop": 0}
    for _ in range(reps):
        k = sum(rng.random() < p for _ in range(n))
        c[band.verdict(k, n)] += 1
    return {v: x / reps for v, x in c.items()}


@pytest.mark.parametrize("band,p", [(S.PROBE1, 0.85), (S.PROBE2, 0.60), (S.PROBE3, 0.20)])
def test_oc_matches_independent_monte_carlo(band, p):
    rng = random.Random(7)
    mc = _mc_oc(band, p, 150, 4000, rng)
    exact = S.operating_characteristic(band, p, 150)
    for v in S.VERDICTS:
        assert mc[v] == pytest.approx(exact[v], abs=0.03)


def test_joint_oc_reproduces_L12():
    j = S.joint_oc_probes_1_3(0.85, 0.10, 150)
    assert j[("go", "go")] == pytest.approx(0.436, abs=6e-4)
    assert sum(j.values()) == pytest.approx(1.0, abs=1e-9)
    j2 = S.joint_oc_probes_1_3(0.88, 0.07, 150)
    assert j2[("go", "go")] == pytest.approx(0.852, abs=6e-4)
    j3 = S.joint_oc_probes_1_3(0.70, 0.20, 150)
    assert sum(v for (a, b), v in j3.items() if a == "stop" or b == "stop") == pytest.approx(0.566, abs=6e-4)
    assert sum(v for (a, b), v in j3.items() if b == "stop") == pytest.approx(0.451, abs=6e-4)


def test_joint_oc_matches_monte_carlo():
    rng = random.Random(11)
    reps, n = 3000, 150
    both_go = 0
    for _ in range(reps):
        c = a = 0
        for _ in range(n):
            u = rng.random()
            if u < 0.85:
                c += 1
            elif u < 0.95:
                a += 1
        both_go += S.PROBE1.verdict(c, n) == "go" and S.PROBE3.verdict(a, n) == "go"
    assert both_go / reps == pytest.approx(S.joint_oc_probes_1_3(0.85, 0.10, n)[("go", "go")], abs=0.03)


def test_joint_oc_rejects_and_degenerate():
    with pytest.raises(ValueError):
        S.joint_oc_probes_1_3(0.9, 0.2, 10)
    j = S.joint_oc_probes_1_3(1.0, 0.0, 20)
    assert j[("go", "go")] == pytest.approx(1.0)


def test_correlation_matches_L12():
    assert S.corr_probes_1_3(0.85, 0.10) == pytest.approx(-0.793, abs=5e-4)
    assert S.corr_probes_1_3(0.75, 0.15) == pytest.approx(-0.728, abs=5e-4)


def test_p_abandon_matches_L12_when_probe1_cannot_stop():
    # at true probe-1 accuracy 0.85 probe 1 practically never stops, so this reduces to L12 section (5)
    assert S.p_abandon(0.85, 0.10, 0.60, 150) == pytest.approx(0.465, abs=2e-3)
    assert S.p_abandon(0.80, 0.20, 0.80, 150) == pytest.approx(0.451, abs=5e-3)
    assert S.p_abandon(0.80, 0.10, 0.80, 150, n_absent=150) == pytest.approx(0.001, abs=2e-3)


def test_probe4_oc_sums_to_one_and_is_sensible():
    oc = S.probe4_oc(0.90, 0.01, 120)
    assert sum(oc.values()) == pytest.approx(1.0, abs=1e-9)
    assert oc["go"] > 0.9
    oc2 = S.probe4_oc(0.60, 0.10, 120)
    assert oc2["stop"] > 0.99
    with pytest.raises(ValueError):
        S.probe4_oc(0.9, 0.2, 10)
    assert S.probe4_oc(1.0, 0.0, 10)["go"] == pytest.approx(1.0)


def test_probe4_oc_matches_monte_carlo():
    rng = random.Random(5)
    reps, n = 3000, 120
    cnt = {"go": 0, "conditional": 0, "stop": 0}
    for _ in range(reps):
        c = w = 0
        for _ in range(n):
            u = rng.random()
            if u < 0.85:
                c += 1
            elif u < 0.88:
                w += 1
        cnt[S.probe4_verdict(c, w, n)] += 1
    exact = S.probe4_oc(0.85, 0.03, n)
    for v in S.VERDICTS:
        assert cnt[v] / reps == pytest.approx(exact[v], abs=0.03)


def test_binom_pmf_outside_support():
    assert S.binom_pmf(-1, 5, 0.5) == 0.0 and S.binom_pmf(6, 5, 0.5) == 0.0


# ---------------------------------------------------------------- kappa

def _table(counts):
    a, b = [], []
    for (x, y), c in counts.items():
        a += [x] * c
        b += [y] * c
    return a, b


def test_kappa_known_tables():
    a, b = _table({("y", "y"): 20, ("y", "n"): 5, ("n", "y"): 10, ("n", "n"): 15})
    assert S.cohen_kappa(a, b) == pytest.approx(0.4)
    a, b = _table({("y", "y"): 45, ("y", "n"): 15, ("n", "y"): 25, ("n", "n"): 15})
    assert S.cohen_kappa(a, b) == pytest.approx(0.1304, abs=1e-4)
    a, b = _table({("y", "y"): 25, ("y", "n"): 35, ("n", "y"): 5, ("n", "n"): 35})
    assert S.cohen_kappa(a, b) == pytest.approx(0.2593, abs=1e-4)
    # three categories (Fleiss, Levin & Paik style table)
    a, b = _table({("a", "a"): 88, ("a", "b"): 14, ("a", "c"): 18, ("b", "a"): 10, ("b", "b"): 40,
                   ("b", "c"): 10, ("c", "a"): 2, ("c", "b"): 6, ("c", "c"): 12})
    po = (88 + 40 + 12) / 200
    pe = (120 * 100 + 60 * 60 + 20 * 40) / 200**2
    assert S.cohen_kappa(a, b) == pytest.approx((po - pe) / (1 - pe))


def test_kappa_perfect_and_constant_and_errors():
    assert S.cohen_kappa(["a", "b", "a"], ["a", "b", "a"]) == pytest.approx(1.0)
    assert S.cohen_kappa(["a", "a"], ["a", "a"]) == 1.0
    assert S.cohen_kappa(["a", "b"], ["b", "a"]) == pytest.approx(-1.0)
    with pytest.raises(ValueError):
        S.cohen_kappa([], [])
    with pytest.raises(ValueError):
        S.cohen_kappa(["a"], ["a", "b"])


# ---------------------------------------------------------------- calibration

def test_tie_safe_bins_never_split_ties():
    ps = [1.0] * 50 + [0.9] * 10 + [0.5 + i / 100 for i in range(40)]
    bins = S.tie_safe_bins(ps, 15)
    seen = {}
    for bi, b in enumerate(bins):
        for i in b:
            seen.setdefault(ps[i], set()).add(bi)
    assert all(len(v) == 1 for v in seen.values())
    assert sorted(i for b in bins for i in b) == list(range(len(ps)))
    assert len(bins) < 15


def test_tie_safe_bins_equal_mass_on_distinct_values():
    ps = [i / 150 for i in range(150)]
    bins = S.tie_safe_bins(ps, 15)
    assert len(bins) == 15 and all(len(b) == 10 for b in bins)
    with pytest.raises(ValueError):
        S.tie_safe_bins([], 15)


def test_ece_brier_reliability():
    ps = [0.9] * 10 + [0.6] * 10
    ys = [1] * 9 + [0] + [1] * 6 + [0] * 4
    assert S.ece(ps, ys) == pytest.approx(0.0)
    ys2 = [1] * 10 + [1] * 10
    assert S.ece(ps, ys2) == pytest.approx(0.5 * 0.1 + 0.5 * 0.4)
    assert S.brier([1.0, 0.0], [1, 0]) == 0.0
    assert S.brier([0.5], [1]) == 0.25
    rows = S.reliability_table(ps, ys)
    assert [r["n"] for r in rows] == [10, 10] and rows[1]["accuracy"] == pytest.approx(0.9)
    with pytest.raises(ValueError):
        S.ece([0.5], [1, 0])
    with pytest.raises(ValueError):
        S.brier([], [])


def test_ece_bootstrap_upper_bound_is_above_point_and_deterministic():
    rng = random.Random(3)
    ps = [rng.choice([0.6, 0.7, 0.8, 0.9, 1.0]) for _ in range(300)]
    ys = [int(rng.random() < p) for p in ps]
    point = S.ece(ps, ys)
    ub = S.ece_bootstrap_upper(ps, ys, n_boot=300, seed=1)
    assert ub >= point - 1e-12
    assert ub == S.ece_bootstrap_upper(ps, ys, n_boot=300, seed=1)


def test_rate_summary():
    r = S.rate_summary(128, 150, S.PROBE1, ties=3)
    assert r["verdict"] == "go" and r["tie_rate"] == pytest.approx(0.02)
    assert r["wilson_lo"] == pytest.approx(0.78791, abs=1e-4)
    assert "verdict" not in S.rate_summary(1, 2)


def test_float_rates_are_read_as_decimals():
    assert S._frac(0.85) == Fraction(85, 100)
    assert math.isclose(float(S._frac("0.1")), 0.1)
