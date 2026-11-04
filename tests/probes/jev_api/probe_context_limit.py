"""Phase 0r: re-measures [P3] (context limits, behaviour over a limit, silent truncation) on the OpenAI Decisions
API (`gpt-6-luna`) through jevclient's `decisions` backend. Adapted, because the Decisions window is model-wide
(1.05M tokens, input above 272k billed at 2x; D3) and the probe budget allows no request above ~950k tokens:
 a) a ladder of state sizes (~30k, ~130k, ~265k, ~500k, ~900k input tokens; one request each, sized from a
    measured tokens-per-sentence) with the needle questions of (b) asked at every rung, so acceptance and
    truncation are measured together; a rejected rung starts a bisection (at most 5 more requests, all <= 950k);
 c) 200 questions (the cap) over a ~250k-token state: accepted? state billed once? any refusals or errors?
 d) one long question over a tiny state: ~10k, ~60k and ~250k tokens of instructions -> a per-question limit?
The Jev binary search (100..8000 sentences) and Jev's `max_tokens_exceeded` check do not apply. The rejection
status and error code are recorded verbatim. Summary: tests/probes/results/0r/probe_context_limit.json.

Claim (DESIGN §2, §8.2, §10): ~64k tokens shared by state + questions; executor must refuse
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
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save, save_summary
random.seed(7)
CITIES = ["Oslo","Lima","Porto","Dakar","Quito","Hanoi","Perth","Tunis","Cork","Riga","Accra","Leeds","Omaha","Turin","Graz"]
ITEMS = ["valves","gaskets","bolts","sensors","cables","filters","pumps","brackets","hinges","fuses"]
SENT = [f"Record {i}: the shipment to {random.choice(CITIES)} contained {random.randint(2,99)} boxes of {random.choice(ITEMS)}." for i in range(70000)]  # first 20,000 identical to the Jev run

def state_of(n): return " ".join(SENT[:n])
Q1 = {"q": {"type": "noul", "instructions": "Does the ledger mention shipments to Oslo?"}}

async def main():
    j = Jev(concurrency=1); out = {"ladder": []}
    cal = await j.ask(state_of(2000), Q1); cal0 = await j.ask(state_of(1), Q1)
    tps = (cal["usage"]["input_tokens"] - cal0["usage"]["input_tokens"]) / 1999
    out["tokens_per_sentence"] = round(tps, 3)
    def needle_req(n):
        st = "SECURITY NOTE: the vault code is PURPLE-ELEPHANT. " + state_of(n) + " FINAL NOTE: the backup generator is located in the basement of building K."
        qs = {"start": {"type": "noul", "instructions": "Does the text state that the vault code is PURPLE-ELEPHANT?"},
              "end": {"type": "noul", "instructions": "Does the text say the backup generator is in the basement of building K?"},
              "end_neg": {"type": "noul", "instructions": "Does the text say the backup generator is on the roof of building K?"},
              "start_c": {"type": "choice", "instructions": "What is the vault code according to the text?", "criteria": {"PURPLE-ELEPHANT": None, "GREEN-TIGER": None, "not stated": None}},
              "end_c": {"type": "choice", "instructions": "Where is the backup generator according to the text?", "criteria": {"basement of building K": None, "roof of building K": None, "not stated": None}},
              "oslo": Q1["q"]}
        return st, qs
    async def rung(target):
        n = min(len(SENT), int(target / tps))
        st, qs = needle_req(n)
        r = await j.ask(st, qs)
        a = r["body"]["answers"] if r["status"] == 200 else None
        rec = {"target_tokens": target, "sentences": n, "chars": len(st), "status": r["status"], "input_tokens": (r.get("usage") or {}).get("input_tokens"),
               "latency_s": round(r["latency_s"], 3) if r.get("latency_s") else None, "refusals": r.get("refusals"),
               "needles": {k: (v.get("noul") if v["type"] == "noul" else v.get("choice")) if v.get("type") != "refusal" else "refusal" for k, v in a.items()} if a else None,
               "error": r["body"] if r["status"] != 200 else None}
        out["ladder"].append(rec); print(json.dumps(rec)[:500], flush=True); return r["status"] == 200
    ok_hi, bad = 0, None
    for target in (30_000, 130_000, 265_000, 500_000, 900_000):
        if await rung(target): ok_hi = target
        else: bad = target; break
    if bad:
        for _ in range(5):
            mid = (ok_hi + bad) // 2
            if await rung(mid): ok_hi = mid
            else: bad = mid
    out["max_ok_target_tokens"] = ok_hi; out["min_rejected_target_tokens"] = bad
    # c) 200 questions over ~250k
    n = int(250_000 / tps); big = state_of(n)
    qs = {f"k{i}": {"type": "noul", "instructions": f"Does the ledger mention a shipment with exactly {i} boxes of valves to Oslo?"} for i in range(200)}
    r1 = await j.ask(big, {"k0": qs["k0"]}); r200 = await j.ask(big, qs)
    out["q200_over_250k"] = {"status": r200["status"], "input_tokens_1q": (r1.get("usage") or {}).get("input_tokens"),
                             "input_tokens_200q": (r200.get("usage") or {}).get("input_tokens"), "latency_1q": r1.get("latency_s"), "latency_200q": r200.get("latency_s"),
                             "n_answers": len(r200["body"]["answers"]) if r200["status"] == 200 else 0, "refusals": r200.get("refusals"),
                             "yes_answers": sum(a.get("noul", 0) > .5 for a in r200["body"]["answers"].values()) if r200["status"] == 200 else None,
                             "k0_alone_vs_batched": [r1["body"]["answers"]["k0"], r200["body"]["answers"]["k0"]] if r200["status"] == 200 and r1["status"] == 200 else None,
                             "error": r200["body"] if r200["status"] != 200 else None}
    print("q200", json.dumps(out["q200_over_250k"])[:600], flush=True)
    # d) one long question
    for target in (10_000, 60_000, 250_000):
        ns = int(target / tps)
        q = {"q": {"type": "noul", "instructions": {"reference": state_of(ns), "question": "Does `reference` mention shipments to Oslo?"}}}
        r = await j.ask("A short state.", q)
        out[f"longq_{target}"] = {"status": r["status"], "input_tokens": (r.get("usage") or {}).get("input_tokens"), "err": r["body"] if r["status"] != 200 else None,
                                  "answer": r["body"]["answers"]["q"] if r["status"] == 200 else None}
        print("longq", target, json.dumps(out[f"longq_{target}"])[:400], flush=True)
    await j.aclose(); save("p03_context", out)
    save_summary("probe_context_limit", j, out, n="one request per size")
    print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
