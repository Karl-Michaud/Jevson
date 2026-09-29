"""Statistics behind the Phase 0 verdicts (PLAN Phase 0, "Decision rule, pre-registered").

- Wilson 95% intervals.
- Band verdicts on the point estimate, compared exactly (``Fraction``), never in floating point.
- The operating characteristic: the probability of each verdict at a true rate, by exact binomial or
  multinomial enumeration, including the joint verdicts of probes 1 and 3, which share their cases.
- Cohen's kappa for the second-labeller agreement.
- The probe 7 calibration reading: tie-safe equal-mass bins, ECE with a one-sided bootstrap bound, Brier.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from statistics import NormalDist
from typing import Literal, Sequence

Z95 = NormalDist().inv_cdf(0.975)
Verdict = Literal["go", "conditional", "stop"]
VERDICTS: tuple[Verdict, ...] = ("go", "conditional", "stop")


def wilson(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for k successes in n trials."""
    if n <= 0:
        raise ValueError("n must be positive")
    if not 0 <= k <= n:
        raise ValueError("k must lie in [0, n]")
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    # the endpoints are exact at k = 0 and k = n; float error would otherwise put 0 just outside the interval
    lo = 0.0 if k == 0 else min(p, max(0.0, c - h))
    hi = 1.0 if k == n else max(p, min(1.0, c + h))
    return lo, hi


def _frac(x: Fraction | int | float | str) -> Fraction:
    # float -> Fraction via its decimal repr, so 0.85 means 85/100, not the nearest binary double
    return Fraction(str(x)) if isinstance(x, float) else Fraction(x)


@dataclass(frozen=True)
class Band:
    """A pre-registered verdict band.

    Higher is better: go iff rate >= go; stop iff rate < stop; otherwise conditional.
    Lower is better:  go iff rate <= go; stop iff rate > stop; otherwise conditional.
    """

    name: str
    higher_is_better: bool
    go: Fraction
    stop: Fraction

    def verdict_of(self, rate: Fraction | int | float | str) -> Verdict:
        r = _frac(rate)
        if self.higher_is_better:
            if r >= self.go:
                return "go"
            return "stop" if r < self.stop else "conditional"
        if r <= self.go:
            return "go"
        return "stop" if r > self.stop else "conditional"

    def verdict(self, k: int, n: int) -> Verdict:
        if n <= 0 or not 0 <= k <= n:
            raise ValueError("need 0 <= k <= n and n > 0")
        return self.verdict_of(Fraction(k, n))

    def cutpoints(self, n: int) -> dict[Verdict, list[int]]:
        """Every k in [0, n], grouped by the verdict its point estimate receives."""
        out: dict[Verdict, list[int]] = {v: [] for v in VERDICTS}
        for k in range(n + 1):
            out[self.verdict(k, n)].append(k)
        return out


PROBE1 = Band("probe 1: disambiguation accuracy", True, Fraction(85, 100), Fraction(70, 100))
PROBE2 = Band("probe 2: abstention sensitivity", True, Fraction(80, 100), Fraction(60, 100))
PROBE3 = Band("probe 3: false abstention", False, Fraction(10, 100), Fraction(20, 100))
PROBE4_CORRECT_GO = Fraction(85, 100)
PROBE4_CORRECT_STOP = Fraction(70, 100)
PROBE4_WRONG_MAX = Fraction(5, 100)


def probe4_verdict(correct: int, silently_wrong: int, n: int) -> Verdict:
    """Probe 4: go iff correct >= 0.85 and silently wrong <= 0.05; stop iff correct < 0.70 or
    silently wrong > 0.05; otherwise conditional."""
    if n <= 0 or correct < 0 or silently_wrong < 0 or correct + silently_wrong > n:
        raise ValueError("need correct + silently_wrong <= n and n > 0")
    c, w = Fraction(correct, n), Fraction(silently_wrong, n)
    if c < PROBE4_CORRECT_STOP or w > PROBE4_WRONG_MAX:
        return "stop"
    return "go" if c >= PROBE4_CORRECT_GO else "conditional"


# ---------------------------------------------------------------- operating characteristic

def binom_pmf(k: int, n: int, p: float) -> float:
    if not 0 <= k <= n:
        return 0.0
    return math.comb(n, k) * p**k * (1 - p) ** (n - k)


def operating_characteristic(band: Band, p: float, n: int) -> dict[Verdict, float]:
    """P(verdict) when the true rate is p and n cases are scored."""
    out = {v: 0.0 for v in VERDICTS}
    for k in range(n + 1):
        out[band.verdict(k, n)] += binom_pmf(k, n, p)
    return out


def joint_oc_probes_1_3(p_correct: float, p_abstain: float, n: int,
                        band1: Band = PROBE1, band3: Band = PROBE3) -> dict[tuple[Verdict, Verdict], float]:
    """Joint verdicts of probes 1 and 3 on the same n present-answer cases.

    Each case is correct, abstained, or something else (wrong commit or tie), a multinomial; probe 1 scores
    correct, probe 3 scores abstained. Exact enumeration."""
    if p_correct < 0 or p_abstain < 0 or p_correct + p_abstain > 1 + 1e-12:
        raise ValueError("probabilities must be non-negative and sum to at most 1")
    rest = max(0.0, 1 - p_correct - p_abstain)
    q = p_abstain / (p_abstain + rest) if p_abstain + rest > 0 else 0.0
    out: dict[tuple[Verdict, Verdict], float] = {(a, b): 0.0 for a in VERDICTS for b in VERDICTS}
    for c in range(n + 1):
        pc = binom_pmf(c, n, p_correct)
        if pc == 0.0:
            continue
        v1 = band1.verdict(c, n)
        for a in range(n - c + 1):
            out[(v1, band3.verdict(a, n))] += pc * binom_pmf(a, n - c, q)
    return out


def corr_probes_1_3(p_correct: float, p_abstain: float) -> float:
    """Correlation of the two point estimates under the multinomial (negative)."""
    return -math.sqrt(p_correct * p_abstain / ((1 - p_correct) * (1 - p_abstain)))


def p_abandon(p_correct: float, p_abstain_present: float, p_abstain_absent: float, n: int,
              n_absent: int | None = None) -> float:
    """P(the abandon criterion fires): probe 1 stop, probe 2 stop, or probe 3 stop.

    Probes 1 and 3 are joint (shared cases); probe 2 runs on disjoint documents and is independent."""
    j = joint_oc_probes_1_3(p_correct, p_abstain_present, n)
    no_stop_13 = sum(v for (a, b), v in j.items() if a != "stop" and b != "stop")
    s2 = operating_characteristic(PROBE2, p_abstain_absent, n_absent or n)["stop"]
    return 1 - no_stop_13 * (1 - s2)


def probe4_oc(p_correct: float, p_wrong: float, n: int) -> dict[Verdict, float]:
    """Probe 4 verdict probabilities for n scored components (correct / unresolved / silently wrong)."""
    if p_correct < 0 or p_wrong < 0 or p_correct + p_wrong > 1 + 1e-12:
        raise ValueError("probabilities must be non-negative and sum to at most 1")
    rest = max(0.0, 1 - p_correct - p_wrong)
    q = p_wrong / (p_wrong + rest) if p_wrong + rest > 0 else 0.0
    out = {v: 0.0 for v in VERDICTS}
    for c in range(n + 1):
        pc = binom_pmf(c, n, p_correct)
        if pc == 0.0:
            continue
        for w in range(n - c + 1):
            out[probe4_verdict(c, w, n)] += pc * binom_pmf(w, n - c, q)
    return out


# ---------------------------------------------------------------- agreement

def cohen_kappa(a: Sequence[str], b: Sequence[str]) -> float:
    """Cohen's kappa for two raters' categorical labels on the same items.

    When both raters use one identical category for every item, chance agreement is 1 and kappa is
    undefined; it is reported as 1.0 (perfect agreement)."""
    if len(a) != len(b) or not a:
        raise ValueError("need two equal-length, non-empty label sequences")
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum(ca[c] * cb[c] for c in set(ca) | set(cb)) / (n * n)
    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


# ---------------------------------------------------------------- calibration (probe 7)

def tie_safe_bins(ps: Sequence[float], n_bins: int = 15) -> list[list[int]]:
    """Equal-mass bins from quantile edges, merged so that equal probabilities are never split.

    The upper edge of bin j is the value at sorted position ceil(j * n / n_bins); duplicate edges merge
    their bins, so there may be fewer than n_bins. Returns item indices per bin, ascending by value."""
    n = len(ps)
    if n == 0 or n_bins < 1:
        raise ValueError("need at least one probability and one bin")
    s = sorted(ps)
    edges = sorted({s[max(0, math.ceil(j * n / n_bins) - 1)] for j in range(1, n_bins + 1)})
    bins: list[list[int]] = [[] for _ in edges]
    for i, p in enumerate(ps):
        lo, hi = 0, len(edges) - 1
        while lo < hi:  # first edge >= p
            mid = (lo + hi) // 2
            if edges[mid] >= p:
                hi = mid
            else:
                lo = mid + 1
        bins[lo].append(i)
    return [b for b in bins if b]


def ece(ps: Sequence[float], ys: Sequence[int], n_bins: int = 15) -> float:
    if len(ps) != len(ys):
        raise ValueError("ps and ys differ in length")
    n = len(ps)
    total = 0.0
    for b in tie_safe_bins(ps, n_bins):
        mp = sum(ps[i] for i in b) / len(b)
        acc = sum(ys[i] for i in b) / len(b)
        total += len(b) / n * abs(mp - acc)
    return total


def ece_bootstrap_upper(ps: Sequence[float], ys: Sequence[int], n_boot: int = 2000, seed: int = 20260929,
                        n_bins: int = 15, level: float = 0.95) -> float:
    """One-sided bootstrap upper bound of ECE (resample items, re-bin each replicate)."""
    rng = random.Random(seed)
    n = len(ps)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(ece([ps[i] for i in idx], [ys[i] for i in idx], n_bins))
    vals.sort()
    return vals[math.ceil(level * n_boot) - 1]


def brier(ps: Sequence[float], ys: Sequence[int]) -> float:
    if len(ps) != len(ys) or not ps:
        raise ValueError("need equal-length, non-empty sequences")
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def reliability_table(ps: Sequence[float], ys: Sequence[int], n_bins: int = 15) -> list[dict]:
    rows = []
    for b in tie_safe_bins(ps, n_bins):
        k = sum(ys[i] for i in b)
        lo, hi = wilson(k, len(b))
        rows.append({"p_min": min(ps[i] for i in b), "p_max": max(ps[i] for i in b), "n": len(b),
                     "mean_p": sum(ps[i] for i in b) / len(b), "accuracy": k / len(b),
                     "wilson_lo": lo, "wilson_hi": hi})
    return rows


# ---------------------------------------------------------------- summaries

def rate_summary(k: int, n: int, band: Band | None = None, ties: int = 0) -> dict:
    """The row every probe reports: n, point estimate, Wilson 95% interval, verdict band, tie rate."""
    lo, hi = wilson(k, n)
    out = {"k": k, "n": n, "rate": k / n, "wilson_lo": lo, "wilson_hi": hi,
           "ties": ties, "tie_rate": ties / n}
    if band is not None:
        out["verdict"] = band.verdict(k, n)
        out["band"] = band.name
    return out
