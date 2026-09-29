"""Claim (DESIGN §5.6, §12; PLAN Phase 0b probe 4, Phase 7): pairwise `noul` "same entity?"
judgements batched in one call support entity resolution; judgements may be non-transitive and
the policy (connected components of p>=0.5; any 'different' pair inside a component ->
Unresolved) avoids silent merges.
Method (synthetic PILOT, not pre-registered): 24 short docs, 3 templates x 8 name sets. Each doc
has 3 people with confusable names (Dana Whitfield / Dan Whitfield / Dana Whitman style) and 8
distinct-surface mentions with gold entity ids resolvable from context (titles, roles,
pronoun-free cues). All 28 pairs per doc asked as keyed nouls in ONE request:
instructions={"mention_a","mention_b","question"}. Metrics: pair accuracy, false-merge and
false-split rates, transitivity violations (triples with two 'same' and one 'different'),
and per-doc outcome under the DESIGN §5.6 policy: correct / Unresolved / silently wrong."""
import asyncio, itertools, json, random
from jevclient import Jev, save, fmt_rate
R = random.Random(11)
SETS = [("Dana","Dan","Whitfield","Whitman"),("Maria","Mario","Castellano","Castell"),("Jean","John","Holloway","Halloway"),
        ("Alexandra","Alexander","Petrov","Petrova"),("Chris","Christine","Morgan","Morgenstern"),("Sam","Samuel","Okafor","Okoro"),
        ("Leah","Leo","Brennan","Brennand"),("Nina","Nino","Rossi","Rosso")]
# title helper: first-name gender for Ms./Mr.
FEM = {"Dana","Maria","Jean","Alexandra","Christine","Leah","Nina"}
def ttl(f): return "Ms." if f in FEM else "Mr."
def doc_t0(F, F2, L, L2):
    # E1 = F L (VP marketing), E2 = F L2 (client), E3 = F2 L (engineer, E1's sibling)
    text = (f"{F} {L}, the VP of Marketing at Acme, met with {F} {L2} from Globex on Monday. "
            f"{ttl(F)} {L} opened by presenting the Q3 campaign, and the marketing VP stressed the launch date. "
            f"The Globex buyer asked about the budget. Later, {F2} {L}, an engineer at Acme and the VP's sibling, joined the call; "
            f"the engineer walked through the integration. The follow-up memo was signed {F[0]}. {L}, VP Marketing, and was addressed to {ttl(F)} {L2}.")
    M = [(f"{F} {L}",1),(f"{ttl(F)} {L}",1),("the marketing VP",1),(f"{F[0]}. {L}, VP Marketing",1),
         (f"{F} {L2}",2),("the Globex buyer",2),(f"{ttl(F)} {L2}",2),(f"{F2} {L}",3)]
    if ttl(F) == ttl(F2): M[1] = (f"{ttl(F)} {L}, the VP", 1); text = text.replace(f"{ttl(F)} {L} opened", f"{ttl(F)} {L}, the VP, opened")
    M.append(("the engineer", 3))
    return text, M
def doc_t1(F, F2, L, L2):
    # E1 = F L (patient), E2 = F2 L (patient's parent), E3 = F L2 (nurse)
    text = (f"Patient {F} {L} was admitted on Tuesday. {F2} {L}, the patient's father, signed the consent form. "
            f"Nurse {F} {L2} took the patient's vitals and noted that {F} was anxious. "
            f"Nurse {L2} later called {ttl(F2)} {L} to confirm the medication list. The chart lists {L}, {F[0]}. as the patient.")
    M = [(f"{F} {L}",1),("the patient",1),(f"{L}, {F[0]}.",1),(f"{F2} {L}",2),("the patient's father",2),(f"{ttl(F2)} {L}",2),
         (f"{F} {L2}",3),(f"Nurse {L2}",3)]
    text = text.replace("father", "parent"); M[4] = ("the patient's parent", 2)
    return text, M
def doc_t2(F, F2, L, L2):
    # E1 = F L (tenant), E2 = F L2 (landlord), E3 = F2 L2 (landlord's agent)
    text = (f"This lease is between {F} {L} (Tenant) and {F} {L2} (Landlord). {F2} {L2} acts as the Landlord's agent. "
            f"The Tenant, {L}, agrees to pay rent monthly. Repairs must be requested in writing to the agent, "
            f"who will forward them to the Landlord. Signed: {F} {L}; {F[0]}. {L2} for the Landlord.")
    M = [(f"{F} {L}",1),("the Tenant",1),(f"{L}",1),(f"{F} {L2}",2),("the Landlord",2),(f"{F[0]}. {L2} for the Landlord",2),
         (f"{F2} {L2}",3),("the agent",3)]
    return text, M
TEMPL = [doc_t0, doc_t1, doc_t2]

async def main():
    j = Jev(concurrency=8); docs = []
    for s in SETS:
        for t in TEMPL: docs.append((t.__name__, *t(*s)))
    reqs = []
    for name, text, M in docs:
        q = {}
        for a, b in itertools.combinations(range(len(M)), 2):
            q[f"p{a}_{b}"] = {"type": "noul", "instructions": {"mention_a": M[a][0], "mention_b": M[b][0],
                              "question": "In the text, do `mention_a` and `mention_b` refer to the same person?"}}
        reqs.append(q)
    res = await asyncio.gather(*[j.ask(d[1], q) for d, q in zip(docs, reqs)])
    tot = ok = fm = fs = same_n = diff_n = 0; viol_docs = 0; viol_triples = 0; triples = 0
    outcomes = {"correct": 0, "unresolved": 0, "silently_wrong": 0}; detail = []
    for (name, text, M), r in zip(docs, res):
        a = r["body"]["answers"]; n = len(M)
        P = {}
        for x, y in itertools.combinations(range(n), 2):
            p = a[f"p{x}_{y}"]["noul"]; P[(x, y)] = P[(y, x)] = p
            g = M[x][1] == M[y][1]; tot += 1; ok += (p >= .5) == g
            if g: same_n += 1; fs += p < .5
            else: diff_n += 1; fm += p >= .5
        v = 0
        for x, y, z in itertools.combinations(range(n), 3):
            s = [P[(x, y)] >= .5, P[(y, z)] >= .5, P[(x, z)] >= .5]; triples += 1
            if sum(s) == 2: v += 1
        viol_triples += v; viol_docs += v > 0
        # policy
        parent = list(range(n))
        def f(i):
            while parent[i] != i: i = parent[i]
            return i
        for x, y in itertools.combinations(range(n), 2):
            if P[(x, y)] >= .5: parent[f(x)] = f(y)
        comps = {}
        for i in range(n): comps.setdefault(f(i), []).append(i)
        conflict = any(P[(x, y)] < .5 for c in comps.values() for x, y in itertools.combinations(c, 2))
        gold = {}
        for i, (_, e) in enumerate(M): gold.setdefault(e, []).append(i)
        pred_part = sorted(sorted(c) for c in comps.values()); gold_part = sorted(sorted(c) for c in gold.values())
        if conflict: o = "unresolved"
        elif pred_part == gold_part: o = "correct"
        else: o = "silently_wrong"
        outcomes[o] += 1
        errs = [(M[x][0], M[y][0], P[(x, y)]) for x, y in itertools.combinations(range(n), 2) if (P[(x, y)] >= .5) != (M[x][1] == M[y][1])]
        detail.append({"template": name, "names": M[0][0], "outcome": o, "violations": v, "pair_errors": errs, "pred_partition": [[M[i][0] for i in c] for c in comps.values()]})
    rep = {"docs": len(docs), "pairs": tot, "pair_accuracy": fmt_rate(ok, tot), "false_merge_rate(diff pairs judged same)": fmt_rate(fm, diff_n),
           "false_split_rate(same pairs judged different)": fmt_rate(fs, same_n), "non_transitive_triples": fmt_rate(viol_triples, triples),
           "docs_with_any_violation": fmt_rate(viol_docs, len(docs)), "policy_outcomes": outcomes,
           "by_template": {t: {o: sum(d["outcome"] == o for d in detail if d["template"] == t) for o in outcomes} for t in ("doc_t0", "doc_t1", "doc_t2")}}
    await j.aclose(); save("p06_entity", {"report": rep, "detail": detail, "docs": docs}); print(json.dumps(rep, indent=1))
    for d in detail[:24]: print(d["template"], d["names"], d["outcome"], d["violations"], d["pair_errors"][:4])
    print("requests", j.count)
asyncio.run(main())
