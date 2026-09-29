"""check_uniseg_conformance.py — alternative to a vendored table (DESIGN §5.9): does the
`uniseg` package pass GraphemeBreakTest.txt at its Unicode version?
Method: run every line of GraphemeBreakTest-<V>.txt through uniseg.graphemecluster.
Usage: python check_uniseg_conformance.py <GraphemeBreakTest.txt> ; output appended by caller."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import sys, uniseg, uniseg.graphemecluster as gc
p = f = 0
for line in open(sys.argv[1], encoding="utf-8"):
    t = line.split("#")[0].strip()
    if not t: continue
    chars, exp, pos = [], {0}, 0
    for tok in t.split():
        if tok == "÷": exp.add(pos)
        elif tok != "×": chars.append(chr(int(tok, 16))); pos += 1
    got, q = {0}, 0
    for g in gc.grapheme_clusters("".join(chars)): q += len(g); got.add(q)
    if got == exp: p += 1
    else: f += 1
print(f"uniseg {uniseg.__version__} unicode {uniseg.unidata_version}: {sys.argv[1].split('/')[-2]} {p} passed, {f} failed")
