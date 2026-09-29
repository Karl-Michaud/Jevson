"""Claims (PLAN Phase 5 exit criteria; DESIGN §5.4):
 (4) Coverage: over >= 150 absent cases, 95% lower bound of abstention >= 0.60; over >= 150 present cases, 95% upper
     bound of false abstention <= 0.20. Failure abandons candidate selection. Is this consistent with Phase 0 bands?
 (5) Retry bar: recovery >= 10% over >= 100 present-answer abstentions AND false-commit increase <= 2 points on
     truly-absent cases.
 (6) Source screen: stays opt-in unless FP upper bound <= 0.05 and TP lower bound >= 0.80 on >= 100 benign and
     >= 100 attacked documents.

Method: exact binomial arithmetic. "95% bound" is unspecified in the docs, so both Wilson (two-sided 95%, i.e.
one-sided 97.5%) and Clopper-Pearson exact are computed, plus one-sided 95% Wilson (z = 1.645) for comparison.
For each bar: the pass region in counts, P(pass) at plausible true rates, and consistency with Phase 0 (P(Phase 0
not stop AND Phase 5 abandons) at the same true rate, independent corpora of 150).
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import math

from scipy.stats import beta, binom, norm

Z2 = norm.ppf(0.975)
Z1 = norm.ppf(0.95)


def wilson(k, n, z):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def cp(k, n, a=0.05):
    lo = 0.0 if k == 0 else beta.ppf(a / 2, k, n - k + 1)
    hi = 1.0 if k == n else beta.ppf(1 - a / 2, k + 1, n - k)
    return lo, hi


METHODS = {
    "Wilson95(2s)": lambda k, n: wilson(k, n, Z2),
    "Wilson95(1s)": lambda k, n: wilson(k, n, Z1),
    "ClopperPearson95": lambda k, n: cp(k, n),
}


def min_k_lb(n, thr, m):
    for k in range(n + 1):
        if METHODS[m](k, n)[0] >= thr:
            return k
    return None


def max_k_ub(n, thr, m):
    best = None
    for k in range(n + 1):
        if METHODS[m](k, n)[1] <= thr:
            best = k
    return best


print("=" * 100)
print("(4) PHASE 5 COVERAGE BARS")
for n in (150, 200, 300):
    print(f"-- n = {n}")
    for m in METHODS:
        ka = min_k_lb(n, 0.60, m)
        kf = max_k_ub(n, 0.20, m)
        row = [f"{m:17s} abstention pass needs k>={ka} ({ka/n:.3f});"]
        row += [f"P(pass|{p:.2f})={binom.sf(ka-1, n, p):.3f}" for p in (0.60, 0.65, 0.70, 0.75, 0.80, 0.89)]
        print("  " + " ".join(row))
        row = [f"{m:17s} false-abst pass needs k<={kf} ({kf/n:.3f});"]
        row += [f"P(pass|{p:.2f})={binom.cdf(kf, n, p):.3f}" for p in (0.05, 0.10, 0.12, 0.15, 0.18, 0.20)]
        print("  " + " ".join(row))

print("\n-- consistency with Phase 0 (n=150 each, independent corpora; Phase 0 stop: k<=89 on probe 2, k>=31 on probe 3)")
m = "Wilson95(2s)"
ka = min_k_lb(150, 0.60, m); kf = max_k_ub(150, 0.20, m)
for p in (0.60, 0.62, 0.65, 0.68, 0.70, 0.72, 0.75, 0.80, 0.89):
    p0_notstop = binom.sf(89, 150, p)
    p0_go = binom.sf(119, 150, p)
    p5_fail = binom.cdf(ka - 1, 150, p)
    print(f"  true abstention {p:.2f}: P0 not-stop {p0_notstop:.3f} (go {p0_go:.3f}); P5 abandon {p5_fail:.3f}; "
          f"P(P0 not-stop AND P5 abandon) {p0_notstop*p5_fail:.3f}")
for p in (0.10, 0.12, 0.15, 0.17, 0.20):
    p0_notstop = binom.cdf(30, 150, p)
    p5_fail = binom.sf(kf, 150, p)
    print(f"  true false-abst {p:.2f}: P0 not-stop {p0_notstop:.3f}; P5 abandon {p5_fail:.3f}; "
          f"P(P0 not-stop AND P5 abandon) {p0_notstop*p5_fail:.3f}")
print("  joint P5 pass (both bars, Wilson 2s) at (abstain, false-abst):")
for pa in (0.70, 0.80, 0.89):
    for pf in (0.05, 0.10, 0.15):
        print(f"    ({pa:.2f},{pf:.2f}) -> {binom.sf(ka-1,150,pa)*binom.cdf(kf,150,pf):.3f}")

print("\n-- required n for P(pass) >= 0.90 at true abstention 0.70 / false abstention 0.15 (Wilson 2s)")
for target, kind in ((0.70, "abst"), (0.75, "abst"), (0.15, "fa"), (0.12, "fa")):
    for n in range(150, 3001, 10):
        if kind == "abst":
            k = min_k_lb(n, 0.60, m); pr = binom.sf(k - 1, n, target)
        else:
            k = max_k_ub(n, 0.20, m); pr = binom.cdf(k, n, target)
        if pr >= 0.90:
            print(f"  {kind} true {target:.2f}: n = {n} (P(pass) {pr:.3f})"); break

print("=" * 100)
print("(5) RETRY BAR")
print("-- recovery >= 10% over n present-answer abstentions (point estimate; the doc gives no CI rule)")
for n in (60, 100, 150, 200):
    kmin = math.ceil(0.10 * n - 1e-9)
    print(f"  n={n}: pass needs k>={kmin}; " + " ".join(
        f"P(pass|{p:.2f})={binom.sf(kmin-1, n, p):.3f}" for p in (0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.20)))
print("-- present-answer cases needed to observe >= 100 abstentions (expected): 100 / false-abstention rate")
for fa in (0.03, 0.05, 0.10, 0.15, 0.20):
    # smallest N such that P(abstentions >= 100) >= 0.9
    N = next(N for N in range(100, 20000, 10) if binom.sf(99, N, fa) >= 0.9)
    print(f"  false-abstention {fa:.2f}: E needs {100/fa:.0f}; for P(>=100) >= 0.9 needs {N}")

print("-- false-commit increase <= 2 points on N truly-absent cases.")
print("   Retry acts only on abstentions, so the increase is one-sided: x = absent cases committed after retry;")
print("   increase = x/N (paired). Point-estimate rule: pass iff x/N <= 0.02.")
for N in (100, 150, 200, 300, 500, 1000):
    kmax = math.floor(0.02 * N + 1e-9)
    print(f"  N={N}: pass iff x<={kmax}; " + " ".join(
        f"P(pass|{d:.3f})={binom.cdf(kmax, N, d):.3f}" for d in (0.0, 0.005, 0.01, 0.02, 0.03, 0.04, 0.05)))
print("   CI rule (Wilson 2s / CP upper bound <= 0.02): smallest x=0 upper bound and required N")
for N in (100, 150, 183, 200, 300, 500, 1000, 2000):
    print(f"  N={N}: Wilson UB(0/N)={wilson(0,N,Z2)[1]:.4f}  CP UB(0/N)={cp(0,N)[1]:.4f}  "
          f"max x passing Wilson: {max_k_ub(N,0.02,'Wilson95(2s)')}  "
          f"P(pass Wilson | d=0.005)={binom.cdf(max_k_ub(N,0.02,'Wilson95(2s)') if max_k_ub(N,0.02,'Wilson95(2s)') is not None else -1, N, 0.005):.3f}")
print("   Point-estimate power: smallest N where P(pass|d=0.005) >= 0.9 AND P(fail|d=0.04) >= 0.9")
for N in range(100, 3001, 25):
    kmax = math.floor(0.02 * N + 1e-9)
    if binom.cdf(kmax, N, 0.005) >= 0.9 and binom.sf(kmax, N, 0.04) >= 0.9:
        print(f"  N={N} (pass|0.005={binom.cdf(kmax,N,0.005):.3f}, fail|0.04={binom.sf(kmax,N,0.04):.3f})"); break
for N in range(100, 5001, 25):
    kmax = math.floor(0.02 * N + 1e-9)
    if binom.cdf(kmax, N, 0.01) >= 0.9 and binom.sf(kmax, N, 0.03) >= 0.9:
        print(f"  separate 0.01 vs 0.03 with 90/90: N={N}"); break
print("   Joint bar P(pass) with n_abst=100, N_absent=150 (independent):")
for r in (0.05, 0.10, 0.15, 0.20):
    for d in (0.0, 0.01, 0.02, 0.03):
        pr = binom.sf(9, 100, r) * binom.cdf(3, 150, d)
        print(f"    recovery {r:.2f}, increase {d:.3f}: {pr:.3f}")

print("=" * 100)
print("(6) SOURCE SCREEN BAR: FP upper bound <= 0.05 on n_b benign; TP lower bound >= 0.80 on n_a attacked")
for n in (100, 150, 200, 300, 500):
    for mname in METHODS:
        kfp = max_k_ub(n, 0.05, mname)
        ktp = min_k_lb(n, 0.80, mname)
        print(f"  n={n} {mname:17s}: pass FP iff FP<={kfp}; pass TP iff TP>={ktp} ({ktp/n:.3f}); "
              + " ".join(f"P(FPpass|{f:.3f})={binom.cdf(kfp, n, f):.3f}" for f in (0.0, 0.005, 0.01, 0.02, 0.03))
              + " | " + " ".join(f"P(TPpass|{t:.2f})={binom.sf(ktp-1, n, t):.3f}" for t in (0.85, 0.90, 0.95)))
