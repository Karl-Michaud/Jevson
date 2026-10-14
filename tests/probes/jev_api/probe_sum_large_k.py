"""Phase 0r: re-measures [P23] (probability sums at K = 51 and 255) on the OpenAI Decisions API (`gpt-6-luna`)
through jevclient's `decisions` backend. Changed: the PROBE_OUT override to the Jev `out/` is removed (output goes to
jevclient's out/0r), and the full distribution is now stored beside the deviation so the calibration checks can
re-read it. Summary: tests/probes/results/0r/probe_sum_large_k.json.

Round 5. Claim (DESIGN §2.1): probability sums stay within min(ceil(K/2),5) hundredths of 1.00 at
large K. Method: 10 live choice questions each with K=51 and K=255 options (realistic span texts, one
correct), over short invoice states; report |sum-1.00| in hundredths, and the argmax/vendor-choice agreement."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, os, pathlib, random
import jevclient as jc
random.seed(51)
W="north harbor street suite avenue road plaza west east center tower park lane drive court square bay hill".split()
def addr(): return f"{random.randint(1,9999)} {random.choice(W).capitalize()} {random.choice(W).capitalize()}, Suite {random.randint(1,900)}"
async def main():
    J=jc.Jev(concurrency=4); out=[]
    for K in (51,255):
        for i in range(10):
            correct=addr(); opts={f"c{j}":addr() for j in range(K-1)}
            cid=f"c{random.randint(0,K-2)}"; opts[cid]=correct
            opts["none_of_these"]="None of the other options is the complete billing address as written in the source; a partial value does not count."
            state={"source":f"INVOICE {1000+i}\nBill to: Contoso Ltd, {correct}\nShip to: Contoso Warehouse, {addr()}\nTotal due: $1,204.50"}
            q={"q":{"type":"choice","instructions":"Which of these is the complete billing address as written in the source? A partial value - for example a street without its city - is not acceptable.","criteria":opts}}
            r=await J.ask(state,q); ans=r["body"]["answers"]["q"] if r["status"]==200 else None
            if not ans: out.append({"K":K,"status":r["status"]}); continue
            pr=ans["probabilities"]; s=round(sum(pr.values())*100); am=max(pr,key=pr.get)
            out.append({"K":K,"dev":abs(s-100),"argmax":am,"choice":ans.get("choice"),"correct":am==cid,"confidence":ans.get("confidence"),"probabilities":pr,"refusals":r.get("refusals")})
    await J.aclose(); jc.save("r5_sum_largek", out)
    for K in (51,255):
        rs=[o for o in out if o["K"]==K and "dev" in o]
        print(K, "n=",len(rs), "max dev=",max(o["dev"] for o in rs), "argmax==choice:",sum(o["argmax"]==o["choice"] for o in rs), "correct:",sum(o["correct"] for o in rs))
    jc.save_summary("probe_sum_large_k", J, {str(K): {"n": len([o for o in out if o["K"] == K and "dev" in o]),
        "non_200": sum(1 for o in out if o["K"] == K and "dev" not in o),
        "max_dev_hundredths": max((o["dev"] for o in out if o["K"] == K and "dev" in o), default=None),
        "argmax_eq_choice": sum(o["argmax"] == o["choice"] for o in out if o["K"] == K and "dev" in o),
        "correct": sum(o["correct"] for o in out if o["K"] == K and "dev" in o)} for K in (51, 255)}, n={"51": 10, "255": 10})
if __name__ == "__main__":
    asyncio.run(main())
