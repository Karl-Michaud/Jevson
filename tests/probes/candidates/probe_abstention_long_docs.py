"""PILOT ONLY (synthetic, NOT pre-registered). Stress follow-up to probe_abstention/05b (both at ceiling).
Claim (DESIGN §5.3; PLAN 0b probes 1-3) under harder conditions:
 S-long : the probe_abstention_traps trap doc embedded at a random position inside ~2.5k tokens of other
          invoices/notes containing many same-type spans; ~10 candidates (correct + trap
          distractor + spans from the noise). Present/absent as before.
 S-part : absent set contains only a PARTIAL span of the correct value (first name only, street
          without city, amount without cents) plus other distractors -> does it commit to the
          partial (bad provenance) or abstain? Also present set with both full and partial.
Designs CH / G / PC as probe_abstention_traps. One request per doc."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random
from jevclient import Jev, save, fmt_rate
from candidates.probe_abstention import person, addr, date, money, uniq, R, choice_q, CO
import candidates.probe_abstention_traps as H
R.seed(4242)

def noise_block(k):
    out = []
    for _ in range(k):
        t = R.randrange(4)
        if t == 0: out.append(f"Invoice INV-{R.randint(1000,9999)} from {R.choice(CO)} dated {date()}: amount {money()}, due {date()}, billed to {person()} at {addr()}.")
        elif t == 1: out.append(f"Note from {person()}: the shipment for {R.choice(CO)} left {addr()} on {date()}; freight was {money()}.")
        elif t == 2: out.append(f"Reminder: {person()} will call {person()} about the renewal with {R.choice(CO)} before {date()}.")
        else: out.append(f"Credit memo CM-{R.randint(100,999)} for {money()} issued to {R.choice(CO)} ({addr()}) on {date()}.")
    return out

def same_type_from(text_items, correct, typ):
    import re
    joined = " ".join(text_items)
    if typ in ("T1", "T6"): pat = r"(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, 20\d\d"
    elif typ == "T3": pat = r"\$[\d,]+\.\d\d"
    elif typ == "T2": pat = r"\d+ [A-Z][a-z]+ (?:Ave|Rd|St|Court|Blvd|Lane|Way|Dr), [A-Za-z]+, [A-Z]{2} \d{5}"
    elif typ == "T5": pat = "|".join(map(re.escape, CO))
    else: pat = r"(?:Dana|Marcus|Priya|Tomasz|Aiko|Rafael|Ingrid|Kwame|Lucia|Oren|Sofia|Declan|Mei|Hassan|Greta|Nikhil|Olga|Bruno|Fatima|Elias) [A-Z][a-z]+"
    found = [m for m in dict.fromkeys(re.findall(pat, joined)) if m != correct]
    return found

async def main():
    j = Jev(concurrency=8); cases = []
    types = ["T1", "T2", "T3", "T5", "T6", "T7"]
    for i in range(36):  # S-long: 6 per type
        typ = types[i % 6]; field, correct, dis, doc = H.GEN[typ]()
        nb = noise_block(45); pos = R.randrange(len(nb)); nb.insert(pos, doc)
        pool = [x for x in same_type_from(nb, correct, typ) if x not in dis]
        R.shuffle(pool); extra = pool[:10 - len(dis) - 1]
        dis2 = dis + extra
        cases.append(("S-long", typ, field, correct, dis2, "\n".join(nb)))
    for i in range(24):  # S-part
        k = i % 3
        if k == 0:
            f, l = R.choice(["Dana","Marcus","Priya"]), R.choice(["Okafor","Moreau","Tanaka","Novak"]); cust = f"{f} {l}"
            rep, mgr = uniq(person, 2)
            doc = f"Sales rep {rep} closed the deal with customer {cust} on Friday. Regional manager {mgr} approved the pricing."
            cases.append(("S-part", "name", "customer's full name", cust, [rep, mgr], doc, f))
        elif k == 1:
            b, s = uniq(addr, 2); partial = b.split(",")[0]
            doc = f"Bill to: {b}. Ship to: {s}."
            cases.append(("S-part", "addr", "complete billing address", b, [s], doc, partial))
        else:
            tot, sub = uniq(money, 2); partial = tot.split(".")[0]
            doc = f"Subtotal {sub}. Total due {tot}."
            cases.append(("S-part", "money", "exact total due", tot, [sub], doc, partial))
    reqs = []
    for c in cases:
        kind, typ, field, correct, dis, doc = c[:6]
        A = list(dis) + ([c[6]] if kind == "S-part" else []); R.shuffle(A)
        P = list(dis) + [correct] + ([c[6]] if kind == "S-part" else []); R.shuffle(P)
        q = {}; q.update(H.qs_for(field, A, "A")); q.update(H.qs_for(field, P, "P")); reqs.append((q, P, A))
    res = await asyncio.gather(*[j.ask(c[5], q) for c, (q, _, _) in zip(cases, reqs)])
    rows = []
    for c, (q, P, A), r in zip(cases, reqs, res):
        if r["status"] != 200: print("ERR", r); continue
        a = r["body"]["answers"]; row = {"kind": c[0], "type": c[1], "field": c[2], "correct": c[3], "partial": c[6] if len(c) > 6 else None, "P": P, "A": A, "tokens": r["usage"]}
        for tag, cs in (("A", A), ("P", P)):
            row[tag] = {"CH": a[f"CH_{tag}"], "G": a[f"G_{tag}"]["noul"], "PC": {x: a[f"PC_{tag}_{i}"]["noul"] for i, x in enumerate(cs)}}
        rows.append(row)
    def M(rs):
        n = len(rs); m = {"n": n}
        m["P_CH_correct"] = fmt_rate(sum(r["P"]["CH"]["choice"] == r["correct"] for r in rs), n)
        m["P_CH_false_abstain"] = fmt_rate(sum(r["P"]["CH"]["choice"] == "none_of_these" for r in rs), n)
        m["P_CH_wrong"] = [(r["type"], r["correct"], r["P"]["CH"]["choice"], r["P"]["CH"]["confidence"]) for r in rs if r["P"]["CH"]["choice"] not in (r["correct"], "none_of_these")]
        m["P_G_false_abstain"] = fmt_rate(sum(r["P"]["G"] <= .5 for r in rs), n)
        m["P_PC_correct"] = fmt_rate(sum(max(r["P"]["PC"], key=r["P"]["PC"].get) == r["correct"] and max(r["P"]["PC"].values()) > .5 for r in rs), n)
        m["P_PC_false_abstain"] = fmt_rate(sum(max(r["P"]["PC"].values()) <= .5 for r in rs), n)
        m["A_CH_abstain"] = fmt_rate(sum(r["A"]["CH"]["choice"] == "none_of_these" for r in rs), n)
        m["A_CH_commits"] = [(r["type"], r["correct"], r["A"]["CH"]["choice"], r["A"]["CH"]["confidence"], r["A"]["CH"]["probabilities"]["none_of_these"]) for r in rs if r["A"]["CH"]["choice"] != "none_of_these"]
        m["A_G_abstain"] = fmt_rate(sum(r["A"]["G"] <= .5 for r in rs), n)
        m["A_PC_abstain"] = fmt_rate(sum(max(r["A"]["PC"].values()) <= .5 for r in rs), n)
        m["A_CH+G_abstain"] = fmt_rate(sum(r["A"]["CH"]["choice"] == "none_of_these" or r["A"]["G"] <= .5 for r in rs), n)
        return m
    rep = {"S-long": M([r for r in rows if r["kind"] == "S-long"])}
    for t in ("name", "addr", "money"): rep[f"S-part-{t}"] = M([r for r in rows if r["type"] == t])
    rep["S-long"]["mean_input_tokens"] = sum(r["tokens"]["input_tokens"] for r in rows if r["kind"] == "S-long") / 36
    await j.aclose(); save("p05c_abstention_stress", {"report": rep, "rows": rows}); print(json.dumps(rep, indent=1)); print("requests", j.count)
if __name__ == "__main__":
    asyncio.run(main())
