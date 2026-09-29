"""Round 2. Claim (DESIGN §5.2 Rev 4, rule 4): a field with exactly one extracted candidate is asked as a
two-option `choice([c0, none_of_these])`; this catches a lone WRONG candidate (the wrong-but-valid failure)
at a low false-abstention cost, whereas direct commit accepts whatever the extractor returned.

Method (SYNTHETIC PILOT, author-written; not a pre-registered Phase 0 probe). 6 field kinds (billing address,
customer name, payment due date, total amount due, patient name, contract effective date), 2 styles
(labelled / prose), randomised values. Every document contains the correct value plus 3 other same-type
spans. Conditions (n = 42 each):
  a   : lone candidate = the correct span
  b1  : lone candidate = a wrong same-type span (e.g. Ship To for billing); the correct value IS in the doc
  b2  : lone candidate = a wrong same-type span; the correct value is NOT in the doc (packing slip etc.)
  c   : lone candidate = a PARTIAL of the correct value (first name only, street without city, no cents,
        date without year); the full value is in the doc
Per document, one request with independent questions:
  S2  : choice {c0: <span>, none_of_these}            (the Rev 4 design)
  S4  : choice {c0..c3: same span + 3 same-type competitors from the doc (never the correct one unless
        condition a), none_of_these}                  (the same candidate among competitors)
  N1  : noul "Is <span> the <field>?"                 (alternative single-candidate gate)
Direct commit is the no-question baseline: it commits the lone candidate in every condition.
Opaque ids; the span text is the option description (DESIGN §5.1)."""
import asyncio, json, random
from jevclient import Jev, save, fmt_rate

R = random.Random(20260929)
FIRST_F = ["Dana", "Priya", "Aiko", "Ingrid", "Lucia", "Sofia", "Mei", "Greta", "Olga", "Fatima", "Nadia", "Hana"]
FIRST_M = ["Marcus", "Tomasz", "Rafael", "Kwame", "Oren", "Declan", "Hassan", "Nikhil", "Bruno", "Elias", "Viktor", "Omar"]
LAST = ["Whitfield", "Okafor", "Lindqvist", "Moreau", "Tanaka", "Castillo", "Brennan", "Novak", "Haddad", "Petrov",
        "Schulz", "Adeyemi", "Ferreira", "Kowalski", "Iyer", "Galloway", "Sato", "Mbeki", "Duarte", "Lachance"]
STREETS = ["Maple Ave", "Harbor Rd", "King St", "Elm Court", "Ridge Blvd", "Mill Lane", "Station Rd", "Cedar Way", "Bay St", "Orchard Dr"]
CITIES = ["Portland, OR 97201", "Austin, TX 78701", "Denver, CO 80202", "Columbus, OH 43215", "Tampa, FL 33602",
          "Madison, WI 53703", "Reno, NV 89501", "Boise, ID 83702"]
CO = ["Acme Corp", "Globex Ltd", "Initech LLC", "Umbrella Supply", "Hooli Inc", "Vandelay Imports", "Stark Parts",
      "Wayne Logistics", "Tyrell Systems", "Soylent Foods", "Cyberdyne Tools", "Wonka Retail"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def person(): return f"{R.choice(FIRST_F + FIRST_M)} {R.choice(LAST)}"
def addr(): return f"{R.randint(10, 9899)} {R.choice(STREETS)}, {R.choice(CITIES)}"
def date(): return f"{R.choice(MONTHS)} {R.randint(1, 28)}, 2026"
def money(): return f"${R.randint(100, 99999):,}.{R.randint(1, 99):02d}"
def uniq(f, n, avoid=()):
    s = []
    while len(s) < n:
        x = f()
        if x in s or x in avoid: continue
        if f is person and any(x.split()[0] == y.split()[0] or x.split()[-1] == y.split()[-1] for y in list(s) + list(avoid)): continue
        s.append(x)
    return s


def g_billing(style):
    bill, ship, vend, remit = uniq(addr, 4); c1, c2 = R.sample(CO, 2)
    partial = bill.split(",")[0]
    if style == 0:
        P = f"INVOICE #{R.randint(1000,9999)}\nFrom: {c1}, {vend}\nBill To: {c2}, {bill}\nShip To: {ship}\nRemit payment to: {remit}\nTerms: Net 30"
        A = f"PACKING SLIP #{R.randint(1000,9999)}\nFrom: {c1}, {vend}\nShip To: {c2}, {ship}\nReturns: {remit}\nContents: 3 cartons. No billing information is included on this slip."
    else:
        P = (f"This invoice is issued by {c1}, whose offices are at {vend}. The goods were delivered to our warehouse at {ship}. "
             f"For accounting purposes the invoice should be addressed to {c2} at {bill}. Checks may be mailed to our lockbox at {remit}.")
        A = (f"Delivery note from {c1} ({vend}). Three cartons were delivered to {c2} at {ship}. Damaged goods may be returned "
             f"to {remit}. This note is not an invoice and carries no billing details.")
    return "billing address", bill, ship, [vend, remit], partial, P, A


def g_customer(style):
    f = R.choice(FIRST_F + FIRST_M); cust = f"{f} {R.choice(LAST)}"
    rep, sig, cc = uniq(person, 3, avoid=(cust,))
    c1 = R.choice(CO)
    if style == 0:
        P = f"ORDER CONFIRMATION\nSupplier: {c1}\nSales representative: {rep}\nCustomer: {cust}\nApproved by: {sig}\nCC: {cc}"
        A = f"INTERNAL PRICING APPROVAL\nSupplier: {c1}\nSales representative: {rep}\nApproved by: {sig}\nCC: {cc}\nCustomer: (to be assigned)"
    else:
        P = (f"{rep} from {c1} spoke with {cust} on Monday about the order {f} wants to place. {sig} signed off on the discount "
             f"internally, and {cc} was copied on the thread.")
        A = (f"{rep} from {c1} asked for approval of a volume discount for a prospective account whose buyer has not been identified yet. "
             f"{sig} signed off internally, and {cc} was copied on the thread.")
    return "customer's name", cust, rep, [sig, cc], f, P, A


def g_due(style):
    due, inv, ship, order = uniq(date, 4)
    partial = due.rsplit(",", 1)[0]
    if style == 0:
        P = f"Invoice date: {inv}\nOrder date: {order}\nShipped: {ship}\nPayment due: {due}"
        A = f"Invoice date: {inv}\nOrder date: {order}\nShipped: {ship}\nPayment terms: to be agreed with the account manager"
    else:
        P = (f"We received your order on {order} and shipped it on {ship}. This invoice was generated on {inv}, and we ask that "
             f"payment reach us no later than {due}.")
        A = (f"We received your order on {order} and shipped it on {ship}. This invoice was generated on {inv}. Payment terms have "
             f"not been set yet; your account manager will confirm them.")
    return "payment due date", due, inv, [ship, order], partial, P, A


def g_total(style):
    tot, sub, tax, ship = uniq(money, 4)
    partial = tot.split(".")[0]
    if style == 0:
        P = f"Subtotal: {sub}\nShipping: {ship}\nSales tax: {tax}\nAmount due: {tot}"
        A = f"QUOTE (not an invoice)\nSubtotal: {sub}\nShipping estimate: {ship}\nEstimated tax: {tax}\nFinal amount: to be confirmed on order"
    else:
        P = (f"Your items came to {sub} before tax. Shipping added {ship} and sales tax was {tax}, so the total amount due is {tot}.")
        A = (f"This is an estimate only. Your items come to {sub} before tax, shipping would be about {ship}, and tax is estimated "
             f"at {tax}. We will confirm the amount due when you place the order.")
    return "total amount due", tot, sub, [tax, ship], partial, P, A


def g_patient(style):
    f = R.choice(FIRST_F + FIRST_M); pat = f"{f} {R.choice(LAST)}"
    doc_, ec, ref = uniq(person, 3, avoid=(pat,))
    if style == 0:
        P = f"PATIENT INTAKE\nAttending physician: Dr. {doc_}\nPatient: {pat}\nEmergency contact: {ec}\nReferred by: Dr. {ref}"
        A = f"CLINIC ROTA\nAttending physician: Dr. {doc_}\nOn-call contact: {ec}\nReferral coordinator: Dr. {ref}\nNo patient is assigned to this slot."
    else:
        P = f"Dr. {ref} referred {pat} to our clinic. {f} was seen today by Dr. {doc_}. In case of emergency, please call {ec}."
        A = (f"Dr. {ref} will cover referrals this week while Dr. {doc_} attends the conference. For urgent staffing issues, "
             f"please call {ec}.")
    return "patient's name", pat, f"Dr. {doc_}", [ec, f"Dr. {ref}"], f, P, A


def g_effective(style):
    eff, sign, term, notice = uniq(date, 4)
    partial = eff.rsplit(",", 1)[0]
    if style == 0:
        P = f"SERVICE AGREEMENT\nSigned: {sign}\nEffective date: {eff}\nNotice deadline: {notice}\nTermination date: {term}"
        A = f"SERVICE AGREEMENT (DRAFT)\nSigned: {sign}\nEffective date: [to be inserted]\nNotice deadline: {notice}\nTermination date: {term}"
    else:
        P = (f"This agreement, signed by both parties on {sign}, takes effect on {eff} and runs until {term}. Either party wishing "
             f"not to renew must give notice by {notice}.")
        A = (f"This agreement was signed by both parties on {sign} and runs until {term}; the date on which it takes effect will be "
             f"fixed in a side letter. Either party wishing not to renew must give notice by {notice}.")
    return "date the agreement takes effect", eff, sign, [term, notice], partial, P, A


GENS = [g_billing, g_customer, g_due, g_total, g_patient, g_effective]


def make_cases():
    cases = []
    for cond in ("a", "b1", "b2", "c"):
        for i in range(42):
            field, correct, trap, others, partial, P, A = GENS[i % 6]((i // 6) % 2)
            if cond == "a": cand, doc = correct, P
            elif cond == "b1": cand, doc = trap, P
            elif cond == "b2": cand, doc = trap, A
            else: cand, doc = partial, P
            assert cand in doc, (cond, field, cand)
            if cond in ("b2",): assert correct not in doc
            comp = [trap] + others if cond in ("a", "c") else others + [trap]
            comp = [x for x in comp if x != cand][:3]
            opts = [cand] + comp; R.shuffle(opts)
            for o in opts: assert o in doc, (cond, field, o)
            cases.append({"cond": cond, "field": field, "correct": correct, "cand": cand, "opts4": opts, "doc": doc,
                          "kind": GENS[i % 6].__name__, "style": (i // 6) % 2})
    return cases


def q_choice(field, opts):
    crit = {f"c{i}": f"\"{o}\"" for i, o in enumerate(opts)}
    crit["none_of_these"] = f"None of the other options is the {field}."
    return {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": crit}


async def main():
    cases = make_cases()
    j = Jev(concurrency=8)
    reqs = []
    for c in cases:
        reqs.append({"S2": q_choice(c["field"], [c["cand"]]), "S4": q_choice(c["field"], c["opts4"]),
                     "N1": {"type": "noul", "instructions": f"Is \"{c['cand']}\" the {c['field']}?"}})
    res = await asyncio.gather(*[j.ask(c["doc"], q) for c, q in zip(cases, reqs)])
    for c, r in zip(cases, res):
        assert r["status"] == 200, r
        a = r["body"]["answers"]
        c["S2"] = a["S2"]; c["S4"] = a["S4"]; c["N1"] = a["N1"]["noul"]
        ci = c["opts4"].index(c["cand"])
        c["S4_sel"] = "none" if a["S4"]["choice"] == "none_of_these" else ("cand" if a["S4"]["choice"] == f"c{ci}" else "other")
        c["S2_sel"] = "none" if a["S2"]["choice"] == "none_of_these" else "cand"
    await j.aclose()
    rep = {}
    for cond in ("a", "b1", "b2", "c"):
        cs = [c for c in cases if c["cond"] == cond]; n = len(cs)
        m = {"n": n,
             "S2_commit": fmt_rate(sum(c["S2_sel"] == "cand" for c in cs), n),
             "S2_abstain": fmt_rate(sum(c["S2_sel"] == "none" for c in cs), n),
             "S4_commit_same_cand": fmt_rate(sum(c["S4_sel"] == "cand" for c in cs), n),
             "S4_abstain": fmt_rate(sum(c["S4_sel"] == "none" for c in cs), n),
             "S4_other": fmt_rate(sum(c["S4_sel"] == "other" for c in cs), n),
             "N1_pass(>0.5)": fmt_rate(sum(c["N1"] > .5 for c in cs), n),
             "direct_commit": f"{n}/{n} (commits by construction)",
             "S2_p_cand_mean": round(sum(c["S2"]["probabilities"]["c0"] for c in cs) / n, 3),
             "S2_p_cand_sorted": sorted(c["S2"]["probabilities"]["c0"] for c in cs),
             "S2_vs_S4_disagree(commit vs not)": sum((c["S2_sel"] == "cand") != (c["S4_sel"] == "cand") for c in cs),
             "by_kind": {g.__name__: {"S2_commit": sum(c["S2_sel"] == "cand" for c in cs if c["kind"] == g.__name__),
                                     "S4_commit": sum(c["S4_sel"] == "cand" for c in cs if c["kind"] == g.__name__),
                                     "N1_pass": sum(c["N1"] > .5 for c in cs if c["kind"] == g.__name__),
                                     "n": sum(c["kind"] == g.__name__ for c in cs)} for g in GENS},
             "S2_wrong_commits": [(c["kind"], c["cand"], c["S2"]["probabilities"]["c0"], c["S2"]["confidence"]) for c in cs if c["S2_sel"] == "cand"] if cond != "a" else
                                 [(c["kind"], c["cand"], c["S2"]["probabilities"]["none_of_these"]) for c in cs if c["S2_sel"] == "none"]}
        rep[cond] = m
    save("r2_single_candidate", {"report": rep, "cases": cases})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
