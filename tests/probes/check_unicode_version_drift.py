"""Claim: DESIGN §5.6 default Normalizer (NFC + casefold + whitespace collapse) is deterministic, and PLAN §3
"Same schema, source, and backend produce the same result", across the supported interpreters
(Python 3.11+; org stack 3.11–3.12).

Method: dump, for every code point, the NFC+casefold result and whether str.isspace() — then run this script
under 3.11 (Unicode 14.0) and 3.12 (Unicode 15.0) and compare the digests / differing code points. Usage:
python check_unicode_version_drift.py > out.txt ; diff the two outputs.
"""
import hashlib, sys, unicodedata as ud
rows = []
for cp in range(0x110000):
    c = chr(cp)
    if 0xD800 <= cp <= 0xDFFF: continue
    rows.append(f"{cp:X}\t{ud.normalize('NFC', c).casefold().encode('utf-8', 'surrogatepass').hex()}\t{int(c.isspace())}\t{ud.category(c)}")
print("python", sys.version.split()[0], "unicode", ud.unidata_version)
print("digest(nfc+casefold+isspace)", hashlib.sha256("\n".join(r.rsplit('\t',1)[0] for r in rows).encode()).hexdigest()[:16])
print("assigned code points:", sum(1 for r in rows if not r.endswith("Cn")))
for r in rows:
    print(r)
