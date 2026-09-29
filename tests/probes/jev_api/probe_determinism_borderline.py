"""Claim (DESIGN §2 determinism; §5.4 'retry useless'; PLAN Phase 3 exit 'same input resolves to
same output across runs'): identical requests give identical decisions.
Method: 40 deliberately ambiguous questions (30 noul, 10 choice) over one ambiguous state, all in
one request, repeated 25 times byte-identically (sequential). For each question: range of the
probability, sd, and whether the decision (noul>0.5 / choice argmax) ever flips. Focus on those
with mean in [0.35,0.65] (noul) or top-2 gap <0.15 (choice). Invoked again later with arg 'later'."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, sys, statistics as st
from jevclient import Jev, save

STATE = ("Email from Priya (account manager) to the ops team, Tuesday: 'Quick one - the Henderson "
         "shipment went out Friday but I think the pallet count on the manifest might be off by one? "
         "Could be my misreading. Henderson hasn't said anything yet. Their contract renews next "
         "month and they've been a bit quiet lately. Not a big deal but maybe someone could double "
         "check when they get a sec. Also, the new label printer is jamming again, third time.'")
NOULS = ["Is this email urgent?", "Is the sender worried?", "Is there a customer complaint?",
 "Is the Henderson account at risk?", "Does the sender request an action?", "Is the manifest wrong?",
 "Is this email about equipment?", "Is the tone informal?", "Is the sender blaming someone?",
 "Should this be escalated to a manager?", "Is the renewal mentioned as a concern?",
 "Is the printer problem the main topic?", "Is this a routine message?", "Does the email contain a deadline?",
 "Is the sender uncertain?", "Is this about logistics?", "Is Henderson unhappy?",
 "Does the email mention a financial loss?", "Should the ops team reply today?", "Is the sender frustrated?",
 "Is there more than one request in the email?", "Is the pallet count issue confirmed?",
 "Is this email sarcastic?", "Would a reasonable reader consider this high priority?",
 "Is the email about a single topic?", "Is the sender apologizing?", "Is the printer issue recurring?",
 "Does the sender expect a written response?", "Is this a sales-related email?", "Is the sender a manager?"]
CHOICES = [
 ("What is the main topic?", ["shipment", "printer", "contract renewal", "staffing"]),
 ("What priority should this get?", ["low", "medium", "high"]),
 ("Who should handle this first?", ["warehouse", "account management", "IT", "finance"]),
 ("What is the sender's mood?", ["calm", "mildly concerned", "anxious", "annoyed"]),
 ("What kind of message is this?", ["request", "report", "complaint", "FYI"]),
 ("Which issue is more important?", ["pallet count", "label printer"]),
 ("How confident is the sender about the error?", ["sure", "unsure", "not stated"]),
 ("What is the risk level for the Henderson account?", ["none", "low", "moderate", "high"]),
 ("What should happen next?", ["recount pallets", "call Henderson", "fix printer", "nothing"]),
 ("Which team does the email go to?", ["ops", "sales", "IT", "unclear"]),
]
Q = {f"n{i:02d}": {"type": "noul", "instructions": s} for i, s in enumerate(NOULS)}
for i, (ins, opts) in enumerate(CHOICES):
    Q[f"c{i:02d}"] = {"type": "choice", "instructions": ins, "criteria": {o: None for o in opts}}

async def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "now"
    j = Jev(); runs = []
    for _ in range(25):
        runs.append(await j.ask(STATE, Q))
    A = [r["body"]["answers"] for r in runs if r["status"] == 200]
    summ = {}
    for k in Q:
        if k.startswith("n"):
            v = [a[k]["noul"] for a in A]
            summ[k] = {"mean": round(st.mean(v), 3), "range": round(max(v)-min(v), 3), "sd": round(st.pstdev(v), 4),
                       "flip": len({x > 0.5 for x in v}) > 1, "vals": sorted(set(v))}
        else:
            ps = [a[k]["probabilities"] for a in A]
            sel = [a[k]["choice"] for a in A]
            m = {o: st.mean(p[o] for p in ps) for o in ps[0]}
            top = sorted(m.values(), reverse=True)
            summ[k] = {"mean": {o: round(x, 3) for o, x in m.items()}, "gap": round(top[0]-top[1], 3),
                       "range": round(max(max(p[o] for p in ps)-min(p[o] for p in ps) for o in ps[0]), 3),
                       "flip": len(set(sel)) > 1, "selections": {s: sel.count(s) for s in set(sel)}}
    out = {"tag": tag, "n_runs": len(A), "summary": summ, "models": sorted({r.get("model") for r in runs}), "raw": runs}
    save(f"p01b_borderline_{tag}", out)
    rngs = [s["range"] for s in summ.values()]
    print("max range", max(rngs), "mean range", round(st.mean(rngs), 4), "flips", [k for k, s in summ.items() if s["flip"]])
    for k, s in summ.items(): print(k, {x: s[x] for x in s if x not in ("vals",)})
    print("requests", j.count)
    await j.aclose()
asyncio.run(main())
