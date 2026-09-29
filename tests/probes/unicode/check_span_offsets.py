"""Claim: DESIGN §5.5 span semantics and §5.6 default Normalizer (NFC + casefold + whitespace collapse).

§5.5: offsets are Python str (code point) offsets, half-open, span valid iff source[start:end] == text.
§5.6: pre-merge candidates whose text is identical after NFC + casefold + whitespace collapse.

Method: build sources with multi-byte, astral, combining, confusable, ZWJ and CRLF content;
check (a) code-point vs byte offsets, (b) exact-match verification behaviour, (c) whether
normalization changes lengths (so normalized offsets cannot be provenance offsets),
(d) which distinct surface strings the default normalizer merges.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import re
import unicodedata as ud

def norm(s: str) -> str:  # the §5.6 default, literally
    return re.sub(r"\s+", " ", ud.normalize("NFC", s).casefold()).strip()

def verify(src, start, end, text):
    return src[start:end] == text

print("== (a) code point vs byte offsets ==")
src = "Café 👍🏽 東京 José́ Zoë"
for t in ["Café", "👍🏽", "東京", "José́", "Zoë"]:
    i = src.index(t); j = i + len(t)
    b = src.encode("utf-8"); bi = len(src[:i].encode()); bj = len(src[:j].encode())
    print(f"{t!r:14} cp=[{i},{j}) len={len(t)}  bytes=[{bi},{bj})  verify_cp={verify(src,i,j,t)}  "
          f"byteslice_as_str_offsets_ok={src[bi:bj]==t}")
print("len('👍🏽') code points =", len("👍🏽"), [hex(ord(c)) for c in "👍🏽"])

print("\n== (b) exact verification: combining vs precomposed ==")
pre = "José"          # precomposed é
dec = "José"         # e + combining acute
src2 = f"Signed by {dec} yesterday"
i = src2.index(dec)
print("source uses decomposed; LLM returns precomposed candidate text")
print(" verify(decomposed offsets, precomposed text) =", verify(src2, i, i+len(dec), pre))
print(" verify(precomposed-length offsets, precomposed text) =", verify(src2, i, i+len(pre), pre))
print(" src2.find(precomposed) =", src2.find(pre), "(no substring => span rejected)")
print(" NFC(src2).find(pre) =", ud.normalize("NFC", src2).find(pre),
      " but NFC(src2) len", len(ud.normalize("NFC", src2)), "vs raw", len(src2))
# grapheme split: a span ending between e and U+0301
cut = src2[i:i+4]
print(" span [i,i+4) =", repr(cut), "verifies against itself:", verify(src2, i, i+4, cut),
      "-> a span can split a grapheme cluster and still verify")

print("\n== confusables (Cyrillic а U+0430 vs Latin a) ==")
lat, cyr = "Acme", "Acmе"  # Cyrillic ie
src3 = f"Paid to {cyr} Ltd"
print(" Latin 'Acme' found in source with Cyrillic е:", src3.find(lat))
print(" norm(lat)==norm(cyr):", norm(lat) == norm(cyr), "(not merged: good for safety, bad for recall)")

print("\n== ZWJ / zero-width ==")
fam = "👨‍👩‍👧"
print(" family emoji len:", len(fam), " slice [0:1] =", repr(fam[0:1]), "verifies:", verify(fam, 0, 1, fam[0:1]))
zw = "Dana​Whitfield"
print(" 'Dana\\u200bWhitfield' norm ->", repr(norm(zw)), "== norm('DanaWhitfield')?", norm(zw) == norm("DanaWhitfield"))
nb = "Dana Whitfield"
print(" NBSP: norm('Dana\\xa0Whitfield') == norm('Dana Whitfield')?", norm(nb) == norm("Dana Whitfield"))

print("\n== CRLF ==")
src4 = "Line one\r\nDana Whitfield\r\nAcme"
cand = "Line one\nDana Whitfield"   # an LLM/extractor that normalised newlines
print(" verify CRLF source vs LF candidate:", src4.find(cand))
t = "Dana Whitfield\r\nAcme"; i = src4.index(t)
print(" CRLF span len", len(t), "norm(CRLF span) == norm('Dana Whitfield Acme'):", norm(t) == norm("Dana Whitfield Acme"))

print("\n== (c) normalization changes length (offsets must be on raw source) ==")
cases = {"ß": "ß", "İ": "İ", "ﬁ": "ﬁ (ligature)", "ﬃ": "ﬃ", "ŉ": "ŉ", "é": "e+U+0301",
         "Å": "Å (angstrom sign)", "ΐ": "ΐ", "Straße": "Straße"}
for s, label in cases.items():
    n = ud.normalize("NFC", s); c = n.casefold()
    print(f" {label:18} raw_len={len(s)} NFC_len={len(n)} casefold(NFC)={c!r} len={len(c)}")
src5 = "Firma: Müller Straße GmbH, Kontakt: Dana"
t = "Dana"; i = src5.index(t)
ns = norm(src5); ni = ns.index(norm(t))
print(f" offset of 'Dana' raw={i} normalized={ni} -> differs by {i-ni}; normalized offsets would fail verify:",
      verify(src5, ni, ni+4, t))

print("\n== (d) what the default normalizer merges ==")
pairs = [("US", "us", "country vs pronoun"), ("Apple", "apple", "company vs fruit"),
         ("MAY", "May", "acronym/month"), ("Straße", "STRASSE", "german ss"),
         ("Acme Corp", "ACME CORP", "PLAN exit-criterion example"),
         ("CAT", "cat", "Caterpillar ticker vs animal"), ("IT", "it", "dept vs pronoun"),
         ("Σίσυφος", "ΣΊΣΥΦΟΣ", "greek final sigma"), ("Dana Whitfield", "Dana  Whitfield", "double space"),
         ("José", "José", "precomposed vs combining"), ("Ⅻ", "XII", "roman numeral compat"),
         ("１２３", "123", "fullwidth digits"), ("Acme", "Acmе", "Cyrillic confusable")]
for a, b, why in pairs:
    print(f" {a!r:18} {b!r:18} merge={norm(a)==norm(b)!s:5}  NFKC-would-merge="
          f"{ud.normalize('NFKC',a).casefold()==ud.normalize('NFKC',b).casefold()!s:5} ({why})")
print(" note: 'ﬁ'.casefold() =", repr("ﬁ".casefold()), "; NFC('ﬁ') =", repr(ud.normalize('NFC','ﬁ')))
print(" note: casefold is not idempotent w.r.t. NFC? NFC(casefold(NFC(x)))==casefold(NFC(x)) for 'ΐ':",
      ud.normalize('NFC', ud.normalize('NFC','ΐ').casefold()) == ud.normalize('NFC','ΐ').casefold())

print("\n== (e) NFC->casefold vs Unicode canonical caseless match NFD(casefold(NFD(x))) ==")
import sys
def ccm(s): return ud.normalize("NFD", ud.normalize("NFD", s).casefold())
miss = []
for cp in range(0x110000):
    c = chr(cp)
    if ud.category(c) in ("Cs", "Cn"): continue
    for other in {c.upper(), c.lower(), c.title(), ud.normalize("NFD", c), ud.normalize("NFD", c.upper())}:
        if other != c and ccm(c) == ccm(other) and norm(c) != norm(other):
            miss.append((c, other))
print(" pairs canonically-caseless-equal but NOT merged by NFC+casefold:", len(miss))
for a, b in miss[:8]:
    print("  ", repr(a), [hex(ord(x)) for x in a], "vs", repr(b), [hex(ord(x)) for x in b],
          "norm:", repr(norm(a)), repr(norm(b)))
