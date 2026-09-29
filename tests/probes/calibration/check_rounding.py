"""Claims (DESIGN §2.1 "values are rounded to two decimals"; §4.2/§6.2 "bool true iff p > 0.5; exactly 0.5 -> tie";
§5.6 "components of pairs with p(same) > 0.5", "p(same) <= conflict_floor", floor in {0.05,0.10,0.20,0.30};
PLAN Phase 3 "a probability outside [0,1]" and "distributions that do not sum" are invalid backend answers,
"top-two margin >= 0.10" fixture rule; DESIGN §8.4 cache: canonical hash of the request with sorted keys; response
probabilities canonicalised to sorted key order).

Method:
 A. Mine every choice/score/noul answer recorded in round 1's raw JSON (out/raw, real jev-1.13.0 responses,
    no new API calls): sum of `probabilities`, exact top ties, whether `choice` equals the argmax, zeros, value
    types (int vs float), noul values of exactly 0.5.
 B. Simulate 2-dp rounding of Dirichlet distributions (K = 2..11) to size sum deviations and top-tie rates.
 C. IEEE-754 edge cases on 2-dp values: complements (1 - p), margins (p1 - p2 >= 0.10), comparisons with floors.
 D. Canonical-hash portability: Python json.dumps(sort_keys=True) vs JS JSON.stringify (node, if present) for
    float formatting and key order; lexicographic sort of opaque ids (c10 < c2) and argmax tie-breaking.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import collections
import glob
import json
import math
import os
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import numpy as np

RAW = Path(__file__).resolve().parents[1] / "out" / "raw"


# ---------------------------------------------------------------- A. real responses
def walk(o, out):
    if isinstance(o, dict):
        if "probabilities" in o and isinstance(o["probabilities"], dict) and o["probabilities"]:
            out["dist"].append(o)
        if "noul" in o and isinstance(o.get("noul"), (int, float)) and not isinstance(o.get("noul"), bool):
            out["noul"].append(o["noul"])
        for v in o.values():
            walk(v, out)
    elif isinstance(o, list):
        for v in o:
            walk(v, out)


def part_a():
    print("== A. round-1 raw Jev responses (jev-1.13.0), mined offline")
    out = {"dist": [], "noul": []}
    types = collections.Counter()
    for f in sorted(glob.glob(str(RAW / "*.json"))):
        d = json.load(open(f))
        walk(d, out)
    # de-duplicate identical answer objects (the same response may be stored twice in a file)
    seen = set(); dists = []
    for o in out["dist"]:
        k = json.dumps(o, sort_keys=True)
        if k not in seen:
            seen.add(k); dists.append(o)
    print(f"distribution answers: {len(dists)} (unique), noul values: {len(out['noul'])}")
    sums = collections.Counter(); ties = 0; mism = 0; zeros = 0; ktot = collections.Counter(); ex = {}
    maxdev = 0.0; sel_zero = 0; kinds = collections.Counter()
    for o in dists:
        pr = o["probabilities"]
        vals = list(pr.values())
        for v in vals:
            types[type(v).__name__] += 1
        s = round(sum(Decimal(str(v)) for v in vals), 2)
        sums[str(s)] += 1
        maxdev = max(maxdev, abs(float(s) - 1))
        ktot[len(vals)] += 1
        srt = sorted(vals, reverse=True)
        top = [k for k, v in pr.items() if v == srt[0]]
        kind = "choice" if "choice" in o else ("score" if "score" in o else "other")
        kinds[kind] += 1
        if len(top) > 1:
            ties += 1; ex.setdefault("tie", o)
        if kind == "choice" and o["choice"] not in top:
            mism += 1; ex.setdefault("mismatch", o)
        if kind == "choice" and pr.get(o["choice"], None) == 0:
            sel_zero += 1
        zeros += sum(1 for v in vals if v == 0)
    print("  answer kinds:", dict(kinds))
    print("  option counts:", dict(sorted(ktot.items())))
    print("  value types:", dict(types))
    print("  sum of probabilities (exact decimal):", dict(sorted(sums.items())))
    print(f"  max |sum - 1| = {maxdev:.2f}; answers with sum != 1.00: {sum(v for k, v in sums.items() if k != '1.00')}/{len(dists)}")
    print(f"  exact ties at the top: {ties}/{len(dists)}; choice field not an argmax: {mism}; selected option at 0.00: {sel_zero}")
    print(f"  option probabilities equal to 0.00: {zeros}")
    for k, o in ex.items():
        print(f"  example {k}: {json.dumps(o)[:300]}")
    nv = out["noul"]
    c = collections.Counter(nv)
    print(f"  noul values exactly 0.5: {c.get(0.5, 0)}/{len(nv)}; at 0.0: {c.get(0.0, 0) + c.get(0, 0)}; at 1.0: {c.get(1.0, 0)}")
    return dists


# ---------------------------------------------------------------- B. simulation
def part_b():
    print("\n== B. simulated 2-dp rounding of Dirichlet distributions (200k per K)")
    rng = np.random.default_rng(1)
    print(f"{'K':>3s} {'alpha':>6s} {'P(sum!=1)':>10s} {'max|dev|':>9s} {'bound K*.005':>12s} {'P(top tie)':>11s} {'P(any 0.00)':>12s}")
    for K in (2, 3, 5, 8, 11):
        for a in (0.05, 0.5, 2.0):
            q = rng.dirichlet(np.full(K, a), 200000)
            r = np.round(q * 100).astype(int)  # integer hundredths, avoids float noise
            s = r.sum(1)
            srt = np.sort(r, 1)
            tie = (srt[:, -1] == srt[:, -2]).mean()
            print(f"{K:3d} {a:6.2f} {np.mean(s != 100):10.3f} {np.abs(s - 100).max() / 100:9.2f} {K * 0.005:12.3f} {tie:11.4f} {(r == 0).any(1).mean():12.3f}")
    # a noul tie: true p in [0.495, 0.505) rounds to 0.50
    print("  noul: any true p in [0.495, 0.505) is reported as 0.50 -> tie band width 0.01")


# ---------------------------------------------------------------- C. float edge cases
def part_c():
    print("\n== C. IEEE-754 edge cases on 2-dp values")
    vals = [round(i / 100, 2) for i in range(101)]
    parsed = [json.loads(f"{i / 100:.2f}") for i in range(101)]
    assert all(a == b for a, b in zip(vals, parsed))
    comp_bad = [p for p in parsed if (1 - p) != json.loads(f"{1 - Decimal(str(p)):.2f}")]
    print(f"  1 - p differs from the 2-dp complement for {len(comp_bad)}/101 values, e.g. 1 - 0.7 = {1 - 0.7!r}")
    floors = (0.05, 0.10, 0.20, 0.30)
    flip = []
    for fl in floors:
        for p in parsed:
            direct = p <= fl
            via_comp = (1 - p) >= (1 - fl)            # p(different) >= 1 - floor
            if direct != via_comp:
                flip.append((fl, p))
    print(f"  'p(same) <= floor' vs '1 - p(same) >= 1 - floor' disagree on {len(flip)} (floor, p) pairs: {flip[:6]}")
    bool_ok = all((p > 0.5) == (Decimal(str(p)) > Decimal('0.5')) for p in parsed)
    print(f"  'p > 0.5' on parsed 2-dp floats matches exact decimal comparison for all 101 values: {bool_ok}")
    print(f"  0.5 parses exactly: {json.loads('0.50') == 0.5}; '1 - p_true' for a bool false at p=0.50: {1 - 0.5}")
    # top-two margin >= 0.10 rule (PLAN Phase 3 live-stability fixture)
    bad_margin = []
    for i in range(101):
        for j in range(i):
            a, b = parsed[i], parsed[j]
            if i - j == 10 and not (a - b >= 0.10):
                bad_margin.append((a, b, a - b))
    print(f"  pairs whose exact margin is 0.10 but float 'p1 - p2 >= 0.10' is False: {len(bad_margin)}/91, e.g. {bad_margin[:3]}")
    over = []
    for i in range(101):
        for j in range(i):
            if i - j == 9 and parsed[i] - parsed[j] >= 0.09 + 0.01 - 1e-18 and parsed[i] - parsed[j] >= 0.10:
                over.append((parsed[i], parsed[j]))
    print(f"  pairs with exact margin 0.09 that float says >= 0.10: {len(over)}")
    # tau comparisons
    for tau in (0.8, 0.9):
        print(f"  tau={tau}: 'p >= tau' matches decimal for all 2-dp p: "
              f"{all((p >= tau) == (Decimal(str(p)) >= Decimal(str(tau))) for p in parsed)}")
    # sum-to-one validation with float tolerance
    cases = [[0.33, 0.33, 0.33], [0.34, 0.33, 0.34], [0.1] * 10, [0.7, 0.2, 0.1]]
    for c in cases:
        print(f"  sum({c}) = {sum(c)!r}; abs(sum-1) <= 1e-9: {abs(sum(c) - 1) <= 1e-9}; "
              f"within K*0.005: {abs(sum(c) - 1) <= len(c) * 0.005 + 1e-9}")


# ---------------------------------------------------------------- D. canonical hash
def part_d():
    print("\n== D. canonicalisation for the cache hash")
    probs_a = {"c10": 0.45, "c2": 0.45, "none_of_these": 0.10}
    probs_b = {"c2": 0.45, "none_of_these": 0.10, "c10": 0.45}
    print("  sorted keys:", sorted(probs_a), "(lexicographic: c10 before c2)")
    print("  max(..., key=get) on two orderings of the same response:",
          max(probs_a, key=probs_a.get), "vs", max(probs_b, key=probs_b.get),
          "-> argmax tie-break depends on key order; sorting makes it deterministic but picks by string order")
    samples = [1.0, 1, 0.1, 1e-7, 1e21, 0.30000000000000004, -0.0, 100.0, 2.50]
    py = [json.dumps(x) for x in samples]
    print("  python json.dumps:", py)
    node = shutil.which("node")
    if node:
        js = subprocess.run([node, "-e", "console.log(JSON.stringify([1.0,1,0.1,1e-7,1e21,0.30000000000000004,-0.0,100.0,2.50]))"],
                            capture_output=True, text=True).stdout.strip()
        print("  node JSON.stringify:", js)
        keys = {"ﬁ": 1, "\U0001F600": 2, "a": 3}
        pyk = list(json.loads(json.dumps(keys, sort_keys=True)))
        jsk = subprocess.run([node, "-e", "const o={'\\uFB01':1,'\\u{1F600}':2,'a':3};"
                              "console.log(JSON.stringify(Object.keys(o).sort()))"], capture_output=True, text=True).stdout.strip()
        print("  key order: python sort_keys (code points):", ascii(pyk), "| JS default sort / RFC 8785 (UTF-16 units):", ascii(json.loads(jsk)))
    else:
        print("  node not found; JS comparison skipped")
    print("  ensure_ascii changes bytes:", json.dumps({"k": "é"}) != json.dumps({"k": "é"}, ensure_ascii=False))
    print("  NaN accepted by json.dumps (not valid JSON):", json.dumps(float("nan")))
    print("  state given as text vs as JSON: json.dumps('{\"a\":1}') != json.dumps({'a':1}):",
          json.dumps('{"a":1}') != json.dumps({"a": 1}, sort_keys=True))


if __name__ == "__main__":
    part_a()
    part_b()
    part_c()
    part_d()
