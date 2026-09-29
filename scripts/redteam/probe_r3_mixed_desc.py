"""Round 3, probe 3. Mixed option descriptions (DESIGN §5.1, Revision 5).

Claim (DESIGN §5.1): when a candidate's text occurs more than once, every occurrence is offered as its own option
with a +/-40-character context window; unique texts keep a bare description. So one choice mixes context-window options
with bare options. Question: does that mix bias selection toward (or away from) the context-bearing options?

Method (SYNTHETIC PILOT, author-written; 4 new domains x 12 = 48 docs: rent statement, e-mail thread about a meeting
room, shipping notice, committee minutes). Each doc supports three questions:
 - R  (correct answer is a REPEATED text): options = correct occurrence, same text at a wrong-role occurrence,
      2 unique distractors, + none_of_these.
 - U  (correct answer is a UNIQUE text): options = the unique correct text, a REPEATED distractor text (both
      occurrences offered), 1 unique distractor, + none_of_these.
 - UA (U with the correct unique text removed; correct answer = abstain): options = the repeated distractor's
      2 occurrences, 1 unique distractor, + none_of_these.
Each question is asked in three description formats, all in one request per doc (questions are independent [P1]):
 - MIX  (Rev 5): repeated-text options get `"<text>" in context: ...[[text]]...` (+/-40 chars, as P15's F2);
        unique-text options get `"<text>"`;
 - CTX: every option gets the context window;
 - BARE: every option is `"<text>"`.
Metrics: correct / wrong occurrence / distractor / abstain per format; for U and UA, the rate at which the
context-bearing (repeated) distractor is chosen, and the probability mass on it, MIX vs CTX vs BARE (paired).
"""
import asyncio, json, random
from collections import Counter
from jevclient import Jev, save, fmt_rate

R = random.Random(4242)
FN = ["Aisha", "Bruno", "Celeste", "Dmitri", "Esther", "Farid", "Greta", "Hamish", "Ilse", "Jonah", "Kalinda", "Lorenzo", "Mireille", "Nkechi", "Osvaldo", "Petra"]
LN = ["Abara", "Brennan", "Cho", "Dalgaard", "Eze", "Fontaine", "Gallo", "Hedlund", "Iqbal", "Juarez", "Kincaid", "Lachance", "Mbeki", "Novak", "Ortega", "Pruitt"]
MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def uniq(f, k):
    out = []
    while len(out) < k:
        v = f()
        if v not in out: out.append(v)
    return out


def date(): return f"{R.choice(MON)} {R.randint(1, 28)}, 2026"
def money(): return f"${R.randint(400, 2900):,}.{R.choice(['00', '50', '25', '75'])}"
def name(): return f"{R.choice(FN)} {R.choice(LN)}"


def g_rent():
    V, d1, d2 = uniq(money, 3); W, D, d3 = uniq(date, 3)
    cur = (f"STATEMENT - Unit 12C, Larkspur Apartments\nStatement date: {D}\nAmount due: {V}\nPlease pay by: {W}\n"
           f"Late fee if paid after the due date: {d1}\nMove-in date on file: {d3}")
    prev = f"--- Previous period (balance as of {D}) ---\nPayment received: {V} - thank you.\nSecurity deposit held: {d2}"
    text = (prev + "\n\n" + cur) if R.random() < .5 else (cur + "\n\n" + prev)
    return {"text": text, "fR": "amount due on this statement", "V": V, "anchorR": f"Amount due: {V}", "dR": [d1, d2],
            "fU": "date by which this statement must be paid", "W": W, "D": D, "dU": d3}


def g_email():
    V, a, b, cc = uniq(name, 4); W, D, d3 = uniq(lambda: f"Room {R.randint(1, 6)}{R.choice('ABCD')}", 3)
    latest = (f"From: {V}\nTo: facilities team\nSubject: Re: Thursday design review\n\nWe have moved Thursday's design review to "
              f"{W}, because {D} is being repainted. {cc} will bring the projector; {b} has the agenda.")
    quoted = (f"> From: {a}\n> To: {V}\n> Is the Thursday review still in {D}? Last month we used {d3} and the screen was too small. "
              f"That room is still shown in the booking system.")
    text = (quoted + "\n\n" + latest) if R.random() < .5 else (latest + "\n\n" + quoted)
    return {"text": text, "fR": "sender of the latest message", "V": V, "anchorR": f"From: {V}\nTo: facilities", "dR": [a, b],
            "fU": "room where Thursday's design review will now take place", "W": W, "D": D, "dU": d3}


def g_ship():
    V, d1, d2 = uniq(lambda: R.choice(["DHL Express", "FedEx Ground", "UPS Standard", "DPD Classic", "Royal Mail Tracked", "GLS Parcel", "TNT Economy", "Purolator"]), 3)
    W, D, d3 = uniq(date, 3)
    cur = (f"SHIPPING NOTICE - Order 55-{R.randint(1000, 9999)}\nCarrier: {V}\nShipped on: {D}\nEstimated delivery: {W}\n"
           f"Returns are collected by {d1}. Order placed: {d3}.")
    prev = (f"--- Your previous order ---\nShipped on {D} with {V}; delivered two days late. "
            f"{d2} was not available for that order.")
    text = (prev + "\n\n" + cur) if R.random() < .5 else (cur + "\n\n" + prev)
    return {"text": text, "fR": "carrier for this order", "V": V, "anchorR": f"Carrier: {V}", "dR": [d1, d2],
            "fU": "estimated delivery date of this order", "W": W, "D": D, "dU": d3}


def g_minutes():
    V, d1, d2 = uniq(date, 3); W, D, d3 = uniq(name, 3)
    cur = (f"MINUTES - Parks and Trails Committee\nChair: {W}\nMinutes taken by: {D}\n"
           f"1. The trail survey report is due on {V}. 2. {d3} presented the budget. 3. The bench order placed on {d1} has arrived.\n"
           f"Next meeting: {V}, 6 pm, Community Hall.")
    prev = (f"--- Actions carried over ---\n{D} to circulate the survey form; volunteers to confirm availability by {d2}.")
    text = (prev + "\n\n" + cur) if R.random() < .5 else (cur + "\n\n" + prev)
    return {"text": text, "fR": "date of the next committee meeting", "V": V, "anchorR": f"Next meeting: {V}", "dR": [d1, d2],
            "fU": "person who chaired this meeting", "W": W, "D": D, "dU": d3}


GENS = [g_rent, g_email, g_ship, g_minutes]


def occ(text, t):
    out, k = [], text.find(t)
    while k >= 0:
        out.append((k, k + len(t))); k = text.find(t, k + 1)
    return out


def win(text, s, e, w=40):
    return (("…" if s - w > 0 else "") + text[max(0, s - w):s] + "[[" + text[s:e] + "]]" + text[e:e + w] + ("…" if e + w < len(text) else "")).replace("\n", " / ")


def desc(fmt, text, sp, repeated):
    s, e = sp; t = text[s:e]
    if fmt == "BARE" or (fmt == "MIX" and not repeated): return f"\"{t}\""
    return f"\"{t}\" in context: {win(text, s, e)}"


def build():
    cases = []
    for i in range(48):
        c = GENS[i % 4](); text = c["text"]
        vo = occ(text, c["V"]); do = occ(text, c["D"])
        assert len(vo) == 2 and len(do) == 2, (GENS[i % 4].__name__, c["V"], len(vo), c["D"], len(do))
        for t in c["dR"] + [c["W"], c["dU"]]: assert len(occ(text, t)) == 1, (GENS[i % 4].__name__, t, text)
        a = text.index(c["anchorR"]) + c["anchorR"].index(c["V"]); right = (a, a + len(c["V"])); assert right in vo
        wrong = [o for o in vo if o != right][0]
        o = lambda t: occ(text, t)[0]
        R_opts = [("right", right, True), ("wrong_occ", wrong, True)] + [("distractor", o(t), False) for t in c["dR"]]
        U_opts = [("correct", o(c["W"]), False), ("rep_distractor", do[0], True), ("rep_distractor", do[1], True), ("distractor", o(c["dU"]), False)]
        UA_opts = U_opts[1:]
        for L in (R_opts, U_opts, UA_opts): R.shuffle(L)
        c.update({"gen": GENS[i % 4].__name__, "R_opts": R_opts, "U_opts": U_opts, "UA_opts": UA_opts})
        cases.append(c)
    return cases


def q(field, text, opts, fmt):
    crit = {f"c{i}": desc(fmt, text, sp, rep) for i, (_, sp, rep) in enumerate(opts)}
    crit["none_of_these"] = f"None of the other options is the {field}."
    return {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": crit}


async def main():
    cases = build(); j = Jev(concurrency=8); reqs = []
    for c in cases:
        qq = {}
        for f in ("MIX", "CTX", "BARE"):
            qq[f"R_{f}"] = q(c["fR"], c["text"], c["R_opts"], f)
            qq[f"U_{f}"] = q(c["fU"], c["text"], c["U_opts"], f)
            qq[f"UA_{f}"] = q(c["fU"], c["text"], c["UA_opts"], f)
        reqs.append(qq)
    res = await asyncio.gather(*[j.ask(c["text"], qq) for c, qq in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        c["ans"] = r["body"]["answers"]
        for k, a in c["ans"].items():
            opts = c[k.split("_")[0] + "_opts"]
            ch = a["choice"]
            c[k] = "abstain" if ch == "none_of_these" else opts[int(ch[1:])][0]
            c[k + "_pctx"] = round(sum(a["probabilities"][f"c{i}"] for i, (_, _, rep) in enumerate(opts) if rep), 2)
    await j.aclose()
    rep = {}
    for Q, outs in (("R", ("right", "wrong_occ", "distractor", "abstain")), ("U", ("correct", "rep_distractor", "distractor", "abstain")),
                    ("UA", ("abstain", "rep_distractor", "distractor"))):
        for f in ("MIX", "CTX", "BARE"):
            k = f"{Q}_{f}"
            rep[k] = {o: fmt_rate(sum(c[k] == o for c in cases), len(cases)) for o in outs}
            rep[k]["mean_p_on_repeated_text_options"] = round(sum(c[k + "_pctx"] for c in cases) / len(cases), 3)
            rep[k]["by_gen"] = {g.__name__: dict(Counter(c[k] for c in cases if c["gen"] == g.__name__)) for g in GENS}
        good = {"R": "right", "U": "correct", "UA": "abstain"}[Q]
        for f in ("CTX", "BARE"):
            rep[f"{Q}_paired_MIX_vs_{f}"] = {"MIX_right_other_wrong": sum(c[f"{Q}_MIX"] == good and c[f"{Q}_{f}"] != good for c in cases),
                                             "MIX_wrong_other_right": sum(c[f"{Q}_MIX"] != good and c[f"{Q}_{f}"] == good for c in cases)}
    save("r3_mixed_desc", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
