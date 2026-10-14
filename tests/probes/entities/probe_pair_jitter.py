"""Phase 0r: re-measures [P12] (entity half: pair ranges and flips over 12 identical calls) on the OpenAI Decisions
API (`gpt-6-luna`) through jevclient's `decisions` backend, after `entities/probe_conflict_floor.py A` and `B` have
been re-run on it (minutes apart). Summary: tests/probes/results/0r/probe_pair_jitter.json; it also records the
A-vs-B flips over all 48 docs (the [P12] "16/1,824 flips between two P10 runs").

Round 2. Claim (DESIGN §2.3, §6 Rev 4): "Byte-identical requests return probabilities that jitter by up to 0.10
(range over 25 repeats; per-question standard deviation <= 0.022)"; "Probabilities jitter by up to ±0.05".
Trigger: probe_conflict_floor runs A and B (identical requests, minutes apart) differed by up to 0.26 on one pair,
with 16/1824 decision flips.
Method: the 6 entity docs containing the largest A-vs-B differences, each re-sent 10 more times byte-identically
(same questions, same state) = 60 requests; per-pair range and sd over the 12 observations (A, B, 10 repeats).
Also reports the same statistics over all pairs in those docs."""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, json, statistics
from jevclient import Jev, save, save_summary, RAW
import entities.probe_conflict_floor as E


async def main():
    A = json.loads((RAW / "r2_entity_floor_runA.json").read_text()); B = json.loads((RAW / "r2_entity_floor_runB.json").read_text())
    docs = E.build_docs()
    diffs = sorted(((max(abs(x["p"] - y["p"]) for x, y in zip(a["pairs"], b["pairs"])), i) for i, (a, b) in enumerate(zip(A, B))), reverse=True)
    pick = [i for _, i in diffs[:6]]
    j = Jev(concurrency=6)
    obs = {i: [[q["p"] for q in A[i]["pairs"]], [q["p"] for q in B[i]["pairs"]]] for i in pick}
    for _ in range(10):
        res = await asyncio.gather(*[j.ask(docs[i][1], E.questions(docs[i][2])) for i in pick])
        for i, r in zip(pick, res):
            assert r["status"] == 200, r
            obs[i].append([r["body"]["answers"][f"p{q['a']}_{q['b']}"]["noul"] for q in A[i]["pairs"]])
    await j.aclose()
    rows = []
    for i in pick:
        for k, q in enumerate(A[i]["pairs"]):
            ps = [o[k] for o in obs[i]]
            rows.append({"doc": i, "template": A[i]["template"], "ma": q["ma"], "mb": q["mb"], "gold_same": q["gold_same"], "ps": ps,
                         "range": round(max(ps) - min(ps), 2), "sd": round(statistics.pstdev(ps), 4), "flip": len({p > .5 for p in ps}) > 1})
    rows.sort(key=lambda r: -r["range"])
    out = {"docs": pick, "pairs": len(rows), "obs_per_pair": 12,
           "range_max": rows[0]["range"], "sd_max": max(r["sd"] for r in rows),
           "pairs_range_gt_0.10": sum(r["range"] > .10 for r in rows), "pairs_sd_gt_0.022": sum(r["sd"] > .022 for r in rows),
           "pairs_with_decision_flip": sum(r["flip"] for r in rows),
           "top": [(r["template"], r["ma"], r["mb"], r["ps"], r["range"], r["sd"]) for r in rows[:12]],
           "range_excluding_A_B(10 back-to-back repeats)": max(max(r["ps"][2:]) - min(r["ps"][2:]) for r in rows)}
    save("r2_jitter_entity", {"report": out, "rows": rows})
    ab = [(x["p"], y["p"]) for a, b in zip(A, B) for x, y in zip(a["pairs"], b["pairs"])]
    out["runA_vs_runB_all_docs"] = {"pairs": len(ab), "decision_flips": sum((x > .5) != (y > .5) for x, y in ab),
                                    "max_abs_diff": round(max(abs(x - y) for x, y in ab), 4), "pairs_differing": sum(x != y for x, y in ab),
                                    "exact_0.50_obs": sum((x == .5) + (y == .5) for x, y in ab)}
    save_summary("probe_pair_jitter", j, out, n={"docs": len(pick), "obs_per_pair": 12, "ab_pairs": len(ab)})
    print(json.dumps(out, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
