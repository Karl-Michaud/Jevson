"""Phase 0r: re-measures [P22] (share of candidate choices with a top-two margin <= 0.10) on the saved OpenAI
Decisions API (`gpt-6-luna`) answers in jevclient.RAW (tests/probes/out/0r/raw). Only the ported source-ceiling
probe asks `none_of_these` choices there, so n is small; the Phase 0 corpus runs (tests/phase0) are the larger
pool. Summary: tests/probes/results/0r/check_tie_margin_pooled.json.

Round 4. Claim (DESIGN §6.2): share of candidate choices (choices offering none_of_these) whose
top-two margin is <= 0.10 in hundredths, pooled over EVERY saved live answer in out/raw/r1..r4 raw JSON.
Method: walk all raw JSON, collect every probabilities map containing none_of_these, dedupe nothing."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import os
import glob, json
by={}
def walk(o,src):
    if isinstance(o,dict):
        pr=o.get("probabilities")
        if isinstance(pr,dict) and "none_of_these" in pr and len(pr)>=2 and all(isinstance(v,(int,float)) for v in pr.values()):
            v=sorted((round(x*100) for x in pr.values()),reverse=True); by.setdefault(src,[]).append(v[0]-v[1])
        for x in o.values(): walk(x,src)
    elif isinstance(o,list):
        for x in o: walk(x,src)
from jevclient import RAW, save_summary
for f in sorted(glob.glob(str(RAW / "*.json"))):
    try: walk(json.load(open(f)), f.rsplit("/", 1)[1])
    except Exception: pass
tot=0;k=0
for s,m in sorted(by.items()):
    kk=sum(x<=10 for x in m); print(s, len(m), kk); tot+=len(m); k+=kk
print("pooled", tot, k, round(k/tot,4) if tot else None)
save_summary("check_tie_margin_pooled", [], {"by_file": {s: {"n": len(m), "margin_le_10": sum(x <= 10 for x in m)} for s, m in by.items()}, "pooled_n": tot, "pooled_margin_le_10": k}, n=tot)
