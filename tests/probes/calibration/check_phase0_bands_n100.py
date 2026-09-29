"""Claim: PLAN Phase 0 — "n = 100 gives a 95% interval of roughly ±8–10 points — enough to separate the
bands"; "n = 20 would give ±20 points and could not distinguish go from stop". Bands: probe 1 go>=0.85,
cond 0.70–0.85, stop<0.70; probe 2 go>=0.80, cond 0.60–0.80, stop<0.60; probe 3 go<=0.10, cond 0.10–0.20,
stop>0.20; probe 4 50 clusters go>=0.85 cond 0.70-0.85.

Method: exact binomial. Compute Wald and Wilson 95% half-widths at several p for n=100, 20, 50; then for each
probe and a grid of TRUE rates, the exact probability that the observed rate lands in go / conditional /
stop (point-estimate classification, as the plan implies). Also: the minimum n at which a true rate
sitting 0.05 inside a band is classified correctly with >= 80% / 90% probability.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import numpy as np
from scipy.stats import binom, norm

z = norm.ppf(0.975)
def wald(p, n): return z * np.sqrt(p * (1 - p) / n)
def wilson(k, n):
    ph = k / n; d = 1 + z**2 / n
    c = (ph + z**2 / (2 * n)) / d; h = z * np.sqrt(ph * (1 - ph) / n + z**2 / (4 * n**2)) / d
    return c - h, c + h

print("95% half-widths (percentage points):")
print(" n    p     wald   wilson(lo,hi around p)")
for n in (20, 50, 100):
    for p in (0.05, 0.10, 0.5, 0.7, 0.8, 0.85, 0.9, 0.95):
        lo, hi = wilson(round(p * n), n)
        print(f" {n:<4} {p:<5} ±{100*wald(p,n):5.1f}  [{100*lo:5.1f},{100*hi:5.1f}] width {100*(hi-lo):5.1f}")

def classify_probs(n, true, go, stop, higher_better=True):
    k = np.arange(n + 1); pmf = binom.pmf(k, n, true); r = k / n
    if higher_better:
        g = pmf[r >= go - 1e-12].sum(); s = pmf[r < stop - 1e-12].sum()
    else:
        g = pmf[r <= go + 1e-12].sum(); s = pmf[r > stop + 1e-12].sum()
    return g, 1 - g - s, s

probes = {"P1 accuracy": (0.85, 0.70, True, 100), "P2 abstention": (0.80, 0.60, True, 100),
          "P3 false-abst": (0.10, 0.20, False, 100), "P4 entity(50)": (0.85, 0.70, True, 50)}
grids = {"P1 accuracy": [0.95, 0.90, 0.87, 0.85, 0.80, 0.75, 0.70, 0.65],
         "P2 abstention": [0.90, 0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55],
         "P3 false-abst": [0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.25],
         "P4 entity(50)": [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.65]}
for name, (go, stop, hb, n) in probes.items():
    print(f"\n{name}: n={n}, go {'>=' if hb else '<='}{go}, stop {'<' if hb else '>'}{stop}")
    for t in grids[name]:
        g, c, s = classify_probs(n, t, go, stop, hb)
        print(f"   true={t:.2f}  P(go)={g:.3f}  P(cond)={c:.3f}  P(stop)={s:.3f}")

print("\nP3 at n=100: Wilson interval when observed = 10/100:", [round(x, 3) for x in wilson(10, 100)],
      "; observed 5/100:", [round(x, 3) for x in wilson(5, 100)])
print("P3 with the ~5% wrong-span allowance: P1 go (>=0.85) + P3 go (<=0.10) jointly")

# Required n so a true rate 0.05 inside the go band (P1 true=0.90) is called go w.p. >= 0.8/0.9, and true
# 0.05 inside stop (0.65) is called stop w.p. >= 0.8/0.9
def need(true, go, stop, want, which):
    for n in range(20, 3000, 5):
        g, c, s = classify_probs(n, true, go, stop, True)
        v = g if which == "go" else s
        if v >= want: return n
for want in (0.8, 0.9):
    print(f"min n: P1 true .90 called go w.p.>={want}: {need(0.90, .85, .70, want, 'go')};"
          f"  true .65 called stop w.p.>={want}: {need(0.65, .85, .70, want, 'stop')}")

# Does n=20 "fail to distinguish go from stop"? P(stop | true=0.90) and P(go | true=0.65) at n=20
g, c, s = classify_probs(20, 0.90, .85, .70); g2, c2, s2 = classify_probs(20, 0.65, .85, .70)
print(f"n=20 P1: true .90 -> P(stop)={s:.3f}, P(go)={g:.3f}; true .65 -> P(go)={g2:.3f}, P(stop)={s2:.3f}")
g, c, s = classify_probs(100, 0.90, .85, .70); g2, c2, s2 = classify_probs(100, 0.65, .85, .70)
print(f"n=100 P1: true .90 -> P(stop)={s:.2e}, P(go)={g:.3f}; true .65 -> P(go)={g2:.2e}, P(stop)={s2:.3f}")

# Probe 1 and 3 on the same 100 cases: correlation of outcomes (multinomial). Joint pass probability.
rng = np.random.default_rng(0)
for pc, pa in [(0.88, 0.07), (0.85, 0.10), (0.90, 0.05)]:
    draws = rng.multinomial(100, [pc, pa, 1 - pc - pa], size=200000)
    both = np.mean((draws[:, 0] >= 85) & (draws[:, 1] <= 10))
    print(f"multinomial true correct={pc}, abstain={pa}: P(P1 go AND P3 go) = {both:.3f}")
