"""Claim checked: whether a stdlib-only UAX #29 implementation is available (DESIGN §5.5 grapheme rule vs PLAN
Phase 8 "dependencies: jsonschema, pydantic, httpx").

Method: two modes.
  --dump  (run in the venv with `regex`): regenerate the check_grapheme_shorthand corpus (same seed) and write every
          string with its regex \\X boundary set to out/grapheme_corpus.json.
  --compare (run in docker python:3.15-rc, stdlib only): recompute boundaries with unicodedata.iter_graphemes and
          count strings whose boundary sets differ from regex's, per class.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import os
import json
import sys
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "out" / "outputs" / "grapheme_corpus.json"

if sys.argv[1] == "--dump":
    import unicode.check_grapheme_shorthand as g
    data = []
    for name, gen in g.CLASSES.items():
        for _ in range(g.N_PER_CLASS):
            s = gen()
            data.append([name, s, sorted(g.uax29_boundaries(s))])
    OUT.write_text(json.dumps(data, ensure_ascii=True))
    print("dumped", len(data))
else:
    import collections, unicodedata
    data = json.loads(OUT.read_text())
    bad = collections.Counter(); tot = collections.Counter(); ex = {}
    for name, s, b in data:
        mine = {0, len(s)} | {seg.end for seg in unicodedata.iter_graphemes(s)}
        tot[name] += 1
        if mine != set(b):
            bad[name] += 1; ex.setdefault(name, (s, sorted(mine), b))
    print(sys.version.split()[0], "unicodedata", unicodedata.unidata_version)
    for n in tot:
        print(f"{n:45s} {bad[n]:5d}/{tot[n]}")
    for n, e in ex.items():
        print("example", n, ascii(e))
