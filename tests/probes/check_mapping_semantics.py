"""Claim: DESIGN §9 / PLAN Phase 2 mapping adopted from jev_jsonschema:
bool -> noul at 0.5; number bounded 0–1 -> raw probability; integer range 2–10 levels -> score.
Also DESIGN §2 table: noul returns "boolean probability + confidence".

Method (no API): (1) read the vendor API doc to see what fields each answer type actually carries;
(2) show the vendor-documented `score` value is probability-weighted and can be non-integer, so
using it for an integer field fails jsonschema, and rounding it differs from argmax on bimodal
distributions; (3) enumerate realistic 0–1 bounded fields and show a noul probability is not the
field's value (worked example); (4) enumerate integer 2–10 ranges that are counts, not ordinals;
(5) the 0.5 bool threshold tie.
"""
import os
import pathlib, re
import jsonschema
import numpy as np

DOCS = pathlib.Path(os.environ.get("JEV_DOCS_DIR", pathlib.Path(__file__).resolve().parent / "jevdocs"))  # vendor docs snapshot: see fetch_vendor_docs.sh
api = (DOCS / "api.md").read_text()
print("(1) vendor api.md, answer types:")
for line in api.splitlines():
    if "Choice and Score answers also carry" in line or 'name="score" type="number"' in line:
        print("   ", line.strip())
noul_block = api[api.index("### Noul answer"): api.index("### Choice answer")]
print("    noul answer fields:", re.findall(r'ResponseField name="(\w+)"', noul_block),
      "-> no 'confidence' on noul; DESIGN §2 says noul returns 'boolean probability + confidence'")
score_block = api[api.index("### Score answer"): api.index("## Errors")]
print("    score answer fields:", re.findall(r'ResponseField name="(\w+)"', score_block))

print("\n(2) integer field mapped to score:")
schema = {"type": "integer", "minimum": 1, "maximum": 5}
levels = np.array([1, 2, 3, 4, 5])
for probs in ([0.0, 0.05, 0.9, 0.05, 0.0], [0.45, 0.0, 0.0, 0.0, 0.55], [0.3, 0.3, 0.0, 0.0, 0.4]):
    p = np.array(probs); weighted = float(p @ levels); argmax = int(levels[p.argmax()])
    try:
        jsonschema.validate(weighted, schema); ok = True
    except jsonschema.ValidationError:
        ok = False
    print(f"    probs={probs} weighted_score={weighted:.2f} validates_as_integer={ok} "
          f"round={round(weighted)} argmax={argmax} (round has prob {p[levels==round(weighted)].sum():.2f})")

print("\n(3) 0–1 bounded numbers are usually VALUES, not probabilities:")
examples = [
    ("tax_rate", "VAT charged at 20%", 0.20),
    ("discount", "15% off list price", 0.15),
    ("ownership_share", "holds 51% of the shares", 0.51),
    ("confidence (self-reported)", "n/a", None),
]
for name, src, true in examples:
    print(f"    {name:28} source={src!r:28} correct value={true}; "
          f"a noul p('{name} predicate') of e.g. 0.93 would be written as {name}=0.93 -> wrong-but-valid")
print("    only a field whose *meaning* is 'probability that <predicate>' can take a noul p; the schema "
      "(minimum:0,maximum:1) cannot tell these apart")

print("\n(4) integer ranges 2–10 that are counts (source-extractable), not ordinal ratings:")
for name, lo, hi in [("bedrooms", 1, 10), ("num_signatories", 2, 10), ("quantity", 1, 10), ("satisfaction", 1, 5)]:
    n = hi - lo + 1
    print(f"    {name:16} range {lo}-{hi} -> {n} levels -> maps to score: {2 <= n <= 10}")

print("\n(5) bool at 0.5: p=0.5 exactly ->", "True" if 0.5 >= 0.5 else "False", "with >=;", 0.5 > 0.5, "with >; "
      "the threshold direction is unspecified in the design")
