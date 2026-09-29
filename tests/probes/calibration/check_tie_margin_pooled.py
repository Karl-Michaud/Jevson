"""Round 4. Claim (DESIGN §6.2): share of candidate choices (choices offering none_of_these) whose
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
for f in sorted(glob.glob(str(PROBES) + "/out/raw/*.json")):
    try: walk(json.load(open(f)), f.split("/")[1])
    except Exception: pass
tot=0;k=0
for s,m in sorted(by.items()):
    kk=sum(x<=10 for x in m); print(s, len(m), kk); tot+=len(m); k+=kk
print("pooled", tot, k, round(k/tot,4))
