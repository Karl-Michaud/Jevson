"""Round 2 follow-up to probe_r2_single_candidate.py. Claim tested: DESIGN §5.2/§5.3 treat `none_of_these` as
catching a lone bad candidate; the base probe found PARTIAL spans (street without city, date without year,
first name only, amount without cents) committed 32/42. Hypothesis: whether a partial span is rejected depends
on whether the question/none description demands completeness (round 1's partial-span set asked for the
"customer's full name" / "complete billing address" / "exact total due" and abstained 24/24).
Method (SYNTHETIC PILOT): the identical condition-a (correct) and condition-c (partial) cases (same seed), one
request each, with the base wording (W0) and a completeness wording (W1):
  W1 instructions: "Which of these is the {field}, complete and exactly as written in full in the text?"
  W1 none: "None of the other options is the complete {field}. An option that is only part of it (for example
           missing the city, the year, the surname, or the cents) does not count."
Both as 2-option choice (S2) and with the 3 competitors (S4)."""
import asyncio, json
from jevclient import Jev, save, fmt_rate
import probe_r2_single_candidate as S


def q(field, opts, w):
    crit = {f"c{i}": f"\"{o}\"" for i, o in enumerate(opts)}
    if w == 0:
        crit["none_of_these"] = f"None of the other options is the {field}."
        ins = f"Which of these is the {field}?"
    else:
        crit["none_of_these"] = (f"None of the other options is the complete {field}. An option that is only part of it "
                                 f"(for example missing the city, the year, the surname, or the cents) does not count.")
        ins = f"Which of these is the {field}, complete and exactly as written in full in the text?"
    return {"type": "choice", "instructions": ins, "criteria": crit}


async def main():
    cases = [c for c in S.make_cases() if c["cond"] in ("a", "c")]
    j = Jev(concurrency=8)
    reqs = [{f"S2W{w}": q(c["field"], [c["cand"]], w) for w in (0, 1)} | {f"S4W{w}": q(c["field"], c["opts4"], w) for w in (0, 1)} for c in cases]
    res = await asyncio.gather(*[j.ask(c["doc"], r) for c, r in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        a = r["body"]["answers"]; ci = c["opts4"].index(c["cand"])
        for w in (0, 1):
            c[f"S2W{w}"] = "cand" if a[f"S2W{w}"]["choice"] == "c0" else "none"
            ch = a[f"S4W{w}"]["choice"]
            c[f"S4W{w}"] = "none" if ch == "none_of_these" else ("cand" if ch == f"c{ci}" else "other")
            c[f"S2W{w}_p"] = a[f"S2W{w}"]["probabilities"]["c0"]
    await j.aclose()
    rep = {}
    for cond in ("a", "c"):
        cs = [c for c in cases if c["cond"] == cond]; n = len(cs)
        rep[cond] = {k: fmt_rate(sum(c[k] == "cand" for c in cs), n) for k in ("S2W0", "S2W1", "S4W0", "S4W1")}
        rep[cond]["by_kind_S2W1_commit"] = {g.__name__: sum(c["S2W1"] == "cand" for c in cs if c["kind"] == g.__name__) for g in S.GENS}
        rep[cond]["by_kind_S2W0_commit"] = {g.__name__: sum(c["S2W0"] == "cand" for c in cs if c["kind"] == g.__name__) for g in S.GENS}
    save("r2_single_candidate_completeness", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
