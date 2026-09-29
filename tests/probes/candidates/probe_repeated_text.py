"""Round 2. Claim (DESIGN §5.1 Rev 4): "Options are opaque ids (c0…cN) with the span text in the option description
… ids represent identical text at two different offsets, which text keys cannot." Question: is choosing the RIGHT
occurrence of identical text a real capability (provenance correct), or only representable?
Method (SYNTHETIC PILOT): 40 docs, 4 types x 10, each containing the SAME string twice at different offsets, once
in the correct role and once in a wrong role (T1 company: vendor header vs customer in a quoted prior invoice;
T2 date: this invoice's date vs a quoted prior invoice's due date; T3 person: recipient of the latest email vs
sender of the quoted original; T4 money: amount due on this statement vs payment received last period). The quoted
block is placed before or after the main part at random; 2 other same-type distractor spans per doc. Options:
both occurrences + 2 distractors + none_of_these, shuffled; opaque ids. Description formats:
  F0 text only ("Acme Corp" twice - indistinguishable; control)
  F1 text + character offsets ("at characters 112-121")
  F2 text + +/-40-char context window with the span in [[ ]]
  F3 text + +/-100-char context window with the span in [[ ]]
  F4 text + the full source line containing the span
Present (P) sets for F0-F4; absent (A) sets (correct occurrence removed; the identical wrong occurrence stays) for
F2-F4. One request per doc. Metrics: right occurrence chosen; wrong occurrence (same text, wrong provenance);
distractor; abstain."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save, fmt_rate

R = random.Random(6060)
CO = ["Acme Corp", "Globex Ltd", "Initech LLC", "Umbrella Supply", "Hooli Inc", "Vandelay Imports", "Stark Parts", "Wayne Logistics", "Tyrell Systems", "Soylent Foods"]
PPL = ["Dana Whitfield", "Marcus Okafor", "Priya Lindqvist", "Tomasz Moreau", "Aiko Tanaka", "Rafael Castillo", "Ingrid Brennan", "Kwame Novak", "Lucia Haddad", "Oren Petrov"]
MO = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
def dt(): return f"{R.choice(MO)} {R.randint(1, 28)}, 2026"
def mn(): return f"${R.randint(100, 9999):,}.{R.randint(0, 99):02d}"
def u(f, n):
    s = []
    while len(s) < n:
        x = f()
        if x not in s: s.append(x)
    return s


def t1():
    x, y, z, w = R.sample(CO, 4)
    main = f"INVOICE INV-{R.randint(1000,9999)}\nFrom: {x}\nBill To: {y}\nDate: {dt()}\nAmount due: {mn()}"
    quoted = (f"--- Attached for reference: prior disputed invoice ---\nINVOICE INV-{R.randint(100,999)}\nFrom: {z}\nBill To: {x}\n"
              f"Date: {dt()}\nNote: {w} handled delivery.")
    return "vendor (issuer) of this invoice", x, [y, z], main, quoted, "main"


def t2():
    dd, o1, o2, o3 = u(dt, 4)
    main = f"INVOICE INV-{R.randint(1000,9999)}\nFrom: {R.choice(CO)}\nInvoice date: {dd}\nShipped: {o1}\nAmount due: {mn()}"
    quoted = (f"--- Prior invoice INV-{R.randint(100,999)} (paid) ---\nInvoice date: {o2}\nDue date: {dd}\nPaid on: {o3}")
    return "invoice date of this invoice", dd, [o1, o2], main, quoted, "main"


def t3():
    a, b, c = R.sample(PPL, 3)
    main = f"From: {b}\nTo: {a}\nCc: {c}\nSubject: Re: onboarding\n\nThanks, see my answers inline below."
    quoted = f"-----Original Message-----\nFrom: {a}\nTo: {b}\nSubject: onboarding\n\nCould you confirm the start date and the laptop order?"
    return "recipient (To) of the latest email in this thread", a, [b, c], main, quoted, "main"


def t4():
    amt, o1, o2 = u(mn, 3)
    main = f"STATEMENT - period ending {dt()}\nPrevious balance: {o1}\nNew charges: {o2}\nAmount due on this statement: {amt}"
    quoted = f"--- Activity from the previous period ---\nPayment received: {amt} (thank you)\nLate fee waived."
    return "amount due on this statement", amt, [o1, o2], main, quoted, "main"


GENS = [t1, t2, t3, t4]


def win(text, s, e, w):
    return (("…" if s - w > 0 else "") + text[max(0, s - w):s] + "[[" + text[s:e] + "]]" + text[e:e + w] + ("…" if e + w < len(text) else "")).replace("\n", " / ")


def line(text, s, e):
    a = text.rfind("\n", 0, s) + 1; b = text.find("\n", e); b = len(text) if b < 0 else b
    return text[a:b]


def desc(fmt, text, sp):
    s, e = sp; t = text[s:e]
    if fmt == "F0": return f"\"{t}\""
    if fmt == "F1": return f"\"{t}\" at characters {s}-{e} of the text"
    if fmt == "F2": return f"\"{t}\" in context: {win(text, s, e, 40)}"
    if fmt == "F3": return f"\"{t}\" in context: {win(text, s, e, 100)}"
    if fmt == "F4": return f"\"{t}\" on the line: {line(text, s, e)}"


def make():
    cases = []
    for i in range(40):
        field, val, dis, main, quoted, _ = GENS[i % 4]()
        qfirst = R.random() < .5
        text = (quoted + "\n\n" + main) if qfirst else (main + "\n\n" + quoted)
        mo = (len(quoted) + 2) if qfirst else 0
        ms = main.find(val); assert ms >= 0 and main.count(val) == 1 and quoted.count(val) == 1, (field, val)
        right = (mo + ms, mo + ms + len(val))
        qo = 0 if qfirst else len(main) + 2
        qs = quoted.find(val); wrong = (qo + qs, qo + qs + len(val))
        assert text[right[0]:right[1]] == val == text[wrong[0]:wrong[1]] and text.count(val) == 2
        dsp = []
        for dval in dis:
            k = text.find(dval); assert k >= 0, dval; dsp.append((k, k + len(dval)))
        cases.append({"type": GENS[i % 4].__name__, "field": field, "text": text, "right": right, "wrong": wrong, "dis": dsp, "quoted_first": qfirst})
    return cases


def q(field, text, spans, fmt):
    crit = {f"c{i}": desc(fmt, text, sp) for i, sp in enumerate(spans)}
    crit["none_of_these"] = f"None of the other options is the {field}."
    return {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": crit}


async def main():
    cases = make(); j = Jev(concurrency=8); reqs = []
    for c in cases:
        P = [c["right"], c["wrong"]] + c["dis"]; R.shuffle(P)
        A = [c["wrong"]] + c["dis"]; R.shuffle(A)
        c["P"], c["A"] = P, A
        qq = {f"{f}_P": q(c["field"], c["text"], P, f) for f in ("F0", "F1", "F2", "F3", "F4")}
        qq.update({f"{f}_A": q(c["field"], c["text"], A, f) for f in ("F2", "F3", "F4")})
        reqs.append(qq)
    res = await asyncio.gather(*[j.ask(c["text"], qq) for c, qq in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        a = r["body"]["answers"]; c["ans"] = a
        for k, v in a.items():
            opts = c["P"] if k.endswith("_P") else c["A"]
            ch = v["choice"]
            if ch == "none_of_these": o = "abstain"
            else:
                sp = tuple(opts[int(ch[1:])])
                o = "right" if sp == tuple(c["right"]) else ("wrong_occurrence" if sp == tuple(c["wrong"]) else "distractor")
            c[k] = o
    await j.aclose()
    rep = {}
    n = len(cases)
    for k in ("F0_P", "F1_P", "F2_P", "F3_P", "F4_P", "F2_A", "F3_A", "F4_A"):
        rep[k] = {o: fmt_rate(sum(c[k] == o for c in cases), n) for o in ("right", "wrong_occurrence", "distractor", "abstain")}
        rep[k]["by_type_right_or_abstain"] = {g.__name__: sum(c[k] == ("right" if k.endswith("_P") else "abstain") for c in cases if c["type"] == g.__name__) for g in GENS}
        rep[k]["by_quoted_first_right_or_abstain"] = {qf: sum(c[k] == ("right" if k.endswith("_P") else "abstain") for c in cases if c["quoted_first"] == qf) for qf in (True, False)}
    rep["F0_P_prob_split_between_occurrences(mean |p_right - p_wrong|)"] = round(sum(
        abs(c["ans"]["F0_P"]["probabilities"][f"c{c['P'].index(c['right'])}"] - c["ans"]["F0_P"]["probabilities"][f"c{c['P'].index(c['wrong'])}"]) for c in cases) / n, 3)
    save("r2_opaque_ids", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
