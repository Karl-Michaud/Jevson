"""PILOT ONLY -- synthetic, author-generated cases; NOT the pre-registered PLAN Phase 0b probes.
Claim (DESIGN §5.3, R1; PLAN Phase 0b probes 1-3): a candidate choice with `none_of_these`
(a) picks the right span when present (go >= .85), (b) abstains when the right span is removed
(go >= .80), (c) rarely abstains when it is present (go <= .10). Vendor docs (jaggedness page)
say Choice is relative, Noul absolute -> compare alternative abstention designs.
Method: 60 templated documents (6 field types x 10), each containing the correct value plus 3-4
same-type competing spans that also occur in the doc. Per doc, one request with:
  CH_P / CH_A    : choice(candidates + none_of_these[described]) with correct present / removed
  CH2_P / CH2_A  : same, none option keyed "none of the above" with no description
  G_P / G_A      : noul gate "Is any of these candidates the <field>?" (candidates in instructions obj)
  PC_*           : one noul per candidate "Is `X` the <field>?" (abstain if max<0.5)
Then re-runs CH_A and CH_P alone (one question per request) to check co-batching leakage.
Metrics with Wilson 95% CIs."""
import asyncio, json, random
from jevclient import Jev, save, fmt_rate
R = random.Random(2026)
FIRST = ["Dana","Marcus","Priya","Tomasz","Aiko","Rafael","Ingrid","Kwame","Lucia","Oren","Sofia","Declan","Mei","Hassan","Greta","Nikhil","Olga","Bruno","Fatima","Elias"]
LAST = ["Whitfield","Okafor","Lindqvist","Moreau","Tanaka","Castillo","Brennan","Novak","Haddad","Petrov","Schulz","Adeyemi","Ferreira","Kowalski","Iyer","Galloway"]
STREETS = ["Maple Ave","Harbor Rd","King St","Elm Court","Ridge Blvd","Mill Lane","Station Rd","Cedar Way","Bay St","Orchard Dr"]
CITIES = ["Portland, OR 97201","Austin, TX 78701","Denver, CO 80202","Columbus, OH 43215","Tampa, FL 33602","Madison, WI 53703","Reno, NV 89501","Boise, ID 83702"]
CO = ["Acme Corp","Globex Ltd","Initech LLC","Umbrella Supply","Hooli Inc","Vandelay Imports","Stark Parts","Wayne Logistics","Tyrell Systems","Soylent Foods","Cyberdyne Tools","Wonka Retail"]
MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"]
def person(): return f"{R.choice(FIRST)} {R.choice(LAST)}"
def addr(): return f"{R.randint(10,9899)} {R.choice(STREETS)}, {R.choice(CITIES)}"
def date(): return f"{R.choice(MONTHS)} {R.randint(1,28)}, 2026"
def money(): return f"${R.randint(100,99999):,}.{R.randint(0,99):02d}"
def uniq(f, n):
    s = []
    while len(s) < n:
        x = f()
        if x not in s: s.append(x)
    return s

def make(i):
    t = i % 6; style = (i // 6) % 2  # 0 labelled, 1 prose
    if t == 0:
        b, s, v, r = uniq(addr, 4); c1, c2 = uniq(lambda: R.choice(CO), 2)
        doc = (f"INVOICE #{R.randint(1000,9999)}\nFrom: {c1}, {v}\nBill To: {c2}, {b}\nShip To: {s}\nRemit payment to: {r}\nTerms: Net 30" if style == 0 else
               f"This invoice is issued by {c1}, whose offices are at {v}. The goods were delivered to our warehouse at {s}. For accounting purposes the invoice should be addressed to {c2} at {b}. Checks may be mailed to our lockbox at {r}.")
        return "billing address", b, [s, v, r], doc
    if t == 1:
        cust, rep, sig, other = uniq(person, 4); c1 = R.choice(CO)
        doc = (f"ORDER CONFIRMATION\nSupplier: {c1}\nSales representative: {rep}\nCustomer: {cust}\nApproved by: {sig}\nCC: {other}" if style == 0 else
               f"{rep} from {c1} spoke with {cust} on Monday about the order {cust} wants to place. {sig} signed off on the discount internally, and {other} was copied on the thread.")
        return "customer name", cust, [rep, sig, other], doc
    if t == 2:
        due, inv, ship, order = uniq(date, 4)
        doc = (f"Invoice date: {inv}\nOrder date: {order}\nShipped: {ship}\nPayment due: {due}" if style == 0 else
               f"We received your order on {order} and shipped it on {ship}. This invoice was generated on {inv}, and we ask that payment reach us no later than {due}.")
        return "payment due date", due, [inv, ship, order], doc
    if t == 3:
        tot, sub, tax, dep, ship = uniq(money, 5)
        doc = (f"Subtotal: {sub}\nShipping: {ship}\nSales tax: {tax}\nDeposit received: {dep}\nAmount due: {tot}" if style == 0 else
               f"Your items came to {sub} before tax. Shipping added {ship} and sales tax was {tax}. We have already received your deposit of {dep}, so the balance you owe now is {tot}.")
        return "amount the customer still owes", tot, [sub, tax, dep, ship], doc
    if t == 4:
        pat, doc_, ec, ref = uniq(person, 4)
        doc = (f"PATIENT INTAKE\nAttending physician: Dr. {doc_}\nPatient: {pat}\nEmergency contact: {ec}\nReferred by: Dr. {ref}" if style == 0 else
               f"Dr. {ref} referred {pat} to our clinic. {pat} was seen today by Dr. {doc_}. In case of emergency, please call {ec}.")
        return "patient's name", pat, [doc_, ec, ref], doc
    eff, sign, term, notice = uniq(date, 4)
    doc = (f"SERVICE AGREEMENT\nSigned: {sign}\nEffective date: {eff}\nNotice deadline: {notice}\nTermination date: {term}" if style == 0 else
           f"This agreement, signed by both parties on {sign}, takes effect on {eff} and runs until {term}. Either party wishing not to renew must give notice by {notice}.")
    return "date the agreement takes effect", eff, [sign, term, notice], doc

CASES = [make(i) for i in range(60)]

def choice_q(field, cands, none_key, none_desc):
    crit = {c: None for c in cands}; crit[none_key] = none_desc
    return {"type": "choice", "instructions": f"Which of these is the {field}?", "criteria": crit}

def build(field, correct, distract):
    P = distract + [correct]; R.shuffle(P); A = list(distract); R.shuffle(A)
    q = {}
    for tag, cs in (("P", P), ("A", A)):
        q[f"CH_{tag}"] = choice_q(field, cs, "none_of_these", f"None of the other options is the {field}.")
        q[f"CH2_{tag}"] = choice_q(field, cs, "none of the above", None)
        q[f"G_{tag}"] = {"type": "noul", "instructions": {"candidates": cs, "question": f"Is any value in `candidates` the {field}?"}}
    for k, c in enumerate(P):
        q[f"PC_{k}"] = {"type": "noul", "instructions": f"Is '{c}' the {field}?"}
    return q, P, A

async def main():
    j = Jev(concurrency=8)
    built = [build(*c[:3]) for c in CASES]
    res = await asyncio.gather(*[j.ask(c[3], b[0]) for c, b in zip(CASES, built)])
    alone = await asyncio.gather(*[j.ask(c[3], {"CH_A": b[0]["CH_A"]}) for c, b in zip(CASES, built)])
    alone_p = await asyncio.gather(*[j.ask(c[3], {"CH_P": b[0]["CH_P"]}) for c, b in zip(CASES, built)])
    rows = []
    for (field, correct, dis, doc), (q, P, A), r, ra, rp in zip(CASES, built, res, alone, alone_p):
        a = r["body"]["answers"]
        pc = {P[k]: a[f"PC_{k}"]["noul"] for k in range(len(P))}
        rows.append({"field": field, "correct": correct, "doc": doc, "P": P, "A": A,
            "CH_P": a["CH_P"], "CH_A": a["CH_A"], "CH2_P": a["CH2_P"], "CH2_A": a["CH2_A"],
            "G_P": a["G_P"]["noul"], "G_A": a["G_A"]["noul"], "PC": pc,
            "CH_A_alone": ra["body"]["answers"]["CH_A"], "CH_P_alone": rp["body"]["answers"]["CH_P"]})
    n = len(rows); rep = {}
    for v, none in (("CH", "none_of_these"), ("CH2", "none of the above")):
        corr = sum(r[f"{v}_P"]["choice"] == r["correct"] for r in rows)
        fab = sum(r[f"{v}_P"]["choice"] == none for r in rows)
        wrongP = n - corr - fab
        absA = sum(r[f"{v}_A"]["choice"] == none for r in rows)
        rep[v] = {"P_accuracy(probe1)": fmt_rate(corr, n), "P_false_abstain(probe3)": fmt_rate(fab, n), "P_wrong_span": fmt_rate(wrongP, n),
                  "A_abstain(probe2)": fmt_rate(absA, n), "A_committed_wrong": fmt_rate(n - absA, n),
                  "A_wrong_commit_conf": sorted(round(r[f"{v}_A"]["confidence"], 2) for r in rows if r[f"{v}_A"]["choice"] != none),
                  "P_none_prob_mean": round(sum(r[f"{v}_P"]["probabilities"][none] for r in rows) / n, 3),
                  "A_none_prob_mean": round(sum(r[f"{v}_A"]["probabilities"][none] for r in rows) / n, 3)}
    # choice-without-none + gate
    for th in (0.5,):
        gP = sum(r["G_P"] > th for r in rows); gA = sum(r["G_A"] <= th for r in rows)
        rep[f"GATE@{th}"] = {"P_pass(not false-abstain)": fmt_rate(gP, n), "A_abstain": fmt_rate(gA, n)}
        pcP_corr = sum(max(r["PC"], key=r["PC"].get) == r["correct"] and r["PC"][r["correct"]] > th for r in rows)
        pcP_abs = sum(max(r["PC"].values()) <= th for r in rows)
        pcA_abs = sum(max(v for k, v in r["PC"].items() if k != r["correct"]) <= th for r in rows)
        rep[f"PER-CAND@{th}"] = {"P_accuracy": fmt_rate(pcP_corr, n), "P_false_abstain": fmt_rate(pcP_abs, n), "A_abstain": fmt_rate(pcA_abs, n)}
    # combined: CH_P selection + gate
    comb_corr = sum(r["CH_P"]["choice"] == r["correct"] and r["G_P"] > 0.5 for r in rows)
    comb_A = sum(r["CH_A"]["choice"] == "none_of_these" or r["G_A"] <= 0.5 for r in rows)
    rep["CH+GATE"] = {"P_accuracy": fmt_rate(comb_corr, n), "A_abstain": fmt_rate(comb_A, n)}
    # leakage check
    rep["cobatch_leak"] = {"CH_A_selection_changed_alone": sum(r["CH_A"]["choice"] != r["CH_A_alone"]["choice"] for r in rows),
        "CH_P_selection_changed_alone": sum(r["CH_P"]["choice"] != r["CH_P_alone"]["choice"] for r in rows),
        "max_prob_diff_A": round(max(abs(r["CH_A"]["probabilities"][k] - r["CH_A_alone"]["probabilities"][k]) for r in rows for k in r["CH_A"]["probabilities"]), 3),
        "max_prob_diff_P": round(max(abs(r["CH_P"]["probabilities"][k] - r["CH_P_alone"]["probabilities"][k]) for r in rows for k in r["CH_P"]["probabilities"]), 3)}
    # by field type
    byf = {}
    for r in rows:
        f = byf.setdefault(r["field"], {"P_ok": 0, "P_abs": 0, "A_abs": 0, "G_A_abs": 0, "n": 0})
        f["n"] += 1; f["P_ok"] += r["CH_P"]["choice"] == r["correct"]; f["P_abs"] += r["CH_P"]["choice"] == "none_of_these"
        f["A_abs"] += r["CH_A"]["choice"] == "none_of_these"; f["G_A_abs"] += r["G_A"] <= 0.5
    rep["by_field"] = byf
    await j.aclose(); save("p05_abstention", {"report": rep, "rows": rows}); print(json.dumps(rep, indent=1)); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
