"""Phase 0r: re-measures [P1] (40 ambiguous questions x 25 identical repeats, two sessions) on the OpenAI
Decisions API (`gpt-6-luna`) through jevclient's `decisions` backend. Added for Phase 0r ("whether question names
affect answers", DESIGN §2): with tag 'now', the same 40 questions are also sent under four name sets (the
original n00/c00 keys; opaque random ids; leading names `yes_<key>`; leading names `no_<key>`), 3 identical
repeats each, and in reversed question order (3 repeats); per question, the range across name sets / orders is
compared with the range across identical repeats, and decision changes (noul > 0.5, choice argmax) are counted.
Summary: tests/probes/results/0r/probe_determinism_borderline_<tag>.json.

Claim (DESIGN §2 determinism; §5.4 'retry useless'; PLAN Phase 3 exit 'same input resolves to
same output across runs'): identical requests give identical decisions.
Method: 40 deliberately ambiguous questions (30 noul, 10 choice) over one ambiguous state, all in
one request, repeated 25 times byte-identically (sequential). For each question: range of the
probability, sd, and whether the decision (noul>0.5 / choice argmax) ever flips. Focus on those
with mean in [0.35,0.65] (noul) or top-2 gap <0.15 (choice). Invoked again later with arg 'later'."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, sys, statistics as st
from jevclient import Jev, save, save_summary
import random

STATE = ("Email from Priya (account manager) to the ops team, Tuesday: 'Quick one - the Henderson "
         "shipment went out Friday but I think the pallet count on the manifest might be off by one? "
         "Could be my misreading. Henderson hasn't said anything yet. Their contract renews next "
         "month and they've been a bit quiet lately. Not a big deal but maybe someone could double "
         "check when they get a sec. Also, the new label printer is jamming again, third time.'")
NOULS = ["Is this email urgent?", "Is the sender worried?", "Is there a customer complaint?",
 "Is the Henderson account at risk?", "Does the sender request an action?", "Is the manifest wrong?",
 "Is this email about equipment?", "Is the tone informal?", "Is the sender blaming someone?",
 "Should this be escalated to a manager?", "Is the renewal mentioned as a concern?",
 "Is the printer problem the main topic?", "Is this a routine message?", "Does the email contain a deadline?",
 "Is the sender uncertain?", "Is this about logistics?", "Is Henderson unhappy?",
 "Does the email mention a financial loss?", "Should the ops team reply today?", "Is the sender frustrated?",
 "Is there more than one request in the email?", "Is the pallet count issue confirmed?",
 "Is this email sarcastic?", "Would a reasonable reader consider this high priority?",
 "Is the email about a single topic?", "Is the sender apologizing?", "Is the printer issue recurring?",
 "Does the sender expect a written response?", "Is this a sales-related email?", "Is the sender a manager?"]
CHOICES = [
 ("What is the main topic?", ["shipment", "printer", "contract renewal", "staffing"]),
 ("What priority should this get?", ["low", "medium", "high"]),
 ("Who should handle this first?", ["warehouse", "account management", "IT", "finance"]),
 ("What is the sender's mood?", ["calm", "mildly concerned", "anxious", "annoyed"]),
 ("What kind of message is this?", ["request", "report", "complaint", "FYI"]),
 ("Which issue is more important?", ["pallet count", "label printer"]),
 ("How confident is the sender about the error?", ["sure", "unsure", "not stated"]),
 ("What is the risk level for the Henderson account?", ["none", "low", "moderate", "high"]),
 ("What should happen next?", ["recount pallets", "call Henderson", "fix printer", "nothing"]),
 ("Which team does the email go to?", ["ops", "sales", "IT", "unclear"]),
]
Q = {f"n{i:02d}": {"type": "noul", "instructions": s} for i, s in enumerate(NOULS)}
for i, (ins, opts) in enumerate(CHOICES):
    Q[f"c{i:02d}"] = {"type": "choice", "instructions": ins, "criteria": {o: None for o in opts}}

async def main():
    tag = sys.argv[1] if len(sys.argv) > 1 else "now"
    j = Jev(); runs = []
    for _ in range(25):
        runs.append(await j.ask(STATE, Q))
    A = [r["body"]["answers"] for r in runs if r["status"] == 200]
    summ = {}
    for k in Q:
        if k.startswith("n"):
            v = [a[k]["noul"] for a in A]
            summ[k] = {"mean": round(st.mean(v), 3), "range": round(max(v)-min(v), 3), "sd": round(st.pstdev(v), 4),
                       "flip": len({x > 0.5 for x in v}) > 1, "vals": sorted(set(v))}
        else:
            ps = [a[k]["probabilities"] for a in A]
            sel = [a[k]["choice"] for a in A]
            m = {o: st.mean(p[o] for p in ps) for o in ps[0]}
            top = sorted(m.values(), reverse=True)
            summ[k] = {"mean": {o: round(x, 3) for o, x in m.items()}, "gap": round(top[0]-top[1], 3),
                       "range": round(max(max(p[o] for p in ps)-min(p[o] for p in ps) for o in ps[0]), 3),
                       "flip": len(set(sel)) > 1, "selections": {s: sel.count(s) for s in set(sel)}}
    out = {"tag": tag, "n_runs": len(A), "summary": summ, "models": sorted({r.get("model") for r in runs}), "raw": runs}
    names = {}
    if tag == "now":
        rnd = random.Random(31)
        sets = {"orig": {k: k for k in Q}, "opaque": {k: "".join(rnd.choice("0123456789abcdef") for _ in range(10)) for k in Q},
                "yes_lead": {k: f"yes_{k}" for k in Q}, "no_lead": {k: f"no_{k}" for k in Q}}
        obs = {}
        for sname, ren in sets.items():
            for _ in range(3):
                r = await j.ask(STATE, {ren[k]: Q[k] for k in Q})
                assert r["status"] == 200, r
                obs.setdefault(sname, []).append({k: r["body"]["answers"][ren[k]] for k in Q})
        for _ in range(3):
            r = await j.ask(STATE, {k: Q[k] for k in reversed(list(Q))})
            assert r["status"] == 200, r
            obs.setdefault("reversed_order", []).append(r["body"]["answers"])
        def vec(a): return [a["noul"]] if a["type"] == "noul" else [a["probabilities"][o] for o in sorted(a["probabilities"])]
        def sel(a): return a["noul"] > .5 if a["type"] == "noul" else a["choice"]
        def rng(ans): vs = [vec(a) for a in ans]; return round(max(max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(len(vs[0]))), 4)
        per_q = {}
        for k in Q:
            rep_ans = [a[k] for a in A]
            alt = {sn: [o[k] for o in obs[sn]] for sn in obs}
            per_q[k] = {"range_identical_repeats": rng(rep_ans), "range_across_names": rng([x for sn in sets for x in alt[sn]]),
                        "range_incl_reversed_order": rng(rep_ans + [x for xs in alt.values() for x in xs]),
                        "decision_changes_across_names_or_order": len({sel(x) for xs in alt.values() for x in xs} | {sel(x) for x in rep_ans}) > 1}
        names = {"per_question": per_q,
                 "max_range_identical_repeats": max(v["range_identical_repeats"] for v in per_q.values()),
                 "max_range_across_names": max(v["range_across_names"] for v in per_q.values()),
                 "max_range_incl_reversed_order": max(v["range_incl_reversed_order"] for v in per_q.values()),
                 "questions_whose_range_across_names_exceeds_repeat_range": sum(v["range_across_names"] > v["range_identical_repeats"] + 1e-9 for v in per_q.values()),
                 "questions_with_decision_change_across_names_or_order": sum(v["decision_changes_across_names_or_order"] for v in per_q.values()),
                 "repeats_per_variant": 3, "variants": list(sets) + ["reversed_order"]}
        out["names"] = {"obs": obs, **names}
    save(f"p01b_borderline_{tag}", out)
    rngs = [s["range"] for s in summ.values()]
    print("max range", max(rngs), "mean range", round(st.mean(rngs), 4), "flips", [k for k, s in summ.items() if s["flip"]])
    for k, s in summ.items(): print(k, {x: s[x] for x in s if x not in ("vals",)})
    print("requests", j.count)
    await j.aclose()
    nouls = [v for k, v in summ.items() if k.startswith("n")]; chs = [v for k, v in summ.items() if k.startswith("c")]
    exact = sum(a[k]["noul"] == 0.5 for a in A for k in Q if k.startswith("n"))
    measured = {"n_runs": len(A), "questions": len(Q), "max_range": max(rngs), "mean_range": round(st.mean(rngs), 4),
                "noul_sd_mean": round(st.mean(v["sd"] for v in nouls), 4), "noul_sd_max": max(v["sd"] for v in nouls),
                "noul_range_max": max(v["range"] for v in nouls), "choice_range_max": max(v["range"] for v in chs),
                "questions_flipping": sorted(k for k, s_ in summ.items() if s_["flip"]),
                "noul_obs_exact_0.50": f"{exact}/{len(A) * len(nouls)}",
                "noul_means_in_[0.35,0.65]": sum(.35 <= v["mean"] <= .65 for v in nouls),
                "summary": {k: {x: v[x] for x in v if x != "vals"} for k, v in summ.items()}}
    if names:
        measured["question_names_and_order"] = {k: v for k, v in names.items() if k != "per_question"}
    save_summary(f"probe_determinism_borderline_{tag}", j, measured, n={"repeats": 25, "name_and_order_variants": 3 if names else 0})
if __name__ == "__main__":
    asyncio.run(main())
