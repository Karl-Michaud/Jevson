"""Phase 0r: run here only as the input of entities/probe_pair_jitter.py ([P12] entity-pair jitter, which needs
runs A and B); on the OpenAI Decisions API (`gpt-6-luna`) through jevclient's `decisions` backend, the object
`instructions` of each pair question is sent as JSON text. The [P10] floor analysis is not re-run here (Phase 0
probe 4's Phase 0r run re-chooses `conflict_floor`).

Round 2. Claim (DESIGN §5.6 Rev 4; PLAN Phase 0 probe 4): per-component conflict handling with a
`conflict_floor` chosen by the pre-registered rule "the largest value in {0.05, 0.10, 0.20, 0.30}
such that same-entity pairs at or below it are <= 2% of all same-entity pairs" yields few silent
errors and fewer Unresolved components than the Rev 3 whole-array policy.

Method (SYNTHETIC PILOT, author-written, not the pre-registered Phase 0 probe):
 - the 24 probe_pairs docs (3 templates x 8 confusable name sets), regenerated verbatim;
 - 24 NEW docs (3 templates x 8 name sets) with realistic coreference chains
   (full name <-> title+surname <-> first name / nickname / role) and near-duplicate DIFFERENT people
   (Katherine Doyle / Kevin Doyle / Katherine Boyle; Dr. Michael Grant / Michaela Grant / Michael Granger;
   Senator Paul Whitaker / Judge Paula Whitaker / Paul Whittaker).
 - every pair asked as a keyed noul in ONE request per doc (probe_pairs wording); the whole set is run
   TWICE (runs A, B) to see whether the floor rule is stable under jitter.
 - EVERY pair probability is stored (raw JSON).
Scoring: p(same) distributions for gold-same / gold-different; floor rule applied verbatim; per-component
outcomes under Rev 4 (components of p>0.5; component with a pair <= floor -> Unresolved), Rev 3 (any pair
<0.5 in any component -> whole array Unresolved), plain connected components; clique completeness.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, itertools, json, sys
from jevclient import Jev, save, fmt_rate
import pathlib, types
# probe_pairs.py runs its probe at import time (unguarded asyncio.run); load its definitions only.
_src = (pathlib.Path(__file__).parent / "probe_pairs.py").read_text().rsplit("asyncio.run(main())", 1)[0]
P6 = types.ModuleType("P6"); P6.__file__ = str(pathlib.Path(__file__).parent / "probe_pairs.py"); exec(compile(_src, "probe_pairs.py", "exec"), P6.__dict__)

# ---------------- new templates ----------------
SETS3 = [("Katherine", "Kate", "Kevin", "Doyle", "Boyle"), ("Elizabeth", "Liz", "Edward", "Carter", "Cartier"),
         ("Margaret", "Peggy", "Martin", "Lowe", "Lowell"), ("Susan", "Sue", "Simon", "Reyes", "Reyna"),
         ("Rebecca", "Becky", "Robert", "Hale", "Hall"), ("Patricia", "Trish", "Patrick", "Byrne", "Burns"),
         ("Jennifer", "Jen", "Jonathan", "Ward", "Warde"), ("Deborah", "Debbie", "David", "Klein", "Kline")]


def doc_t3(F, nick, M, L, L2):
    # E1 = F L (Chair), E2 = M L (Treasurer, male), E3 = F L2 (Secretary, near-dup name)
    text = (f"Minutes of the annual meeting of the Riverside Housing Co-op. Present: {F} {L} (Chair), {M} {L} (Treasurer), "
            f"and {F} {L2} (Secretary). Ms. {L} called the meeting to order at 7 pm. The Treasurer, Mr. {L}, presented the accounts; "
            f"{M} noted a small surplus. {nick}, as everyone calls the Chair, thanked him for his work. The Secretary read the "
            f"previous minutes, and Ms. {L2} was asked to circulate them by Friday. The Chair closed the meeting at 8:15 pm.")
    M_ = [(f"{F} {L}", 1), (f"Ms. {L}", 1), (nick, 1), ("the Chair", 1),
          (f"{M} {L}", 2), (f"Mr. {L}", 2), (M, 2), ("the Treasurer", 2),
          (f"{F} {L2}", 3), (f"Ms. {L2}", 3), ("the Secretary", 3)]
    return text, M_


SETS4 = [("Michael", "Mike", "Michaela", "Grant", "Granger"), ("Daniel", "Dan", "Danielle", "Frost", "Forst"),
         ("Christopher", "Chris", "Christina", "Lang", "Lange"), ("Francis", "Frank", "Frances", "Moore", "Moorer"),
         ("Joseph", "Joe", "Josephine", "Stone", "Stoner"), ("Alexander", "Alex", "Alexandra", "Wolfe", "Wolff"),
         ("Nicholas", "Nick", "Nicole", "Pratt", "Platt"), ("Gabriel", "Gabe", "Gabriela", "Hart", "Harte")]


def doc_t4(M, nick, F, L, L2):
    # E1 = Dr. M L (physician), E2 = F L (paralegal, unrelated, female near-dup first name), E3 = M L2 (outside counsel)
    text = (f"Dr. {M} {L} will lead the clinical review of the incident. {F} {L}, a paralegal who is not related to the doctor, "
            f"will handle the paperwork; Ms. {L} can be reached at extension 4410. {M} {L2}, the hospital's outside counsel, "
            f"asked to be copied on everything. Dr. {L} replied that counsel should receive only the summary, and Mr. {L2} agreed. "
            f"In a later email, {nick} (the doctor signs his emails that way) confirmed the review date, and the paralegal "
            f"scheduled the interviews.")
    M_ = [(f"Dr. {M} {L}", 1), (f"Dr. {L}", 1), (nick, 1), ("the doctor", 1),
          (f"{F} {L}", 2), (f"Ms. {L}", 2), ("the paralegal", 2),
          (f"{M} {L2}", 3), (f"Mr. {L2}", 3), ("the hospital's outside counsel", 3)]
    return text, M_


SETS5 = [("Paul", "Paula", "Whitaker", "Whittaker"), ("Carl", "Carla", "Jensen", "Jenson"), ("Eric", "Erica", "Mills", "Miles"),
         ("Glen", "Glenda", "Porter", "Potter"), ("Dean", "Deanna", "Fischer", "Fisher"), ("Louis", "Louise", "Bennet", "Bennett"),
         ("Justin", "Justine", "Rowe", "Roe"), ("Adrian", "Adriana", "Nash", "Nashe")]


def doc_t5(M, F, L, L2):
    # E1 = Senator M L, E2 = Judge F L (cousin), E3 = M L2 (businessman, near-dup full name)
    text = (f"Senator {M} {L} announced on Tuesday that he will not seek re-election. {L} has served three terms. "
            f"His cousin, {F} {L}, is a state appeals judge; Judge {L} declined to comment. The announcement surprised "
            f"{M} {L2}, a local businessman who is no relation and who had donated to the campaign. Mr. {L2} said the senator "
            f"had been a friend for years. Asked about his plans after leaving the Senate, {M} told reporters he would return "
            f"to teaching. The businessman said he would support the senator's chosen successor.")
    M_ = [(f"Senator {M} {L}", 1), (L, 1), ("the senator", 1), (M, 1),
          (f"{F} {L}", 2), (f"Judge {L}", 2),
          (f"{M} {L2}", 3), (f"Mr. {L2}", 3), ("the businessman", 3)]
    return text, M_


def build_docs():
    docs = []
    for s in P6.SETS:
        for t in P6.TEMPL:
            docs.append((t.__name__, *t(*s)))
    for s in SETS3: docs.append(("doc_t3", *doc_t3(*s)))
    for s in SETS4: docs.append(("doc_t4", *doc_t4(*s)))
    for s in SETS5: docs.append(("doc_t5", *doc_t5(*s)))
    for name, text, M in docs:  # every mention surface occurs in the text
        for m, _ in M:
            assert m in text or m.lower() in text.lower(), (name, m)
        assert len({m for m, _ in M}) == len(M), (name, "duplicate surface")
    return docs


def questions(M):
    q = {}
    for a, b in itertools.combinations(range(len(M)), 2):
        q[f"p{a}_{b}"] = {"type": "noul", "instructions": {"mention_a": M[a][0], "mention_b": M[b][0],
                          "question": "In the text, do `mention_a` and `mention_b` refer to the same person?"}}
    return q


async def run(tag):
    docs = build_docs()
    j = Jev(concurrency=8)
    res = await asyncio.gather(*[j.ask(text, questions(M)) for _, text, M in docs])
    out = []
    for (name, text, M), r in zip(docs, res):
        assert r["status"] == 200, r
        a = r["body"]["answers"]
        pairs = [{"a": x, "b": y, "ma": M[x][0], "mb": M[y][0], "gold_same": M[x][1] == M[y][1], "p": a[f"p{x}_{y}"]["noul"]}
                 for x, y in itertools.combinations(range(len(M)), 2)]
        out.append({"template": name, "text": text, "mentions": M, "pairs": pairs, "usage": r["usage"]})
    await j.aclose()
    save(f"r2_entity_floor_run{tag}", out)
    print("run", tag, "docs", len(out), "requests", j.count)


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1]))
