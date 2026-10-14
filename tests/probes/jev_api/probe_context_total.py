"""Phase 0r: re-measures [P3] (state billed once per request; the total budget shared by state and questions) on
the OpenAI Decisions API (`gpt-6-luna`) through jevclient's `decisions` backend. Adapted: the question-count search
is replaced by the 200-question cap (measured in probe_limits.py), so (a) is dropped; (b) bills a ~15k-token state
with 1, 10, 100 and 200 questions and a tiny state with 100 and 200 (per-question token cost); (c)/(d) become one
request of 200 long questions (~500 tokens each, ~100k tokens of questions) over the ~15k state: accepted, and
billed as state + questions? The >900k total-limit behaviour is in probe_context_limit.py.
Summary: tests/probes/results/0r/probe_context_total.json.

Claim (DESIGN §8.2): 64k total shared window; §8.1 cost accounting via input tokens.
Method: (a) binary search number of ~26-token questions over a tiny state to find the total
input_tokens ceiling; (b) state billing: 15k-token state with 1, 10, 100 questions -> is the state
counted once per request or once per question? (c) 25k-token state + questions summing ~45k
(total ~70k) -> rejected? (d) 25k state + questions totalling ~35k (total ~60k) accepted?"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save, save_summary
from jev_api.probe_context_limit import state_of  # noqa  (module guarded below)
def qs(n, off=0): return {f"k{i}": {"type": "noul", "instructions": f"Does the ledger mention a shipment with exactly {i+off} boxes of valves to Oslo?"} for i in range(n)}
async def main():
    j = Jev(concurrency=2); out = {}
    big = state_of(950)
    for n in [1, 10, 100, 200]:
        r = await j.ask(big, qs(n)); out[f"bill_15k_{n}"] = (r.get("usage") or {}).get("input_tokens"); print("bill", n, out[f"bill_15k_{n}"])
    for n in [1, 100, 200]:
        r = await j.ask(state_of(1), qs(n)); out[f"bill_tiny_{n}"] = (r.get("usage") or {}).get("input_tokens"); print("tiny", n, out[f"bill_tiny_{n}"])
    out["tokens_per_question_15k"] = round((out["bill_15k_200"] - out["bill_15k_1"]) / 199, 2)
    out["tokens_per_question_tiny"] = round((out["bill_tiny_200"] - out["bill_tiny_1"]) / 199, 2)
    out["state_tokens_once"] = out["bill_15k_1"] - out["bill_tiny_1"]
    out["state_billed_once_per_request"] = abs((out["bill_15k_200"] - out["bill_tiny_200"]) - out["state_tokens_once"]) < 50
    longq = {f"k{i}": {"type": "noul", "instructions": f"Consider this background before answering: {state_of(25 + (i % 5))} Question {i}: does the ledger mention a shipment with exactly {i} boxes of valves to Oslo?"} for i in range(200)}
    r = await j.ask(big, longq)
    out["long_200q"] = {"status": r["status"], "input_tokens": (r.get("usage") or {}).get("input_tokens"), "refusals": r.get("refusals"),
                        "latency_s": r.get("latency_s"), "err": r["body"] if r["status"] != 200 else None}
    print("long200", out["long_200q"])
    await j.aclose(); save("p03b_context_total", out); save_summary("probe_context_total", j, out, n="one request per size"); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
