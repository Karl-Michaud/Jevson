"""Round 2. Claim (DESIGN §4.2 Rev 4): for a score, the value is the MOST PROBABLE LEVEL (argmax of
`probabilities`), not the vendor's probability-weighted float `score` and not round(score); rounding "can pick a
zero-probability level" [L4 was a local arithmetic check, never observed live].
Method (SYNTHETIC PILOT): 12 short texts (reviews, tickets, bug reports, candidate notes), several written to be
mixed/polarised (e.g. "food superb, service appalling"), x 5 score questions each with 3, 4, 5, 7 or 10 levels
= 60 score questions, one request per text; the whole set is sent twice to see decode stability under jitter.
Recorded per question: float score, round(score), argmax level (ties noted), median level (first level whose
cumulative probability >= 0.5), the `legend` field, and whether the distribution is bimodal (two levels each >= 0.15
separated by a level with lower probability than both). Reports how often decodes disagree, whether round(score) or
argmax lands on a level with p < 0.10, and what `legend` contains."""
import asyncio, json, math
from jevclient import Jev, save, fmt_rate

TEXTS = [
 "Review: The food was superb, easily the best risotto I've had in years. The service, however, was appalling: we waited 50 minutes, the waiter was rude, and our bill was wrong.",
 "Review: Perfectly fine hotel. Room was clean, bed was okay, breakfast was average. Nothing to complain about, nothing to rave about.",
 "Support ticket: URGENT!!! Your update wiped all our invoices and our accountant is threatening to quit. Fix this today or we cancel. Also, thanks for the quick reply last week.",
 "Support ticket: Hi, small thing - the export button label says 'Exprot'. No rush at all. Love the product otherwise!",
 "Bug report: The app crashes on launch for about half of our Android users (Android 12 only). iOS and Android 13+ are fine. We have a workaround: users can install the web version.",
 "Bug report: Tooltip on the settings page overlaps the save button by two pixels on 4K monitors.",
 "Candidate note: Ten years of backend Python, led a team of eight, built payment systems at scale. No frontend experience at all, and the role is 60% React.",
 "Candidate note: Recent bootcamp graduate, strong portfolio of three React apps, eager, communicates well; no professional experience yet.",
 "Review: I either love this vacuum or hate it depending on the day. On carpets it's incredible. On hardwood it scatters debris everywhere and the battery died after two weeks.",
 "Email: We are reviewing our options for next year. Your pricing is higher than two competitors, but our team likes the support. We'll decide in Q1.",
 "Review: Absolutely terrible. Broke on day one, customer service hung up on me twice. Never again.",
 "Essay feedback: The argument is original and well-structured, but the essay ignores the word limit by 40%, has no citations, and the conclusion contradicts the thesis.",
]
QS = [
 ("How satisfied is the writer overall?", ["Very dissatisfied", "Dissatisfied", "Neutral", "Satisfied", "Very satisfied"]),
 ("How urgent is a response?", ["Not urgent", "Somewhat urgent", "Urgent", "Critical"]),
 ("How positive is the tone?", ["Hostile", "Negative", "Neutral", "Positive", "Enthusiastic", "Glowing", "Ecstatic"]),
 ("How likely is this person to keep doing business with or recommend the product, on a 0-10 scale?", [str(i) for i in range(10)]),
 ("How severe is the problem described?", ["No problem", "Minor", "Major"]),
]


def decode(ans):
    P = {int(k): v for k, v in ans["probabilities"].items()}
    L = sorted(P)
    mx = max(P.values()); arg = [l for l in L if P[l] == mx]
    cum = 0; med = None
    for l in L:
        cum += P[l]
        if cum >= 0.5 - 1e-9: med = l; break
    ws = sum(l * P[l] for l in L)
    peaks = [l for l in L if P[l] >= .15]
    bimodal = any(P[a] >= .15 and P[b] >= .15 and any(P[m] < min(P[a], P[b]) for m in range(a + 1, b)) for a in L for b in L if b > a + 1)
    return {"score": ans["score"], "round": int(math.floor(ans["score"] + 0.5)), "argmax": arg, "median": med, "ws": round(ws, 3),
            "P": P, "bimodal": bimodal, "legend": ans.get("legend"), "confidence": ans.get("confidence")}


async def main():
    j = Jev(concurrency=8)
    runs = []
    for rep in range(2):
        res = await asyncio.gather(*[j.ask(t, {f"s{i}": {"type": "score", "instructions": q, "criteria": lv} for i, (q, lv) in enumerate(QS)}) for t in TEXTS])
        rows = []
        for ti, r in enumerate(res):
            assert r["status"] == 200, r
            for i, (q, lv) in enumerate(QS):
                d = decode(r["body"]["answers"][f"s{i}"]); d.update({"text": ti, "q": i, "levels": len(lv)})
                d["legend_matches_levels"] = d["legend"] == {str(k): v for k, v in enumerate(lv)}
                rows.append(d)
        runs.append(rows)
    await j.aclose()
    A = runs[0]; n = len(A)
    out = {"n": n}
    out["score_equals_weighted_sum(±0.011)"] = fmt_rate(sum(abs(r["score"] - r["ws"]) <= 0.011 for r in A), n)
    out["score_is_integer"] = fmt_rate(sum(float(r["score"]).is_integer() for r in A), n)
    out["argmax_tie"] = sum(len(r["argmax"]) > 1 for r in A)
    out["round_ne_argmax"] = fmt_rate(sum(r["round"] not in r["argmax"] for r in A), n)
    out["median_ne_argmax"] = fmt_rate(sum(r["median"] not in r["argmax"] for r in A), n)
    out["round_ne_median"] = fmt_rate(sum(r["round"] != r["median"] for r in A), n)
    out["round_level_p<0.10"] = fmt_rate(sum(r["P"][r["round"]] < .10 for r in A), n)
    out["round_level_p==0"] = sum(r["P"][r["round"]] == 0 for r in A)
    out["argmax_p_max<0.5"] = fmt_rate(sum(max(r["P"].values()) < .5 for r in A), n)
    out["bimodal"] = fmt_rate(sum(r["bimodal"] for r in A), n)
    out["bimodal_detail"] = [(r["text"], r["q"], r["P"], r["score"], r["argmax"], r["median"]) for r in A if r["bimodal"]]
    out["legend_present"] = sum(r["legend"] is not None for r in A)
    out["legend_equals_level_texts"] = sum(r["legend_matches_levels"] for r in A)
    out["legend_example"] = A[3]["legend"]
    out["by_levels"] = {L: {"n": sum(r["levels"] == L for r in A), "round_ne_argmax": sum(r["round"] not in r["argmax"] for r in A if r["levels"] == L)} for L in (3, 4, 5, 7, 10)}
    out["disagreements"] = [(r["text"], r["q"], r["levels"], r["score"], r["round"], r["argmax"], r["median"], r["P"]) for r in A if r["round"] not in r["argmax"] or r["median"] not in r["argmax"]]
    B = runs[1]
    out["run2_argmax_changed"] = sum(a["argmax"] != b["argmax"] for a, b in zip(A, B))
    out["run2_round_changed"] = sum(a["round"] != b["round"] for a, b in zip(A, B))
    out["run2_median_changed"] = sum(a["median"] != b["median"] for a, b in zip(A, B))
    out["run2_score_absdiff_max"] = max(abs(a["score"] - b["score"]) for a, b in zip(A, B))
    save("r2_score_decode", {"report": out, "runs": runs})
    print(json.dumps(out, indent=1, default=str)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
