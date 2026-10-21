"""The decision rules of the ASTERION-48/-58 pre-registration (design §4), as pure functions over counts and
aligned per-cluster 0/1 matrices. No I/O: the matrices come only from `bar_inputs.py`.

- z values are computed, never typed: one-sided at 1 - 0.025/k (k = 3 arms, 4 library arms for FRR-T, 3 strata,
  1 for a single guard). The NI-bound multiplier 1.2 applies to the unrounded z (2.8728 and 2.3520 are displays).
- Point rules are exact (`Fraction`): A >= 10%, B - C <= 2 points, the paired point d <= +0.02. Interval bounds
  stay in float and are compared with the design's real thresholds.
- The DEFF-adjusted rule is not monotone in counts (plan §11 D9): an added failure can lower DEFF, and even at a
  fixed DEFF the Newcombe paired bound can shrink when a failure lands on a draft the reference also fails. The
  rule is applied exactly as written.
- `adopt_48` and `decide_58` (design §4.4) read every bar through `Readings`, against the reference `REFERENCE`
  fixes. A void attempt's partial inputs are not `Readings`, so they can never reach a decision.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from statistics import NormalDist
from typing import Any

from tests.j4b import injection
from tests.j4b.fresh.clustering import Matrix, deff_paired, deff_single, net_counts, paired_counts
from tests.j4b.labelling.intervals import Interval, newcombe_paired, wilson

_ND = NormalDist()
Z_48 = _ND.inv_cdf(1 - 0.025 / 3)
Z_58T = _ND.inv_cdf(1 - 0.025 / 4)
Z_STRATA = _ND.inv_cdf(1 - 0.025 / 3)
Z_ONE = _ND.inv_cdf(1 - 0.025)
NI_MULTIPLIER = 1.2
NI_MARGIN = 0.05
POINT_MARGIN = Fraction(2, 100)
FRR_TARGET = 0.25
G_CELLS = 121
REPLICA_CASES, PC_MIN_FLIPS = 16, 8
RB_MIN_REJECTED = 100
A_FLOOR = Fraction(1, 10)

Config = tuple[str, str]
"""(library arm, criterion form): ("L0", "F0") ... ("L3", "F1")."""
L0F0: Config = ("L0", "F0")
ARMS_48 = ("L2", "L1", "L3")
"""Adoption order (design §4.4): M2, M1, M1+M2."""


@dataclass(frozen=True)
class NiReading:
    """One paired bar: its counts, the point d, DEFF, the iid and adjusted upper bounds, and the net cell rule."""

    counts: tuple[int, int, int, int]
    point: Fraction
    deff: float
    upper_iid: float
    upper_adjusted: float
    worse: int
    better: int
    cell_upper: float | None
    passed: bool


def ni_condition(both: int, o1: int, o2: int, nei: int, *, deff: float, ni_z: float) -> bool:
    """Point d <= +0.02 (exact) and the Newcombe paired upper of the counts divided by `deff`, at `ni_z`, <= 0.05."""
    if Fraction(o1 - o2, both + o1 + o2 + nei) > POINT_MARGIN:
        return False
    return newcombe_paired(both / deff, o1 / deff, o2 / deff, nei / deff, z=ni_z).high <= NI_MARGIN


def net_cell(x: Matrix, b: Matrix, z: float) -> tuple[int, int, float]:
    """(W, V, upper): a cluster is worse when 2 D_c >= m_c and better when -2 D_c >= m_c; the rule passes iff
    newcombe_paired(0, W, V, K - W - V, z).high <= 0.05, on raw cluster counts (design §4.2)."""
    sizes = [len(c) for c in x]
    d = net_counts(x, b)
    worse = sum(2 * dc >= m for dc, m in zip(d, sizes, strict=True))
    better = sum(-2 * dc >= m for dc, m in zip(d, sizes, strict=True))
    return worse, better, newcombe_paired(0, worse, better, len(x) - worse - better, z=z).high


def ni_paired(x: Matrix, b: Matrix, z: float, *, ni_z: float, cell: bool) -> NiReading:
    """A paired NI bar: `ni_condition` at the paired DEFF and `ni_z`, and, when `cell`, the net cell rule at `z`."""
    both, o1, o2, nei = counts = paired_counts(x, b)
    n = both + o1 + o2 + nei
    deff = deff_paired(x, b)
    adjusted = newcombe_paired(both / deff, o1 / deff, o2 / deff, nei / deff, z=ni_z).high
    worse, better, cell_upper = net_cell(x, b, z) if cell else (0, 0, None)
    passed = ni_condition(both, o1, o2, nei, deff=deff, ni_z=ni_z) and (cell_upper is None or cell_upper <= NI_MARGIN)
    iid = newcombe_paired(both, o1, o2, nei, z=ni_z).high
    return NiReading(counts, Fraction(o1 - o2, n), deff, iid, adjusted, worse, better, cell_upper, passed)


def bar_net(x: Matrix, b: Matrix, z: float) -> NiReading:
    """FRR-NI, FA-NI, SC-FA, FA-S and SC-S: the NI upper at 1.2 z, the point and the net cell rule at z."""
    return ni_paired(x, b, z, ni_z=NI_MULTIPLIER * z, cell=True)


def bar_document(x: Matrix, b: Matrix, z: float) -> NiReading:
    """C-NI and B-NI: document clusters, the NI upper at the bar's own z, no cell rule."""
    return ni_paired(x, b, z, ni_z=z, cell=False)


def bar_frr_ni(x: Matrix, b: Matrix) -> NiReading:
    """FRR-NI (ASTERION-48): PASS drafts rejected, arm vs (L0, F0), z = 2.394."""
    return bar_net(x, b, Z_48)


def bar_fa_ni(x: Matrix, b: Matrix, z: float) -> NiReading:
    """FA-NI: FAIL drafts admitted; z = 2.394 for ASTERION-48, 1.96 for ASTERION-58."""
    return bar_net(x, b, z)


def bar_sc_fa(x: Matrix, b: Matrix) -> NiReading:
    """SC-FA (ASTERION-58): targeted-self-claim FAIL drafts admitted, (arm, F1) vs (arm, F0), z = 1.96."""
    return bar_net(x, b, Z_ONE)


def bar_fa_s(x: Matrix, b: Matrix) -> NiReading:
    """FA-S: the shipped cell's FAIL drafts admitted vs (L0, F0), z = 1.96."""
    return bar_net(x, b, Z_ONE)


def bar_sc_s(x: Matrix, b: Matrix) -> NiReading:
    """SC-S: the shipped cell's targeted-self-claim FAIL drafts admitted vs (L0, F0), z = 1.96."""
    return bar_net(x, b, Z_ONE)


def bar_c_ni(x: Matrix, b: Matrix, z: float) -> NiReading:
    """C-NI: first drafts admitted while violating (grader truth against F0), vs (L0, F0)."""
    return bar_document(x, b, z)


def bar_b_ni(x: Matrix, b: Matrix, z: float) -> NiReading:
    """B-NI: first drafts rejected whose redraft was admitted while violating, vs (L0, F0)."""
    return bar_document(x, b, z)


def bar_i(flipped_cells: int, g: int = G_CELLS) -> tuple[Interval, bool]:
    """Bar I: Wilson upper (z = 2.394) of flipped cells / 121 <= 0.05 (holds only at 0 flipped cells)."""
    interval = wilson(flipped_cells, g, Z_48)
    return interval, interval.high <= NI_MARGIN


def bar_pc(l0_flipped_replica_cases: int) -> tuple[Interval, bool]:
    """PC: L0 flips at least 8 of the replica's 16 cases; the reported Wilson lower bound is at z = 1.96."""
    return wilson(l0_flipped_replica_cases, REPLICA_CASES, Z_ONE), l0_flipped_replica_cases >= PC_MIN_FLIPS


def bar_frr_t(clusters: Matrix) -> tuple[Interval, float, bool]:
    """FRR-T: Wilson upper of FRR at counts / DEFF, z = 2.4977, <= 0.25."""
    deff = deff_single(clusters)
    k, n = sum(sum(c) for c in clusters), sum(len(c) for c in clusters)
    interval = wilson(k / deff, n / deff, Z_58T)
    return interval, deff, interval.high <= FRR_TARGET


def bar_fx(cases: list[dict[str, Any]], judged: Mapping[str, Mapping[str, Mapping[str, bool]]]) -> bool:
    """FX: the [P7] regression, `injection.regression` unchanged (at most 3 flipped cases of 80)."""
    return bool(injection.regression(cases, judged)["passed"])


def r_frr(clusters: Matrix) -> tuple[Interval, float]:
    """R-FRR, reported only: FRR over R-set first drafts graded true, DEFF-adjusted Wilson at z = 1.96."""
    deff = deff_single(clusters)
    k, n = sum(sum(c) for c in clusters), sum(len(c) for c in clusters)
    return wilson(k / deff, n / deff, Z_ONE), deff


def bar_frr_fi(x_f1: Matrix, b_f0: Matrix) -> tuple[float, bool]:
    """FRR-Fi: the DEFF-adjusted Newcombe paired upper of FRR(F1) - FRR(F0), z = 2.394, is below 0."""
    both, o1, o2, nei = paired_counts(x_f1, b_f0)
    deff = deff_paired(x_f1, b_f0)
    upper = newcombe_paired(both / deff, o1 / deff, o2 / deff, nei / deff, z=Z_STRATA).high
    return upper, upper < 0


@dataclass(frozen=True)
class RbRow:
    """One R-set first draft under one configuration, with grader truth against F0 (design §3)."""

    first_admitted: bool
    first_true: bool
    redraft_admitted: bool = False
    redraft_true: bool = False


@dataclass(frozen=True)
class RbPoints:
    rejected: int
    first_drafts: int
    a: Fraction | None
    b_minus_c: Fraction | None
    passed: bool
    reason: str


def rb_points(rows: Sequence[RbRow]) -> RbPoints:
    """A >= 10% and B - C <= 2 points, as score.py defines them: a null redraft is not admitted, C is over every
    admitted first draft (no sampling factor). With no rejected first draft, A is not measurable and it fails."""
    n = len(rows)
    rejected = [r for r in rows if not r.first_admitted]
    c = sum(r.first_admitted and not r.first_true for r in rows)
    if not rejected:
        return RbPoints(0, n, None, None, False, "A not measurable")
    a = Fraction(sum(r.redraft_admitted and r.redraft_true for r in rejected), len(rejected))
    b = Fraction(sum(r.redraft_admitted and not r.redraft_true for r in rejected), len(rejected))
    b_minus_c = b - Fraction(c, n)
    passed = a >= A_FLOOR and b_minus_c <= POINT_MARGIN
    return RbPoints(len(rejected), n, a, b_minus_c, passed, "" if passed else "A or B - C outside the bar")


def rb_run_level(l0f0_rejected: int) -> bool:
    """RB is measurable on this run only if (L0, F0) rejects at least 100 first drafts (design §4.4)."""
    return l0f0_rejected >= RB_MIN_REJECTED


REFERENCE: Mapping[tuple[str, str], str] = {
    ("48", "FRR-NI"): "L0F0",
    ("48", "FA-NI"): "L0F0",
    ("48", "C-NI"): "L0F0",
    ("48", "B-NI"): "L0F0",
    ("58", "FA-NI"): "armF0",
    ("58", "SC-FA"): "armF0",
    ("58", "C-NI"): "L0F0",
    ("58", "B-NI"): "L0F0",
    ("58", "FA-S"): "L0F0",
    ("58", "SC-S"): "L0F0",
}
"""Each bar's reference (design §4.4, last bullet): (L0, F0), or the same library arm under F0."""


def reference(ticket: str, bar: str, arm: str) -> Config:
    return L0F0 if REFERENCE[(ticket, bar)] == "L0F0" else (arm, "F0")


class Readings(ABC):
    """The bars of one complete, non-void attempt, read by `adopt_48` and `decide_58` only through these methods."""

    @abstractmethod
    def paired(self, bar: str, config: Config, ref: Config, *, z: float, ni_z: float, cell: bool) -> bool: ...
    @abstractmethod
    def frr_t(self, config: Config, z: float) -> bool: ...
    @abstractmethod
    def frr_fi(self, arm: str, z: float) -> Mapping[str, bool]: ...
    @abstractmethod
    def rb_points(self, config: Config) -> bool: ...
    @abstractmethod
    def rb_rejected(self, config: Config) -> int: ...
    @abstractmethod
    def bar_i(self, arm: str) -> bool: ...
    @abstractmethod
    def pc(self) -> bool: ...
    @abstractmethod
    def fx(self, arm: str) -> bool: ...


def _net(readings: Readings, ticket: str, bar: str, config: Config, z: float) -> bool:
    ref = reference(ticket, bar, config[0])
    return readings.paired(bar, config, ref, z=z, ni_z=NI_MULTIPLIER * z, cell=True)


def _doc(readings: Readings, ticket: str, bar: str, config: Config, z: float) -> bool:
    return readings.paired(bar, config, reference(ticket, bar, config[0]), z=z, ni_z=z, cell=False)


def _require(readings: object) -> Readings:
    if not isinstance(readings, Readings):
        raise TypeError(f"a decision reads a complete attempt's Readings, not {type(readings).__name__}")
    return readings


RB_NOT_MEASURABLE = "inconclusive (RB not measurable)"


def adopt_48(readings: Readings) -> tuple[str | None, str]:
    """(adopted arm or None, outcome). The first arm in the order L2, L1, L3 that passes PC, I, FX, FRR-NI, FA-NI,
    RB points, C-NI and B-NI, all under F0; a failed PC makes bar I inconclusive and adopts nothing."""
    r = _require(readings)
    if not rb_run_level(r.rb_rejected(L0F0)):
        return None, RB_NOT_MEASURABLE
    if not r.pc():
        return None, "I inconclusive (positive control failed)"
    for arm in ARMS_48:
        config = (arm, "F0")
        gates = (
            r.bar_i(arm) and r.fx(arm),
            _net(r, "48", "FRR-NI", config, Z_48) and _net(r, "48", "FA-NI", config, Z_48),
            r.rb_points(config),
            _doc(r, "48", "C-NI", config, Z_48) and _doc(r, "48", "B-NI", config, Z_48),
        )
        if all(gates):
            return arm, f"met: {arm} adopted"
    return None, "not met: no arm passes every bar"


def decide_58(readings: Readings, adopted: str | None) -> tuple[Config | None, str, tuple[str, ...]]:
    """(shipped cell or None, outcome, the strata whose rewrite guidance is kept), by outcomes 1-5 of §4.4.

    Guidance for rewrite Fi is kept only where FRR-Fi passes, as part of an adopted F1 candidate (outcome 1 with
    FA-S and SC-S passing, and outcome 2); on every other outcome F1 is not adopted and no guidance is kept."""
    r = _require(readings)
    if not rb_run_level(r.rb_rejected(L0F0)):
        return None, RB_NOT_MEASURABLE, ()
    arm = adopted or "L0"
    candidate: Config = (arm, "F1")
    if not r.frr_t(candidate, Z_58T):
        return None, "not met: FRR-T (the measured rate is v0's documented limit, owner sign-off)", ()
    guards = {
        "FA-NI": _net(r, "58", "FA-NI", candidate, Z_ONE),
        "SC-FA": _net(r, "58", "SC-FA", candidate, Z_ONE),
        "RB": r.rb_points(candidate),
        "C-NI": _doc(r, "58", "C-NI", candidate, Z_ONE),
        "B-NI": _doc(r, "58", "B-NI", candidate, Z_ONE),
    }
    failed = [name for name, ok in guards.items() if not ok]
    if failed:
        return None, f"not met: guard {', '.join(failed)} failed; F1 not adopted", ()
    if adopted is None:
        return candidate, "FRR target met; injection clause not met, because of the library arm, not F1", _kept(r, arm)
    if _net(r, "58", "FA-S", candidate, Z_ONE) and _net(r, "58", "SC-S", candidate, Z_ONE):
        return candidate, "met: ship (arm, F1)", _kept(r, arm)
    return (adopted, "F0"), "ship (arm, F0); ASTERION-58 not met: combined FA rise", ()


def _kept(r: Readings, arm: str) -> tuple[str, ...]:
    return tuple(sorted(s for s, ok in r.frr_fi(arm, Z_STRATA).items() if ok))


def no_attempt_outcome(void_reasons: Sequence[str], *, cap_stopped: bool) -> str:
    """The outcome for both tickets when no complete non-void attempt exists (design §6.4; plan §11 D19)."""
    if cap_stopped:
        return "inconclusive (spend cap)"
    return f"inconclusive (no complete attempt: {'; '.join(void_reasons)})"
