
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
            if ae: ep_seq = 1                                   # ExtPict seen
            elif a == "Extend" and ep_seq == 1: pass            # ExtPict Extend*
            elif a == "ZWJ" and ep_seq == 1: ep_seq = 2         # ExtPict Extend* ZWJ
            else: ep_seq = 0
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
            elif a == "ZWJ" and be and ep_seq == 2: brk = False                  # GB11
            elif a == "Regional_Indicator" and b == "Regional_Indicator" and ri % 2 == 1: brk = False  # GB12/13
            else: brk = True                                                           # GB999
            if brk: out.add(i)
        return out
