"""Phase 0r: re-measures [P2] (option, level and question-count limits; error shape) on the OpenAI Decisions API
(`gpt-6-luna`) through jevclient's `decisions` backend. Adapted: question counts 199/200/201/256/1000 (the documented
Decisions cap is 200 per request, D2/0r), score levels 1/2/10/11/20/50/100/255/256 and then a binary search for the
largest accepted level count (Jev capped at 10), and a predicate is sent without `criteria` (Decisions has no noul
criteria). Summary: tests/probes/results/0r/probe_limits.json.

Claim (DESIGN §2 table, §10): choice <=255 options, score 2-10 levels.
Method: one request each: choice with 2,255,256,500,1000 options; score with 1,2,10,11,20 levels.
Also: noul with criteria; choice with 0/1 option; duplicate-ish option keys; empty instructions.
Record status and exact error body."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json
from jevclient import Jev, save, save_summary
STATE = "The customer wants to know the price of the premium plan."
async def main():
    j = Jev(); out = {}
    for n in [1, 2, 255, 256, 500, 1000]:
        crit = {f"opt{i}": None for i in range(n)}
        crit["opt0"] = "Pricing questions"
        r = await j.ask(STATE, {"q": {"type": "choice", "instructions": "Which option fits?", "criteria": crit}})
        out[f"choice_{n}"] = {"status": r["status"], "body": r["body"] if r["status"] != 200 else
                              {"choice": r["body"]["answers"]["q"]["choice"], "n_probs": len(r["body"]["answers"]["q"]["probabilities"]),
                               "usage": r["usage"]}}
    out["choice_0"] = (await j.ask(STATE, {"q": {"type": "choice", "instructions": "x", "criteria": {}}}))
    async def score(n):
        r = await j.ask(STATE, {"q": {"type": "score", "instructions": "How interested is the customer?",
                                       "criteria": [f"level {i}" for i in range(n)]}})
        out[f"score_{n}"] = {"status": r["status"], "body": r["body"] if r["status"] != 200 else
                             {k: r["body"]["answers"]["q"][k] for k in ("score", "confidence", "probabilities")}}
        return r["status"] == 200
    ok = {n: await score(n) for n in [1, 2, 10, 11, 20, 50, 100, 255, 256]}
    rej = sorted(n for n, v in ok.items() if not v and n > 2); hi = rej[0] if rej else None
    lo = max(n for n, v in ok.items() if v and (hi is None or n < hi))
    if hi:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if await score(mid): lo = mid
            else: hi = mid
    out["score_max_levels_accepted"] = lo; out["score_min_levels_rejected"] = hi
    for n in [199, 200, 201, 256, 1000]:
        qs = {f"k{i}": {"type": "noul", "instructions": f"Is this about item {i}?"} for i in range(n)}
        r = await j.ask(STATE, qs)
        out[f"nquestions_{n}"] = {"status": r["status"], "n_answers": len(r["body"].get("answers", {})) if isinstance(r["body"], dict) else None,
                                  "usage": r.get("usage"), "err": r["body"] if r["status"] != 200 else None}
    out["noul_with_confidence?"] = (await j.ask(STATE, {"q": {"type": "noul", "instructions": "Is this about pricing?"}}))["body"]
    out["empty_instructions"] = {k: v for k, v in (await j.ask(STATE, {"q": {"type": "noul", "instructions": ""}})).items() if k in ("status", "body")}
    await j.aclose(); save("p02_limits", out)
    st = {k: v.get("status") if isinstance(v, dict) else None for k, v in out.items()}
    errs = {k: (v.get("body") or v.get("err")) for k, v in out.items() if isinstance(v, dict) and v.get("status") not in (200, None)}
    save_summary("probe_limits", j, {"status_by_case": st, "error_bodies": errs,
        "score_max_levels_accepted": out["score_max_levels_accepted"], "score_min_levels_rejected": out["score_min_levels_rejected"],
        "choice_255_tokens": (out.get("choice_255", {}).get("body") or {}).get("usage") if out.get("choice_255", {}).get("status") == 200 else None,
        "noul_answer_shape": out["noul_with_confidence?"].get("decisions_answers") if isinstance(out["noul_with_confidence?"], dict) else None},
        n="one request per size")
    for k, v in out.items(): print(k, json.dumps(v)[:400])
    print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
