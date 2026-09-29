"""Round 2, analysis only (no API calls) for probe_conflict_floor.py raw runs A and B.
Claim (DESIGN §5.6 Rev 4; PLAN Phase 0 probe 4): see probe_conflict_floor.py.
Method: load stored pair probabilities; (a) p(same) histograms by gold label; (b) apply the pre-registered
floor rule verbatim; (c) per-component outcomes under Rev 4 at every candidate floor, Rev 3 whole-array,
plain connected components; (d) clique completeness. SYNTHETIC PILOT."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import itertools, json, sys
from collections import Counter
from jevclient import RAW, fmt_rate, wilson

FLOORS = [0.05, 0.10, 0.20, 0.30]


def comps(n, P):
    parent = list(range(n))
    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for (x, y), p in P.items():
        if p > 0.5: parent[f(x)] = f(y)
    c = {}
    for i in range(n): c.setdefault(f(i), []).append(i)
    return [sorted(v) for v in c.values()]


def score_doc(doc, policy, floor=None):
    M = doc["mentions"]; n = len(M)
    P = {(q["a"], q["b"]): q["p"] for q in doc["pairs"]}
    gold = {}
    for i, (_, e) in enumerate(M): gold.setdefault(e, []).append(i)
    gold_sets = [sorted(v) for v in gold.values()]
    C = comps(n, P)
    def inside(c):
        return [P[(x, y)] for x, y in itertools.combinations(c, 2)]
    res = []  # per predicted component: correct | unresolved | wrong_merge | wrong_split
    if policy == "rev3":
        if any(p < 0.5 for c in C for p in inside(c)):
            return [("unresolved", c) for c in C]
    for c in C:
        if policy in ("rev4", "rev4g") and any(p <= floor for p in inside(c)):
            res.append(("unresolved", c)); continue
        if policy == "rev4g":  # exploratory guard: a cross-component pair in (floor, 0.5] marks both uncertain
            if any(floor < P[(min(x, y), max(x, y))] <= 0.5 for d in C if d is not c for x in c for y in d):
                res.append(("unresolved", c)); continue
        if c in gold_sets: res.append(("correct", c))
        else:
            ents = {M[i][1] for i in c}
            res.append(("wrong_merge" if len(ents) > 1 else "wrong_split", c))
    return res


def doc_outcome(r):
    kinds = {k for k, _ in r}
    if kinds & {"wrong_merge", "wrong_split"}: return "silently_wrong"
    if "unresolved" in kinds: return "unresolved"
    return "correct"


def analyse(docs, label):
    out = {"label": label, "docs": len(docs)}
    same = [q["p"] for d in docs for q in d["pairs"] if q["gold_same"]]
    diff = [q["p"] for d in docs for q in d["pairs"] if not q["gold_same"]]
    edges = [0, .05, .10, .20, .30, .40, .50, .60, .70, .80, .90, .95, 1.0001]
    def hist(v):
        return {f"[{edges[i]:.2f},{min(edges[i+1],1):.2f}{']' if i == len(edges)-2 else ')'}": sum(edges[i] <= x < edges[i+1] for x in v) for i in range(len(edges)-1)}
    out["n_same_pairs"], out["n_diff_pairs"] = len(same), len(diff)
    out["hist_same"], out["hist_diff"] = hist(same), hist(diff)
    out["same_le_floor"] = {f: fmt_rate(sum(p <= f for p in same), len(same)) for f in FLOORS}
    out["diff_le_floor"] = {f: fmt_rate(sum(p <= f for p in diff), len(diff)) for f in FLOORS}
    out["same_in_(floor,0.5]"] = {f: sum(f < p <= .5 for p in same) for f in FLOORS}
    out["pair_accuracy(p>0.5)"] = fmt_rate(sum(p > .5 for p in same) + sum(p <= .5 for p in diff), len(same) + len(diff))
    out["false_merge(diff p>0.5)"] = fmt_rate(sum(p > .5 for p in diff), len(diff))
    out["false_split(same p<=0.5)"] = fmt_rate(sum(p <= .5 for p in same), len(same))
    out["exact_0.50_pairs"] = sum(p == 0.5 for p in same + diff)
    ok = [f for f in FLOORS if sum(p <= f for p in same) / len(same) <= 0.02]
    out["rule_selected_floor"] = max(ok) if ok else None
    # clique completeness over gold same-entity clusters of size >=2
    cc = tot = 0
    for d in docs:
        M = d["mentions"]; P = {(q["a"], q["b"]): q["p"] for q in d["pairs"]}
        gold = {}
        for i, (_, e) in enumerate(M): gold.setdefault(e, []).append(i)
        for g in gold.values():
            if len(g) < 2: continue
            tot += 1; cc += all(P[(x, y)] > .5 for x, y in itertools.combinations(g, 2))
    out["clique_completeness"] = fmt_rate(cc, tot)
    # non-transitive triples
    vt = tr = vd = 0
    for d in docs:
        P = {(q["a"], q["b"]): q["p"] for q in d["pairs"]}; n = len(d["mentions"]); v = 0
        for x, y, z in itertools.combinations(range(n), 3):
            s = [P[(x, y)] > .5, P[(y, z)] > .5, P[(x, z)] > .5]; tr += 1; v += sum(s) == 2
        vt += v; vd += v > 0
    out["non_transitive_triples"] = fmt_rate(vt, tr); out["docs_with_violation"] = fmt_rate(vd, len(docs))
    pols = [("plain_cc", None), ("rev3", None)] + [(f"rev4@{f}", f) for f in FLOORS] + [(f"rev4g@{f}", f) for f in (0.2, 0.3)]
    out["policies"] = {}
    for name, f in pols:
        pol = name.split("@")[0]
        per = [score_doc(d, pol, f) for d in docs]
        comp = Counter(k for r in per for k, _ in r)
        ncomp = sum(comp.values())
        dco = Counter(doc_outcome(r) for r in per)
        # silently wrong components: each gold entity mis-represented counts
        out["policies"][name] = {
            "components": ncomp,
            "comp_correct": fmt_rate(comp["correct"], ncomp),
            "comp_unresolved": fmt_rate(comp["unresolved"], ncomp),
            "comp_silently_wrong": fmt_rate(comp["wrong_merge"] + comp["wrong_split"], ncomp),
            "comp_wrong_merge": comp["wrong_merge"], "comp_wrong_split": comp["wrong_split"],
            "doc_correct": fmt_rate(dco["correct"], len(docs)),
            "doc_unresolved(no silent error)": fmt_rate(dco["unresolved"], len(docs)),
            "doc_silently_wrong": fmt_rate(dco["silently_wrong"], len(docs)),
            "by_template": {t: dict(Counter(doc_outcome(r) for d, r in zip(docs, per) if d["template"] == t)) for t in sorted({d["template"] for d in docs})},
        }
    # detail of silent errors under the selected floor and under rev4@0.30
    det = []
    for f in sorted({out["rule_selected_floor"] or 0.05, 0.30}):
        for d in docs:
            r = score_doc(d, "rev4", f)
            M = d["mentions"]; P = {(q["a"], q["b"]): q["p"] for q in d["pairs"]}
            for k, c in r:
                if k in ("wrong_merge", "wrong_split"):
                    det.append({"floor": f, "template": d["template"], "kind": k, "component": [M[i][0] for i in c],
                                "min_pair_in_comp": min([P[(x, y)] for x, y in itertools.combinations(c, 2)] or [None])})
    out["silent_error_detail"] = det
    # lowest-scoring gold-same pairs (what the floor has to sit under)
    lows = sorted(((q["p"], d["template"], q["ma"], q["mb"]) for d in docs for q in d["pairs"] if q["gold_same"]))[:25]
    out["lowest_gold_same_pairs"] = lows
    highs = sorted(((q["p"], d["template"], q["ma"], q["mb"]) for d in docs for q in d["pairs"] if not q["gold_same"]), reverse=True)[:25]
    out["highest_gold_diff_pairs"] = highs
    return out


def main():
    A = json.loads((RAW / "r2_entity_floor_runA.json").read_text())
    B = json.loads((RAW / "r2_entity_floor_runB.json").read_text())
    rep = {}
    for label, sel in (("ALL", lambda d: True), ("OLD_p06", lambda d: d["template"] in ("doc_t0", "doc_t1", "doc_t2")),
                       ("NEW_t3-5", lambda d: d["template"] in ("doc_t3", "doc_t4", "doc_t5"))):
        for run, docs in (("A", A), ("B", B)):
            rep[f"{label}_{run}"] = analyse([d for d in docs if sel(d)], f"{label}_{run}")
    # run-to-run pair stability
    pa = [q["p"] for d in A for q in d["pairs"]]; pb = [q["p"] for d in B for q in d["pairs"]]
    rep["AB_stability"] = {"pairs": len(pa), "max_abs_diff": max(abs(x - y) for x, y in zip(pa, pb)),
                           "decision_flips(>0.5)": sum((x > .5) != (y > .5) for x, y in zip(pa, pb))}
    (RAW / "r2_entity_floor_analysis.json").write_text(json.dumps(rep, indent=1))
    for k, v in rep.items():
        if k == "AB_stability": print(k, v); continue
        print("=====", k)
        for kk in ("n_same_pairs", "n_diff_pairs", "pair_accuracy(p>0.5)", "false_merge(diff p>0.5)", "false_split(same p<=0.5)",
                   "exact_0.50_pairs", "same_le_floor", "diff_le_floor", "rule_selected_floor", "clique_completeness",
                   "non_transitive_triples", "docs_with_violation", "hist_same", "hist_diff"):
            print(" ", kk, v[kk])
        for p, s in v["policies"].items(): print("  ", p, json.dumps(s))
        if k.startswith("ALL"):
            print("  silent:", json.dumps(v["silent_error_detail"], indent=0)[:3000])
            print("  lowest same:", v["lowest_gold_same_pairs"][:15])
            print("  highest diff:", v["highest_gold_diff_pairs"][:15])


if __name__ == "__main__":
    main()
