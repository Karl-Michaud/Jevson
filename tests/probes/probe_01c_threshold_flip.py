"""Claim (DESIGN §2 determinism; §5.4; PLAN Phase 3 'same input resolves to the same output'):
the DECISION (not just the probability) is stable across identical requests.
Method: 40 ambiguous nouls over one ambiguous state in a screening request; the ones with
p in [0.44, 0.56] are then re-asked in 30 byte-identical requests (all near-threshold questions
together). Count questions whose noul>0.5 decision flips at least once, and per-question flip
share. Also prints now-vs-later cross-session mean shift from probe_01b files."""
import asyncio, json, statistics as st
from jevclient import Jev, save, RAW
STATE = ("Review posted by 'mk_22': The hotel was fine I guess. Room was smaller than the photos but clean. "
         "Breakfast ran out of eggs by 9. Staff were polite, not especially warm. Wifi worked most of the time. "
         "Would I stay again? Maybe, if the price is right. 3 stars.")
QS = ["Is the review positive?", "Is the reviewer satisfied?", "Would the reviewer recommend the hotel?", "Is the reviewer disappointed?",
      "Is the room described favorably?", "Is the breakfast criticized?", "Are the staff praised?", "Is the wifi described as reliable?",
      "Is the reviewer likely to return?", "Is the price mentioned as a concern?", "Is the review balanced?", "Is the review lukewarm?",
      "Is the reviewer annoyed?", "Is the hotel good value?", "Does the review mention a problem with cleanliness?", "Is the review detailed?",
      "Is the tone sarcastic?", "Is the hotel described as meeting expectations?", "Did the photos misrepresent the room?", "Is the reviewer a business traveler?",
      "Is this review helpful to other travelers?", "Is the reviewer hard to please?", "Is the overall experience described as good?", "Is the review mostly negative?",
      "Would the hotel management be pleased by this review?", "Is the reviewer indifferent?", "Does the reviewer complain about service?", "Is the review fair?",
      "Is the breakfast described as adequate?", "Is the room size a major complaint?", "Is the stay described as comfortable?", "Is the reviewer hesitant about returning?",
      "Does the review praise anything?", "Is the review emotional?", "Is the review trustworthy?", "Did the reviewer enjoy the stay?",
      "Is the staff described as friendly?", "Is the wifi a complaint?", "Would the reviewer give 4 or more stars?", "Is the review short?"]
async def main():
    j = Jev(concurrency=1)
    Q = {f"q{i:02d}": {"type": "noul", "instructions": s} for i, s in enumerate(QS)}
    scr = await j.ask(STATE, Q); a = scr["body"]["answers"]
    near = {k: Q[k] for k in Q if 0.44 <= a[k]["noul"] <= 0.56}
    print("screen near-threshold:", {k: a[k]["noul"] for k in near})
    runs = []
    for _ in range(30): runs.append((await j.ask(STATE, near))["body"]["answers"])
    rep = {}
    for k in near:
        v = [r[k]["noul"] for r in runs]
        rep[k] = {"q": Q[k]["instructions"], "min": min(v), "max": max(v), "n_yes": sum(x > .5 for x in v), "n_exact_0.5": sum(x == .5 for x in v), "n": len(v)}
    nf = sum(1 for r in rep.values() if 0 < r["n_yes"] < r["n"])
    # cross-session drift from 01b
    now = json.load(open(RAW / "p01b_borderline_now.json"))["summary"]; later = json.load(open(RAW / "p01b_borderline_later.json"))["summary"]
    shifts = [abs(now[k]["mean"] - later[k]["mean"]) for k in now if k.startswith("n")]
    out = {"screen": {k: a[k]["noul"] for k in Q}, "near": rep, "questions_flipping": nf, "n_near": len(near),
           "cross_session_mean_shift_max": max(shifts), "cross_session_mean_shift_mean": round(st.mean(shifts), 4)}
    await j.aclose(); save("p01c_threshold_flip", out); print(json.dumps({k: v for k, v in out.items() if k != "screen"}, indent=1)); print("requests", j.count)
asyncio.run(main())
