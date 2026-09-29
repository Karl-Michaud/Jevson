"""Round 3, probe 2. Complete-value template with MULTIPLE candidates (DESIGN §5.2, Revision 5).

Claim (DESIGN §5.2): candidate questions ask for "the complete <field> as written in the source; a partial value -
for example a street without its city, or a date without its year - is not acceptable." P11 validated this only
with LONE candidates (partials committed 32/42 without the wording, 0/42 with it; correct kept 42/42).
Questions here: (1) when the full value is offered ALONGSIDE partial variants of itself and other-entity competitors,
does the wording lower accuracy? (2) when only partial variants (plus competitors) are offered, does the wording
raise abstention? (3, descriptive) when the SOURCE itself only states partial forms, what does each wording do?

Method (SYNTHETIC PILOT, author-written; new domains and value pools, not the P11 invoice/patient set):
 - 6 field kinds x 12 docs = 72 docs: hotel guest name, freight delivery address, court hearing date, purchase-order
   supplier legal name, HR emergency-contact phone, conference venue. Each doc states the full value once, partial
   variants of it elsewhere (e.g. "Dear Dana", "Ms. Whitfield"), and a same-type value of another entity (+ its partial).
 - FULL condition: options = full + 2 partials + competitor full + competitor partial (5) + none_of_these.
 - PARTIAL condition: the same minus the full value (4) + none_of_these. Correct answer: abstain.
 - Wordings W0 (base) and W1 (Rev 5 complete-value template); same shuffled option order for both.
   One request per doc with 4 questions (FULL/PARTIAL x W0/W1).
 - DOCPARTIAL (descriptive, 6 x 6 = 36 docs): the source never states the full value, only partial forms;
   options = the partials + competitor + competitor partial. No single "correct" answer is claimed.
Options are opaque ids c0..cN with the quoted span as description (as in P11).
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save, fmt_rate

R = random.Random(20260929)
FIRST = ["Dana", "Priyanka", "Tobias", "Lucille", "Emeka", "Svetlana", "Ramon", "Ingrid", "Kenji", "Aurelie", "Declan", "Yasmin", "Bartholomew", "Oksana"]
LAST = ["Whitfield", "Castellanos", "Okwuosa", "Lindahl", "Marchbanks", "Villeneuve", "Abernathy", "Kowalczyk", "Haverford", "Nakashima", "Pellegrino", "Thackeray"]
STREETS = ["Harbor Blvd", "Quarry Lane", "Juniper Ave", "Foundry Rd", "Lakeshore Dr", "Cedar Crest Way", "Beacon St", "Old Mill Rd", "Prospect Pkwy", "Wexford Ct"]
CITIES = [("Long Beach", "CA", "90813"), ("Tacoma", "WA", "98402"), ("Dayton", "OH", "45402"), ("Laredo", "TX", "78040"), ("Savannah", "GA", "31401"),
          ("Duluth", "MN", "55802"), ("Reno", "NV", "89501"), ("Albany", "NY", "12207"), ("Mobile", "AL", "36602"), ("Boise", "ID", "83702")]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
DOW = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
CO1 = ["Brightline", "Kestrova", "Halvorsen", "Quintara", "Marlowe", "Ostwind", "Pellucid", "Tamberlane", "Verdigris", "Ashcombe", "Norrland", "Callisto"]
CO2 = ["Components", "Precision", "Polymers", "Optics", "Fasteners", "Circuits", "Hydraulics", "Coatings"]
SUF = ["GmbH", "Ltd", "S.A.", "AB", "B.V.", "Inc.", "S.r.l.", "Oy"]
VENUE = ["Riverside Convention Centre", "Kingsgate Exhibition Hall", "Harbourfront Conference Centre", "Old Exchange Assembly Rooms", "Northgate Events Pavilion", "Castlefield Congress Centre"]
VCITY = ["Bristol", "Leeds", "Glasgow", "Cardiff", "Belfast", "Norwich"]


def uniq(f, k):
    out = []
    while len(out) < k:
        v = f()
        if v not in out: out.append(v)
    return out


def person():
    return R.choice(FIRST), R.choice(LAST)


def two_people():
    f1, f2 = uniq(lambda: R.choice(FIRST), 2); l1, l2 = uniq(lambda: R.choice(LAST), 2)
    return (f1, l1), (f2, l2)


def k_guest(docpartial=False):
    (f, l), (af, al) = two_people()
    full, p1, p2 = f"{f} {l}", f"Dear {f}"[5:], f"Ms. {l}"
    comp, compp = f"{af} {al}", af
    head = "" if docpartial else f"Guest: {full}\n"
    text = (f"HOTEL MERIDIAN - RESERVATION CONFIRMATION\nConfirmation no. {R.randint(100000, 999999)}\n{head}Arrival: 14 Nov, 2 nights, Deluxe King\n\n"
            f"Dear {f},\nThank you for choosing the Meridian. Ms. {l}, your room will be ready from 3 pm; early check-in is subject to availability.\n"
            f"If you need anything, reply to this message and I will take care of it.\nWarm regards,\n{comp}\nReservations Agent\n"
            f"P.S. {af} is on duty at the front desk every weekday.")
    return "guest's name", full, [p1, p2], [comp, compp], text


def k_address(docpartial=False):
    (s1, s2) = uniq(lambda: R.choice(STREETS), 2); (c1, c2) = uniq(lambda: R.choice(CITIES), 2)
    n1, n2 = R.randint(10, 9999), R.randint(10, 999)
    street = f"{n1} {s1}, Unit {R.randint(2, 40)}"; city = f"{c1[0]}, {c1[1]} {c1[2]}"
    full = f"{street}, {city}"
    comp = f"{n2} {s2}, {c2[0]}, {c2[1]} {c2[2]}"; compp = f"{n2} {s2}"
    dl = "" if docpartial else f"Deliver to: {full}\n"
    text = (f"FREIGHT BOOKING #{R.randint(20000, 99999)}\nPickup from: {comp}\n{dl}Pallets: 4 (1,850 lb)\n\n"
            f"Notes: driver must call 30 minutes before arriving at {street}. The receiving dock in {city} closes at 4 pm. "
            f"Pickup at {compp} is from the rear loading bay.")
    return "delivery address", full, [street, city], [comp, compp], text


def k_hearing(docpartial=False):
    m, d, y = R.randrange(12), R.randint(1, 28), 2026
    m2, d2 = R.randrange(12), R.randint(1, 28)
    while (m2, d2) == (m, d): m2, d2 = R.randrange(12), R.randint(1, 28)
    dow = R.choice(DOW)
    full, p1, p2 = f"{MONTHS[m]} {d}, {y}", f"{MONTHS[m]} {d}", dow
    comp, compp = f"{MONTHS[m2]} {d2}, 2025", f"{MONTHS[m2]} {d2}"
    hl = f"A hearing on the motion is set for {dow}, {full}, at 9:30 a.m. in Courtroom 4B." if not docpartial else \
         f"A hearing on the motion is set for {dow}, {p1}, at 9:30 a.m. in Courtroom 4B."
    text = (f"SUPERIOR COURT - NOTICE OF HEARING\nCase No. {R.randint(10, 99)}-CV-{R.randint(1000, 9999)}\n"
            f"The motion to compel was filed on {comp}. {hl}\n"
            f"Counsel should note that {p1} is the only date the court has available this term, and that the {compp} filing "
            f"will be considered together with any opposition. Please arrive by 9:00 a.m. on {dow}.")
    return "hearing date", full, [p1, p2], [comp, compp], text


def k_supplier(docpartial=False):
    a, b = uniq(lambda: R.choice(CO1), 2); x = R.choice(CO2); sfx, sfx2 = uniq(lambda: R.choice(SUF), 2)
    full, p1, p2 = f"{a} {x} {sfx}", a, f"{a} {x}"
    comp, compp = f"{b} Instruments {sfx2}", b
    sl = f"Supplier: {full}\n" if not docpartial else ""
    text = (f"PURCHASE ORDER PO-{R.randint(40000, 49999)}\nBuyer: {comp}\n{sl}Date: 2026-08-14\n\n"
            f"1. 400 x hex flange bolts M8, unit price EUR 0.42\n2. 60 x panel gaskets, unit price EUR 3.10\n\n"
            f"{p2} shall deliver to the buyer's warehouse within 21 days. Invoices from {p1} must quote this PO number. "
            f"{compp} will pay within 45 days of receipt of a correct invoice.")
    return "supplier's legal name", full, [p1, p2], [comp, compp], text


def k_phone(docpartial=False):
    a, b = R.randint(1000, 9999), R.randint(1000, 9999); a2, b2 = R.randint(1000, 9999), R.randint(1000, 9999)
    full, p1, p2 = f"+44 20 {a} {b}", f"{a} {b}", f"{b}"
    comp, compp = f"+44 20 {a2} {b2}", f"{a2} {b2}"
    (ef, el), (cf, cl) = two_people()
    cl_ = f"Emergency contact: {cf} {cl} (spouse), tel. {full}\n" if not docpartial else f"Emergency contact: {cf} {cl} (spouse)\n"
    text = (f"NEW STARTER FORM - PERSONAL DETAILS\nEmployee: {ef} {el}\nEmployee mobile: {comp}\n{cl_}\n"
            f"HR note: {cf} prefers calls after 5 pm on {p1}; if there is no answer, text the number ending {p2}. "
            f"The employee can also be reached on {compp} during working hours.")
    return "emergency contact's phone number", full, [p1, p2], [comp, compp], text


def k_venue(docpartial=False):
    v, h = R.choice(VENUE), R.choice(["Hall B", "Suite 3", "Room 214", "Auditorium 2", "Hall C"]); c = R.choice(VCITY)
    num, road = R.randint(2, 480), R.choice(["Quay Road", "Mill Street", "Canal Walk", "Station Approach"])
    full, p1, p2 = f"{h}, {v}, {num} {road}, {c}", h, v
    comp, compp = f"Harbour Hotel, {R.randint(2, 90)} Anchor Street, {c}", "Harbour Hotel"
    vl = f"Venue: {full}\n" if not docpartial else ""
    text = (f"INVITATION - ANNUAL SUPPLY CHAIN FORUM\nDate: 12 May 2027, 09:00-17:30\n{vl}Accommodation: {comp}\n\n"
            f"Registration opens at 08:30 outside {p1}. The {p2} is a ten-minute walk from the hotel. Delegates staying at "
            f"{compp} can use the free shuttle.")
    return "event venue", full, [p1, p2], [comp, compp], text


KINDS = [k_guest, k_address, k_hearing, k_supplier, k_phone, k_venue]


def q(field, opts, w):
    crit = {f"c{i}": f"\"{o}\"" for i, o in enumerate(opts)}
    if w == 0:
        ins = f"Which of these is the {field}?"
        crit["none_of_these"] = f"None of the other options is the {field}."
    else:
        ins = (f"Which of these is the complete {field} as written in the source? A partial value - for example a street "
               f"without its city, or a date without its year - is not acceptable.")
        crit["none_of_these"] = f"None of the other options is the complete {field} as written in the source; a partial value does not count."
    return {"type": "choice", "instructions": ins, "criteria": crit}


def classify(ch, opts, full, partials, comps):
    if ch == "none_of_these": return "abstain"
    o = opts[int(ch[1:])]
    return "full" if o == full else ("partial" if o in partials else "competitor")


def build():
    cases = []
    for g in KINDS:
        for _ in range(12):
            field, full, partials, comps, text = g()
            for o in [full] + partials + comps: assert o in text, (g.__name__, o)
            assert len(set([full] + partials + comps)) == 5
            F = [full] + partials + comps; R.shuffle(F)
            P = partials + comps; R.shuffle(P)
            cases.append({"kind": g.__name__, "cond": "main", "field": field, "full": full, "partials": partials, "comps": comps, "text": text, "F": F, "P": P})
        for _ in range(6):
            field, full, partials, comps, text = g(docpartial=True)
            assert full not in text, (g.__name__, "docpartial leaks full")
            for o in partials + comps: assert o in text, (g.__name__, o)
            P = partials + comps; R.shuffle(P)
            cases.append({"kind": g.__name__, "cond": "docpartial", "field": field, "full": full, "partials": partials, "comps": comps, "text": text, "P": P})
    return cases


async def main():
    cases = build()
    j = Jev(concurrency=8); reqs = []
    for c in cases:
        qq = {f"P_W{w}": q(c["field"], c["P"], w) for w in (0, 1)}
        if c["cond"] == "main": qq.update({f"F_W{w}": q(c["field"], c["F"], w) for w in (0, 1)})
        reqs.append(qq)
    res = await asyncio.gather(*[j.ask(c["text"], r) for c, r in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        c["ans"] = r["body"]["answers"]
        for k, a in c["ans"].items():
            opts = c["F"] if k.startswith("F") else c["P"]
            c[k] = classify(a["choice"], opts, c["full"], c["partials"], c["comps"])
            c[k + "_p"] = max(a["probabilities"].values())
            c[k + "_pnone"] = a["probabilities"].get("none_of_these")
    await j.aclose()
    rep = {}
    main_ = [c for c in cases if c["cond"] == "main"]; dp = [c for c in cases if c["cond"] == "docpartial"]
    for key, sub, outs in (("F", main_, ("full", "partial", "competitor", "abstain")), ("P", main_, ("abstain", "partial", "competitor")),
                           ("DOCPARTIAL", dp, ("abstain", "partial", "competitor"))):
        qk = "P" if key == "DOCPARTIAL" else key
        for w in (0, 1):
            rep[f"{key}_W{w}"] = {o: fmt_rate(sum(c[f"{qk}_W{w}"] == o for c in sub), len(sub)) for o in outs}
            rep[f"{key}_W{w}"]["by_kind"] = {g.__name__: dict(__import__("collections").Counter(c[f"{qk}_W{w}"] for c in sub if c["kind"] == g.__name__)) for g in KINDS}
        good = "full" if key == "F" else "abstain"
        b = sum(c[f"{qk}_W0"] == good and c[f"{qk}_W1"] != good for c in sub); cc = sum(c[f"{qk}_W0"] != good and c[f"{qk}_W1"] == good for c in sub)
        rep[f"{key}_paired"] = {"W0_right_W1_wrong": b, "W0_wrong_W1_right": cc}
    rep["F_mean_p_full_W0"] = round(sum(c["ans"]["F_W0"]["probabilities"][f"c{c['F'].index(c['full'])}"] for c in main_) / len(main_), 3)
    rep["F_mean_p_full_W1"] = round(sum(c["ans"]["F_W1"]["probabilities"][f"c{c['F'].index(c['full'])}"] for c in main_) / len(main_), 3)
    save("r3_complete_value", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
