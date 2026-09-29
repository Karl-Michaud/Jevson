"""Round 4. Claims: (a) DESIGN §8.2 — the default candidate declaration (50 candidates x 120 characters)
costs roughly 2-3k tokens (extrapolated in Rev 6 from P14's ~35 tokens per ~80-char option);
(b) DESIGN §6.2 — the 0.10 tie margin's effect on candidate choices (Phase 0 is to report it).
Method: (a) one live request per condition with 50 options whose descriptions are 120-character
realistic spans (and 40-char-context variants), comparing usage.input_tokens with a 2-option baseline
over the same small state; (b) offline: recompute the top-two margin over every saved candidate-choice
answer (r1 p05*, r3 complete_value, r3 mixed_desc) and report the share with margin <= 0.10.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, glob, json, os, random, pathlib
os.environ.setdefault("PROBE_OUT", str(pathlib.Path(__file__).resolve().parents[1] / "out"))
import jevclient as jc
random.seed(4)
WORDS = "invoice remit account payable north harbor street suite logistics global holdings limited partner services quarterly net terms due upon receipt".split()
def span(n):
    s=""
    while len(s)<n: s+=random.choice(WORDS).capitalize()+" "
    return s[:n].strip()
async def main():
    J=jc.Jev(concurrency=2)
    state={"source": "Invoice 4417 from Northwind Holdings to Contoso Ltd. Total due: $1,204.50 by 2026-10-15."}
    async def ask(opts):
        q={"q":{"type":"choice","instructions":"Which of these is the complete billing address as written in the source?","criteria":opts}}
        r=await J.ask(state,q); assert r['status']==200, r.get('body'); return r
    base=await ask({"c0":"Contoso Ltd","none_of_these":"None of the other options is the complete billing address."})
    out={"baseline_tokens":base["usage"]["input_tokens"]}
    for label,n,ctx in (("50x120",120,0),("50x120+ctx80",120,80)):
        opts={f"c{i}": (span(n) if not ctx else f"{span(n)} — context: …{span(ctx)}…") for i in range(50)}
        opts["none_of_these"]="None of the other options is the complete billing address as written in the source; a partial value does not count."
        r=await ask(opts); out[label]=r["usage"]["input_tokens"]-out["baseline_tokens"]
    print(json.dumps(out))
    await J.aclose()
    # (b) offline margins
    margins=[]
    def walk(o):
        if isinstance(o,dict):
            pr=o.get("probabilities")
            if isinstance(pr,dict) and "none_of_these" in pr and len(pr)>=2 and all(isinstance(v,(int,float)) for v in pr.values()):
                v=sorted((round(x*100) for x in pr.values()),reverse=True); margins.append(v[0]-v[1])
            for x in o.values(): walk(x)
        elif isinstance(o,list):
            for x in o: walk(x)
    for f in glob.glob(str(PROBES) + "/out/raw/p05*.json")+glob.glob(str(PROBES) + "/out/raw/p09*.json")+glob.glob(str(PROBES) + "/out/raw/*complete*.json")+glob.glob(str(PROBES) + "/out/raw/*mixed*.json"):
        try: walk(json.load(open(f)))
        except Exception: pass
    n=len(margins); k=sum(m<=10 for m in margins)
    print(json.dumps({"candidate_choices":n,"margin_le_0.10":k,"share":round(k/n,4) if n else None}))
asyncio.run(main())
