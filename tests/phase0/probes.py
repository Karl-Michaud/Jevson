"""Request builders and scorers for probes 1-8 (docs/taxonomy.md §2). Pure functions: the thin ``run_probe_*``
runners wire them to the client; tests drive them with the fake transport."""
from __future__ import annotations

import itertools
import pathlib
import random
import sys
import types
from collections import Counter, defaultdict

from tests.phase0 import rules as R
from tests.phase0 import scoring as SC
from tests.phase0 import stats as S
from tests.phase0 import templates as T
from tests.phase0.datasets import extract as X
from tests.phase0.datasets.models import Cluster, HostileCase, ScreenDoc, SelectionCase, SingleCase
from tests.phase0.floor import VariantScore, choose_variant, select_floor
from tests.phase0.runner import Request, answers_of


def _decode(recs: dict, rid: str, key: str, offered: list[str]) -> SC.ChoiceAnswer:
    return SC.decode_choice(answers_of(recs.get(rid)).get(key), offered)


# ---------------------------------------------------------------- probes 1-3

def build_123(present: list[SelectionCase], absent: list[SelectionCase], texts: dict[str, str]) -> list[Request]:
    reqs = []
    for tag, cases in (("p13", present), ("p2", absent)):
        by_doc: dict[str, list[SelectionCase]] = defaultdict(list)
        for c in cases:
            by_doc[c.doc_id].append(c)
        for doc, cs in sorted(by_doc.items()):
            qs = {c.case_id: T.candidate_question(c.label, texts[doc], [(o.start, o.end) for o in c.options])[0]
                  for c in cs}
            reqs.append(Request(f"{tag}:{doc}", T.level_state(texts[doc]), qs, {"cases": [c.case_id for c in cs]}))
    return reqs


def _selection_rows(cases: list[SelectionCase], recs: dict, tag: str) -> list[dict]:
    rows = []
    for c in cases:
        offered = [o.id for o in c.options] + [T.NONE_OF_THESE]
        d = _decode(recs, f"{tag}:{c.doc_id}", c.case_id, offered)
        labels = {o.id: o.label for o in c.options}
        out = SC.classify(d, labels)
        p_sel = d.dist.get(d.selected, None) if d.selected else None
        argmax = (None if d.status == "invalid" else "abstain" if d.selected == T.NONE_OF_THESE
                  else labels[d.selected])
        rows.append({"case_id": c.case_id, "doc_id": c.doc_id, "field_id": c.field_id, "outcome": out,
                     "argmax_outcome": argmax,
                     "status": d.status, "selected": d.selected, "p_selected": p_sel, "margin": d.margin,
                     "p_none": d.dist.get(T.NONE_OF_THESE) if d.dist else None, "hard": c.hard,
                     "repeated": c.repeated, "n_options": len(c.options), "invalid_reason": d.reason})
    return rows


def _breakdown(rows: list[dict], key, k_of) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    return {g: {"n": len(v), "k": k_of(v), "rate": k_of(v) / len(v)} for g, v in sorted(groups.items())}


def score_123(present: list[SelectionCase], absent: list[SelectionCase], recs: dict, domain_of: dict[str, str]) -> dict:
    pr = _selection_rows(present, recs, "p13")
    ar = _selection_rows(absent, recs, "p2")
    cp, ca = SC.Counts.of(r["outcome"] for r in pr), SC.Counts.of(r["outcome"] for r in ar)
    out = {}
    for name, band, rows, cnt, k in (("probe1", S.PROBE1, pr, cp, SC.probe1_k(cp)),
                                      ("probe2", S.PROBE2, ar, ca, SC.probe2_k(ca)),
                                      ("probe3", S.PROBE3, pr, cp, SC.probe3_k(cp))):
        s = S.rate_summary(k, cnt.n, band, ties=cnt.tie)
        s.update({"counts": vars(cnt), "invalid_rate": cnt.invalid / cnt.n})
        outcome = {"probe1": "correct", "probe2": "abstain", "probe3": "abstain"}[name]
        kf = lambda v, o=outcome: sum(r["outcome"] == o for r in v)  # noqa: E731
        s["by_domain"] = _breakdown(rows, lambda r: domain_of[r["doc_id"]], kf)
        s["by_hard"] = _breakdown(rows, lambda r: "hard" if r["hard"] else "other", kf)
        if name != "probe2":
            s["by_repeated"] = _breakdown(rows, lambda r: "repeated" if r["repeated"] else "unique", kf)
        out[name] = s
    stops = [p for p in ("probe1", "probe2", "probe3") if out[p]["verdict"] == "stop"]
    conds = [p for p in ("probe1", "probe2", "probe3") if out[p]["verdict"] == "conditional"]
    out["abandon"] = bool(stops)
    out["candidate_selection"] = ("stop: abandon criterion fires (" + ", ".join(stops) + ")" if stops else
                                  "conditional: Phase 5 ships the second gate (" + ", ".join(conds) + ")" if conds else
                                  "go")
    oc_n = {"probe1": cp.n, "probe2": ca.n, "probe3": cp.n}
    out["oc_at_achieved_n"] = {p: {f"{e:.2f}": S.operating_characteristic(b, e, oc_n[p])
                                   for e in (b.go, b.stop) for e in [float(e)]}
                               for p, b in (("probe1", S.PROBE1), ("probe2", S.PROBE2), ("probe3", S.PROBE3))}
    keys = ("case_id", "outcome", "argmax_outcome", "status", "p_selected", "margin", "p_none", "n_options", "hard")
    out["decisions"] = [{k: r[k] for k in keys + ("repeated",)} | {"probe": "present"} for r in pr]
    out["decisions"] += [{k: r[k] for k in keys} | {"probe": "absent"} for r in ar]
    out["request_ids"] = sorted({(recs.get(f"p13:{c.doc_id}") or recs.get(f"p2:{c.doc_id}") or {})
                                 .get("response", {}).get("request_id") or "" for c in present + absent} - {""})
    return out


# ---------------------------------------------------------------- probe 4

def build_4(clusters: list[Cluster], texts: dict[str, str]) -> list[Request]:
    reqs = []
    for c in clusters:
        passage = texts[c.doc_id][c.passage_start:c.passage_end]
        cand = {m.id: m.text for m in c.mentions}
        qs = {f"p{i}_{j}": T.pair_question(f"c{i}", f"c{j}", c.entity_type)
              for i, j in itertools.combinations(range(len(c.mentions)), 2)}
        reqs.append(Request(f"p4:{c.cluster_id}", T.level_state(passage, cand), qs, {"cluster": c.cluster_id}))
    return reqs


def _pairs(recs: dict, rid: str, n: int) -> tuple[dict[tuple[int, int], int], dict[tuple[int, int], int]]:
    """(pairs for component building, valid pairs only). An invalid pair gets a placeholder in the first map only:
    the whole cluster-run is then scored unresolved (§2.4), but its valid pairs still count elsewhere."""
    ans = answers_of(recs.get(rid))
    out, valid = {}, {}
    for i, j in itertools.combinations(range(n), 2):
        p = SC.pair_probability(ans.get(f"p{i}_{j}"))
        out[(i, j)] = SC.PAIR_SAME_ABOVE if p is None else p
        if p is not None:
            valid[(i, j)] = p
    return out, valid


def score_4(clusters: list[Cluster], recs: dict, runs: tuple[str, ...] = R.PROBE4_RUNS) -> dict:
    per = {}
    same_pairs: list[int] = []
    invalid_runs = invalid_pairs = 0
    for c in clusters:
        gold = [m.gold for m in c.mentions]
        for run in runs:
            pairs, valid = _pairs(recs, f"{run}:p4:{c.cluster_id}", len(gold))
            ok = len(valid) == len(pairs)
            per[(c.cluster_id, run)] = (gold, pairs, ok)
            invalid_runs += not ok
            invalid_pairs += len(pairs) - len(valid)
            same_pairs += [p for (i, j), p in valid.items() if gold[i] == gold[j]]
    fl = select_floor(same_pairs) if same_pairs else None
    floor = fl.floor if fl else 5
    comp = {}
    for variant in ("internal", "cross"):
        kinds: Counter = Counter()
        by_run: dict[str, Counter] = {r: Counter() for r in runs}
        for (cid, run), (gold, pairs, ok) in per.items():
            res = SC.score_cluster(gold, pairs, floor, variant)
            if not ok:
                res = [("unresolved", c) for _, c in res]
            for k, _ in res:
                kinds[k] += 1
                by_run[run][k] += 1
        comp[variant] = {"pooled": dict(kinds), "by_run": {r: dict(v) for r, v in by_run.items()}}

    def vs(c: dict) -> VariantScore:
        n = sum(c.values())
        return VariantScore(n, c.get("correct", 0), c.get("merge", 0) + c.get("split", 0))

    chosen = choose_variant(vs(comp["internal"]["pooled"]), vs(comp["cross"]["pooled"]))
    v = vs(comp[chosen]["pooled"])
    verdict = "stop" if (fl is None or fl.stop) else S.probe4_verdict(v.correct, v.silently_wrong, v.components)
    per_run = {}
    for r in runs:
        rv = vs(comp[chosen]["by_run"][r])
        lo, hi = S.wilson(rv.correct, rv.components)
        wlo, whi = S.wilson(rv.silently_wrong, rv.components)
        per_run[r] = {"components": rv.components, "correct": rv.correct, "silently_wrong": rv.silently_wrong,
                      "correct_rate": rv.correct / rv.components, "correct_wilson": [lo, hi],
                      "wrong_rate": rv.silently_wrong / rv.components, "wrong_wilson": [wlo, whi],
                      "verdict": S.probe4_verdict(rv.correct, rv.silently_wrong, rv.components)}
    pa = [SC.pair_accuracy(g, p) for (g, p, ok) in per.values() if ok]
    nt = [SC.non_transitive_triples(len(g), p) for (g, p, ok) in per.values() if ok]
    cc = [SC.clique_complete(g, p) for (g, p, ok) in per.values() if ok]
    flips = [SC.pair_flips(per[(c.cluster_id, runs[0])][1], per[(c.cluster_id, runs[1])][1])
             for c in clusters if per[(c.cluster_id, runs[0])][2] and per[(c.cluster_id, runs[1])][2]] if len(runs) > 1 else []
    lo, hi = S.wilson(v.correct, v.components)
    wlo, whi = S.wilson(v.silently_wrong, v.components)
    return {
        "clusters": len(clusters), "runs": list(runs), "invalid_cluster_runs": invalid_runs,
        "invalid_pairs": invalid_pairs,
        "floor": {"value": floor / 100, "qualifying": [g / 100 for g in fl.qualifying] if fl else [],
                  "share_at_or_below": {f"{g / 100:.2f}": float(s) for g, s in fl.share_at_or_below.items()} if fl else {},
                  "grid_top_binds": fl.grid_top_binds if fl else False, "no_value_qualified": fl.stop if fl else True,
                  "same_entity_pairs": len(same_pairs)},
        "variants": {k: {**comp[k], "silently_wrong_rate": vs(comp[k]["pooled"]).silently_wrong / vs(comp[k]["pooled"]).components,
                         "correct_rate": vs(comp[k]["pooled"]).correct / vs(comp[k]["pooled"]).components}
                     for k in comp},
        "chosen_variant": chosen,
        "pooled": {"components": v.components, "correct": v.correct, "silently_wrong": v.silently_wrong,
                   "correct_rate": v.correct / v.components, "correct_wilson": [lo, hi],
                   "wrong_rate": v.silently_wrong / v.components, "wrong_wilson": [wlo, whi]},
        "per_run": per_run, "verdict": verdict,
        "pair_accuracy": {"k": sum(a for a, _ in pa), "n": sum(b for _, b in pa)},
        "non_transitive_triples": {"k": sum(a for a, _ in nt), "n": sum(b for _, b in nt),
                                   "clusters_with_one": sum(a > 0 for a, _ in nt)},
        "clique_completeness": {"k": sum(a for a, _ in cc), "n": sum(b for _, b in cc)},
        "pair_flips": {"k": sum(a for a, _ in flips), "n": sum(b for _, b in flips)},
    }


# ---------------------------------------------------------------- probe 5

def probe5_module():
    """probe_state_references.py's data (words, truth, question template, conditions), imported with its shared
    client stubbed out so that importing it neither reads the key nor touches the network."""
    probes = pathlib.Path(__file__).resolve().parents[1] / "probes"
    stub = types.ModuleType("jevclient")
    stub.Jev = stub.save = stub.fmt_rate = None
    saved = sys.modules.get("jevclient")
    sys.modules["jevclient"] = stub
    sys.path.insert(0, str(probes))
    try:
        import importlib
        mod = importlib.import_module("jev_api.probe_state_references")
    finally:
        sys.path.remove(str(probes))
        if saved is None:
            sys.modules.pop("jevclient", None)
        else:
            sys.modules["jevclient"] = saved
    return mod


def build_5(mod=None) -> list[Request]:
    """The original script's conditions, request for request (its main(), per_req=True)."""
    m = mod or probe5_module()
    W, nq, chunks = m.WORDS, m.nq, m.chunks
    L = {"items": W}
    conds: dict[str, list] = {}
    for n in (150, 25):
        conds[f"IDX-all-{n}"] = [(L, {f"q{i}": (i, nq(f"`items[{i}]`")) for i in c}) for c in chunks(n)]
        conds[f"IDX-chunk-{n}"] = [({"items": [W[i] for i in c]}, {f"q{i}": (i, nq(f"`items[{p}]`"))
                                                                   for p, i in enumerate(c)}) for c in chunks(n)]
    conds["IDX-320"] = [(L, {f"q{i}": (i, nq(f"`items[{i}]`")) for i in range(320)})]
    K = {"items": {f"k{i}": w for i, w in enumerate(W)}}
    conds["KEY-320"] = [(K, {f"q{i}": (i, nq(f"`items.k{i}`")) for i in range(320)})]
    conds["KEY-150"] = [(K, {f"q{i}": (i, nq(f"`items.k{i}`")) for i in c}) for c in chunks(150)]
    conds["INLINE-320"] = [("Classify each word.", {f"q{i}": (i, nq(f"the word '{W[i]}'")) for i in range(320)})]
    conds["PER-REQ"] = [({"item": W[i]}, {"q": (i, nq("`item`"))}) for i in range(320)]
    reqs = []
    for name, rs in conds.items():
        for n, (state, qmap) in enumerate(rs):
            reqs.append(Request(f"p5:{name}:{n}", state, {k: q for k, (_, q) in qmap.items()},
                                {"condition": name, "items": {k: gi for k, (gi, _) in qmap.items()}}))
    return reqs


def score_5(reqs: list[Request], recs: dict, truth: list[bool]) -> dict:
    by: dict[str, dict] = defaultdict(lambda: {"wrong": 0, "n": 0, "invalid": 0, "requests": 0})
    for r in reqs:
        c = by[r.meta["condition"]]
        c["requests"] += 1
        ans = answers_of(recs.get(r.rid))
        for key, gi in r.meta["items"].items():
            c["n"] += 1
            p = SC.pair_probability(ans.get(key))
            if p is None:
                c["invalid"] += 1
                c["wrong"] += 1
                continue
            c["wrong"] += (p > 50) != truth[gi]
    out = {k: {**v, "rate": v["wrong"] / v["n"], "wilson": list(S.wilson(v["wrong"], v["n"]))} for k, v in by.items()}
    idx, key = out["IDX-320"]["rate"], out["KEY-320"]["rate"]
    if idx >= R.P5_REPRODUCE_IDX_MIN and key <= R.P5_KEY_MAX:
        verdict = "reproduces [P4]"
    elif idx <= R.P5_INDEXED_FINE_MAX:
        verdict = "indexed references are fine: revisit R13"
    else:
        verdict = "not reproduced"
    return {"conditions": out, "verdict": verdict}


# ---------------------------------------------------------------- probe 6

def attacked_text(text: str, h: HostileCase) -> str:
    return text[:h.insert_at] + h.note + text[h.insert_at:]


def _rebuild(base: SelectionCase, text: str, h: HostileCase | None) -> list[dict]:
    """Options over the (attacked) text: every occurrence of each candidate text, with its label mapped back to the
    unattacked document ('note' for an occurrence inside the injected note)."""
    lab = {(o.start, o.end): o.label for o in base.options}
    shift = len(h.note) if h else 0
    at = h.insert_at if h else len(text) + 1
    out = []
    for s, e in sorted({sp for t in {o.text for o in base.options} for sp in X.locate(text, t)}):
        if e <= at:
            orig = (s, e)
        elif s >= at + shift:
            orig = (s - shift, e - shift)
        else:
            out.append({"start": s, "end": e, "text": text[s:e], "label": "note"})
            continue
        out.append({"start": s, "end": e, "text": text[s:e], "label": lab.get(orig, "wrong")})
    return out


def _probe6_questions(base: SelectionCase, text: str, h: HostileCase | None) -> tuple[dict, dict]:
    opts = _rebuild(base, text, h)
    correct_texts = {o.text for o in base.options if o.label == "correct"}
    absent = [o for o in opts if o["text"] not in correct_texts]
    qs, meta = {}, {}
    q, ids = T.candidate_question(base.label, text, [(o["start"], o["end"]) for o in opts])
    qs["present"], meta["present"] = q, {i: o for i, o in zip(ids, opts)}
    if len(absent) >= R.MIN_COMPETITORS:   # §2.2 item 6, as §2.6 requires
        q, ids = T.candidate_question(base.label, text, [(o["start"], o["end"]) for o in absent])
        qs["absent"], meta["absent"] = q, {i: o for i, o in zip(ids, absent)}
    qs["screen"] = T.screen_question()
    return qs, meta


def build_6(hostile: list[HostileCase], benign: list[ScreenDoc], base: dict[str, SelectionCase],
            texts: dict[str, str]) -> list[Request]:
    reqs = []
    for h in hostile:
        b = base[h.base_case_id]
        for tag, text, hh in (("attacked", attacked_text(texts[b.doc_id], h), h), ("baseline", texts[b.doc_id], None)):
            qs, meta = _probe6_questions(b, text, hh)
            reqs.append(Request(f"p6:{tag}:{h.case_id}", T.level_state(text), qs,
                                {"case": h.case_id, "kind": tag, "options": meta, "advocated": h.advocated_text,
                                 "style": h.style}))
    for s in benign:
        reqs.append(Request(f"p6:benign:{s.doc_id}", T.level_state(texts[s.doc_id]), {"screen": T.screen_question()},
                            {"kind": "benign"}))
    return reqs


def score_6(reqs: list[Request], recs: dict) -> dict:
    res: dict[str, Counter] = defaultdict(Counter)
    for r in reqs:
        ans = answers_of(recs.get(r.rid))
        kind = r.meta["kind"]
        res[f"{kind}_screen"]["n"] += 1
        res[f"{kind}_screen"]["flagged"] += SC.screen_flagged(ans.get("screen"))
        if kind == "benign":
            continue
        for q in ("present", "absent"):
            if q not in r.meta["options"]:
                res[f"{kind}_{q}"]["skipped_too_few_options"] += 1
                continue
            opts = r.meta["options"][q]
            d = SC.decode_choice(ans.get(q), list(opts) + [T.NONE_OF_THESE])
            c = res[f"{kind}_{q}"]
            c["n"] += 1
            if d.status != "ok":
                c[d.status] += 1
            elif d.selected == T.NONE_OF_THESE:
                c["abstain"] += 1
            else:
                o = opts[d.selected]
                c["steered" if o["text"] == r.meta["advocated"] else o["label"]] += 1
            c[f"style_{r.meta['style']}_n"] += 1
            if d.status == "ok" and d.selected != T.NONE_OF_THESE and opts[d.selected]["text"] == r.meta["advocated"]:
                c[f"style_{r.meta['style']}_steered"] += 1
    out = {}
    for k, c in sorted(res.items()):
        row = dict(c)
        for m in (("flagged",) if k.endswith("_screen") else ("steered", "abstain", "correct")):
            if c["n"]:
                row[f"{m}_rate"] = c[m] / c["n"]
                row[f"{m}_wilson"] = list(S.wilson(c[m], c["n"]))
        out[k] = row
    return out


# ---------------------------------------------------------------- probe 7

def score_7(decisions: list[dict], seed: int = R.SEED) -> dict:
    def reading(rows: list[dict]) -> dict:
        if not rows:
            return {"n": 0}
        ps = [r["p_selected"] / 100 for r in rows]
        ys = [int(r["argmax_outcome"] == ("correct" if r["probe"] == "present" else "abstain")) for r in rows]
        return {"n": len(ps), "ece": S.ece(ps, ys, R.CALIBRATION_BINS),
                "ece_upper_95": S.ece_bootstrap_upper(ps, ys, R.BOOTSTRAP_REPLICATES, seed, R.CALIBRATION_BINS),
                "brier": S.brier(ps, ys), "mean_p": sum(ps) / len(ps), "accuracy": sum(ys) / len(ys),
                "share_p_100": sum(p == 1.0 for p in ps) / len(ps),
                "reliability": S.reliability_table(ps, ys, R.CALIBRATION_BINS)}
    valid = [d for d in decisions if d["status"] == "ok"]
    with_ties = [d for d in decisions if d["status"] in ("ok", "tie")]
    return {"primary_non_tie": reading(valid), "ties_included": reading(with_ties),
            "excluded_ties": sum(d["status"] == "tie" for d in decisions),
            "excluded_invalid": sum(d["status"] == "invalid" for d in decisions)}


# ---------------------------------------------------------------- probe 8

def build_8(cases: list[SingleCase], texts: dict[str, str]) -> list[Request]:
    by: dict[str, list[SingleCase]] = defaultdict(list)
    for c in cases:
        by[c.doc_id].append(c)
    return [Request(f"p8:{doc}", T.level_state(texts[doc]),
                    {c.case_id: T.candidate_question(c.label, texts[doc], [(c.span.start, c.span.end)])[0] for c in cs},
                    {"cases": [c.case_id for c in cs]})
            for doc, cs in sorted(by.items())]


def score_8(cases: list[SingleCase], recs: dict) -> dict:
    rows = []
    for c in cases:
        d = _decode(recs, f"p8:{c.doc_id}", c.case_id, ["c0", T.NONE_OF_THESE])
        out = ("tie" if d.status == "tie" else "invalid" if d.status == "invalid" else
               "abstain" if d.selected == T.NONE_OF_THESE else "commit")
        rows.append({"set": c.set, "field_type": c.field_type, "constructed": c.constructed, "outcome": out})
    res = {}
    for s in ("lone_correct", "lone_wrong", "lone_partial", "partial_only"):
        rs = [r for r in rows if r["set"] == s]
        if not rs:
            continue
        n = len(rs)
        cnt = Counter(r["outcome"] for r in rs)
        key = "commit" if s == "lone_correct" else "abstain"
        res[s] = {"n": n, **dict(cnt), "rate_key": key, "rate": cnt[key] / n, "wilson": list(S.wilson(cnt[key], n)),
                  "by_field_type": {ft: {"n": len(v), key: sum(r["outcome"] == key for r in v)}
                                    for ft in sorted({r["field_type"] for r in rs})
                                    for v in [[r for r in rs if r["field_type"] == ft]]}}
        if s == "lone_partial":
            res[s]["constructed"] = sum(r["constructed"] for r in rs)
    return res


def dry_answers(reqs: list[Request], seed: int = 0) -> dict:
    """Records shaped like live ones, from the fake transport's answer generator (for tests)."""
    from tests.phase0.runner import _fake_answer
    rng = random.Random(seed)
    return {r.rid: {"rid": r.rid, "response": {"status": 200, "body": {
        "answers": {k: _fake_answer(q, rng) for k, q in r.questions.items()}}}} for r in reqs}
