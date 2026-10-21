"""Design effects for clustered binary outcomes (ASTERION-48/-58 pre-registration §4.2).

Every count a bar reads is divided by a design effect (DEFF) before its interval is computed. The independent unit
is a cluster: a P-set template pair or an R-set document. A matrix is one row per cluster of 0/1 outcomes (1 = the
error the bar counts); in a paired bar the configuration's matrix `x` and the reference's `b` are aligned draft by
draft. Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence

Matrix = Sequence[Sequence[int]]


def icc_anova(clusters: Matrix) -> float:
    """The one-way ANOVA intraclass correlation of a binary outcome, floored at 0.

    Equal cluster sizes give exactly the design's `joint_lib.icc`. Unequal sizes (R-FRR, and a void attempt's
    partial report) use the standard m0 = (N - sum n_i^2 / N) / (K - 1), which is m at equal sizes (plan §11 D7).
    Fewer than two clusters, or no within-cluster degrees of freedom, give 0."""
    k = len(clusters)
    n = sum(len(c) for c in clusters)
    if k < 2 or n <= k:
        return 0.0
    grand = sum(sum(c) for c in clusters) / n
    msb = sum(len(c) * (sum(c) / len(c) - grand) ** 2 for c in clusters if c) / (k - 1)
    msw = sum(sum((v - sum(c) / len(c)) ** 2 for v in c) for c in clusters if c) / (n - k)
    m0 = (n - sum(len(c) ** 2 for c in clusters) / n) / (k - 1)
    den = msb + (m0 - 1) * msw
    return 0.0 if den == 0 else max(0.0, (msb - msw) / den)


def deff_single(clusters: Matrix) -> float:
    """DEFF = 1 + (m - 1) * rho for one proportion, m = n / clusters (design §4.2)."""
    n = sum(len(c) for c in clusters)
    return 1 + (n / len(clusters) - 1) * icc_anova(clusters)


def paired_counts(x: Matrix, b: Matrix) -> tuple[int, int, int, int]:
    """(both, only the configuration, only the reference, neither) over aligned drafts."""
    both = only_x = only_b = neither = 0
    for xs, bs in zip(x, b, strict=True):
        for xv, bv in zip(xs, bs, strict=True):
            both += xv & bv
            only_x += xv & (1 - bv)
            only_b += bv & (1 - xv)
            neither += (1 - xv) & (1 - bv)
    return both, only_x, only_b, neither


def net_counts(x: Matrix, b: Matrix) -> list[int]:
    """D_c per cluster: drafts the configuration gets wrong and the reference right, minus the reverse."""
    return [sum(xs) - sum(bs) for xs, bs in zip(x, b, strict=True)]


def deff_paired(x: Matrix, b: Matrix) -> float:
    """The larger of (i) 1 + (m - 1) * max(rho_x, rho_b) and (ii) the paired difference's cluster-robust variance
    over its iid variance, K/(K-1) * sum (D_c - m_c d)^2 / n^2 / (((o1 + o2)/n - d^2)/n); term (ii) only when its
    denominator is positive, as `joint_lib.ni` computes it (design §4.2)."""
    k = len(x)
    n = sum(len(c) for c in x)
    _, o1, o2, _ = paired_counts(x, b)
    d = (o1 - o2) / n
    deff = 1 + (n / k - 1) * max(icc_anova(x), icc_anova(b))
    iid = ((o1 + o2) / n - d * d) / n
    if iid > 0 and k > 1:
        spread = sum((dc - len(xs) * d) ** 2 for dc, xs in zip(net_counts(x, b), x, strict=True))
        deff = max(deff, k / (k - 1) * spread / n**2 / iid)
    return deff
