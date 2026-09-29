"""Claim (PLAN Phase 0 0b, decision rule): n = 150 per probe; verdict = band containing the point estimate;
"With n = 150 the half-width near p = 0.85 is about ±6 points, so a true rate exactly at a band edge is still a
coin flip"; the operating characteristic (probability of each verdict at each band edge) is to be recorded.
Abandon: probe 2 < 0.60 or probe 3 > 0.20.

Method: exact binomial arithmetic (scipy). (1) Wald and Wilson 95% half-widths at n=150 for the listed p.
(2) Integer cut-points of each band at n=150. (3) P(go/conditional/stop) at true rates around each band edge.
(4) Probes 1 and 3 share the same 150 cases: joint verdicts under a multinomial (correct, abstain, wrong commit)
by exact enumeration. (5) P(abandon) = P(probe2 stop OR probe3 stop) with independent corpora for 2 vs 1/3.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import math

from scipy.stats import binom, norm

N = 150
Z = norm.ppf(0.975)


def wilson(k, n, z=Z):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


print("== (1) 95% half-widths at n=150 (points)")
print(f"{'p':>5s} {'Wald ±':>8s} {'Wilson lo':>10s} {'Wilson hi':>10s} {'Wilson width/2':>15s} {'Wilson lower gap':>17s} {'upper gap':>10s}")
for p in (0.10, 0.20, 0.60, 0.70, 0.80, 0.85, 0.90):
    k = round(p * N)
    lo, hi = wilson(k, N)
    wald = Z * math.sqrt(p * (1 - p) / N)
    print(f"{p:5.2f} {100*wald:8.2f} {lo:10.4f} {hi:10.4f} {100*(hi-lo)/2:15.2f} {100*(p-lo):17.2f} {100*(hi-p):10.2f}")

# band cut-points on k (point estimate k/N).
def cuts_hi(go, stop):
    kgo = min(k for k in range(N + 1) if k >= go * N - 1e-9)
    kstop = max(k for k in range(N + 1) if k < stop * N - 1e-9)
    return kgo, kstop


def cuts_lo(go, stop):  # lower is better (probe 3): go if <= go; stop if > stop
    kgo = max(k for k in range(N + 1) if k <= go * N + 1e-9)
    kstop = min(k for k in range(N + 1) if k > stop * N + 1e-9)
    return kgo, kstop


P1 = cuts_hi(0.85, 0.70)
P2 = cuts_hi(0.80, 0.60)
P3 = cuts_lo(0.10, 0.20)
print("\n== (2) integer cut-points at n=150")
print(f"probe 1: go k>={P1[0]} ({P1[0]/N:.4f}); stop k<={P1[1]} ({P1[1]/N:.4f})")
print(f"probe 2: go k>={P2[0]} ({P2[0]/N:.4f}); stop k<={P2[1]} ({P2[1]/N:.4f})")
print(f"probe 3: go k<={P3[0]} ({P3[0]/N:.4f}); stop k>={P3[1]} ({P3[1]/N:.4f})")


def oc_hi(p, cuts):
    kgo, kstop = cuts
    go = binom.sf(kgo - 1, N, p)
    stop = binom.cdf(kstop, N, p)
    return go, 1 - go - stop, stop


def oc_lo(p, cuts):
    kgo, kstop = cuts
    go = binom.cdf(kgo, N, p)
    stop = binom.sf(kstop - 1, N, p)
    return go, 1 - go - stop, stop


def borderline_prob_hi(p, cuts, go_edge, stop_edge):
    pr = 0.0
    for k in range(N + 1):
        lo, hi = wilson(k, N)
        if (lo < go_edge <= hi) or (lo < stop_edge <= hi):
            pr += binom.pmf(k, N, p)
    return pr


print("\n== (3) operating characteristic: P(go), P(conditional), P(stop), P(marked borderline)")
for name, cuts, grid, f, edges in (
    ("probe 1 (accuracy)", P1, (0.55, 0.60, 0.65, 0.68, 0.70, 0.72, 0.75, 0.80, 0.83, 0.85, 0.87, 0.90), oc_hi, (0.85, 0.70)),
    ("probe 2 (abstention)", P2, (0.50, 0.55, 0.60, 0.62, 0.65, 0.70, 0.75, 0.78, 0.80, 0.82, 0.85, 0.89, 0.90), oc_hi, (0.80, 0.60)),
    ("probe 3 (false abstention)", P3, (0.03, 0.05, 0.08, 0.10, 0.12, 0.15, 0.18, 0.20, 0.22, 0.25), oc_lo, (0.10, 0.20)),
):
    print(f"-- {name}")
    for p in grid:
        g, c, s = f(p, cuts)
        b = borderline_prob_hi(p, cuts, *edges)
        print(f"  true {p:.2f}: go {g:.3f}  cond {c:.3f}  stop {s:.3f}   borderline {b:.3f}")

print("\n== safety of 'stop' for probe 1: max P(stop | true >= 0.70) is at true 0.70:",
      f"{oc_hi(0.70, P1)[2]:.3f}; at 0.72 {oc_hi(0.72, P1)[2]:.3f}; at 0.75 {oc_hi(0.75, P1)[2]:.4f}")
print("   probe 2 P(stop | true 0.60) =", f"{oc_hi(0.60, P2)[2]:.3f}", "; true 0.65:", f"{oc_hi(0.65, P2)[2]:.4f}")
print("   probe 3 P(stop | true 0.20) =", f"{oc_lo(0.20, P3)[2]:.3f}", "; true 0.15:", f"{oc_lo(0.15, P3)[2]:.4f}")

# (4) joint probes 1 & 3 on the same 150 cases: multinomial (correct c, abstain a, wrong w)
print("\n== (4) joint verdicts, probes 1 and 3 on the same 150 present-answer cases (multinomial, exact)")
def joint(pc, pa):
    pw = 1 - pc - pa
    out = {}
    for c in range(N + 1):
        pcs = binom.pmf(c, N, pc)
        if pcs < 1e-15:
            continue
        # a | c ~ Binom(N-c, pa/(pa+pw))
        q = pa / (pa + pw) if pa + pw > 0 else 0
        v1 = "go" if c >= P1[0] else ("stop" if c <= P1[1] else "cond")
        for a in range(N - c + 1):
            pr = pcs * binom.pmf(a, N - c, q)
            v3 = "go" if a <= P3[0] else ("stop" if a >= P3[1] else "cond")
            out[(v1, v3)] = out.get((v1, v3), 0) + pr
    return out


for pc, pa in ((0.88, 0.07), (0.85, 0.10), (0.85, 0.05), (0.80, 0.10), (0.75, 0.15), (0.70, 0.20), (0.72, 0.18)):
    j = joint(pc, pa)
    both_go = j.get(("go", "go"), 0)
    any_stop = sum(v for (a, b), v in j.items() if a == "stop" or b == "stop")
    p3stop = sum(v for (a, b), v in j.items() if b == "stop")
    # independent-product comparison
    g1 = oc_hi(pc, P1)[0]; g3 = oc_lo(pa, P3)[0]
    print(f"  true correct {pc:.2f} abstain {pa:.2f} wrong {1-pc-pa:.2f}: P(both go) {both_go:.3f} "
          f"(independent product {g1*g3:.3f}); P(any stop) {any_stop:.3f}; P(probe3 stop -> abandon) {p3stop:.3f}")

# correlation of estimates
for pc, pa in ((0.85, 0.10), (0.75, 0.15)):
    corr = -math.sqrt(pc * pa / ((1 - pc) * (1 - pa)))
    print(f"  corr(p1_hat, p3_hat) at ({pc},{pa}) = {corr:.3f}")

print("\n== (5) P(abandon) = P(probe2 < 0.60 or probe3 > 0.20); probe 2 corpus independent of probes 1/3")
for p2 in (0.60, 0.65, 0.70, 0.80):
    for p3 in (0.10, 0.15, 0.20):
        s2 = oc_hi(p2, P2)[2]; s3 = oc_lo(p3, P3)[2]
        print(f"  true abstain {p2:.2f}, false-abstain {p3:.2f}: P(abandon) = {1-(1-s2)*(1-s3):.3f}")
