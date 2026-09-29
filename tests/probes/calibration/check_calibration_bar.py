"""Claim (DESIGN §6.2, PLAN §6/§9): a default threshold is adopted in v1 only if, over >= 1,000 decisions, the
"95% bootstrap upper bound of top-label ECE on the selected option's probability (15 equal-mass bins) is <= 0.05,
AND the observed accuracy of decisions at or above the proposed threshold tau is >= tau - 0.02".

Method: Monte Carlo with Jev-like data.
  * Each decision is a choice over K ~ U{2..10} options. The model's distribution q ~ Dirichlet(alpha * 1_K);
    the REPORTED probabilities are q rounded to 2 dp (as Jev returns them); the selected option is the argmax of
    the reported values; the reported top-label p = round(q_top, 2). alpha is chosen so mass sits at 0.9-1.0 with
    many exact 1.00 values: scenario HEAVY alpha=0.02 (~61% exactly 1.00, ~81% >= 0.90), scenario MODERATE alpha=0.05 (~34% exactly 1.00, ~61% >= 0.90) (histograms printed).
  * Truth: a correct decision ~ Bernoulli(a(p)) with a(p) = q_top (calibrated), clip(q_top - delta) (overconfident
    by delta) or clip(q_top + delta) (underconfident; capped at 1, so 1.00 values cannot be underconfident).
  * ECE estimators, 15 "equal-mass" bins, two readings of the pre-registration:
      RANK  : sort by p (ties broken at random), bin = floor(rank * 15 / n)  -> ties at 1.00 are split across bins
      QEDGE : edges = np.quantile(p, linspace(0,1,16)); bin = #inner edges <= p -> duplicate edges, empty bins
    plus the debiased ECE (Kumar et al. 2019 style) and the percentile-bootstrap upper bound (B = 300; 95th
    percentile = one-sided, 97.5th = two-sided).
  * tau rule: accuracy among p >= tau is >= tau - 0.02 (point estimate), tau in {0.80, 0.90}.
  * Proposed alternative (THRESH-CI): among p >= tau, Wilson 95% lower bound of accuracy >= mean(p | p >= tau) - 0.03,
    AND debiased RANK ECE <= 0.03.
Reports P(pass) per cell over R replicates, at n = 1,000 and 2,000.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import math
import sys

import numpy as np

rng = np.random.default_rng([20260929] + [ord(c) for c in "".join(sys.argv[2:])])
R = int(sys.argv[1]) if len(sys.argv) > 1 else 300
B = 300
NB = 15


def gen(n, alpha):
    K = rng.integers(2, 11, n)
    p_top = np.empty(n)
    q_top = np.empty(n)
    for k in range(2, 11):
        m = K == k
        cnt = m.sum()
        if not cnt:
            continue
        q = rng.dirichlet(np.full(k, alpha), cnt)
        rep = np.round(q, 2)
        sel = rep.argmax(1)
        p_top[m] = rep[np.arange(cnt), sel]
        q_top[m] = q[np.arange(cnt), sel]
    return p_top, q_top


def outcomes(q_top, delta):
    a = np.clip(q_top - delta, 0, 1)
    return (rng.random(len(a)) < a).astype(float)


def rank_bins(n):
    return (np.arange(n) * NB // n)


def ece_rank_batch(P, Y):
    """P, Y: (b, n). Random tie-breaking via jitter; returns plain and debiased ECE per row."""
    b, n = P.shape
    key = P + rng.random(P.shape) * 1e-6
    o = np.argsort(key, axis=1, kind="stable")
    Ps = np.take_along_axis(P, o, 1)
    Ys = np.take_along_axis(Y, o, 1)
    bins = rank_bins(n)
    starts = np.r_[0, np.flatnonzero(np.diff(bins)) + 1]
    cnt = np.diff(np.r_[starts, n])
    sp = np.add.reduceat(Ps, starts, axis=1)
    sy = np.add.reduceat(Ys, starts, axis=1)
    plain = np.abs(sy - sp).sum(1) / n
    acc = sy / cnt
    g2 = (sy / cnt - sp / cnt) ** 2 - acc * (1 - acc) / np.maximum(cnt - 1, 1)
    deb = (cnt * np.sqrt(np.maximum(g2, 0))).sum(1) / n
    return plain, deb


def ece_qedge(p, y):
    edges = np.quantile(p, np.linspace(0, 1, NB + 1))
    idx = np.searchsorted(edges[1:-1], p, side="right")
    e = 0.0
    nonempty = 0
    for b_ in range(NB):
        m = idx == b_
        if m.any():
            nonempty += 1
            e += m.sum() / len(p) * abs(y[m].mean() - p[m].mean())
    return e, nonempty, len(np.unique(edges))


def ece_qedge_batch(P, Y):
    b, n = P.shape
    edges = np.quantile(P, np.linspace(0, 1, NB + 1), axis=1).T  # (b, 16)
    inner = edges[:, 1:-1]
    idx = (P[:, :, None] >= inner[:, None, :]).sum(-1)  # side='right' semantics
    off = idx + (np.arange(b) * NB)[:, None]
    sp = np.bincount(off.ravel(), P.ravel(), minlength=b * NB).reshape(b, NB)
    sy = np.bincount(off.ravel(), Y.ravel(), minlength=b * NB).reshape(b, NB)
    return np.abs(sy - sp).sum(1) / n


def wilson_lo(k, n, z=1.959964):
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h


def describe(alpha, label):
    p, q = gen(200000, alpha)
    h = {">=0.90": (p >= 0.9).mean(), "==1.00": (p == 1.0).mean(), "0.99": (p == 0.99).mean(),
         "<0.80": (p < 0.8).mean(), "<0.60": (p < 0.6).mean()}
    print(f"scenario {label} (alpha={alpha}): " + ", ".join(f"P(p{k})={v:.3f}" for k, v in h.items())
          + f", distinct values={len(np.unique(p))}, mean p={p.mean():.4f}")
    # equal-mass degeneracy on one sample
    y = outcomes(q, 0.0)
    for n in (1000, 2000):
        e, ne, ue = ece_qedge(p[:n], y[:n])
        print(f"   n={n}: QEDGE unique edges {ue}/16, non-empty bins {ne}/15")


def cell(alpha, n, delta):
    res = {k: 0 for k in ("rank_ub95", "rank_ub975", "qedge_ub95", "tau80", "tau90", "bar_rank_tau90",
                          "bar_qedge_tau90", "bar_rank_tau80", "plain_rank_le05", "deb_rank_le03",
                          "alt_tau90", "alt_tau80", "tie_split")}
    stats = {"rank_plain": [], "rank_deb": [], "rank_ub95": [], "qedge_plain": [], "acc90": [], "meanp90": [],
             "n90": [], "gap_all": []}
    for _ in range(R):
        p, q = gen(n, alpha)
        y = outcomes(q, delta)
        plain, deb = ece_rank_batch(p[None, :], y[None, :])
        # repeat RANK with a second random tie-break to measure tie-split sensitivity
        plain2, _ = ece_rank_batch(p[None, :], y[None, :])
        res["tie_split"] += abs(plain2[0] - plain[0]) > 0.002
        qe = ece_qedge_batch(p[None, :], y[None, :])[0]
        idx = rng.integers(0, n, (B, n))
        Pb, Yb = p[idx], y[idx]
        bp, _ = ece_rank_batch(Pb, Yb)
        bq = ece_qedge_batch(Pb, Yb)
        ub95, ub975 = np.quantile(bp, 0.95), np.quantile(bp, 0.975)
        qub95 = np.quantile(bq, 0.95)
        stats["rank_plain"].append(plain[0]); stats["rank_deb"].append(deb[0]); stats["rank_ub95"].append(ub95)
        stats["qedge_plain"].append(qe)
        stats["gap_all"].append(p.mean() - y.mean())
        res["rank_ub95"] += ub95 <= 0.05
        res["rank_ub975"] += ub975 <= 0.05
        res["qedge_ub95"] += qub95 <= 0.05
        res["plain_rank_le05"] += plain[0] <= 0.05
        res["deb_rank_le03"] += deb[0] <= 0.03
        taus = {}
        for tau in (0.80, 0.90):
            m = p >= tau
            acc = y[m].mean()
            taus[tau] = acc >= tau - 0.02
            lo = wilson_lo(y[m].sum(), m.sum())
            alt = (lo >= p[m].mean() - 0.03) and deb[0] <= 0.03
            res["alt_tau80" if tau == 0.8 else "alt_tau90"] += alt
            if tau == 0.9:
                stats["acc90"].append(acc); stats["meanp90"].append(p[m].mean()); stats["n90"].append(m.sum())
        res["tau80"] += taus[0.8]
        res["tau90"] += taus[0.9]
        res["bar_rank_tau90"] += (ub95 <= 0.05) and taus[0.9]
        res["bar_rank_tau80"] += (ub95 <= 0.05) and taus[0.8]
        res["bar_qedge_tau90"] += (qub95 <= 0.05) and taus[0.9]
    return {k: v / R for k, v in res.items()}, {k: float(np.mean(v)) for k, v in stats.items()}


def main():
    """argv: R [scenario n]  -- with scenario/n given, run only that slice (for parallel runs)."""
    print(f"R={R} replicates per cell, B={B} bootstrap resamples, {NB} equal-mass bins")
    SC = {"HEAVY": 0.02, "MODERATE": 0.05}
    NS = (1000, 2000)
    if len(sys.argv) > 3:
        SC = {sys.argv[2]: SC[sys.argv[2]]}
        NS = (int(sys.argv[3]),)
    for lab, a in SC.items():
        describe(a, lab)
    print()
    hdr = ("scen", "n", "delta", "ECEplain", "ECEdeb", "UB95", "QEDGE", "gap", "acc|p>=.9", "mean p|p>=.9",
           "P:UB95<=.05", "P:UB97.5", "P:QEDGE-UB95", "P:tau.8", "P:tau.9", "P:BAR(.9)", "P:BAR(.8)",
           "P:BARqedge(.9)", "P:plainECE<=.05", "P:debECE<=.03", "P:ALT(.9)", "P:ALT(.8)", "P:tiesplit>.002")
    print(" | ".join(hdr))
    for lab, a in SC.items():
        for n in NS:
            for d in (-0.05, -0.02, 0.0, 0.02, 0.05, 0.08):
                r, s = cell(a, n, d)
                print(" | ".join([lab, str(n), f"{d:+.2f}", f"{s['rank_plain']:.4f}", f"{s['rank_deb']:.4f}",
                                  f"{s['rank_ub95']:.4f}", f"{s['qedge_plain']:.4f}", f"{s['gap_all']:+.4f}",
                                  f"{s['acc90']:.4f}", f"{s['meanp90']:.4f}",
                                  f"{r['rank_ub95']:.3f}", f"{r['rank_ub975']:.3f}", f"{r['qedge_ub95']:.3f}",
                                  f"{r['tau80']:.3f}", f"{r['tau90']:.3f}", f"{r['bar_rank_tau90']:.3f}",
                                  f"{r['bar_rank_tau80']:.3f}", f"{r['bar_qedge_tau90']:.3f}",
                                  f"{r['plain_rank_le05']:.3f}", f"{r['deb_rank_le03']:.3f}",
                                  f"{r['alt_tau90']:.3f}", f"{r['alt_tau80']:.3f}", f"{r['tie_split']:.3f}"]),
                      flush=True)


if __name__ == "__main__":
    main()
