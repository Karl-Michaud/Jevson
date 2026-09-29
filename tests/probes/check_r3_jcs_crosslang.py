"""check_r3_jcs_crosslang.py — DESIGN §8.4 RFC 8785 cache keys reproducible across languages.

Claim (DESIGN §8.4, Rev 5): CachingBackend's key is "RFC 8785 canonical JSON of model id,
state, and questions, hashed with SHA-256; probabilities stored as integer hundredths, so
the key is reproducible in any language".

Method: build realistic cache-key payloads (model id, keyed state with unicode source text:
NFD/NFC, astral emoji, CJK, U+2028, control chars, keys whose UTF-16 order differs from
code-point order; questions; integer-hundredth probabilities) plus edge cases (floats,
-0, 1e21, 2**53+1). Canonicalise + SHA-256 with Python `rfc8785`, `jcs`, `canonicaljson`,
and naive `json.dumps(sort_keys=True, separators=(',',':'), ensure_ascii=False)`; then with
Node `canonicalize` and `json-canonicalize` (check_r3_jcs_crosslang.mjs). Compare hashes.
Output: out/check_r3_jcs_crosslang.txt
"""
import json, hashlib, subprocess, sys, os
import rfc8785, jcs, canonicaljson

HERE = os.path.dirname(os.path.abspath(__file__))
OUTD = os.path.join(HERE, "out")
NODE_DIR = sys.argv[1]  # dir with node_modules/canonicalize and json-canonicalize
OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)

src = ("Invoice from Ｍüller GmbH (Mu\u0308ller) — total €1\u202f204,50\r\n"
       "Signed: 👩🏽‍💻 Dana Whitfield\u2028Note: \u0915\u094d\u0937 \u0000\u001f\u007f \"quoted\" \\ /")
req = {
    "model": "jev-1.13.0",
    "state": {"source": src, "candidates": {"c0": "Müller GmbH", "c1": "Mu\u0308ller", "c10": "👩🏽‍💻", "c2": "€1 204,50"}},
    "questions": {
        "q:/vendor#choice": {"type": "choice", "question": "Which candidate is the vendor’s complete name?",
                             "options": {"c0": "Müller GmbH", "c1": "Mu\u0308ller", "none_of_these": "none"}},
        "\ufb01eld": {"type": "noul", "question": "ﬁ ligature key (U+FB01)"},
        "\U0001F600key": {"type": "noul", "question": "astral key sorts before U+FB01 in UTF-16, after it in code points"},
        "é": {"type": "noul", "question": "precomposed"}, "e\u0301": {"type": "noul", "question": "decomposed"},
    },
}
resp = {"answers": {"q:/vendor#choice": {"probabilities_hundredths": {"c0": 93, "c1": 5, "none_of_these": 2}},
                    "\ufb01eld": {"noul_hundredths": 55}}, "input_tokens": 1234}
floaty = {"p": [0.1, 0.07, 1.0, 0.5, 1e21, 1e-7, -0.0, 5e-324, 0.30000000000000004]}
bigint = {"n": 2**53 + 1}
cases = {"request": req, "response_hundredths": resp, "floats_edge": floaty, "bigint": bigint}
json.dump(cases, open(os.path.join(OUTD, "check_r3_jcs_vectors.json"), "w", encoding="utf-8"), ensure_ascii=True)

def naive(o): return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
impls = {"py:rfc8785": rfc8785.dumps, "py:jcs": jcs.canonicalize, "py:canonicaljson": canonicaljson.encode_canonical_json, "py:naive_sorted_dumps": naive}
py = {}
for name, f in impls.items():
    for c, o in cases.items():
        try: b = f(o); py[(name, c)] = (hashlib.sha256(b).hexdigest(), b)
        except Exception as e: py[(name, c)] = ("ERROR " + type(e).__name__ + ": " + str(e)[:80], b"")
node = subprocess.run(["node", os.path.join(HERE, "check_r3_jcs_crosslang.mjs"), os.path.join(OUTD, "check_r3_jcs_vectors.json")],
                      cwd=NODE_DIR, capture_output=True, text=True)
if node.returncode: log("node stderr:", node.stderr[:500])
js = json.loads(node.stdout)
log(f"node {subprocess.run(['node','--version'],capture_output=True,text=True).stdout.strip()}; rfc8785 {getattr(rfc8785,'__version__','?')}")
ref = {c: py[("py:rfc8785", c)][0] for c in cases}
for c in cases:
    log(f"\n== case {c}  (reference py:rfc8785 = {ref[c][:16]}…)")
    for (name, cc), (h, b) in py.items():
        if cc == c: log(f"  {name:24s} {h[:16]}{'…' if not h.startswith('ERROR') else ''}  {'RAISES' if h.startswith('ERROR') else ('MATCH' if h == ref[c] else 'DIFF')}")
    for name, r in js.items():
        h = r[c]
        log(f"  {name:24s} {h[:16]}{'…' if not h.startswith('ERROR') else ''}  {'RAISES' if h.startswith('ERROR') else ('MATCH' if h == ref[c] else 'DIFF')}")
b = py[("py:rfc8785", "request")][1].decode()
qi = b.index('"questions"'); log("\nrfc8785 question-key order:", [k for k in json.loads(b)["questions"]], "(UTF-16 order: astral before U+FB01)")
log("naive sorted dumps order:", list(json.loads(py[("py:naive_sorted_dumps", "request")][1])["questions"]))
log("bigint 2**53+1: py:jcs emits", jcs.canonicalize(bigint).decode(), "(silently rounded, equals JS after JSON.parse); rfc8785 raises; canonicaljson emits", canonicaljson.encode_canonical_json(bigint).decode())
log("rfc8785 floats_edge:", py[("py:rfc8785", "floats_edge")][1].decode())
open(os.path.join(OUTD, "check_r3_jcs_crosslang.txt"), "w").write("\n".join(OUT) + "\n")
