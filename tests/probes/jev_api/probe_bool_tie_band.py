"""Phase 0r: re-measures [P12] (contract half: exact-0.50 incidence, flips across 10 identical calls, tie bands up to
the 0.10 margin) on the OpenAI Decisions API (`gpt-6-luna`) through jevclient's `decisions` backend; unchanged
otherwise. Summary: tests/probes/results/0r/probe_bool_tie_band.json.

Round 2. Claim (DESIGN §4.2, §6.2 Rev 4): bool fields decide true iff p > 0.5, and an exact p = 0.50 yields
Unresolved(tie). Question: how often does an exact 0.50 occur on realistic yes/no extraction questions, how many
land in [0.45, 0.55], how often does the decision flip across byte-identical repeats, and is a wider tie band
better?
Method (SYNTHETIC PILOT, author-written clause pools): 40 short commercial contracts, each built from 5 of 6
clause topics (auto-renewal, termination for convenience, liability cap, governing law, exclusivity,
confidentiality survival); each topic's clause is drawn as clearly-yes, clearly-no/absent, or genuinely
ambiguous (hedged wording such as "may be extended by mutual agreement"). 200 yes/no nouls, 5 per contract, one
request per contract. The full set is sent 10 times (byte-identical requests, 10 passes) = 400 requests, so every
question has 10 observations. Gold labels are NOT the point; the metrics are distributional:
exact-0.50 incidence, [0.45,0.55] incidence, per-question decision flips, and outcome consistency under tie bands
b in {0 (exact), 0.01, 0.02, 0.05, 0.10}: Unresolved(tie) iff |p - 0.5| <= b."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, random, sys
from jevclient import Jev, save, save_summary, fmt_rate

R = random.Random(777)
Q = {
 "renew": "Does the contract include an automatic renewal clause?",
 "tconv": "Can the customer terminate the contract for convenience, without cause?",
 "cap": "Does the contract cap either party's liability?",
 "law": "Does the contract specify which jurisdiction's law governs it?",
 "excl": "Is the customer required to buy these services exclusively from this supplier?",
 "conf": "Does the confidentiality obligation continue after the contract ends?",
}
POOL = {
 "renew": {"yes": ["This Agreement shall automatically renew for successive one-year terms unless either party gives sixty (60) days' written notice of non-renewal.",
                   "Upon expiry of the Initial Term, the term renews automatically for additional twelve-month periods."],
           "no": ["This Agreement expires at the end of the Initial Term and will not be renewed.",
                  "The term of this Agreement is twenty-four months from the Effective Date."],
           "amb": ["The parties may extend this Agreement by mutual written agreement.",
                   "If the Customer continues to use the Services after expiry, the Agreement will continue on a month-to-month basis.",
                   "Renewal terms will be discussed in good faith ninety days before expiry.",
                   "Unless terminated, the Supplier will continue to provide the Services under its then-current price list."]},
 "tconv": {"yes": ["Customer may terminate this Agreement at any time, for any reason, on thirty (30) days' written notice.",
                   "Either party may terminate this Agreement without cause on sixty days' notice."],
           "no": ["Either party may terminate this Agreement only for a material breach that remains uncured for thirty days.",
                  "This Agreement may not be terminated before the end of the Initial Term except for cause."],
           "amb": ["Customer may terminate if the Services no longer meet its business needs, subject to paying an early-termination fee equal to three months' fees.",
                   "Termination other than for cause requires the Supplier's consent, which shall not be unreasonably withheld.",
                   "The parties may end this arrangement by agreement.",
                   "Customer may terminate if a change of control of the Supplier occurs."]},
 "cap": {"yes": ["In no event shall either party's aggregate liability under this Agreement exceed $500,000.",
                 "Each party's total liability is limited to the fees paid in the twelve months preceding the claim."],
         "no": ["Nothing in this Agreement limits or excludes either party's liability.",
                "The Supplier is responsible for all losses arising from its performance of the Services."],
         "amb": ["The Supplier shall not be liable for indirect, incidental or consequential damages.",
                 "Liability shall be limited to the extent permitted by applicable law.",
                 "The parties will agree a liability cap in a separate schedule.",
                 "The Supplier's liability for data loss is limited to restoring the last available backup."]},
 "law": {"yes": ["This Agreement is governed by the laws of the State of New York.",
                 "The laws of the Province of Ontario and the federal laws of Canada applicable therein govern this Agreement."],
         "no": ["The parties have not selected a governing law for this Agreement.",
                "Notices under this Agreement must be in writing and delivered by courier."],
         "amb": ["Any dispute shall be resolved by arbitration seated in London.",
                 "This Agreement shall be interpreted in accordance with applicable law.",
                 "The courts of Ontario have exclusive jurisdiction over any dispute.",
                 "This Agreement is governed by the law of the Supplier's principal place of business."]},
 "excl": {"yes": ["During the Term, Customer shall purchase all of its requirements for the Services exclusively from Supplier.",
                  "Customer shall not engage any other provider for services of the kind described in Schedule A."],
          "no": ["Nothing in this Agreement prevents Customer from obtaining similar services from third parties.",
                 "This Agreement is non-exclusive."],
          "amb": ["Customer intends to use Supplier as its preferred provider.",
                  "Customer shall give Supplier a right of first refusal on any additional work of the same kind.",
                  "Customer will purchase at least eighty percent of its requirements for the Services from Supplier.",
                  "Supplier is Customer's primary vendor for the Services."]},
 "conf": {"yes": ["The obligations in the Confidentiality section survive termination of this Agreement for five years.",
                  "Each party's duty of confidentiality continues indefinitely after this Agreement ends."],
          "no": ["The confidentiality obligations in this Agreement end when this Agreement terminates.",
                 "Each party shall keep the other's confidential information secret during the Term."],
          "amb": ["On termination, each party shall return or destroy the other party's confidential information.",
                  "Confidentiality shall be maintained for a reasonable period.",
                  "Sections 4, 7 and 9 survive termination.",
                  "The Supplier shall not use the Customer's data for any purpose other than performing the Services."]},
}
FILLER = ["Fees are invoiced monthly in arrears and payable within thirty days.",
          "The Supplier shall perform the Services with reasonable skill and care.",
          "Each party shall comply with applicable anti-bribery laws.",
          "Neither party may assign this Agreement without the other's prior written consent.",
          "Service levels are set out in Schedule B."]


def build():
    docs = []
    for d in range(40):
        topics = R.sample(list(Q), 5)
        clauses, meta = [], []
        for t in topics:
            lvl = R.choices(["yes", "no", "amb"], weights=[.35, .35, .30])[0]
            clauses.append(R.choice(POOL[t][lvl])); meta.append((t, lvl))
        body = clauses + R.sample(FILLER, 3); R.shuffle(body)
        a, b = R.sample(["Acme Corp", "Globex Ltd", "Initech LLC", "Hooli Inc", "Stark Parts", "Tyrell Systems"], 2)
        text = (f"MASTER SERVICES AGREEMENT between {a} (\"Supplier\") and {b} (\"Customer\").\n" +
                "\n".join(f"{i+1}. {c}" for i, c in enumerate(body)))
        docs.append({"text": text, "meta": meta, "qs": {t: {"type": "noul", "instructions": Q[t]} for t, _ in meta}})
    return docs


async def main(passes):
    docs = build()
    j = Jev(concurrency=8)
    obs = [[] for _ in docs]
    for p in range(passes):
        res = await asyncio.gather(*[j.ask(d["text"], d["qs"]) for d in docs])
        for i, r in enumerate(res):
            assert r["status"] == 200, r
            obs[i].append({t: r["body"]["answers"][t]["noul"] for t in docs[i]["qs"]})
        print("pass", p, "requests", j.count, flush=True)
    await j.aclose()
    rows = []
    for d, o in zip(docs, obs):
        for t, lvl in d["meta"]:
            rows.append({"topic": t, "level": lvl, "ps": [x[t] for x in o]})
    save("r2_tie_rule", {"docs": docs, "rows": rows})
    save_summary("probe_bool_tie_band", j, analyse(rows), n={"questions": len(rows), "repeats": passes})


def analyse(rows):
    N = len(rows); allp = [p for r in rows for p in r["ps"]]
    out = {"questions": N, "observations": len(allp)}
    out["obs_exact_0.50"] = fmt_rate(sum(p == 0.5 for p in allp), len(allp))
    out["q_with_any_exact_0.50"] = fmt_rate(sum(any(p == 0.5 for p in r["ps"]) for r in rows), N)
    out["first_pass_exact_0.50"] = fmt_rate(sum(r["ps"][0] == 0.5 for r in rows), N)
    out["first_pass_in_[0.45,0.55]"] = fmt_rate(sum(.45 <= r["ps"][0] <= .55 for r in rows), N)
    out["obs_in_[0.45,0.55]"] = fmt_rate(sum(.45 <= p <= .55 for p in allp), len(allp))
    out["q_mean_in_[0.40,0.60]"] = sum(.4 <= sum(r["ps"]) / len(r["ps"]) <= .6 for r in rows)
    out["q_decision_flip(p>0.5 differs across repeats)"] = fmt_rate(sum(len({p > .5 for p in r["ps"]}) > 1 for r in rows), N)
    out["q_range_max"] = max(max(r["ps"]) - min(r["ps"]) for r in rows)
    rng = sorted(max(r["ps"]) - min(r["ps"]) for r in rows)
    out["q_range_p50_p90_p99"] = (rng[N // 2], rng[int(N * .9)], rng[min(N - 1, int(N * .99))])
    import statistics
    out["q_sd_mean_max"] = (round(statistics.mean(statistics.pstdev(r["ps"]) for r in rows), 4), round(max(statistics.pstdev(r["ps"]) for r in rows), 4))
    bands = {}
    for b in (0.0, 0.01, 0.02, 0.05, 0.10):
        def oc(p): return "tie" if abs(p - 0.5) <= b + 1e-9 else (p > .5)
        incons = sum(len({oc(p) for p in r["ps"]}) > 1 for r in rows)
        tie_any = sum(any(oc(p) == "tie" for p in r["ps"]) for r in rows)
        tf_flip = sum({True, False} <= {oc(p) for p in r["ps"]} for r in rows)
        tie_obs = sum(oc(p) == "tie" for p in allp)
        bands[f"b={b}"] = {"q_outcome_inconsistent_across_10": fmt_rate(incons, N), "q_true_false_flip": fmt_rate(tf_flip, N),
                           "q_ever_tie": tie_any, "obs_tie_rate": fmt_rate(tie_obs, len(allp))}
    out["bands"] = bands
    # by clause level
    out["by_level"] = {lvl: {"n": sum(r["level"] == lvl for r in rows),
                             "flip": sum(len({p > .5 for p in r["ps"]}) > 1 for r in rows if r["level"] == lvl),
                             "mean_in_[.3,.7]": sum(.3 <= sum(r["ps"]) / 10 <= .7 for r in rows if r["level"] == lvl)} for lvl in ("yes", "no", "amb")}
    out["flippers"] = [(r["topic"], r["level"], r["ps"]) for r in rows if len({p > .5 for p in r["ps"]}) > 1 or 0.5 in r["ps"]]
    hist = {}
    for p in allp:
        k = round(int(p * 10) / 10, 1); hist[k] = hist.get(k, 0) + 1
    out["hist_obs_by_0.1"] = dict(sorted(hist.items()))
    print(json.dumps(out, indent=1))
    save("r2_tie_rule_analysis", out)
    return out


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "analyse":
        from jevclient import RAW
        analyse(json.loads((RAW / "r2_tie_rule.json").read_text())["rows"])
    else:
        asyncio.run(main(10))
