"""Renders the computed tables of docs/taxonomy.md from code and from the committed result files.

``uv run python -m tests.phase0.report oc`` prints the operating-characteristic tables (§2.10) and writes
tests/phase0/results/oc.json.
"""
from __future__ import annotations

import json
import pathlib
import sys

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


def main(argv: list[str]) -> int:
    if argv[:1] == ["oc"]:
        d = oc_data()
        RESULTS.mkdir(exist_ok=True)
        (RESULTS / "oc.json").write_text(json.dumps(d, indent=1) + "\n")
        print(render_oc(d))
        return 0
    print("usage: python -m tests.phase0.report oc", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
