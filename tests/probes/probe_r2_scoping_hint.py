"""Round 2. Claim (DESIGN §5.3 Rev 4): "Field questions carry a scoping hint ('of *this* invoice, the one being
issued') because under-specified scope was the pilot's main failure" - i.e. a scoping hint should raise abstention
when the answer is absent in long multi-entity documents above round 1's 32/36.
Method (SYNTHETIC PILOT): the 36 round-1 S-long cases of probe_05c_abstention_stress.py regenerated exactly as
probe_09 did (same seed path): one trap passage embedded in ~45 other invoice/note/reminder lines, ~10 same-type
candidates. One request per doc, choice + described none_of_these, text keys as in round 1, present (P) and absent
(A) candidate sets, three wordings:
  H0 no hint   : "Which of these is the {field}?"  (round-1 wording)
  H1 generic   : "Which of these is the {field} of this document's main item (the one being issued or described),
                  not of the other invoices, notes, reminders or memos around it?"
  H2 anchored  : "In the passage that begins \"<first 60 chars of the target passage>\", which of these is the {field}?"
H2 needs to know where the target passage is, which a compiler generally does not; it is an upper bound."""
import asyncio, json, random
from jevclient import Jev, save, fmt_rate
import probe_05c_abstention_stress as S
import probe_05b_abstention_hard as H
from probe_05_abstention import R


def rebuild():
    R.seed(4242)
    cases = []
    types = ["T1", "T2", "T3", "T5", "T6", "T7"]
    for i in range(36):
        typ = types[i % 6]; field, correct, dis, doc = H.GEN[typ]()
        nb = S.noise_block(45); pos = R.randrange(len(nb)); nb.insert(pos, doc)
        pool = [x for x in S.same_type_from(nb, correct, typ) if x not in dis]
        R.shuffle(pool); extra = pool[:10 - len(dis) - 1]
        cases.append({"type": typ, "field": field, "correct": correct, "cands": dis + extra, "passage": doc, "text": "\n".join(nb)})
    return cases


def q(field, cands, hint, passage):
    crit = {c: None for c in cands}; crit["none_of_these"] = f"None of the other options is the {field}."
    if hint == "H0": ins = f"Which of these is the {field}?"
    elif hint == "H1": ins = (f"Which of these is the {field} of this document's main item (the one being issued or described), "
                              f"not of the other invoices, notes, reminders or memos around it?")
    else: ins = f"In the passage that begins \"{passage[:60]}\", which of these is the {field}?"
    return {"type": "choice", "instructions": ins, "criteria": crit}


async def main():
    cases = rebuild(); rr = random.Random(31)
    j = Jev(concurrency=8); reqs = []
    for c in cases:
        P = c["cands"] + [c["correct"]]; rr.shuffle(P); A = list(c["cands"]); rr.shuffle(A)
        c["P"], c["A"] = P, A
        reqs.append({f"{h}_{t}": q(c["field"], S_, h, c["passage"]) for h in ("H0", "H1", "H2") for t, S_ in (("P", P), ("A", A))})
    res = await asyncio.gather(*[j.ask(c["text"], qq) for c, qq in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        c["ans"] = r["body"]["answers"]
    await j.aclose()
    n = len(cases); rep = {"n": n}
    for h in ("H0", "H1", "H2"):
        rep[h] = {"P_correct": fmt_rate(sum(c["ans"][f"{h}_P"]["choice"] == c["correct"] for c in cases), n),
                  "P_false_abstain": fmt_rate(sum(c["ans"][f"{h}_P"]["choice"] == "none_of_these" for c in cases), n),
                  "A_abstain": fmt_rate(sum(c["ans"][f"{h}_A"]["choice"] == "none_of_these" for c in cases), n),
                  "A_commits": [(c["type"], c["ans"][f"{h}_A"]["choice"], c["ans"][f"{h}_A"]["confidence"]) for c in cases if c["ans"][f"{h}_A"]["choice"] != "none_of_these"],
                  "P_errors": [(c["type"], c["correct"], c["ans"][f"{h}_P"]["choice"]) for c in cases if c["ans"][f"{h}_P"]["choice"] != c["correct"]]}
    # paired comparison on absent sets
    rep["A_H1_vs_H0"] = {"H1_abstain_H0_commit": sum(c["ans"]["H1_A"]["choice"] == "none_of_these" and c["ans"]["H0_A"]["choice"] != "none_of_these" for c in cases),
                         "H0_abstain_H1_commit": sum(c["ans"]["H0_A"]["choice"] == "none_of_these" and c["ans"]["H1_A"]["choice"] != "none_of_these" for c in cases)}
    save("r2_scoping_hint", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
