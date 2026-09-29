"""Claim (DESIGN §5.5, PLAN Phase 1 exit criteria): a span is valid only if "neither boundary falls inside a
grapheme cluster (before a combining mark, variation selector, skin-tone modifier, or zero-width joiner)".

Method: implement the simple rule literally, in two readings of "combining mark":
  SIMPLE_Mn  : forbidden-before = gc in {Mn, Me} | VS (FE00-FE0F, E0100-E01EF) | skin tone (1F3FB-1F3FF) | ZWJ
  SIMPLE_M   : same but gc in {Mn, Mc, Me}
and compare, position by position, with full UAX #29 extended grapheme cluster boundaries from the `regex`
module (\\X), cross-checked against the `grapheme` and `uniseg` packages where installed.
Over a generated corpus per class (combining sequences, emoji ZWJ, flags, keycaps, tag flags, Hangul jamo L V T,
Hangul LV+T, Devanagari/Tamil/Bengali with virama and spacing marks, prepend, CR LF, Thai, Lao, controls
followed by marks, ZWNJ, halfwidth katakana voiced marks), every interior position 1..len-1 is classified:
  false accept  = simple rule allows a boundary, UAX #29 says it is inside a cluster
  false reject  = simple rule forbids a boundary, UAX #29 says it is a boundary
Also reports: Unicode versions of Python's unicodedata vs the libraries; stdlib `unicodedata` grapheme API
presence; the size of a vendored GCB table (to price a stdlib-only implementation).
"""
import collections
import json
import random
import sys
import unicodedata
import zlib

import regex

try:
    import grapheme as grapheme_pkg
except Exception:  # pragma: no cover
    grapheme_pkg = None
try:
    from uniseg import graphemecluster as uniseg_gc
except Exception:  # pragma: no cover
    uniseg_gc = None

rng = random.Random(20260929)

VS = set(range(0xFE00, 0xFE10)) | set(range(0xE0100, 0xE01F0))
SKIN = set(range(0x1F3FB, 0x1F400))
ZWJ = 0x200D


def forbidden_before(ch, mc):
    cp = ord(ch)
    cat = unicodedata.category(ch)
    marks = {"Mn", "Me", "Mc"} if mc else {"Mn", "Me"}
    return cat in marks or cp in VS or cp in SKIN or cp == ZWJ


def simple_ok(s, i, mc):
    """True if the simple rule allows a boundary at position i (0 < i < len)."""
    return not forbidden_before(s[i], mc)


def uax29_boundaries(s):
    out = {0, len(s)}
    pos = 0
    for m in regex.finditer(r"\X", s):
        pos = m.end()
        out.add(pos)
    return out


def lib_boundaries_grapheme(s):
    if grapheme_pkg is None:
        return None
    out = {0}
    pos = 0
    for g in grapheme_pkg.graphemes(s):
        pos += len(g)
        out.add(pos)
    return out


def lib_boundaries_uniseg(s):
    if uniseg_gc is None:
        return None
    out = {0}
    pos = 0
    for g in uniseg_gc.grapheme_clusters(s):
        pos += len(g)
        out.add(pos)
    return out


# ---------------------------------------------------------------- corpus generators
LATIN = "aeiouAEIOUnsc"
COMB = [0x0301, 0x0300, 0x0308, 0x0327, 0x0323, 0x030A, 0x20DD]  # incl. Me enclosing circle
EMOJI_BASE = [0x1F468, 0x1F469, 0x1F467, 0x1F466, 0x1F44D, 0x1F9D1]
EXT_PICT_OTHER = [0x2764, 0x1F525, 0x1F4BB, 0x1F9B0, 0x2640, 0x2642, 0x1F308, 0x1F3F3]


def g_combining():
    s = ""
    for _ in range(rng.randint(2, 5)):
        s += rng.choice(LATIN) + "".join(chr(rng.choice(COMB)) for _ in range(rng.randint(0, 3)))
    return s


def g_zwj():
    parts = []
    for _ in range(rng.randint(2, 4)):
        b = chr(rng.choice(EMOJI_BASE + EXT_PICT_OTHER))
        if rng.random() < 0.4:
            b += chr(rng.choice(sorted(SKIN)))
        if rng.random() < 0.3:
            b += "️"
        parts.append(b)
    return "x" + "‍".join(parts) + "y"


def g_flags():
    ri = lambda: chr(0x1F1E6 + rng.randint(0, 25))
    return "x" + "".join(ri() + ri() for _ in range(rng.randint(1, 3))) + ("" if rng.random() < .5 else ri()) + "y"


def g_tagflag():
    # England flag: 1F3F4 E0067 E0062 E0065 E006E E0067 E007F  (tags are gc=Cf, GCB=Extend)
    return "x" + "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F" + "y"


def g_keycap():
    d = rng.choice("0123456789#*")
    return "x" + d + ("️" if rng.random() < .7 else "") + "⃣" + "y"


def g_hangul_jamo():
    L = chr(0x1100 + rng.randint(0, 18))
    V = chr(0x1161 + rng.randint(0, 20))
    T = chr(0x11A8 + rng.randint(0, 26))
    return "x" + L + V + (T if rng.random() < .7 else "") + L + V + "y"


def g_hangul_lv_t():
    # precomposed LV syllable (no final) + conjoining T jamo
    lv = chr(0xAC00 + 28 * rng.randint(0, 398))
    T = chr(0x11A8 + rng.randint(0, 26))
    return "x" + lv + T + "y"


DEVA_C = [chr(c) for c in range(0x0915, 0x0939)]
DEVA_VIRAMA = "्"
DEVA_MC = ["ा", "ि", "ी", "ॉ", "ॊ", "ो", "ौ"]  # spacing vowel signs (Mc)
DEVA_MN = ["ु", "ू", "े", "ै", "ं"]


def g_deva():
    s = "x"
    for _ in range(rng.randint(1, 3)):
        s += rng.choice(DEVA_C)
        if rng.random() < 0.5:
            s += DEVA_VIRAMA + rng.choice(DEVA_C)  # conjunct: C virama C (UAX29 15.1 GB9c: one cluster)
        r = rng.random()
        s += rng.choice(DEVA_MC) if r < .4 else (rng.choice(DEVA_MN) if r < .7 else "")
    return s + "y"


TAMIL_C = [chr(c) for c in (0x0B95, 0x0B99, 0x0B9A, 0x0B9E, 0x0B9F, 0x0BA3, 0x0BA4, 0x0BA8, 0x0BAA, 0x0BAE)]


def g_tamil():
    s = "x"
    for _ in range(rng.randint(1, 3)):
        s += rng.choice(TAMIL_C)
        r = rng.random()
        if r < .3:
            s += "்" + rng.choice(TAMIL_C)  # pulli (virama) — Tamil is NOT InCB=Linker
        elif r < .7:
            s += rng.choice(["ா", "ி", "ெ", "ே", "ொ", "ீ", "ு"])
    return s + "y"


def g_bengali():
    # 09BE Bengali vowel sign AA is Mc but GCB=Extend (Other_Grapheme_Extend)
    return "x" + rng.choice([chr(c) for c in range(0x0995, 0x09A8)]) + rng.choice(["া", "ি", "ী", "্ক"]) + "y"


def g_prepend():
    # Prepend: U+0600..0605 Arabic number signs, U+06DD, U+070F, U+0D4E Malayalam dot reph, U+110BD
    return "x " + rng.choice(["؀", "؁", "۝", "ൎ", "\U000110BD"]) + rng.choice(["١٢", "ക", "क"]) + "y"


def g_crlf():
    return "ab" + rng.choice(["\r\n", "\r\n\r\n", "\n\r", "\r"]) + "cd"


THAI = ["ก", "ข", "ค", "ง", "น", "ม"]


def g_thai():
    s = "x"
    for _ in range(rng.randint(1, 3)):
        s += rng.choice(THAI)
        r = rng.random()
        if r < .3:
            s += "ำ"          # SARA AM: gc=Lo, GCB=SpacingMark
        elif r < .6:
            s += rng.choice(["ิ", "ี", "่", "้"])  # above vowels / tone marks: Mn
        elif r < .8:
            s = s[:-1] + "เ" + s[-1]  # preposed vowel SARA E: Lo, GCB=Other (not Prepend)
    return s + "y"


def g_lao():
    return "xກຳy"  # LAO VOWEL SIGN AM: Lo, SpacingMark


def g_control_mark():
    # a combining mark after a control or newline: UAX29 GB4 breaks after Control/CR/LF
    return "ab" + rng.choice(["\n", "\t", "\r", "\u0000"]) + chr(rng.choice(COMB)) + "c"


def g_zwnj():
    # ZWNJ U+200C is gc=Cf but GCB=Extend (used in Persian/Indic)
    return "xمی‌خواهمy"


def g_halfwidth():
    # FF9E/FF9F halfwidth katakana (semi-)voiced marks: gc=Lm, GCB=Extend
    return "xｶﾞﾊﾟy"


def g_emoji_vs_text():
    # heart + VS16, digits + VS15
    return "x❤️1︎ y"


def g_leading_mark():
    # span candidate text starting at a mark that follows a space: " ́" — boundary before mark?
    return "a ́b"


def g_spacing_mark_misc():
    # Mc that are not grapheme-extending? e.g. U+1D165 MUSICAL SYMBOL COMBINING STEM (Mc, GCB=Extend)
    # U+0903 DEVANAGARI SIGN VISARGA (Mc, SpacingMark)
    return "x\U0001D158\U0001D165कःy"


CLASSES = {
    "combining (Latin + Mn/Me)": g_combining,
    "emoji ZWJ sequences (+skin, +VS16)": g_zwj,
    "regional-indicator flags": g_flags,
    "tag-sequence flags (England)": g_tagflag,
    "keycaps (digit VS16 20E3)": g_keycap,
    "Hangul jamo L V T": g_hangul_jamo,
    "Hangul LV syllable + T jamo": g_hangul_lv_t,
    "Devanagari (virama conjuncts, Mc/Mn)": g_deva,
    "Tamil (pulli, Mc)": g_tamil,
    "Bengali (09BE Mc=Extend, virama)": g_bengali,
    "Prepend (Arabic number sign, dot reph)": g_prepend,
    "CR LF": g_crlf,
    "Thai (SARA AM, marks)": g_thai,
    "Lao AM": g_lao,
    "control/newline + combining mark": g_control_mark,
    "ZWNJ (Persian)": g_zwnj,
    "halfwidth katakana voiced marks": g_halfwidth,
    "emoji/text presentation VS": g_emoji_vs_text,
    "mark after space": g_leading_mark,
    "Mc misc (musical stem, visarga)": g_spacing_mark_misc,
}

N_PER_CLASS = 3000


def analyse():
    results = {}
    examples = collections.defaultdict(list)
    lib_disagree = collections.Counter()
    for name, gen in CLASSES.items():
        c = collections.Counter()
        for _ in range(N_PER_CLASS):
            s = gen()
            ub = uax29_boundaries(s)
            gb = lib_boundaries_grapheme(s)
            us = lib_boundaries_uniseg(s)
            if gb is not None and gb != ub:
                lib_disagree[("grapheme", name)] += 1
            if us is not None and us != ub:
                lib_disagree[("uniseg", name)] += 1
            for i in range(1, len(s)):
                truth = i in ub
                for key, mc in (("Mn", False), ("M", True)):
                    ok = simple_ok(s, i, mc)
                    c[(key, "positions")] += 1
                    if ok and not truth:
                        c[(key, "false_accept")] += 1
                        if len(examples[(name, key, "FA")]) < 2:
                            examples[(name, key, "FA")].append((s, i, f"U+{ord(s[i-1]):04X}|U+{ord(s[i]):04X}"))
                    elif (not ok) and truth:
                        c[(key, "false_reject")] += 1
                        if len(examples[(name, key, "FR")]) < 2:
                            examples[(name, key, "FR")].append((s, i, f"U+{ord(s[i-1]):04X}|U+{ord(s[i]):04X}"))
                    if not truth:
                        c[(key, "interior")] += 1
        results[name] = c
    return results, examples, lib_disagree


def fmt_pair(s, i):
    return f"{s[:i]!r} | {s[i:]!r}"


def gcb_table_size():
    """Price a stdlib-only implementation: range table of every non-Other GCB value + InCB + ExtPict."""
    props = ["Grapheme_Cluster_Break=" + v for v in (
        "CR", "LF", "Control", "Extend", "ZWJ", "Regional_Indicator", "Prepend", "SpacingMark", "L", "V", "T", "LV", "LVT")]
    props += ["Extended_Pictographic"]
    ranges = {}
    for p in props:
        pat = regex.compile(r"\p{" + p + "}")
        rs = []
        start = None
        prev = None
        for cp in range(0x110000):
            if 0xD800 <= cp <= 0xDFFF:
                hit = False
            else:
                hit = bool(pat.match(chr(cp)))
            if hit and start is None:
                start = cp
            if not hit and start is not None:
                rs.append((start, cp - 1))
                start = None
        if start is not None:
            rs.append((start, 0x10FFFF))
        ranges[p] = rs
    # InCB (Unicode 15.1) — regex may or may not expose it
    for v in ("Linker", "Consonant", "Extend"):
        try:
            pat = regex.compile(r"\p{InCB=" + v + "}")
            rs = []
            start = None
            for cp in range(0x110000):
                hit = (not 0xD800 <= cp <= 0xDFFF) and bool(pat.match(chr(cp)))
                if hit and start is None:
                    start = cp
                if not hit and start is not None:
                    rs.append((start, cp - 1)); start = None
            ranges["InCB=" + v] = rs
        except Exception as e:  # noqa
            ranges["InCB=" + v] = f"unsupported: {e}"
    blob = json.dumps(ranges).encode()
    return {k: (len(v) if isinstance(v, list) else v) for k, v in ranges.items()}, len(blob), len(zlib.compress(blob, 9))


def main():
    print("python", sys.version.split()[0], "unicodedata", unicodedata.unidata_version)
    print("regex", regex.__version__, "grapheme", getattr(grapheme_pkg, "__version__", None),
          "grapheme.UNICODE_VERSION", getattr(grapheme_pkg, "UNICODE_VERSION", None) if grapheme_pkg else None,
          "uniseg", getattr(__import__("uniseg"), "__version__", None) if uniseg_gc else None)
    print("stdlib unicodedata has grapheme API:",
          [n for n in dir(unicodedata) if "graph" in n.lower()] or "none")
    # regex's own Unicode version check: U+1FAE9 (Unicode 16 emoji face with bags) is Extended_Pictographic?
    print("regex \\p{Extended_Pictographic} knows U+1FAE9 (Unicode 16):",
          bool(regex.match(r"\p{Extended_Pictographic}", "\U0001FAE9")))
    print("regex Devanagari conjunct क्ष as one \\X (UAX29 15.1 GB9c):",
          [m.group() for m in regex.finditer(r"\X", "क्ष")])
    print()
    res, ex, dis = analyse()
    print(f"{'class':45s} | {'Mn,Me reading':>28s} | {'Mn,Mc,Me reading':>28s}")
    print(f"{'':45s} | {'interior  FA      FR':>28s} | {'FA      FR':>28s}")
    tot = collections.Counter()
    for name, c in res.items():
        for k, v in c.items():
            tot[k] += v
        print(f"{name:45s} | {c[('Mn','interior')]:8d} {c[('Mn','false_accept')]:6d} {c[('Mn','false_reject')]:7d}"
              f" | {c[('M','false_accept')]:14d} {c[('M','false_reject')]:7d}")
    print(f"{'TOTAL positions=' + str(tot[('Mn','positions')]):45s} | {tot[('Mn','interior')]:8d} "
          f"{tot[('Mn','false_accept')]:6d} {tot[('Mn','false_reject')]:7d} | {tot[('M','false_accept')]:14d} {tot[('M','false_reject')]:7d}")
    print("\nExamples (split shown as left | right; FA=false accept, FR=false reject):")
    for (name, key, kind), lst in sorted(ex.items()):
        for s, i, cps in lst[:1]:
            print(f"  [{kind} {key:2s}] {name:40s} {cps:18s} {fmt_pair(s, i)}")
    print("\nLibrary disagreement with regex \\X (strings, out of", N_PER_CLASS, "per class):")
    if not dis:
        print("  none")
    for (lib, name), v in sorted(dis.items()):
        print(f"  {lib:9s} {name:45s} {v}")
    sizes, raw, comp = gcb_table_size()
    print("\nVendored-table cost for a stdlib-only UAX #29 (range counts):", sizes)
    print(f"  JSON bytes {raw}, zlib {comp}")


if __name__ == "__main__":
    main()
