import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import numpy as np
rng=np.random.default_rng(7)
def ece_em(c,y,B=15):
    o=np.argsort(c); cs=c[o]; ys=y[o]
    parts=np.array_split(np.arange(len(c)),B)
    return sum(len(p)/len(c)*abs(cs[p].mean()-ys[p].mean()) for p in parts)
def bar(n,dist,delta,R=300,BS=200):
    passes=0
    for _ in range(R):
        c = rng.uniform(.5,1,n) if dist=='U' else rng.beta(18,2,n)
        y = rng.random(n) < np.clip(c-delta,0,1)
        bs=[]
        for _ in range(BS):
            i=rng.integers(0,n,n); bs.append(ece_em(c[i],y[i]))
        ub=np.percentile(bs,97.5)
        passes+= ub<=0.05
    return passes/R
for dist in ['U','B']:
    for d in [0,0.03,0.05]:
        print(dist,d,bar(1000,dist,d))
