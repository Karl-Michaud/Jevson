"""Claim: DESIGN §5.4 / PLAN Phase 5 — "the recovery rate (abstentions that end in a correct committed value
after the retry) is written down. If it is below 10%, the default candidate retry budget becomes 0."

Method: exact binomial. The denominator is the number of ABSTENTION events, not the number of decisions,
so first estimate how many abstentions a 300-decision corpus produces; then for n abstentions compute
P(observed < 10%) for true recovery 0.05 / 0.10 / 0.15 / 0.20, the Wilson interval at observed 10%, and
the n needed so that true 5% -> "below" and true 15% -> "not below" each with >= 90% / 80% probability.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import numpy as np
from scipy.stats import binom, norm
z = norm.ppf(0.975)
def wilson(k, n):
    ph = k / n; d = 1 + z**2 / n; c = (ph + z**2 / (2*n)) / d
    h = z * np.sqrt(ph*(1-ph)/n + z**2/(4*n**2)) / d; return round(c-h, 3), round(c+h, 3)

print("abstention events in a 300-decision corpus, if false abstention = 5–10% and 1/3 of cases have the answer absent:")
for fa, absent_frac, sens in [(0.05, 0.0, 0.8), (0.10, 0.0, 0.8), (0.05, 0.33, 0.8), (0.10, 0.33, 0.8)]:
    ab = 300 * ((1-absent_frac) * fa + absent_frac * sens)
    print(f"  false-abst {fa}, absent share {absent_frac}, abst-sensitivity {sens}: ≈{ab:.0f} abstentions")

def p_below(n, p):  # P(observed k/n < 0.10)
    k = np.arange(n + 1); return binom.pmf(k, n, p)[k / n < 0.10 - 1e-12].sum()
print("\nP(observed recovery < 10%)  [→ budget set to 0]")
for n in (15, 30, 50, 100, 200, 400):
    print(f"  n_abst={n:4}: " + "  ".join(f"true {p:.2f}: {p_below(n,p):.3f}" for p in (0.02, 0.05, 0.10, 0.15, 0.20)),
          f"  Wilson@10%: {wilson(round(0.1*n), n)}")
for want in (0.8, 0.9):
    for lo, hi in ((0.05, 0.15), (0.03, 0.20)):
        n_ok = next(n for n in range(10, 5000) if p_below(n, lo) >= want and 1 - p_below(n, hi) >= want)
        print(f"min abstentions so true {lo} -> below AND true {hi} -> not-below, each w.p. >= {want}: {n_ok}")
