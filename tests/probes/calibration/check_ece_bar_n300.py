"""Claim: DESIGN §6.2 / PLAN §6, §9, Phase 5 — pre-registered bar "ECE <= 0.05 over >= 300 candidate-backed
decisions" decides whether a default confidence threshold is adopted in v1.

Method: Monte Carlo. Confidences drawn from realistic distributions (Beta concentrated in 0.8–1.0, and a
wider one). Outcomes ~ Bernoulli(true accuracy), where true accuracy = confidence (perfectly calibrated) or
confidence - delta (overconfident by delta). Measure top-label ECE with 10 and 15 equal-width bins, n in
{100, 300, 1000, 3000}. Report the sampling distribution of measured ECE, P(fail | calibrated), P(pass |
miscalibrated), and compare a debiased estimator (Kumar et al. 2019 style: subtract per-bin binomial
variance) and a bootstrap-CI rule (pass iff upper 95% bound of ECE <= 0.05 ... or of |mean gap|).
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import numpy as np

rng = np.random.default_rng(12345)
R = 4000

def ece(conf, y, bins):
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(conf, edges[1:-1]), 0, bins - 1)
    n = len(conf); e = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            e += m.sum() / n * abs(y[m].mean() - conf[m].mean())
    return e

def ece_debiased(conf, y, bins):
    """Squared-gap debiasing: sum_b w_b * sqrt(max(0,(acc-conf)^2 - acc(1-acc)/(n_b-1)))."""
    edges = np.linspace(0, 1, bins + 1)
    idx = np.clip(np.digitize(conf, edges[1:-1]), 0, bins - 1)
    n = len(conf); e = 0.0
    for b in range(bins):
        m = idx == b; nb = m.sum()
        if nb > 1:
            a = y[m].mean(); g2 = (a - conf[m].mean()) ** 2 - a * (1 - a) / (nb - 1)
            e += nb / n * np.sqrt(max(g2, 0.0))
    return e

dists = {
    "Beta(18,2) mean .90 (mass .8–1.0)": lambda n: rng.beta(18, 2, n),
    "Uniform(.5,1) wider": lambda n: rng.uniform(0.5, 1.0, n),
}
print(f"R={R} Monte Carlo replicates per cell. Pass = measured ECE <= 0.05")
for dname, draw in dists.items():
    print(f"\n### confidence ~ {dname}")
    for bins in (10, 15):
        print(f"  bins={bins}")
        for n in (100, 300, 1000, 3000):
            row = []
            for delta in (0.0, 0.03, 0.05, 0.08, 0.10):
                es, ed = np.empty(R), np.empty(R)
                for r in range(R):
                    c = draw(n); acc = np.clip(c - delta, 0, 1); y = (rng.random(n) < acc).astype(float)
                    es[r] = ece(c, y, bins)
                    if n == 300: ed[r] = ece_debiased(c, y, bins)
                pas = np.mean(es <= 0.05)
                s = f"δ={delta:.2f}: ECE mean {es.mean():.3f} [p5 {np.percentile(es,5):.3f}, p95 {np.percentile(es,95):.3f}] P(pass)={pas:.3f}"
                if n == 300:
                    s += f" | debiased mean {ed.mean():.3f} P(pass)={np.mean(ed<=0.05):.3f}"
                row.append(s)
            print(f"    n={n}")
            for s in row: print("      " + s)
