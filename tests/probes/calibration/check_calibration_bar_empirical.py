"""Claim: DESIGN §6.2 calibration bar (95% bootstrap upper bound of top-label ECE <= 0.05)
has adequate power at a given n. Round 2 simulations disagreed because they assumed
different distributions of Jev's top-label probability (uniform(.5,1) vs Dirichlet mass at 1.00).
Method: take the EMPIRICAL distribution of top-label probabilities from every real Jev
choice answer saved in out/raw (jev-1.13.0), resample it as the
model's reported p, draw outcomes ~ Bernoulli(p - delta), and compute P(pass) of the bar
with 15 bins whose edges are equal-mass quantiles merged so tied values are never split.
Reports P(pass) for delta in {0, 0.02, 0.05} at n in {1000, 2000, 3000}.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import os
import glob, json, numpy as np
ps=[]
def walk(o):
    if isinstance(o,dict):
        pr=o.get('probabilities')
        if isinstance(pr,dict) and pr and all(isinstance(v,(int,float)) for v in pr.values()) and len(pr)>=2:
            ps.append(max(pr.values()))
        for v in o.values(): walk(v)
    elif isinstance(o,list):
        for v in o: walk(v)
for f in glob.glob(str(PROBES) + '/out/raw/*.json'):
    try: walk(json.load(open(f)))
    except Exception: pass
ps=np.array(ps); print(f"empirical top-label p: n={len(ps)} mean={ps.mean():.3f} share==1.00 {np.mean(ps>=0.995):.2f} share>=0.9 {np.mean(ps>=0.9):.2f} p10={np.quantile(ps,.1):.2f}")
rng=np.random.default_rng(7)
def ece(p,y):
    q=np.unique(np.quantile(p,np.linspace(0,1,16)))
    idx=np.clip(np.searchsorted(q,p,side='right')-1,0,len(q)-2)
    e=0.
    for b in np.unique(idx):
        m=idx==b; e+=m.mean()*abs(p[m].mean()-y[m].mean())
    return e
def passes(p,y,B=200):
    n=len(p); bs=[ece(p[i],y[i]) for i in (rng.integers(0,n,n) for _ in range(B))]
    return np.quantile(bs,0.95)<=0.05
for n in (1000,2000,3000):
    for d in (0,0.02,0.05):
        R=150; k=0
        for _ in range(R):
            p=rng.choice(ps,n); y=(rng.random(n)<np.clip(p-d,0,1)).astype(float); k+=passes(p,y)
        print(f"n={n} delta={d:.2f} P(pass)={k/R:.2f}")
