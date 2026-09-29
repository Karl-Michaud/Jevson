"""PILOT ONLY (synthetic, author-generated, NOT pre-registered). Harder follow-up to probe_05,
whose templated cases hit a 100% ceiling. Claim as probe_05 (DESIGN §5.3, PLAN 0b probes 1-3).
Trap types (10 docs each, randomised values):
 T1 superseded   : "originally X, amended to Y"             absent-set keeps superseded X
 T2 negated      : "do NOT send to X ... send to Y"           absent-set keeps X
 T3 hypothetical : "if express, total would be X; chose standard, total is Y"
 T5 role inverse : buyer/seller named with roles; asked seller
 T6 near-dup     : correct date 2026 vs same day 2025 in a referenced prior invoice
 T7 similar name : "Dana Whitfield (rep)" vs customer "Dana Whitman"
 T4 missing      : field genuinely absent from doc; only same-type distractors exist (absent only)
Designs: CH (choice + described none_of_these), G (noul gate over candidate list),
PC (per-candidate noul, abstain if all <=0.5), CH+G (commit only if choice selects and gate>0.5).
One request per doc containing all questions (co-batching shown harmless in probe_05)."""
import asyncio, json, random
from jevclient import Jev, save, fmt_rate
from probe_05_abstention import person, addr, date, money, uniq, R, CO, choice_q, MONTHS
R.seed(99)

def t1():
    old, new, inv, ship = uniq(date, 4)
    return ("payment due date", new, [old, inv, ship],
            f"Invoice issued {inv}; goods shipped {ship}. Payment was originally due {old}, but per the client's request the due date has been amended to {new}.")
def t2():
    x, y, s = uniq(addr, 3)
    return ("address invoices should be sent to", y, [x, s],
            f"Please note: do NOT send invoices to our old office at {x}; that location closed in May. All invoices must go to {y}. Deliveries continue to {s}.")
def t3():
    x, y, z = uniq(money, 3)
    return ("final order total the customer is paying", y, [x, z],
            f"With express shipping your total would have been {x}. You selected standard shipping, so your order total is {y}. Your previous order last month came to {z}.")
def t5():
    a, b, c = uniq(lambda: R.choice(CO), 3)
    return ("seller", b, [a, c],
            f"This purchase agreement is between {a} (the Buyer) and {b} (the Seller). {c} will act as the escrow agent for the transaction.")
def t6():
    m = R.choice(MONTHS); d = R.randint(1, 28); other = date()
    return ("invoice date of this invoice", f"{m} {d}, 2026", [f"{m} {d}, 2025", other],
            f"This invoice (INV-{R.randint(100,999)}) is dated {m} {d}, 2026. It replaces invoice INV-{R.randint(100,999)} dated {m} {d}, 2025. Payment due {other}.")
def t7():
    f = R.choice(["Dana","Marcus","Priya","Tomasz","Aiko","Rafael"]); base = R.choice(["Whit","Hart","Brook","Ash"])
    rep = f"{f} {base}field"; cust = f"{f} {base}man"; mgr = person()
    return ("customer's name", cust, [rep, mgr],
            f"Sales rep {rep} closed the deal with customer {cust} on Friday. Regional manager {mgr} approved the pricing.")
def t4():
    s, v = uniq(addr, 2)
    return ("billing address", None, [s, v],
            f"PACKING SLIP. Ship to: {s}. Shipped from warehouse: {v}. Contents: 3 cartons. No billing information is included on this slip.")

GEN = {"T1": t1, "T2": t2, "T3": t3, "T5": t5, "T6": t6, "T7": t7, "T4": t4}
CASES = [(k, *GEN[k]()) for k in GEN for _ in range(10)]

def qs_for(field, cands, tag):
    return {f"CH_{tag}": choice_q(field, cands, "none_of_these", f"None of the other options is the {field}."),
            f"G_{tag}": {"type": "noul", "instructions": {"candidates": cands, "question": f"Is any value in `candidates` the {field}?"}},
            **{f"PC_{tag}_{i}": {"type": "noul", "instructions": f"Is '{c}' the {field}?"} for i, c in enumerate(cands)}}

async def main():
    j = Jev(concurrency=8); reqs = []
    for typ, field, correct, dis, doc in CASES:
        q = {}
        A = list(dis); R.shuffle(A); q.update(qs_for(field, A, "A"))
        P = None
        if correct:
            P = dis + [correct]; R.shuffle(P); q.update(qs_for(field, P, "P"))
        reqs.append((q, P, A))
    res = await asyncio.gather(*[j.ask(c[4], q) for c, (q, _, _) in zip(CASES, reqs)])
    rows = []
    for (typ, field, correct, dis, doc), (q, P, A), r in zip(CASES, reqs, res):
        a = r["body"]["answers"]; row = {"type": typ, "field": field, "correct": correct, "doc": doc, "A": A, "P": P}
        for tag, cs in (("A", A), ("P", P)):
            if cs is None: continue
            row[tag] = {"CH": a[f"CH_{tag}"], "G": a[f"G_{tag}"]["noul"], "PC": {c: a[f"PC_{tag}_{i}"]["noul"] for i, c in enumerate(cs)}}
        rows.append(row)
    def metrics(rs):
        m = {}
        Ps = [r for r in rs if r["P"]]
        n = len(Ps); N = len(rs)
        if n:
            m["P_CH_correct"] = fmt_rate(sum(r["P"]["CH"]["choice"] == r["correct"] for r in Ps), n)
            m["P_CH_false_abstain"] = fmt_rate(sum(r["P"]["CH"]["choice"] == "none_of_these" for r in Ps), n)
            m["P_CH_wrong_span"] = fmt_rate(sum(r["P"]["CH"]["choice"] not in (r["correct"], "none_of_these") for r in Ps), n)
            m["P_G_false_abstain"] = fmt_rate(sum(r["P"]["G"] <= .5 for r in Ps), n)
            m["P_PC_correct"] = fmt_rate(sum(max(r["P"]["PC"], key=r["P"]["PC"].get) == r["correct"] and max(r["P"]["PC"].values()) > .5 for r in Ps), n)
            m["P_PC_false_abstain"] = fmt_rate(sum(max(r["P"]["PC"].values()) <= .5 for r in Ps), n)
            m["P_CH+G_correct"] = fmt_rate(sum(r["P"]["CH"]["choice"] == r["correct"] and r["P"]["G"] > .5 for r in Ps), n)
        m["A_CH_abstain"] = fmt_rate(sum(r["A"]["CH"]["choice"] == "none_of_these" for r in rs), N)
        m["A_G_abstain"] = fmt_rate(sum(r["A"]["G"] <= .5 for r in rs), N)
        m["A_PC_abstain"] = fmt_rate(sum(max(r["A"]["PC"].values()) <= .5 for r in rs), N)
        m["A_CH+G_abstain"] = fmt_rate(sum(r["A"]["CH"]["choice"] == "none_of_these" or r["A"]["G"] <= .5 for r in rs), N)
        wc = [r["A"]["CH"]["confidence"] for r in rs if r["A"]["CH"]["choice"] != "none_of_these"]
        m["A_CH_wrong_commit_confidences"] = sorted(wc)
        return m
    rep = {"ALL": metrics(rows)}
    for t in GEN: rep[t] = metrics([r for r in rows if r["type"] == t])
    await j.aclose(); save("p05b_abstention_hard", {"report": rep, "rows": rows}); print(json.dumps(rep, indent=1)); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
