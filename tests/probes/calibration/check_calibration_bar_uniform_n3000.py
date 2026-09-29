import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import numpy as np
rng=np.random.default_rng(11)
def ece_em(c,y,B=15):
    o=np.argsort(c,kind='stable'); cs=c[o]; ys=y[o]
    parts=np.array_split(np.arange(len(c)),B)
    return sum(len(p)/len(c)*abs(cs[p].mean()-ys[p].mean()) for p in parts)
def run(n,dist,delta,q,R=200,BS=200):
    passes=0; pt=[]
    for _ in range(R):
        c = rng.uniform(.5,1,n) if dist=='U' else rng.beta(18,2,n)
        y = rng.random(n) < np.clip(c-delta,0,1)
        pt.append(ece_em(c,y))
        bs=[ece_em(c[i],y[i]) for i in (rng.integers(0,n,n) for _ in range(BS))]
        passes+= np.percentile(bs,q)<=0.05
    return passes/R, float(np.mean(pt))
for n in [1000,3000]:
  for dist in ['U','B']:
    print(n,dist,'calibrated one-sided95 pass/meanECE',run(n,dist,0,95))
