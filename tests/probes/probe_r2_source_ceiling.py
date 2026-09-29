"""Round 2. Claim (DESIGN §8.2 Rev 4): "The source has a hard ceiling below 32k tokens minus the longest question
(a 255-option candidate choice costs ~2.5k tokens [P2])". Round 1's 2,485-token figure came from a 255-option
choice whose options were bare short keys; realistic candidate options carry span text (5-80 chars) or, per
probe_r2_opaque_ids, a context window.
Method: (1) token cost of a 255-option choice (254 candidates + none_of_these, opaque ids c0..c253) over a
1-word state, for option descriptions of: bare short span (5-12 chars), realistic span (uniform 5-80 chars),
long span (~80 chars), and span + ~160-char context window; the cost is usage.input_tokens minus a 1-word-state
baseline with a 2-option choice. (2) Binary search on the largest state (English prose) accepted together with
the realistic 255-option choice, for two corpora: A = business-document prose dense in names/numbers/addresses,
B = plain English prose (DESIGN.md paragraphs, code/tables removed). Reports chars, input_tokens, chars/token.
"""
import asyncio, json, pathlib, random, re
from jevclient import Jev, save

R = random.Random(55)
ROOT = pathlib.Path(__file__).resolve().parents[2]
FIRST = ["Dana", "Marcus", "Priya", "Tomasz", "Aiko", "Rafael", "Ingrid", "Kwame", "Lucia", "Oren", "Sofia", "Declan"]
LAST = ["Whitfield", "Okafor", "Lindqvist", "Moreau", "Tanaka", "Castillo", "Brennan", "Novak", "Haddad", "Petrov"]
CO = ["Acme Corp", "Globex Ltd", "Initech LLC", "Umbrella Supply", "Hooli Inc", "Vandelay Imports", "Stark Parts"]
ST = ["Maple Ave", "Harbor Rd", "King St", "Elm Court", "Ridge Blvd", "Mill Lane"]
CI = ["Portland, OR 97201", "Austin, TX 78701", "Denver, CO 80202", "Columbus, OH 43215"]
MO = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def p(): return f"{R.choice(FIRST)} {R.choice(LAST)}"
def a(): return f"{R.randint(10, 9899)} {R.choice(ST)}, {R.choice(CI)}"
def d(): return f"{R.choice(MO)} {R.randint(1, 28)}, 2026"
def m(): return f"${R.randint(100, 99999):,}.{R.randint(0, 99):02d}"


def corpus_A(nchars):
    out = []
    while sum(map(len, out)) < nchars:
        t = R.randrange(4)
        if t == 0: out.append(f"Invoice INV-{R.randint(1000,9999)} from {R.choice(CO)} dated {d()}: amount {m()}, due {d()}, billed to {p()} at {a()}.")
        elif t == 1: out.append(f"Note from {p()}: the shipment for {R.choice(CO)} left {a()} on {d()}; freight was {m()}.")
        elif t == 2: out.append(f"Reminder: {p()} will call {p()} about the renewal with {R.choice(CO)} before {d()}.")
        else: out.append(f"Credit memo CM-{R.randint(100,999)} for {m()} issued to {R.choice(CO)} ({a()}) on {d()}.")
    return " ".join(out)[:nchars]


def _prose():
    txt = (ROOT / "DESIGN.md").read_text()
    txt = re.sub(r"```.*?```", " ", txt, flags=re.S)
    lines = [l for l in txt.splitlines() if l.strip() and not l.lstrip().startswith(("|", "#", ">", "-", "```"))]
    return " ".join(re.sub(r"[*`\[\]]", "", l).strip() for l in lines)
PROSE = _prose()


def corpus_B(nchars):
    s = PROSE
    while len(s) < nchars: s += " " + PROSE
    return s[:nchars]


def spans(kind, n=254):
    words = PROSE.split()
    out = []
    for _ in range(n):
        if kind == "short": L = R.randint(5, 12)
        elif kind == "realistic": L = R.randint(5, 80)
        else: L = R.randint(75, 80)
        i = R.randrange(len(words) - 30); s = ""
        while len(s) < L: s = (s + " " + words[i]).strip(); i += 1
        out.append(s[:L])
    return out


def choice_q(kind):
    if kind == "context":
        crit = {f"c{i}": f"\"{s}\" — context: …{PROSE[j:j+70]}[{s}]{PROSE[j+70:j+140]}…"
                for i, (s, j) in enumerate(zip(spans("realistic"), [R.randrange(len(PROSE) - 200) for _ in range(254)]))}
    else:
        crit = {f"c{i}": f"\"{s}\"" for i, s in enumerate(spans(kind))}
    crit["none_of_these"] = "None of the other options is the billing address of this invoice."
    return {"type": "choice", "instructions": "Which of these is the billing address of this invoice (the one being issued)?", "criteria": crit}


async def main():
    j = Jev(concurrency=4)
    out = {"cost": {}, "search": {}}
    base = await j.ask("x", {"q": {"type": "choice", "instructions": "Which of these is the billing address of this invoice (the one being issued)?",
                                   "criteria": {"c0": "\"12 King St\"", "none_of_these": "None of the other options is the billing address of this invoice."}}})
    b0 = base["usage"]["input_tokens"]; out["cost"]["baseline_2opt_tiny_state"] = b0
    Qs = {k: choice_q(k) for k in ("short", "realistic", "long", "context")}
    for k, q in Qs.items():
        r = await j.ask("x", {"q": q})
        out["cost"][k] = {"status": r["status"], "input_tokens": r.get("usage", {}).get("input_tokens"),
                          "question_tokens_over_baseline": (r["usage"]["input_tokens"] - b0) if r["status"] == 200 else None,
                          "desc_chars_total": sum(len(v) for v in q["criteria"].values())}
    # chars per token of each corpus (state-only, short noul)
    for cname, cf in (("A_business", corpus_A), ("B_prose", corpus_B)):
        r0 = await j.ask("x", {"q": {"type": "noul", "instructions": "Is this about invoices?"}})
        r1 = await j.ask(cf(40000), {"q": {"type": "noul", "instructions": "Is this about invoices?"}})
        cpt = 40000 / (r1["usage"]["input_tokens"] - r0["usage"]["input_tokens"])
        out["search"][cname] = {"chars_per_token": round(cpt, 3)}
        # binary search with the realistic 255-option question
        lo, hi = 60000, 160000; best = None
        R.seed(99); text = cf(hi)
        while hi - lo > 1500:
            mid = (lo + hi) // 2
            r = await j.ask(text[:mid], {"q": Qs["realistic"]})
            if r["status"] == 200:
                lo = mid; best = (mid, r["usage"]["input_tokens"])
            else:
                hi = mid; out["search"][cname].setdefault("rejections", []).append((mid, r["status"], str(r["body"])[:120]))
        out["search"][cname].update({"max_state_chars_accepted": best[0] if best else None, "input_tokens_at_max": best[1] if best else None,
                                     "first_rejected_chars": hi})
        # same corpus, no big question: max state with a short noul (for comparison)
        lo2, hi2 = lo, lo + 30000; best2 = None
        while hi2 - lo2 > 1500:
            mid = (lo2 + hi2) // 2
            r = await j.ask(text[:mid] if len(text) >= mid else cf(mid), {"q": {"type": "noul", "instructions": "Is this about invoices?"}})
            if r["status"] == 200: lo2 = mid; best2 = (mid, r["usage"]["input_tokens"])
            else: hi2 = mid
        out["search"][cname]["max_state_chars_short_noul"] = best2
    await j.aclose()
    save("r2_source_ceiling", out)
    print(json.dumps(out, indent=1)); print("requests", j.count)


if __name__ == "__main__":
    asyncio.run(main())
