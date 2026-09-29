"""Claims: DESIGN §2 — "Context ~64k tokens for state plus questions"; "$0.042 per million input tokens;
~$0.068 per 1000 decisions"; §8.2 — "If a single question plus its state exceeds the window, refuse";
§2 noul returns "boolean probability + confidence"; §2.1 keyed batching measured at 320 items/request vs
§8.2 pairwise cap 435 questions in ONE call.

Method: grep the vendor docs saved locally (no API call) and do the arithmetic.
"""
import os
import pathlib, re
D = pathlib.Path(os.environ.get("JEV_DOCS_DIR", pathlib.Path(__file__).resolve().parent / "jevdocs"))  # vendor docs snapshot: see fetch_vendor_docs.sh
models = (D / "models.md").read_text()
row = next(l for l in models.splitlines() if l.startswith("| Context length"))
print("vendor models.md:", row)
print("-> two limits: 64k for state+ALL questions; 32k for state + LONGEST question. DESIGN §2/§8.2 mention only ~64k.")
price = 0.042 / 1e6
print(f"$0.068 per 1000 decisions at $0.042/Mtok implies {0.068/1000/price:.0f} input tokens per decision")
hits = [(p.name, l.strip()[:160]) for p in D.glob("*.md") for l in p.read_text().splitlines() if re.search(r"0\.068|per 1,?000 decisions", l)]
print("vendor docs mentioning 0.068 / per 1000 decisions:", hits[:5] or "none")
for n in (20, 30):
    q = n*(n-1)//2
    print(f"pairwise n={n}: {q} questions in one call; §2.1 measured keyed batching up to 320 items/request -> "
          f"{'within' if q <= 320 else 'OUTSIDE'} the measured regime")
api = (D / "api.md").read_text()
blk = api[api.index("### Noul answer"): api.index("### Choice answer")]
print("noul answer fields:", re.findall(r'ResponseField name="(\w+)"', blk))
