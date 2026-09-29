"""check_r3_grapheme_table.py — DESIGN §5.9 "vendors a generated boundary table (~9 KB)
rather than adding a dependency", tested against GraphemeBreakTest.txt.

Claim (DESIGN §5.9, Rev 5): UAX #29 extended-grapheme boundaries at a pinned Unicode
version, from a vendored generated table of ~9 KB, no dependency, passing the official
GraphemeBreakTest.txt.

Method:
  1. Generator: from GraphemeBreakProperty.txt, emoji-data.txt (Extended_Pictographic)
     and DerivedCoreProperties.txt (Indic_Conjunct_Break, 15.1+) at version V, build one
     merged range table: (range start, combined class) where the class combines GCB,
     ExtPict and InCB. Serialise it (a) as a Python source literal (what would be vendored),
     (b) as a packed binary (uint32 start delta varint + uint8 class), and measure raw and
     zlib/base85 sizes.
  2. Runtime: a minimal pure-Python segmenter (bisect lookup + rules GB3–GB13, GB9c);
     count its lines of code (non-blank, non-comment).
  3. Run every line of GraphemeBreakTest.txt for V; report pass/fail.
  4. Cross-check against `regex` \\X and `uniseg` on random strings (regex/uniseg report
     their own Unicode version).
Usage: python check_r3_grapheme_table.py <ucd_dir> <version>
Output: results/r3/outputs/check_r3_grapheme_table_<version>.txt (+ generated table/segmenter
in results/r3/outputs/grapheme_gen_<version>/)
"""
import sys, os, re, zlib, base64, bisect, random, inspect, textwrap

UCD, VER = sys.argv[1], sys.argv[2]
OUTDIR = "/Users/karlosins/project-asterion/Jevson/scripts/redteam/results/r3/outputs"
GEN = os.path.join(OUTDIR, f"grapheme_gen_{VER}"); os.makedirs(GEN, exist_ok=True)
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)

def parse(path, want=None, field=1):
    res = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#")[0].strip()
        if not line: continue
        parts = [p.strip() for p in line.split(";")]
        if want and parts[1] != want: continue
        cps = parts[0].split("..")
        a = int(cps[0], 16); b = int(cps[-1], 16)
        res.append((a, b, parts[field] if field < len(parts) else parts[1]))
    return res

# ---------------- generator ----------------
N = 0x110000
gcb = ["Other"] * N
for a, b, v in parse(f"{UCD}/GraphemeBreakProperty.txt"):
    for c in range(a, b + 1): gcb[c] = v
ep = bytearray(N)
for a, b, v in parse(f"{UCD}/emoji-data.txt", "Extended_Pictographic"):
    for c in range(a, b + 1): ep[c] = 1
incb = [""] * N
has_incb = False
for line in open(f"{UCD}/DerivedCoreProperties.txt", encoding="utf-8"):
    line = line.split("#")[0].strip()
    if not line: continue
    parts = [p.strip() for p in line.split(";")]
    if parts[1] == "InCB":
        has_incb = True
        cps = parts[0].split(".."); a = int(cps[0], 16); b = int(cps[-1], 16)
        for c in range(a, b + 1): incb[c] = parts[2]
log(f"Unicode {VER}: InCB present = {has_incb}")
keys = {}
cls = [0] * N
for c in range(N):
    k = (gcb[c], ep[c], incb[c])
    cls[c] = keys.setdefault(k, len(keys))
starts, vals = [0], [cls[0]]
for c in range(1, N):
    if cls[c] != cls[c - 1]: starts.append(c); vals.append(cls[c])
CLASSES = [None] * len(keys)
for k, i in keys.items(): CLASSES[i] = k
log(f"combined classes: {len(CLASSES)}; ranges: {len(starts)}")
# default (Other, 0, "") class must be 0 index-independent; fine.

# (a) Python source literal
src = "CLASSES = %r\nSTARTS = %r\nVALS = bytes(%r)\n" % (CLASSES, starts, bytes(vals))
open(f"{GEN}/table_literal.py", "w").write(src)
# (b) packed binary: varint start deltas + class bytes, zlib, base85 for embedding
def varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n: return bytes(out)
packed = b"".join(varint(starts[i] - (starts[i - 1] if i else 0)) for i in range(len(starts))) + bytes(vals)
z = zlib.compress(packed, 9); b85 = base64.b85encode(z)
src_packed = "CLASSES = %r\nN = %d\nDATA = %r\n" % (CLASSES, len(starts), b85.decode())
open(f"{GEN}/table_packed.py", "w").write(src_packed)
log(f"table as Python literal: {len(src.encode())} bytes (zlib -9: {len(zlib.compress(src.encode(), 9))} bytes)")
log(f"table packed binary: {len(packed)} bytes; zlib -9: {len(z)} bytes; base85-embedded .py: {len(src_packed.encode())} bytes")

OLD_STATE = '            if ae: ep_seq = True\n            elif not (a == "Extend" or (a == "ZWJ" and ep_seq)): ep_seq = False'
NEW_STATE = '            if ae: ep_seq = 1                                   # ExtPict seen\n            elif a == "Extend" and ep_seq == 1: pass            # ExtPict Extend*\n            elif a == "ZWJ" and ep_seq == 1: ep_seq = 2         # ExtPict Extend* ZWJ\n            else: ep_seq = 0'
# ---------------- runtime segmenter (what would ship) ----------------
RUNTIME = r'''
import bisect, zlib, base64
def _load(CLASSES, N, DATA):
    raw = zlib.decompress(base64.b85decode(DATA)); starts = []; i = 0; cur = 0
    for _ in range(N):
        v = 0; shift = 0
        while True:
            b = raw[i]; i += 1; v |= (b & 0x7F) << shift; shift += 7
            if not b & 0x80: break
        cur += v; starts.append(cur)
    return starts, raw[i:i + N]

class Segmenter:
    def __init__(self, CLASSES, N, DATA):
        self.C = CLASSES; self.starts, self.vals = _load(CLASSES, N, DATA)
    def prop(self, ch):
        return self.C[self.vals[bisect.bisect_right(self.starts, ord(ch)) - 1]]
    def boundaries(self, s):
        """Set of code-point offsets that are extended grapheme cluster boundaries."""
        n = len(s); out = {0, n} if n else {0}
        if n < 2: return out
        P = [self.prop(c) for c in s]
        ri = 0; ep_seq = False; incb_state = 0  # 0 none, 1 consonant seen, 2 linker seen
        for i in range(1, n):
            (a, ae, ai), (b, be, bi) = P[i - 1], P[i]
            # state tracked over the text before the candidate boundary
            ri = ri + 1 if a == "Regional_Indicator" else 0
            if ae: ep_seq = True
            elif not (a == "Extend" or (a == "ZWJ" and ep_seq)): ep_seq = False
            if ai == "Consonant": incb_state = 1
            elif ai == "Linker" and incb_state: incb_state = 2
            elif ai == "Extend" and incb_state: pass
            else: incb_state = 0
            if a == "CR" and b == "LF": brk = False                                   # GB3
            elif a in ("Control", "CR", "LF"): brk = True                              # GB4
            elif b in ("Control", "CR", "LF"): brk = True                              # GB5
            elif a == "L" and b in ("L", "V", "LV", "LVT"): brk = False                # GB6
            elif a in ("LV", "V") and b in ("V", "T"): brk = False                     # GB7
            elif a in ("LVT", "T") and b == "T": brk = False                           # GB8
            elif b in ("Extend", "ZWJ"): brk = False                                   # GB9
            elif b == "SpacingMark": brk = False                                       # GB9a
            elif a == "Prepend": brk = False                                           # GB9b
            elif incb_state == 2 and bi == "Consonant": brk = False                    # GB9c
            elif a == "ZWJ" and be and ep_seq == GB11_OK: brk = False                  # GB11
            elif a == "Regional_Indicator" and b == "Regional_Indicator" and ri % 2 == 1: brk = False  # GB12/13
            else: brk = True                                                           # GB999
            if brk: out.add(i)
        return out
'''
# The first draft of this segmenter (kept as RUNTIME_V1) tracked GB11 state loosely: it let
# ExtPict ZWJ Extend ZWJ ExtPict join. Both are run to show what the conformance file catches.
RUNTIME_V1 = RUNTIME.replace("GB11_OK", "True")
RUNTIME = RUNTIME.replace(OLD_STATE, NEW_STATE).replace("GB11_OK", "2")
open(f"{GEN}/segmenter.py", "w").write(RUNTIME)
loc = sum(1 for l in RUNTIME.splitlines() if l.strip() and not l.strip().startswith("#"))
log(f"runtime segmenter: {loc} non-blank lines, {len(RUNTIME.encode())} bytes; stdlib only (bisect, zlib, base64)")
gen_loc = sum(1 for l in open(__file__).read().split("# ---------------- runtime")[0].split("# ---------------- generator ----------------")[1].splitlines() if l.strip() and not l.strip().startswith("#"))
log(f"generator (table build + serialise): {gen_loc} non-blank lines")
def build(code):
    ns = {}; exec(code, ns); return ns["Segmenter"](CLASSES, len(starts), b85.decode())
seg_v1 = build(RUNTIME_V1); seg = build(RUNTIME)

# ---------------- conformance ----------------
def conformance(seg):
  passed = failed = 0; fails = []
  for ln, line in enumerate(open(f"{UCD}/GraphemeBreakTest.txt", encoding="utf-8"), 1):
      t = line.split("#")[0].strip()
      if not t: continue
      toks = t.split(); chars = []; exp = set(); pos = 0
      for tok in toks:
          if tok == "÷": exp.add(pos)
          elif tok == "×": pass
          else: chars.append(chr(int(tok, 16))); pos += 1
      got = seg.boundaries("".join(chars))
      if got == exp: passed += 1
      else: failed += 1; fails.append((ln, t))
  return passed, failed, fails
for name, sg in (("v1 (loose GB11 state)", seg_v1), ("final", seg)):
    passed, failed, fails = conformance(sg)
    log(f"[{name}] GraphemeBreakTest-{VER}.txt: {passed} passed, {failed} failed of {passed + failed}")
    for f in fails[:10]: log("  FAIL line", f)
probe = "\U0001F468\u200d\u0301\u200d\U0001F469"
log("  ExtPict ZWJ Extend ZWJ ExtPict: v1", sorted(seg_v1.boundaries(probe)), "final", sorted(seg.boundaries(probe)), "(UAX #29: break before the last ExtPict, i.e. {0,4,5})")

# ---------------- cross-checks ----------------
import regex, unicodedata
log(f"regex {regex.__version__} (its Unicode tables: {getattr(regex, 'UNICODE_VERSION', 'n/a')}); python unicodedata {unicodedata.unidata_version}")
def rx_b(s):
    out = {0}; p = 0
    for m in regex.finditer(r"\X", s): p = m.end(); out.add(p)
    return out
pool = [c for c in range(0x20, 0x30000) if gcb[c] != "Other" or ep[c] or incb[c]]
pool += [0x61, 0x915, 0x94D, 0x930, 0x200D, 0x1F468, 0x1F1FA, 0x1F1F8, 0xD, 0xA, 0x1100, 0x1161, 0x11A8, 0xAC00]
random.seed(29)
agree = 0; dis = []
M = 20000
for _ in range(M):
    s = "".join(chr(random.choice(pool)) for _ in range(random.randint(1, 8)))
    if seg.boundaries(s) == rx_b(s): agree += 1
    elif len(dis) < 5: dis.append(s)
log(f"vs regex \\X on {M} random strings from break-relevant code points: {agree} agree")
for s in dis: log("  disagree:", [hex(ord(c)) for c in s], sorted(seg.boundaries(s)), sorted(rx_b(s)))
try:
    import uniseg, uniseg.graphemecluster as gc
    uv = getattr(uniseg, "unidata_version", None) or getattr(uniseg, "__unicode_version__", None)
    def us_b(s):
        out = {0}; p = 0
        for g in gc.grapheme_clusters(s): p += len(g); out.add(p)
        return out
    random.seed(29); ua = 0; ua_v1 = 0
    for _ in range(M):
        s = "".join(chr(random.choice(pool)) for _ in range(random.randint(1, 8)))
        if seg.boundaries(s) == us_b(s): ua += 1
    if seg_v1.boundaries(s) != us_b(s): ua_v1 += 1
    log(f"vs uniseg {getattr(uniseg, '__version__', '?')} (unicode {uv}) on the same {M} strings: final {ua} agree; v1 disagrees on {ua_v1}")
except Exception as e:
    log("uniseg cross-check skipped:", type(e).__name__, e)

open(f"{OUTDIR}/check_r3_grapheme_table_{VER}.txt", "w").write("\n".join(OUT) + "\n")
