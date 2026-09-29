"""Claim: DESIGN §8.2 / §12 / PLAN Phase 7 — pairwise resolution costs n(n−1)/2 questions (n=20→190,
n=30→435, n=255→32385), is issued as ONE backend call, and the cap n=30 was "chosen against the context
budget" (~64k tokens for state plus questions, DESIGN §2).

Method: verify the arithmetic; read the vendor models.md context limits; build realistic keyed noul
question maps (JSON, as sent in `questions`) for n = 10..40 under three question templates and count
tokens with tiktoken cl100k_base as a PROXY (Jev's tokenizer is unpublished; counts are indicative only).
Report the tokens left for `state` under the 64k total budget.
"""
import json, pathlib, itertools, re
import tiktoken

for n in (20, 30, 255):
    print(f"n={n}: n(n-1)/2 = {n*(n-1)//2}")

DOCS = pathlib.Path(os.environ.get("JEV_DOCS_DIR", pathlib.Path(__file__).resolve().parent / "jevdocs"))  # vendor docs snapshot: see fetch_vendor_docs.sh
for line in (DOCS / "models.md").read_text().splitlines():
    if "Context length" in line: print("vendor:", line.strip()[:200])

enc = tiktoken.get_encoding("cl100k_base")
names = ["Dana Whitfield", "Ms. Whitfield", "Dana", "John Smith", "Mr. Smith", "Acme Corp", "ACME Corporation",
         "Globex", "Globex Inc.", "Sarah O'Neill", "Michael Chen", "M. Chen", "the vendor", "the customer",
         "Initech LLC", "Initech", "Bob Porter", "Robert Porter", "Hooli", "Hooli Inc", "Pied Piper",
         "Richard Hendricks", "R. Hendricks", "Gavin Belson", "G. Belson", "Big Head", "Nelson Bighetti",
         "Jian Yang", "Erlich Bachman", "E. Bachman", "Monica Hall", "Laurie Bream", "Jared Dunn", "Donald Dunn",
         "Peter Gregory", "P. Gregory", "Russ Hanneman", "Jack Barker", "Ed Chen", "Carla Walton"]
ctx = "…signed on behalf of {x} at the March meeting, as noted in section 4.2 of the agreement…"

templates = {
    "A keys-only": lambda i, j, a, b: f"Do `candidates.k{i}` and `candidates.k{j}` refer to the same person or organisation in the state?",
    "B inline strings": lambda i, j, a, b: f"In the state, does \"{a}\" (candidates.k{i}) refer to the same real-world person or organisation as \"{b}\" (candidates.k{j})? Answer yes only if the source supports it.",
    "C inline + context": lambda i, j, a, b: {"question": "Do `a` and `b` refer to the same real-world person or organisation in the state?",
                                              "a": {"text": a, "context": ctx.format(x=a)}, "b": {"text": b, "context": ctx.format(x=b)}},
}
for tname, t in templates.items():
    print(f"\n{tname}")
    for n in (10, 20, 25, 30, 35, 40):
        qs = {}
        for i, j in itertools.combinations(range(n), 2):
            qs[f"same.k{i}_k{j}"] = {"type": "noul", "instructions": t(i, j, names[i], names[j])}
        toks = len(enc.encode(json.dumps({"questions": qs})))
        longest = max(len(enc.encode(json.dumps(q))) for q in qs.values())
        print(f"  n={n:3} questions={len(qs):4} question-map tokens≈{toks:6}  per-q≈{toks/len(qs):5.1f}  "
              f"left for state under 64k≈{65536-toks:6}  (fits={toks<65536})")

# How big is a realistic state that yields 30 entity candidates? e.g. 3000-word contract ~ 4k tokens
print("\nstate proxy: 3000 English words ≈", len(enc.encode(("The vendor shall deliver the goods to the customer. " * 350))), "tokens")
