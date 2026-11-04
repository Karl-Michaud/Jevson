"""Phase 0r: re-measures [P23] (and the sum half of [L17]) on the saved OpenAI Decisions API (`gpt-6-luna`)
answers in jevclient.RAW (tests/probes/out/0r/raw); the K buckets now include score answers, and the full
deviation histogram per bucket is written to tests/probes/results/0r/check_sum_tolerance.json.

Round 5. Claim (DESIGN §2.1): the sum-tolerance cap min(ceil(K/2), 5) hundredths holds for large option
counts. Method: walk every saved live answer in out/raw, and for every probabilities map report K and
|sum - 1.00| in hundredths; summarise the maximum deviation by K bucket."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import os
import glob, json
rows=[]
def walk(o):
    if isinstance(o,dict):
        pr=o.get("probabilities")
        if isinstance(pr,dict) and len(pr)>=2 and all(isinstance(v,(int,float)) for v in pr.values()):
            rows.append((len(pr), abs(round(sum(pr.values())*100)-100)))
        for x in o.values(): walk(x)
    elif isinstance(o,list):
        for x in o: walk(x)
from jevclient import RAW, save_summary
for f in glob.glob(str(RAW / "*.json")):
    try: walk(json.load(open(f)))
    except Exception: pass
from collections import defaultdict
b=defaultdict(list)
for k,d in rows: b["2-11" if k<=11 else "12-60" if k<=60 else "61-255"].append(d)
from collections import Counter
for k,v in sorted(b.items()): print(k, "n=",len(v), "max dev (hundredths)=",max(v), "dev>5:",sum(x>5 for x in v), "hist:", dict(sorted(Counter(v).items())))
save_summary("check_sum_tolerance", [], {k: {"n": len(v), "max_dev_hundredths": max(v), "dev_gt_5": sum(x > 5 for x in v),
             "hist_dev_hundredths": dict(sorted(Counter(v).items()))} for k, v in sorted(b.items())},
             n="every saved probabilities map, not de-duplicated")
