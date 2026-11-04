"""Phase 0r: re-measures [P8] (latency and usage fields) on the OpenAI Decisions API (`gpt-6-luna`) through
jevclient's `decisions` backend. Adapted: 300 questions -> 200 (the Decisions cap per request); the ~20k-token
("big") input is run at 1, 100 and 200 questions; an "xl" ~200k-token input (below the 272k long-context price
step) is added at 1 and 200 questions, 3 reps each; p95 is reported beside p50/p90/p99 (nearest-rank on small n).
Summary: tests/probes/results/0r/probe_latency.json.

Claim (DESIGN §2: 'adding questions costs almost no latency', 'latency 70-500 ms'; §8.1 cost
accounting needs jev_input_tokens). Method: sequential requests (concurrency 1) with a ~250-token
state and 1, 10, 100, 300 noul questions, 30 reps each (interleaved order); plus 1 and 100
questions over a ~20k-token state, 10 reps each. Report p50/p90/p99 wall-clock (client-side,
includes network) and the usage fields present."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random, statistics as st
from jevclient import Jev, save, save_summary
from jev_api.probe_context_limit import state_of
def pct(v, p): v = sorted(v); return round(v[min(len(v) - 1, int(round(p / 100 * (len(v) - 1))))], 3)
async def main():
    j = Jev(concurrency=1); lat = {}; usage = {}
    small = state_of(12); big = state_of(1080); xl = state_of(12400)
    plan = ([(n, "small") for n in (1, 10, 100, 200) for _ in range(30)] + [(n, "big") for n in (1, 100, 200) for _ in range(10)]
            + [(n, "xl") for n in (1, 200) for _ in range(3)])
    random.Random(5).shuffle(plan)
    for n, s in plan:
        qs = {f"q{i}": {"type": "noul", "instructions": f"Does the ledger mention a shipment of exactly {i} boxes?"} for i in range(n)}
        r = await j.ask({"small": small, "big": big, "xl": xl}[s], qs)
        if r["status"] != 200: print(r); continue
        key = f"{s}_{n}"; lat.setdefault(key, []).append(r["latency_s"]); usage[key] = r["usage"]
    rep = {k: {"n": len(v), "p50": pct(v, 50), "p90": pct(v, 90), "p95": pct(v, 95), "p99": pct(v, 99), "max": round(max(v), 3), "mean": round(st.mean(v), 3), "usage": usage[k]} for k, v in sorted(lat.items())}
    await j.aclose(); save("p08_latency", {"report": rep, "raw": lat}); save_summary("probe_latency", j, rep, n={"small": 30, "big": 10, "xl": 3})
    print(json.dumps(rep, indent=1)); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
