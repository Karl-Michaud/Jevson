"""Claim (DESIGN §2 table, §10): choice <=255 options, score 2-10 levels.
Method: one request each: choice with 2,255,256,500,1000 options; score with 1,2,10,11,20 levels.
Also: noul with criteria; choice with 0/1 option; duplicate-ish option keys; empty instructions.
Record status and exact error body."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json
from jevclient import Jev, save
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
    for n in [1, 2, 10, 11, 20]:
        r = await j.ask(STATE, {"q": {"type": "score", "instructions": "How interested is the customer?",
                                       "criteria": [f"level {i}" for i in range(n)]}})
        out[f"score_{n}"] = {"status": r["status"], "body": r["body"] if r["status"] != 200 else
                             {k: r["body"]["answers"]["q"][k] for k in ("score", "confidence", "probabilities")}}
    for n in [256, 1000]:
        qs = {f"k{i}": {"type": "noul", "instructions": f"Is this about item {i}?"} for i in range(n)}
        r = await j.ask(STATE, qs)
        out[f"nquestions_{n}"] = {"status": r["status"], "n_answers": len(r["body"].get("answers", {})) if isinstance(r["body"], dict) else None,
                                  "usage": r.get("usage"), "err": r["body"] if r["status"] != 200 else None}
    out["noul_with_confidence?"] = (await j.ask(STATE, {"q": {"type": "noul", "instructions": "Is this about pricing?"}}))["body"]
    await j.aclose(); save("p02_limits", out)
    for k, v in out.items(): print(k, json.dumps(v)[:400])
    print("requests", j.count)
asyncio.run(main())
