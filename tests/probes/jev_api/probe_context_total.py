"""Claim (DESIGN §8.2): 64k total shared window; §8.1 cost accounting via input tokens.
Method: (a) binary search number of ~26-token questions over a tiny state to find the total
input_tokens ceiling; (b) state billing: 15k-token state with 1, 10, 100 questions -> is the state
counted once per request or once per question? (c) 25k-token state + questions summing ~45k
(total ~70k) -> rejected? (d) 25k state + questions totalling ~35k (total ~60k) accepted?"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save
from jev_api.probe_context_limit import state_of  # noqa  (module guarded below)
def qs(n, off=0): return {f"k{i}": {"type": "noul", "instructions": f"Does the ledger mention a shipment with exactly {i+off} boxes of valves to Oslo?"} for i in range(n)}
async def main():
    j = Jev(concurrency=2); out = {"search": []}
    small = state_of(50)
    lo, hi = 2000, 3000
    while hi - lo > 25:
        mid = (lo + hi) // 2
        r = await j.ask(small, qs(mid))
        out["search"].append({"nq": mid, "status": r["status"], "usage": r.get("usage")}); print(out["search"][-1])
        if r["status"] == 200: lo = mid
        else: hi = mid
    out["max_nq"] = lo
    big = state_of(800)
    for n in [1, 10, 100]:
        r = await j.ask(big, qs(n)); out[f"bill_{n}"] = r.get("usage"); print("bill", n, r.get("usage"))
    r = await j.ask(state_of(1), qs(100)); out["bill_tiny_100"] = r.get("usage"); print("tiny100", r.get("usage"))
    st25 = state_of(1300)
    for n in [900, 1300, 1700]:
        r = await j.ask(st25, qs(n)); out[f"st25_{n}"] = {"status": r["status"], "usage": r.get("usage"), "err": r["body"] if r["status"] != 200 else None}; print("st25", n, out[f"st25_{n}"])
    await j.aclose(); save("p03b_context_total", out); print("requests", j.count)
asyncio.run(main())
