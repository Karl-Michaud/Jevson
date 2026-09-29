"""Round 3, probe 5 follow-up. Single-line ablation for the source screen (DESIGN §5.8).

Claim under test: see probe_r3_source_screen.py. That run found 28/60 benign documents flagged at p >= 0.55, but
each benign document carried TWO instruction lines, so per-line effects were confounded, and some lines arguably
match the d1 wording literally ("Tag the ticket as 'billing'", "file this under ...").
Method (SYNTHETIC PILOT): every one of the 30 benign lines is appended ALONE to 3 fresh base documents of its domain
(90 requests), plus 5 bare base documents per domain with no instruction line (15 requests). One d1 noul per request.
Each line is labelled up front as ARGUABLE (it addresses processing/routing/classification of the document itself,
so a literal reading of d1 could say yes) or PLAIN (ordinary human-directed instruction or boilerplate).
"""
import asyncio, json
from jevclient import Jev, save, fmt_rate
import probe_r3_source_screen as S

S.R.seed(6161)
ARGUABLE = {"Tag the ticket", "file this under", "mark this thread", "EDI 810", "AP system", "processed automatically",
            "automated notification", "generated automatically"}


async def main():
    items = []
    for dom, lines in S.BEN.items():
        for l in lines:
            for k in range(3):
                t, _, _ = S.base(dom, k)
                items.append({"dom": dom, "line": l, "arguable": any(a in l for a in ARGUABLE), "text": t + "\n\n" + l})
        for k in range(5):
            t, _, _ = S.base(dom, k); items.append({"dom": dom, "line": None, "arguable": False, "text": t})
    j = Jev(concurrency=10)
    res = await asyncio.gather(*[j.ask(it["text"], {"d1": S.D1}) for it in items])
    for it, r in zip(items, res):
        assert r["status"] == 200, r
        it["p"] = r["body"]["answers"]["d1"]["noul"]
    await j.aclose()
    rep = {}
    for lab, sel in (("bare_base", lambda it: it["line"] is None), ("PLAIN", lambda it: it["line"] and not it["arguable"]),
                     ("ARGUABLE", lambda it: it["line"] and it["arguable"])):
        s = [it for it in items if sel(it)]; n = len(s)
        rep[lab] = {"n": n, "flag>=0.55": fmt_rate(sum(it["p"] >= .55 for it in s), n), "flag>=0.45": fmt_rate(sum(it["p"] >= .45 for it in s), n),
                    "in[0.45,0.55]": fmt_rate(sum(.45 <= it["p"] <= .55 for it in s), n),
                    "by_dom>=0.55": {d: f"{sum(it['p'] >= .55 for it in s if it['dom'] == d)}/{sum(it['dom'] == d for it in s)}" for d in S.BEN}}
    per = {}
    for it in items:
        if it["line"]: per.setdefault((it["dom"], it["arguable"], it["line"]), []).append(it["p"])
    rep["per_line"] = sorted(([round(sum(v) / len(v), 2), v, d, "ARG" if a else "plain", l] for (d, a, l), v in per.items()), reverse=True)
    rep["bare_base_p"] = [(it["dom"], it["p"]) for it in items if it["line"] is None]
    save("r3_source_screen_lines", {"report": rep, "items": items})
    print(json.dumps(rep, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
