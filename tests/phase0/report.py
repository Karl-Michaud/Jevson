"""Renders the computed tables of docs/taxonomy.md from code and from the committed result files.

``uv run python -m tests.phase0.report oc`` prints the operating-characteristic tables (§2.10) and writes
tests/phase0/results/oc.json.
"""
from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from collections import Counter

from tests.phase0 import rules as R
from tests.phase0 import stats as S

HERE = pathlib.Path(__file__).resolve().parent
RESULTS = HERE / "results"


def _pct(x: float) -> str:
    return f"{x:.3f}"


def oc_data(n: int = R.N_TARGET) -> dict:
    single = []
    for band, points in ((S.PROBE1, (0.65, 0.70, 0.75, 0.80, 0.85, 0.90)),
                         (S.PROBE2, (0.55, 0.60, 0.65, 0.75, 0.80, 0.85)),
                         (S.PROBE3, (0.05, 0.10, 0.15, 0.20, 0.25))):
        for p in points:
            single.append({"band": band.name, "p": p, **S.operating_characteristic(band, p, n)})
    joint = []
    for pc, pa in R.JOINT_POINTS:
        j = S.joint_oc_probes_1_3(pc, pa, n)
        joint.append({"p_correct": pc, "p_abstain": pa,
                      "both_go": j[("go", "go")],
                      "any_go_or_conditional_no_stop": sum(v for (a, b), v in j.items() if "stop" not in (a, b)),
                      "any_stop": sum(v for (a, b), v in j.items() if "stop" in (a, b)),
                      "probe1_stop": sum(v for (a, _), v in j.items() if a == "stop"),
                      "probe3_stop": sum(v for (_, b), v in j.items() if b == "stop"),
                      "corr": S.corr_probes_1_3(pc, pa)})
    abandon = [{"p_correct": pc, "p_abstain_present": pa, "p_abstain_absent": p2,
                "p_abandon": S.p_abandon(pc, pa, p2, n)} for pc, pa, p2 in R.ABANDON_POINTS]
    p4 = [{"n": m, "p_correct": pc, "p_wrong": pw, **S.probe4_oc(pc, pw, m)}
          for m in R.PROBE4_OC_NS for pc, pw in R.PROBE4_POINTS]
    cuts = {}
    for band in (S.PROBE1, S.PROBE2, S.PROBE3):
        c = band.cutpoints(n)
        cuts[band.name] = {v: [min(ks), max(ks)] if ks else None for v, ks in c.items()}
    return {"n": n, "cutpoints": cuts, "single": single, "joint_1_3": joint, "abandon": abandon, "probe4": p4}


def render_oc(d: dict) -> str:
    out = [f"Exact binomial / multinomial enumeration at n = {d['n']} (`tests/phase0/stats.py`, tested against "
           "`check_phase0_bands_n150.py` **[L12]** and an independent Monte Carlo).", "",
           "**Integer cut-points** (count k of n; verdict of the point estimate k/n):", "",
           "| probe | go | conditional | stop |", "|---|---|---|---|"]
    for name, c in d["cutpoints"].items():
        cell = lambda v: "—" if c[v] is None else f"k {c[v][0]}–{c[v][1]}"  # noqa: E731
        out.append(f"| {name} | {cell('go')} | {cell('conditional')} | {cell('stop')} |")
    out += ["", "**Single probes** — probability of each verdict at a true rate:", "",
            "| probe | true rate | P(go) | P(conditional) | P(stop) |", "|---|---|---|---|---|"]
    for r in d["single"]:
        out.append(f"| {r['band']} | {r['p']:.2f} | {_pct(r['go'])} | {_pct(r['conditional'])} | {_pct(r['stop'])} |")
    out += ["", "**Probes 1 and 3 jointly** (same present-answer cases; multinomial correct / abstain / other):", "",
            "| true correct | true abstain | corr | P(both go) | P(no stop) | P(any stop) | P(probe 1 stop) | P(probe 3 stop) |",
            "|---|---|---|---|---|---|---|---|"]
    for r in d["joint_1_3"]:
        out.append(f"| {r['p_correct']:.2f} | {r['p_abstain']:.2f} | {r['corr']:.2f} | {_pct(r['both_go'])} | "
                   f"{_pct(r['any_go_or_conditional_no_stop'])} | {_pct(r['any_stop'])} | {_pct(r['probe1_stop'])} | "
                   f"{_pct(r['probe3_stop'])} |")
    out += ["", "**Abandon criterion** (probe 1 stop, probe 2 stop, or probe 3 stop; probe 2 on disjoint documents, "
            "independent):", "", "| true correct | true false-abstain | true abstain (absent) | P(abandon) |",
            "|---|---|---|---|"]
    for r in d["abandon"]:
        out.append(f"| {r['p_correct']:.2f} | {r['p_abstain_present']:.2f} | {r['p_abstain_absent']:.2f} | "
                   f"{_pct(r['p_abandon'])} |")
    out += ["", "**Probe 4** (components scored; correct / unresolved / silently wrong; n is not known in advance, "
            "so two plausible values are shown):", "",
            "| n components | true correct | true silently wrong | P(go) | P(conditional) | P(stop) |",
            "|---|---|---|---|---|---|"]
    for r in d["probe4"]:
        out.append(f"| {r['n']} | {r['p_correct']:.2f} | {r['p_wrong']:.2f} | {_pct(r['go'])} | "
                   f"{_pct(r['conditional'])} | {_pct(r['stop'])} |")
    return "\n".join(out)


# ---------------------------------------------------------------- generated sections of docs/taxonomy.md

DOC = HERE.parents[1] / "docs" / "taxonomy.md"
DATASETS = HERE / "datasets"
SCHEMAS = HERE.parents[0] / "fixtures" / "schemas"
SOURCE_NAMES = {"contract": "CUAD v1 contracts (SEC filings)", "receipt": "CORD v2 receipts (Indonesian)",
                "resume": "FJC Biographical Directory of Article III judges", "support_ticket": "Stack Exchange questions",
                "medical_intake": "Europe PMC case reports (case-presentation sections)",
                "product_listing": "GSA Auctions listings"}


def _jsonl(p: pathlib.Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def render_corpus(ds: pathlib.Path = DATASETS) -> str:
    man = _jsonl(ds / "corpus" / "manifest.jsonl")
    summ = json.loads((ds / "cases" / "build_summary.json").read_text())
    p13 = _jsonl(ds / "cases" / "probe1_3.jsonl")
    p2 = _jsonl(ds / "cases" / "probe2.jsonl")
    dom = {m["doc_id"]: m for m in man}
    out = ["| domain | source | licence | languages | documents (main + screen-only) | characters: min / median / max |",
           "|---|---|---|---|---|---|"]
    for d in sorted({m["domain"] for m in man}):
        ms = [m for m in man if m["domain"] == d]
        ch = sorted(m["chars"] for m in ms)
        langs = ", ".join(f"{k} {v}" for k, v in sorted(Counter(m["language"] for m in ms).items()))
        main_n, scr = sum(m["pool"] == "main" for m in ms), sum(m["pool"] == "screen" for m in ms)
        out.append(f"| {d} | {SOURCE_NAMES.get(d, d)} ({ms[0]['source_url'] if d == 'contract' else 'per document'}) | "
                   f"{ms[0]['licence']} | {langs} | {main_n}{f' + {scr}' if scr else ''} | {ch[0]} / {int(statistics.median(ch))} / {ch[-1]} |")
    both = p13 + p2
    s = summ["sampling"]
    non_en = sum(dom[c["doc_id"]]["language"] != "en" for c in both)
    out += ["", "**Composition of the probe 1-3 cases** (rules in §2.2):", "",
            "| rule | required | achieved |", "|---|---|---|",
            f"| long multi-entity documents or superseded values | >= 30% of the 300 | {s['hard_present'] + s['hard_absent']}/"
            f"{s['n_present'] + s['n_absent']} = {s['hard_share']:.1%} ({s['hard_present']} present, {s['hard_absent']} absent) |",
            f"| present cases with the correct text at more than one offset | >= 20 | {s['repeated_present']} |",
            f"| a non-English extraction domain | >= 1 | receipts (Indonesian) and 10 Spanish support tickets; {non_en}/{len(both)} cases from non-English documents |",
            f"| cases per probe | 150 | probe 1/3: {s['n_present']} (pool {s['pool_present']}); probe 2: {s['n_absent']} (pool {s['pool_absent']}) |",
            "", "Cases by domain:", "", "| domain | probe 1/3 | probe 2 |", "|---|---|---|"]
    cp, ca = Counter(dom[c["doc_id"]]["domain"] for c in p13), Counter(dom[c["doc_id"]]["domain"] for c in p2)
    for d in sorted(set(cp) | set(ca)):
        out.append(f"| {d} | {cp[d]} | {ca[d]} |")
    return "\n".join(out)


def render_labelling(ds: pathlib.Path = DATASETS) -> str:
    ag = json.loads((ds / "labels" / "agreement.json").read_text())
    adj = _jsonl(ds / "labels" / "adjudication.jsonl")
    c, m = ag["candidates"], ag["mentions"]
    agreed = Counter(a["agreed_with"] for a in adj)
    kinds = Counter(a["kind"] for a in adj)
    summ = json.loads((ds / "cases" / "build_summary.json").read_text())
    f = lambda x: "n/a" if x is None else f"{x:.3f}"  # noqa: E731
    return "\n".join([
        "| judgement | items | raw agreement | Cohen's kappa |", "|---|---|---|---|",
        f"| option label (correct / partial / wrong) | {c['n_option_labels']} options in {c['n_field_instances']} field instances "
        f"| {f(c['agreement_options'])} | {f(c['kappa_options'])} |",
        f"| field status (present / absent / partial_only) | {c['n_field_instances']} | {f(c['agreement_status'])} | {f(c['kappa_status'])} |",
        f"| document multi_entity | {c['n_documents']} documents | — | {f(c['kappa_multi_entity'])} |",
        f"| mention pair same / different (probe 4) | {m['n_pairs']} pairs in {m['n_passages']} passages | {f(m['agreement_pairs'])} | {f(m['kappa_pairs'])} |",
        f"| mention ambiguous flag | {m['n_passages']} passages | — | {f(m['kappa_ambiguous'])} |",
        f"| mention role-noun flag | {m['n_passages']} passages | — | {f(m['kappa_role_noun'])} |",
        "", f"**Disagreements:** {len(c['disagreements'])} candidate items and {len(m['disagreements'])} passages; all "
        f"{len(adj)} were adjudicated ({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}); the adjudicator agreed with the first labeller "
        f"{agreed.get('A', 0)} times, the second {agreed.get('B', 0)} times, and neither {agreed.get('neither', 0)} times. "
        "Every decision and its reason is in `tests/phase0/datasets/labels/adjudication.jsonl`.",
        "", f"**Probe 4 clusters:** {summ['clusters']['passages']} passages extracted, {summ['clusters']['labelled']} with 4-14 "
        f"mentions labelled, {summ['clusters']['eligible']} eligible, {summ['clusters']['excluded_ambiguous']} mentions excluded "
        f"as ambiguous; 50 sampled ({', '.join(f'{k} {v}' for k, v in sorted(summ['clusters']['chosen_by_domain'].items()))})."])


def render_taxonomy(tax: dict, prov: list[dict]) -> str:
    s, rows = tax["summary"], tax["rows"]
    out = ["**The sample** (provenance, SHA-256 and conversion of each in `tests/fixtures/schemas/provenance.json`):", "",
           "| schema | group | title | source | licence | leaves |", "|---|---|---|---|---|---|"]
    leaves = Counter(r["schema"] for r in rows if r["kind"] == "leaf")
    for p in prov:
        out.append(f"| `{p['id']}` | {p['group']} | {p['title']} | [{p['project']}]({p['source_url']}) | {p['licence']} | {leaves[p['id']]} |")
    out += ["", f"**Counts by class** ({s['schemas']} schemas, {s['nodes']} nodes, {s['leaves']} leaf fields):", "",
            "| group | schemas | leaf fields | A | B | C | D | E | F | G | all nodes: A / C / D / E / F / G |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for g in ("extraction", "non_extraction", "additional"):
        lc = s["leaf_classes_by_group"].get(g, {})
        nc = s["node_classes_by_group"].get(g, {})
        out.append(f"| {g} | {s['schemas_by_group'].get(g, 0)} | {s['leaves_by_group'].get(g, 0)} | "
                   + " | ".join(str(lc.get(k, 0)) for k in "ABCDEFG") + " | "
                   + " / ".join(str(nc.get(k, 0)) for k in "ACDEFG") + " |")
    out += ["", "**Constructs** (every column PLAN Phase 0 lists; frequency counted over the sample):", "",
            "| construct / operation | class | Jev primitive | option source | `none_of_these`? | dependency pattern | "
            "provenance | batching | frequency (ext / non-ext / add) | importance (h/m/l) | existing alternatives | "
            "existing Jev implementations | v0 candidate? |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    by: dict[tuple, list] = {}
    for r in rows:
        by.setdefault((r["cls"], r["construct"]), []).append(r)
    for (cls, con), rs in sorted(by.items()):
        r0 = rs[0]
        fq = Counter(r["group"] for r in rs)
        im = Counter(r["importance"] for r in rs)
        v0 = r0["v0"] if not r0["v0"].startswith("no: inside") else "see rows"
        out.append(f"| {con} | {cls} | {r0['primitive']} | {r0['option_source']} | {r0['none_of_these']} | {r0['dependency']} | "
                   f"{r0['provenance']} | {r0['batching']} | {fq['extraction']} / {fq['non_extraction']} / {fq['additional']} | "
                   f"{im['high']}/{im['medium']}/{im['low']} | {r0['alternatives']} | {r0['jev_implementations']} | {v0} |")
    p = s["prediction"]
    out += ["", f"**v0 reach of the leaf fields** (by the derived v0 column): {'; '.join(f'{k}: {v}' for k, v in sorted(s['v0_leaves'].items()))}.", "",
            "**The prediction's three conditions** (§2.9):", "",
            "| condition | measured | holds? |", "|---|---|---|",
            f"| (a) class A is more than half of all schema nodes | {p['a_A_share_of_all_nodes']:.3f} | {'yes' if p['a_holds'] else 'no'} |",
            f"| (b) D + E are more than half of extraction leaf fields | {p['b_DE_share_of_extraction_leaves']:.3f} | {'yes' if p['b_holds'] else 'no'} |",
            f"| (c) median per-schema share of C + D leaf fields is below one half | {p['c_median_CD_share_per_schema']:.3f} "
            f"(without the six jev_jsonschema fixtures: {p['c_median_without_additional_fixtures']:.3f}) | {'yes' if p['c_holds'] else 'no'} |",
            "", f"**Verdict on the prediction: {p['verdict']}.**"]
    return "\n".join(out)


def render_field_table(tax: dict) -> str:
    out = ["| schema | pointer | type | class | construct | primitive | option source | `none_of_these` | dependency | "
           "provenance | importance | v0 | note |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in tax["rows"]:
        out.append(f"| {r['schema']} | `{r['pointer']}` | {r['json_type']} | {r['cls']} | {r['construct']} | {r['primitive']} | "
                   f"{r['option_source']} | {r['none_of_these']} | {r['dependency']} | {r['provenance']} | {r['importance']} | "
                   f"{r['v0']} | {r['note']} |")
    return "\n".join(out)


def _w(lo: float, hi: float) -> str:
    return f"{lo:.3f}–{hi:.3f}"


def _r(k: int, n: int) -> str:
    lo, hi = S.wilson(k, n)
    return f"{k}/{n} = {k / n:.3f} ({_w(lo, hi)})"


def render_results(res: dict) -> str:
    p123, p4, p5, p6, p7, p8 = (res[k] for k in ("probe1_2_3", "probe4", "probe5", "probe6", "probe7", "probe8"))
    out = ["| probe | tag | n | point estimate | Wilson 95% | verdict | ties | raw result | summary |",
           "|---|---|---|---|---|---|---|---|---|"]
    for i, key in ((1, "probe1"), (2, "probe2"), (3, "probe3")):
        x = p123[key]
        out.append(f"| {i}. {x['band'].split(': ', 1)[1]} | [Z{i}] | {x['n']} | {x['rate']:.3f} ({x['k']}/{x['n']}) | "
                   f"{_w(x['wilson_lo'], x['wilson_hi'])} | **{x['verdict']}** | {x['ties']} ({x['tie_rate']:.3f}) | "
                   "`tests/phase0/out/probe1_2_3.jsonl` | `tests/phase0/results/probe1_2_3.json` |")
    pc = p4["pooled"]
    out.append(f"| 4. entity resolution ({p4['chosen_variant']} variant, both runs pooled) | [Z4] | {pc['components']} components, "
               f"{p4['clusters']} clusters | correct {pc['correct_rate']:.3f}; silently wrong {pc['wrong_rate']:.3f} | "
               f"correct {_w(*pc['correct_wilson'])}; wrong {_w(*pc['wrong_wilson'])} | **{p4['verdict']}** | "
               f"— | `tests/phase0/out/probe4.runA.jsonl`, `.runB.jsonl` | `tests/phase0/results/probe4.json` |")
    c5 = p5["conditions"]
    out.append(f"| 5. state referencing | [Z5] | 320 items × 9 conditions | IDX-320 wrong {c5['IDX-320']['rate']:.3f}; "
               f"KEY-320 wrong {c5['KEY-320']['rate']:.3f} | IDX-320 {_w(*c5['IDX-320']['wilson'])} | **{p5['verdict']}** | — | "
               "`tests/phase0/out/probe5.jsonl` | `tests/phase0/results/probe5.json` |")
    ap, bp = p6["attacked_present"], p6["baseline_present"]
    out.append(f"| 6. hostile source | [Z6] | 50 attacked + 50 benign | steered {ap['steered_rate']:.3f} (baseline "
               f"{bp['steered_rate']:.3f}); screen TP {p6['attacked_screen']['flagged_rate']:.3f}, FP "
               f"{p6['benign_screen']['flagged_rate']:.3f} | see below | reading only | — | `tests/phase0/out/probe6.jsonl` | "
               "`tests/phase0/results/probe6.json` |")
    q = p7["primary_non_tie"]
    out.append(f"| 7. calibration reading | [Z7] | {q['n']} decisions | ECE {q['ece']:.3f} (one-sided 95% bound {q['ece_upper_95']:.3f}); "
               f"Brier {q['brier']:.3f} | per bin, below | reading only | {p7['excluded_ties']} excluded | from probes 1-3 | "
               "`tests/phase0/results/probe7.json` |")
    out.append(f"| 8. single candidates and partials | [Z8] | 50 / 50 / 50 / {p8['partial_only']['n']} | see below | see below | "
               "reading only | — | `tests/phase0/out/probe8.jsonl` | `tests/phase0/results/probe8.json` |")
    out += ["", f"**Candidate selection: {p123['candidate_selection'].replace('probe', 'probe ')}.** Abandon criterion fired: "
            f"{'yes' if p123['abandon'] else 'no'}.", "", "### 6.1 Probes 1-3 in detail", "",
            "| probe | correct | abstain | tie | partial commit | wrong commit | invalid |", "|---|---|---|---|---|---|---|"]
    for key in ("probe1", "probe2"):
        c = p123[key]["counts"]
        label = "present (probes 1 and 3)" if key == "probe1" else "absent (probe 2)"
        out.append(f"| {label} | {c['correct']} | {c['abstain']} | {c['tie']} | {c['partial']} | {c['wrong']} | {c['invalid']} |")
    out += ["", "| breakdown | probe 1 (correct) | probe 2 (abstain) | probe 3 (false abstention) |", "|---|---|---|---|"]
    keys = sorted(set(p123["probe1"]["by_domain"]) | set(p123["probe2"]["by_domain"]))
    for group, rows in (("by_domain", keys), ("by_hard", ["hard", "other"])):
        for g in rows:
            cells = []
            for key in ("probe1", "probe2", "probe3"):
                b = p123[key][group].get(g)
                cells.append(f"{b['k']}/{b['n']}" if b else "—")
            out.append(f"| {g} | " + " | ".join(cells) + " |")
    for g in ("repeated", "unique"):
        b1, b3 = p123["probe1"]["by_repeated"].get(g), p123["probe3"]["by_repeated"].get(g)
        out.append(f"| {g} text | {b1['k']}/{b1['n']} | — | {b3['k']}/{b3['n']} |")
    out += ["", "The operating characteristic at the achieved n (150 per probe) is the one pre-registered in §2.10.", "",
            "### 6.2 Probe 4 in detail", "",
            "| variant | components | correct | unresolved | merges | splits | silently wrong rate | correct rate |",
            "|---|---|---|---|---|---|---|---|"]
    for v in ("internal", "cross"):
        x = p4["variants"][v]["pooled"]
        out.append(f"| {v} | {sum(x.values())} | {x.get('correct', 0)} | {x.get('unresolved', 0)} | {x.get('merge', 0)} | "
                   f"{x.get('split', 0)} | {p4['variants'][v]['silently_wrong_rate']:.3f} | {p4['variants'][v]['correct_rate']:.3f} |")
    out += ["", "| run | components | correct | silently wrong | verdict |", "|---|---|---|---|---|"]
    for r, x in p4["per_run"].items():
        out.append(f"| {r} | {x['components']} | {_r(x['correct'], x['components'])} | {_r(x['silently_wrong'], x['components'])} | {x['verdict']} |")
    pa, nt, cc, fl = p4["pair_accuracy"], p4["non_transitive_triples"], p4["clique_completeness"], p4["pair_flips"]
    out += ["", f"Pair accuracy at 0.5: {_r(pa['k'], pa['n'])}. Non-transitive triples: {nt['k']}/{nt['n']} "
            f"({nt['clusters_with_one']} cluster-runs with at least one). Clique completeness: {_r(cc['k'], cc['n'])}. "
            f"Pair decisions flipping between the two identical runs: {fl['k']}/{fl['n']}.", "",
            "### 6.3 Probe 5 in detail", "", "| condition | requests | wrong | rate | Wilson 95% |", "|---|---|---|---|---|"]
    for k, v in c5.items():
        out.append(f"| {k} | {v['requests']} | {v['wrong']}/{v['n']} | {v['rate']:.3f} | {_w(*v['wilson'])} |")
    out += ["", "### 6.4 Probe 6 in detail", "",
            "| question | n | correct | steered to the advocated span | abstained | tie | other commit |", "|---|---|---|---|---|---|---|"]
    for k in ("baseline_present", "attacked_present", "baseline_absent", "attacked_absent"):
        x = p6[k]
        other = x["n"] - x.get("correct", 0) - x.get("steered", 0) - x.get("abstain", 0) - x.get("tie", 0) - x.get("invalid", 0)
        out.append(f"| {k.replace('_', ', ')} | {x['n']} | {x.get('correct', 0)} | {_r(x.get('steered', 0), x['n'])} | "
                   f"{_r(x.get('abstain', 0), x['n'])} | {x.get('tie', 0)} | {other} |")
    for k in ("attacked_present", "attacked_absent"):
        x = p6[k]
        out.append(f"| {k.replace('_', ', ')}: style A (inline) / B (appended) steered | | | "
                   f"{x.get('style_A_steered', 0)}/{x.get('style_A_n', 0)} / {x.get('style_B_steered', 0)}/{x.get('style_B_n', 0)} | | | |")
    out += ["", "| source screen (d1, flags at p >= 0.56) | n | flagged |", "|---|---|---|"]
    for k, lab in (("attacked_screen", "attacked documents (true positives)"), ("baseline_screen", "the same documents unattacked"),
                   ("benign_screen", "benign documents with an ordinary processing note (false positives)")):
        out.append(f"| {lab} | {p6[k]['n']} | {_r(p6[k]['flagged'], p6[k]['n'])} |")
    out += ["", "### 6.5 Probe 7 in detail", "", "| reading | n | mean p | accuracy | ECE | ECE 95% bound | Brier | share at p = 1.00 |",
            "|---|---|---|---|---|---|---|---|"]
    for k, lab in (("primary_non_tie", "committed decisions (ties excluded)"), ("ties_included", "ties included (argmax)")):
        x = p7[k]
        out.append(f"| {lab} | {x['n']} | {x['mean_p']:.3f} | {x['accuracy']:.3f} | {x['ece']:.3f} | {x['ece_upper_95']:.3f} | "
                   f"{x['brier']:.3f} | {x['share_p_100']:.3f} |")
    out += ["", "Reliability (committed decisions, tie-safe equal-mass bins):", "",
            "| p range | n | mean p | accuracy | Wilson 95% |", "|---|---|---|---|---|"]
    for b in p7["primary_non_tie"]["reliability"]:
        out.append(f"| {b['p_min']:.2f}–{b['p_max']:.2f} | {b['n']} | {b['mean_p']:.3f} | {b['accuracy']:.3f} | {_w(b['wilson_lo'], b['wilson_hi'])} |")
    out += ["", "### 6.6 Probe 8 in detail", "", "| set | intended answer | n | rate of the intended answer | commit | abstain | tie |",
            "|---|---|---|---|---|---|---|"]
    for k, lab in (("lone_correct", "commit"), ("lone_wrong", "abstain"), ("lone_partial", "abstain"), ("partial_only", "abstain")):
        x = p8[k]
        out.append(f"| {k.replace('_', ' ')} | {lab} | {x['n']} | {_r(round(x['rate'] * x['n']), x['n'])} | {x.get('commit', 0)} | "
                   f"{x.get('abstain', 0)} | {x.get('tie', 0)} |")
    out += ["", f"{p8['lone_partial'].get('constructed', 0)} of the 50 lone partials were constructed by the §2.8 rule; the rest "
            "were labelled partial options. Only 17 of the 932 labelled field instances had a source stating only a "
            f"partial value, so the partial-only set has {p8['partial_only']['n']} cases, "
            f"{max(0, R.N_PROBE8 - p8['partial_only']['n'])} short of the 50 target (reading only; §2.8). "
            "Partial-only sources, by field type: "
            + "; ".join(f"{ft} {v['abstain']}/{v['n']}" for ft, v in p8["partial_only"]["by_field_type"].items()) + "."]
    return "\n".join(out)


def render_floor(p4: dict) -> str:
    f = p4["floor"]
    out = ["| floor | same-entity pairs at or below (both runs pooled) | <= 2%? |", "|---|---|---|"]
    for g, sh in f["share_at_or_below"].items():
        out.append(f"| {g} | {sh:.4f} ({round(sh * f['same_entity_pairs'])}/{f['same_entity_pairs']}) | {'yes' if sh <= 0.02 else 'no'} |")
    return "\n".join(out + ["", f"**conflict_floor = {f['value']:.2f}**; qualifying values {f['qualifying']}; grid top binds: "
                                 f"{'yes' if f['grid_top_binds'] else 'no'}; no value qualified: {'yes' if f['no_value_qualified'] else 'no'}. "
                                 f"**Variant: {p4['chosen_variant']}** (lower silently-wrong point estimate: internal "
                                 f"{p4['variants']['internal']['silently_wrong_rate']:.3f}, cross {p4['variants']['cross']['silently_wrong_rate']:.3f}). "
                                 f"**Probe 4 verdict under the chosen variant: {p4['verdict']}.**"])


def replace_block(doc: str, name: str, body: str) -> str:
    pat = re.compile(rf"(<!-- BEGIN:{name} -->\n).*?(<!-- END:{name} -->)", re.S)
    if not pat.search(doc):
        raise ValueError(f"no generated block {name!r} in the document")
    return pat.sub(lambda m: m.group(1) + body.rstrip("\n") + "\n" + m.group(2), doc)


def generated_blocks(ds: pathlib.Path = DATASETS, results: pathlib.Path = RESULTS,
                     schemas: pathlib.Path = SCHEMAS) -> dict[str, str]:
    blocks = {}
    if (ds / "cases" / "build_summary.json").exists():
        blocks["corpus"] = render_corpus(ds)
        blocks["labelling"] = render_labelling(ds)
    if (results / "taxonomy.json").exists():
        tax = json.loads((results / "taxonomy.json").read_text())
        prov = json.loads((schemas / "provenance.json").read_text())
        blocks["taxonomy"] = render_taxonomy(tax, prov)
        blocks["fields"] = render_field_table(tax)
    names = ("probe1_2_3", "probe4", "probe5", "probe6", "probe7", "probe8")
    if all((results / f"{n}.json").exists() for n in names):
        res = {n: json.loads((results / f"{n}.json").read_text()) for n in names}
        blocks["results"] = render_results(res)
        blocks["floor"] = render_floor(res["probe4"])
    return blocks


def update_doc(doc_path: pathlib.Path = DOC, **kw) -> list[str]:
    doc = doc_path.read_text()
    names = []
    for name, body in generated_blocks(**kw).items():
        if f"<!-- BEGIN:{name} -->" in doc:
            doc = replace_block(doc, name, body)
            names.append(name)
    doc_path.write_text(doc)
    return names


def main(argv: list[str]) -> int:
    if argv[:1] == ["doc"]:
        print("updated blocks:", ", ".join(update_doc()))
        return 0
    if argv[:1] == ["oc"]:
        d = oc_data()
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "oc.json").write_text(json.dumps(d, indent=1) + "\n")
        print(render_oc(d))
        return 0
    print("usage: python -m tests.phase0.report <oc|doc>", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
