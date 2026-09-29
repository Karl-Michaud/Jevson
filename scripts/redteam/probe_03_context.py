"""Claim (DESIGN §2, §8.2, §10): ~64k tokens shared by state + questions; executor must refuse
rather than truncate. Vendor models.md: 64k per request total AND 32k for state + longest question.
Method:
 a) binary search on state size (synthetic ledger sentences) with one short noul -> max accepted
    input_tokens, exact error body at rejection.
 b) needle test for silent truncation: a unique fact placed at the START and at the END of a
    state just below the found limit; ask about both. If the end needle is missed on accepted
    requests near the limit, truncation is suspected.
 c) total-vs-per-question: small state + many questions whose sum exceeds 32k and then 64k.
 d) single long question: small state + one question with ~20k / ~40k tokens of instructions.
"""
import asyncio, json, random
from jevclient import Jev, save
random.seed(7)
CITIES = ["Oslo","Lima","Porto","Dakar","Quito","Hanoi","Perth","Tunis","Cork","Riga","Accra","Leeds","Omaha","Turin","Graz"]
ITEMS = ["valves","gaskets","bolts","sensors","cables","filters","pumps","brackets","hinges","fuses"]
SENT = [f"Record {i}: the shipment to {random.choice(CITIES)} contained {random.randint(2,99)} boxes of {random.choice(ITEMS)}." for i in range(20000)]

def state_of(n): return " ".join(SENT[:n])
Q1 = {"q": {"type": "noul", "instructions": "Does the ledger mention shipments to Oslo?"}}

async def main():
    j = Jev(concurrency=2); out = {"search": []}
    lo, hi = 100, 8000  # sentences
    probe = {}
    async def t(n):
        r = await j.ask(state_of(n), Q1)
        rec = {"sentences": n, "status": r["status"], "usage": r.get("usage"), "body": r["body"] if r["status"] != 200 else None, "latency": r["latency_s"]}
        out["search"].append(rec); print(rec); return r
    r = await t(hi)
    while hi - lo > 20:
        mid = (lo + hi) // 2
        r = await t(mid)
        if r["status"] == 200: lo = mid
        else: hi = mid
    out["max_ok_sentences"] = lo
    # b) needle
    for n in [lo - 5, lo, lo // 2]:
        st = "SECURITY NOTE: the vault code is PURPLE-ELEPHANT. " + state_of(n) + " FINAL NOTE: the backup generator is located in the basement of building K."
        qs = {"start": {"type": "noul", "instructions": "Does the text state that the vault code is PURPLE-ELEPHANT?"},
              "end": {"type": "noul", "instructions": "Does the text say the backup generator is in the basement of building K?"},
              "end_neg": {"type": "noul", "instructions": "Does the text say the backup generator is on the roof of building K?"},
              "start_c": {"type": "choice", "instructions": "What is the vault code according to the text?", "criteria": {"PURPLE-ELEPHANT": None, "GREEN-TIGER": None, "not stated": None}},
              "end_c": {"type": "choice", "instructions": "Where is the backup generator according to the text?", "criteria": {"basement of building K": None, "roof of building K": None, "not stated": None}}}
        r = await j.ask(st, qs)
        out[f"needle_{n}"] = {"status": r["status"], "usage": r.get("usage"), "answers": r["body"].get("answers") if isinstance(r["body"], dict) else r["body"]}
        print("needle", n, json.dumps(out[f"needle_{n}"])[:600])
    # c) many questions: total budget
    small = state_of(50)
    for nq in [2000, 3000, 3600, 4000, 5000]:
        qs = {f"k{i}": {"type": "noul", "instructions": f"Does the ledger mention a shipment with exactly {i} boxes of valves to Oslo?"} for i in range(nq)}
        r = await j.ask(small, qs)
        out[f"manyq_{nq}"] = {"status": r["status"], "usage": r.get("usage"), "err": r["body"] if r["status"] != 200 else None,
                              "n_answers": len(r["body"]["answers"]) if r["status"] == 200 else 0, "latency": r["latency_s"]}
        print("manyq", nq, out[f"manyq_{nq}"])
    # d) one long question
    for ns in [1000, 1800, 2500, 3500]:
        qs = {"q": {"type": "noul", "instructions": {"reference": state_of(ns), "question": "Does `reference` mention shipments to Oslo?"}}}
        r = await j.ask("A short state.", qs)
        out[f"longq_{ns}"] = {"status": r["status"], "usage": r.get("usage"), "err": r["body"] if r["status"] != 200 else None}
        print("longq", ns, out[f"longq_{ns}"])
    # e) state near 32k + one long question (state+longest > 32k while total < 64k?)
    await j.aclose(); save("p03_context", out); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
