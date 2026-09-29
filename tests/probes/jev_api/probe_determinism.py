"""Claim (DESIGN §2, PLAN §3 'Determinism', DESIGN §5.4 'retry useless against identical input'):
Jev is deterministic -- same input produces the same answer; vendor sigma=0.01 over 15 repeats.
Also DESIGN §12 / PLAN Phase 3: does co-batching (adding unrelated questions) or splitting a
level change an existing question's answer? Does map key name / order change answers?

Method:
 A. 20 byte-identical requests (sequential) for a borderline noul, choice, score (3 questions
    in one request), and 20 identical requests with each question alone. Measure per-value
    max abs deviation and whether the argmax (choice/score level, noul>0.5) ever flips.
    The whole block is repeated in phase 'B' when invoked with arg 'later' (minutes later).
 C. Key-name test: same question under 5 different keys (alone), 3 repeats each.
 D. Order test: same 3 questions in 6 permutations of map order, 2 repeats each.
 E. Co-batching test: target questions alone vs with 1, 10, 50 unrelated questions added,
    3 repeats each; compare target distributions against the alone-run spread.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, itertools, json, sys, statistics as st
from jevclient import Jev, save

STATE = ("Hi, I ordered the blue jacket two weeks ago (order 5531). It arrived but the zipper "
         "feels a bit stiff. Not sure if that's normal or if I should send it back? Also the "
         "tracking said delivered a day before it actually came. Thanks.")
TARGETS = {
 "n_refund": {"type": "noul", "instructions": "Is the customer asking for a refund?"},
 "c_intent": {"type": "choice", "instructions": "What does the customer primarily want?",
              "criteria": {"return": "Send the item back", "exchange": "Get a replacement",
                           "info": "Information or advice", "complaint": "Register a complaint about service"}},
 "s_frust": {"type": "score", "instructions": "How frustrated is the customer?",
             "criteria": ["Not at all", "Slightly", "Moderately", "Very", "Extremely"]},
}
FILLER = [f"Does the message mention the word '{w}'?" for w in
          ["blue","zipper","order","tracking","jacket","red","shoes","refund","delivered","thanks",
           "stiff","week","normal","send","back","day","came","hat","coat","box","price","store",
           "manager","email","phone","size","color","late","early","broken","gift","card","bank",
           "sale","coupon","warranty","repair","label","courier","parcel","door","sorry","help",
           "urgent","please","account","login","password","address","city"]]

def summarize(answers_list, key):
    t = answers_list[0][key]["type"]
    if t == "noul":
        vals = [a[key]["noul"] for a in answers_list]
        return {"type": t, "values": sorted(set(vals)), "max_abs_dev": max(vals)-min(vals),
                "sd": st.pstdev(vals), "argmax_set": sorted({v > 0.5 for v in vals})}
    probs = [a[key]["probabilities"] for a in answers_list]
    ks = probs[0].keys()
    dev = max(max(p[k] for p in probs) - min(p[k] for p in probs) for k in ks)
    conf = [a[key]["confidence"] for a in answers_list]
    sel = [a[key]["choice"] if t == "choice" else max(a[key]["probabilities"], key=a[key]["probabilities"].get) for a in answers_list]
    extra = {}
    if t == "score":
        sc = [a[key]["score"] for a in answers_list]; extra = {"score_range": [min(sc), max(sc)]}
    return {"type": t, "max_abs_dev_prob": round(dev, 4), "conf_range": [min(conf), max(conf)],
            "selected_set": sorted(set(sel)), "n_distinct_distributions": len({json.dumps(p, sort_keys=True) for p in probs}), **extra}

async def rep(j, state, qs, n):
    out = []
    for _ in range(n):  # sequential on purpose
        r = await j.ask(state, qs); out.append(r)
    return out

async def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "now"
    j = Jev(concurrency=4)
    res = {"tag": tag}
    joint = await rep(j, STATE, TARGETS, 20)
    res["joint_raw"] = joint
    ans = [r["body"]["answers"] for r in joint if r["status"] == 200]
    res["joint_summary"] = {k: summarize(ans, k) for k in TARGETS}
    for k in TARGETS:
        alone = await rep(j, STATE, {k: TARGETS[k]}, 20)
        res[f"alone_{k}_raw"] = alone
        res[f"alone_{k}_summary"] = summarize([r["body"]["answers"] for r in alone], k)
    if tag == "now":
        # C key names
        kn = {}
        for key in ["a", "q_refund", "zzz_totally_unrelated_key", "is_customer_angry", "items[3]"]:
            rs = await rep(j, STATE, {key: TARGETS["n_refund"]}, 3)
            kn[key] = [r["body"]["answers"][key]["noul"] if r["status"] == 200 else r for r in rs]
        # key-name semantic leak test on choice
        for key in ["c_intent", "wants_exchange", "definitely_a_complaint"]:
            rs = await rep(j, STATE, {key: TARGETS["c_intent"]}, 3)
            kn["choice:"+key] = [r["body"]["answers"][key]["probabilities"] for r in rs]
        res["keyname"] = kn
        # D order
        order = {}
        for perm in itertools.permutations(list(TARGETS)):
            rs = await rep(j, STATE, {k: TARGETS[k] for k in perm}, 2)
            order["|".join(perm)] = [r["body"]["answers"] for r in rs]
        res["order"] = order
        # E co-batching
        cob = {}
        for nf in [0, 1, 10, 50]:
            qs = dict(TARGETS)
            for i in range(nf):
                qs[f"f{i}"] = {"type": "noul", "instructions": FILLER[i]}
            rs = await rep(j, STATE, qs, 3)
            cob[nf] = [{k: r["body"]["answers"][k] for k in TARGETS} for r in rs]
        res["cobatch"] = cob
    await j.aclose()
    save(f"p01_determinism_{tag}", res)
    print(json.dumps({k: v for k, v in res.items() if "summary" in k}, indent=1))
    print("requests:", j.count)
asyncio.run(main())
