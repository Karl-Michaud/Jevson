"""Round 3, probe 4. Choice tie band (DESIGN §4.2, §6.2, Revision 5).

Claim (DESIGN §4.2 / §6.2): for string/int enums mapped to `choice`, "top-two within 0.05 -> Unresolved(tie)", adopted
"for the same reason" as the bool band, which P12 measured only on yes/no nouls (a +/-0.05 band removed every
true<->false flip across 10 identical calls on 200 questions, at ~1% of answers).
Questions: on realistic 3-6-option enum classifications, (a) how often is the top-two margin <= 0.05; (b) how often
does the argmax flip across 10 byte-identical repeats; (c) does the +/-0.05 top-two band remove those flips (no two
repeats DECIDING different options); (d) what fraction of answers does the band convert to Unresolved(tie)?

Method (SYNTHETIC PILOT, author-written snippet pools, composed at random; deliberately includes mixed/hedged texts):
 - 60 texts: 20 support tickets, 20 contract excerpts, 20 product reviews. Each has 3 enum questions:
   tickets: category (6), sentiment (5-level scale as choice), priority (4);
   contracts: contract type (6), payment terms (5), governing-law region (4);
   reviews: sentiment (5), main aspect (5), would recommend (3).
   = 180 questions. Options are opaque ids o0..oN with the label text as description (DESIGN §5.1).
 - One request per text with its 3 questions; the full set is sent 10 times byte-identically = 600 requests.
Margins are computed in integer hundredths (DESIGN §2.1): tie iff top1 - top2 <= 5 hundredths.
"""
import asyncio, json, random, sys
from collections import Counter
from jevclient import Jev, save, fmt_rate

R = random.Random(8080)
Q = {
 "ticket": {
  "category": ("Which category does this support ticket belong to?", ["billing or payment", "technical problem with the product", "account access or login", "shipping or delivery", "feature request", "cancellation"]),
  "sentiment": ("What is the customer's overall sentiment in this ticket?", ["very negative", "negative", "neutral", "positive", "very positive"]),
  "priority": ("What priority should this ticket get?", ["low", "medium", "high", "urgent"]),
 },
 "contract": {
  "ctype": ("What type of contract is this excerpt from?", ["non-disclosure agreement", "master services agreement", "statement of work", "commercial lease", "employment agreement", "software licence agreement"]),
  "payterms": ("What are the payment terms?", ["payment in advance", "net 30 days or less", "net 45 to 90 days", "payment on milestones", "not stated"]),
  "law": ("Which jurisdiction's law governs this contract?", ["a US state", "England and Wales", "an EU member state", "not stated"]),
 },
 "review": {
  "sentiment": ("What is the reviewer's overall sentiment?", ["very negative", "negative", "neutral", "positive", "very positive"]),
  "aspect": ("Which aspect of the purchase does the review focus on most?", ["price or value", "product quality", "delivery", "customer service", "ease of use"]),
  "recommend": ("Would the reviewer recommend the product?", ["yes", "no", "unclear"]),
 },
}
TICKET = [
 "I was charged twice for my March subscription and nobody has replied to my last two emails.",
 "The app crashes every time I open the reports tab on my iPad. I've reinstalled it twice.",
 "I can't log in - the password reset email never arrives, and I have a client demo at 2 pm today.",
 "My order #88213 says delivered but there is nothing at my door.",
 "It would be great if the dashboard could export to CSV. Not urgent, just an idea.",
 "Please cancel my account at the end of this billing cycle. Thanks for the service so far.",
 "The invoice shows the old company address; can you update it before we pay?",
 "Sync between the desktop and mobile apps is sometimes a few minutes behind. Not a big deal.",
 "Honestly this is the third outage this month and my team can't work. Fix it or we're leaving.",
 "Love the new update! One small thing: dark mode resets after a restart.",
 "The courier left the parcel with a neighbour, which is fine, but the box was damaged.",
 "I'd like to downgrade to the basic plan, or cancel if that isn't possible.",
 "Two-factor codes arrive late, so I'm locked out about half the time.",
 "Could you tell me whether the annual plan includes the API add-on before I renew?",
 "Your checkout page rejected my card three times, but my bank says the charges went through.",
 "The export works, but the dates come out in the wrong format for our region.",
]
CONTRACT = [
 "The Receiving Party shall hold the Confidential Information in strict confidence for three (3) years.",
 "This Master Services Agreement governs all Statements of Work entered into by the parties.",
 "Deliverables under this Statement of Work: phase 1 discovery report; phase 2 prototype.",
 "Tenant shall pay Base Rent monthly in advance on the first day of each month.",
 "Employee shall be entitled to twenty-five (25) days of paid annual leave.",
 "Licensor grants Licensee a non-exclusive, non-transferable licence to use the Software.",
 "Invoices are payable within thirty (30) days of receipt.",
 "Fees are payable within sixty (60) days of the end of the month in which the invoice is received.",
 "Payment of 40% is due on signature, 40% on acceptance of the prototype, and 20% on go-live.",
 "This Agreement is governed by the laws of the State of Delaware.",
 "This Agreement shall be governed by the laws of England and Wales.",
 "This Agreement is governed by German law, and the courts of Munich have exclusive jurisdiction.",
 "Any dispute shall be settled by arbitration under the ICC Rules, seated in Geneva.",
 "The Supplier will perform the Services with reasonable skill and care.",
 "Either party may disclose Confidential Information if required by law.",
 "The parties will agree the payment schedule in each Statement of Work.",
]
REVIEW = [
 "Arrived a day early and well packed.",
 "The blender is powerful but it is so loud that I only use it when nobody is home.",
 "For the price, you really can't beat it.",
 "Broke after two weeks. Customer service replaced it without any fuss, to be fair.",
 "Setup took five minutes and the instructions were clear.",
 "Overpriced for what it is. The cheaper model does the same thing.",
 "The stitching came loose after the first wash.",
 "Delivery took three weeks and nobody answered my emails about it.",
 "It does the job. Nothing special.",
 "Absolutely love it - I bought a second one for my sister.",
 "The app that controls it is confusing and keeps logging me out.",
 "Good quality, but I'm not sure it was worth double the price of the old one.",
 "Returned it. The colour was nothing like the photos.",
 "My kids use it every day and it still looks new.",
 "Support was friendly, but they couldn't fix the connection problem.",
 "Would buy again if it came in a smaller size.",
]
POOLS = {"ticket": TICKET, "contract": CONTRACT, "review": REVIEW}


def build():
    texts = []
    for dom, pool in POOLS.items():
        seen = set()
        while len([t for t in texts if t["dom"] == dom]) < 20:
            k = R.choice([1, 2, 2, 3])
            idx = tuple(sorted(R.sample(range(len(pool)), k)))
            if idx in seen: continue
            seen.add(idx)
            texts.append({"dom": dom, "text": " ".join(pool[i] for i in idx)})
    return texts


def questions(dom):
    return {k: {"type": "choice", "instructions": ins, "criteria": {f"o{i}": o for i, o in enumerate(opts)}} for k, (ins, opts) in Q[dom].items()}


async def run():
    texts = build(); j = Jev(concurrency=10); passes = []
    for p in range(10):
        res = await asyncio.gather(*[j.ask(t["text"], questions(t["dom"])) for t in texts])
        for r in res: assert r["status"] == 200, r
        passes.append([{k: {"choice": v["choice"], "probabilities": v["probabilities"], "confidence": v.get("confidence")} for k, v in r["body"]["answers"].items()} for r in res])
        print("pass", p, "requests", j.count, flush=True)
    await j.aclose()
    save("r3_choice_tie", {"texts": texts, "passes": passes})


def analyse():
    from jevclient import RAW
    d = json.loads((RAW / "r3_choice_tie.json").read_text()); texts, passes = d["texts"], d["passes"]
    rows = []  # per question: list of 10 (argmax, margin_hundredths, sorted distribution)
    for ti, t in enumerate(texts):
        for qk in Q[t["dom"]]:
            obs = []
            for p in passes:
                pr = {k: round(v * 100) for k, v in p[ti][qk]["probabilities"].items()}
                srt = sorted(pr.items(), key=lambda kv: -kv[1])
                top = [k for k, v in pr.items() if v == srt[0][1]]
                obs.append({"argmax": p[ti][qk]["choice"], "top_set": top, "m": srt[0][1] - srt[1][1], "p1": srt[0][1], "sum": sum(pr.values())})
            rows.append({"dom": t["dom"], "q": qk, "text": t["text"], "obs": obs})
    nq, no = len(rows), len(rows) * 10
    rep = {"questions": nq, "observations": no}
    rep["distribution_sums_not_100"] = Counter(o["sum"] for r in rows for o in r["obs"] if o["sum"] != 100)
    rep["exact_tie_top_two_equal(obs)"] = fmt_rate(sum(o["m"] == 0 for r in rows for o in r["obs"]), no)
    for b in (0, 2, 5, 10):
        obs_in = sum(o["m"] <= b for r in rows for o in r["obs"])
        q_any = sum(any(o["m"] <= b for o in r["obs"]) for r in rows)
        q_first = sum(r["obs"][0]["m"] <= b for r in rows)
        # decided outcomes: argmax if margin > b, else tie
        flips = 0; incons = 0
        for r in rows:
            dec = {o["argmax"] for o in r["obs"] if o["m"] > b}
            outs = {o["argmax"] if o["m"] > b else "TIE" for o in r["obs"]}
            flips += len(dec) > 1; incons += len(outs) > 1
        rep[f"band<={b}"] = {"obs_in_band(converted to Unresolved)": fmt_rate(obs_in, no), "questions_first_pass_in_band": fmt_rate(q_first, nq),
                             "questions_ever_in_band": fmt_rate(q_any, nq), "questions_with_decided_flip": fmt_rate(flips, nq),
                             "questions_outcome_not_identical": fmt_rate(incons, nq)}
    rep["argmax_flip_questions(no band)"] = fmt_rate(sum(len({o["argmax"] for o in r["obs"]}) > 1 for r in rows), nq)
    rep["low_support_p1<50(obs)"] = fmt_rate(sum(o["p1"] < 50 for r in rows for o in r["obs"]), no)
    # jitter of the top-two margin per question
    rng = sorted(max(o["m"] for o in r["obs"]) - min(o["m"] for o in r["obs"]) for r in rows)
    rep["margin_range_per_question(p50,p90,max)"] = (rng[len(rng) // 2], rng[int(len(rng) * .9)], rng[-1])
    rep["by_question_type"] = {}
    for dom in Q:
        for qk in Q[dom]:
            rs = [r for r in rows if r["dom"] == dom and r["q"] == qk]
            rep["by_question_type"][f"{dom}.{qk}"] = {"n": len(rs), "flip(no band)": sum(len({o["argmax"] for o in r["obs"]}) > 1 for r in rs),
                                                     "flip(band5)": sum(len({o["argmax"] for o in r["obs"] if o["m"] > 5}) > 1 for r in rs),
                                                     "obs_in_band5": sum(o["m"] <= 5 for r in rs for o in r["obs"])}
    rep["flipping_questions"] = [{"q": f"{r['dom']}.{r['q']}", "text": r["text"][:140], "argmaxes": dict(Counter(o["argmax"] for o in r["obs"])),
                                  "margins": [o["m"] for o in r["obs"]]} for r in rows if len({o["argmax"] for o in r["obs"]}) > 1]
    rep["flips_surviving_band5"] = [f for f, r in zip(rep["flipping_questions"], [r for r in rows if len({o["argmax"] for o in r["obs"]}) > 1])
                                    if len({o["argmax"] for o in r["obs"] if o["m"] > 5}) > 1]
    save("r3_choice_tie_analysis", rep); print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    if sys.argv[1] == "run": asyncio.run(run())
    else: analyse()
