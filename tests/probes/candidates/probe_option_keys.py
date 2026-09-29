"""Claim area (DESIGN §5.1/§5.5: candidate spans become choice options; duplicate span texts at
different offsets are possible). Tests whether options can be keyed by opaque ids with the span
text in the criteria description (needed when two candidates share text or text is long) without
losing accuracy/abstention. Method: re-use probe_abstention_long_docs S-long cases (36 long noisy docs, ~10
candidates) from raw JSON; ask choice keyed by text (as before) vs keyed 'c0..cN' with text as the
description, present and absent sets, in one request per doc. Also: duplicate-text options with
opaque ids, and a 3000-char option key / 3000-char question key acceptance check."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json
from jevclient import Jev, save, fmt_rate, RAW
import candidates.probe_abstention_long_docs  # noqa: F401  (guarded)
import random
random.seed(9)
# regenerate docs deterministically is fragile; instead rebuild S-long docs by re-running generator is not stored,
# so we rebuild from stored rows: rows lack the doc text for S-long -> regenerate via the same seeded generator.
import candidates.probe_abstention_long_docs as S
async def main():
    # re-create the exact S-long cases using the same seed path as probe_abstention_long_docs
    from candidates.probe_abstention import R
    import candidates.probe_abstention_traps as H
    R.seed(4242)
    cases = []
    types = ["T1", "T2", "T3", "T5", "T6", "T7"]
    for i in range(36):
        typ = types[i % 6]; field, correct, dis, doc = H.GEN[typ]()
        nb = S.noise_block(45); pos = R.randrange(len(nb)); nb.insert(pos, doc)
        pool = [x for x in S.same_type_from(nb, correct, typ) if x not in dis]
        R.shuffle(pool); extra = pool[:10 - len(dis) - 1]
        cases.append((typ, field, correct, dis + extra, "\n".join(nb)))
    j = Jev(concurrency=8); jobs = []
    for typ, field, correct, dis, doc in cases:
        P = dis + [correct]; random.shuffle(P); A = list(dis); random.shuffle(A)
        none_desc = f"None of the other options is the {field}."
        q = {"TXT_P": {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": {**{c: None for c in P}, "none_of_these": none_desc}},
             "TXT_A": {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": {**{c: None for c in A}, "none_of_these": none_desc}},
             "ID_P": {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": {**{f"c{i}": c for i, c in enumerate(P)}, "none_of_these": none_desc}},
             "ID_A": {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": {**{f"c{i}": c for i, c in enumerate(A)}, "none_of_these": none_desc}}}
        jobs.append((correct, P, A, doc, q))
    res = await asyncio.gather(*[j.ask(doc, q) for *_, doc, q in jobs])
    def sel(ans, opts, mode):
        c = ans["choice"]
        return c if (mode == "TXT" or c == "none_of_these") else opts[int(c[1:])]
    rep = {}
    for mode in ("TXT", "ID"):
        okP = sum(sel(r["body"]["answers"][f"{mode}_P"], P, mode) == corr for (corr, P, A, *_), r in zip(jobs, res))
        absA = sum(r["body"]["answers"][f"{mode}_A"]["choice"] == "none_of_these" for r in res)
        rep[mode] = {"P_correct": fmt_rate(okP, 36), "A_abstain": fmt_rate(absA, 36)}
    agree = sum(sel(r["body"]["answers"]["TXT_A"], A, "TXT") == sel(r["body"]["answers"]["ID_A"], A, "ID") for (corr, P, A, *_), r in zip(jobs, res))
    rep["TXT_vs_ID_absent_selection_agreement"] = f"{agree}/36"
    # long keys
    long_opt = "x" * 3000
    r1 = await j.ask("hello", {"q": {"type": "choice", "instructions": "Pick one", "criteria": {long_opt: None, "b": None}}})
    r2 = await j.ask("hello", {"k" * 3000: {"type": "noul", "instructions": "Is this a greeting?"}})
    rep["long_option_key_status"] = r1["status"]; rep["long_question_key_status"] = r2["status"]
    rep["long_option_key_err"] = r1["body"] if r1["status"] != 200 else None
    await j.aclose(); save("p09_option_keys", rep); print(json.dumps(rep, indent=1)); print("requests", j.count)
asyncio.run(main())
