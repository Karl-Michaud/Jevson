"""Round 5. Claim (DESIGN §2.1): the sum-tolerance cap min(ceil(K/2), 5) hundredths holds for large option
counts. Method: walk every saved live answer in results/r*/raw, and for every probabilities map report K and
|sum - 1.00| in hundredths; summarise the maximum deviation by K bucket."""
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
for f in glob.glob("results/r*/raw/*.json"):
    try: walk(json.load(open(f)))
    except Exception: pass
from collections import defaultdict
b=defaultdict(list)
for k,d in rows: b["2-11" if k<=11 else "12-60" if k<=60 else "61-255"].append(d)
for k,v in sorted(b.items()): print(k, "n=",len(v), "max dev (hundredths)=",max(v), "dev>5:",sum(x>5 for x in v))
