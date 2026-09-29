"""Round 3, probe 1. Out-of-sample test of the two-directional entity rule (DESIGN §5.7, Revision 5) and of the
pre-registered `conflict_floor` selection rule (PLAN Phase 0 probe 4).

Claim (DESIGN §5.7.3): a component of p(same) > 0.5 is emitted only if (i) no internal pair is <= conflict_floor and
(ii) no pair between it and another component lies in (conflict_floor, 0.5]; otherwise it is Unresolved(entity_conflict).
On the 48 in-sample pilot documents this gave 0/133 and 0/134 silently wrong components [P10]. The rule was found and
scored on the same data, so it is a hypothesis.

Method (SYNTHETIC PILOT, author-written, NEW templates / domains / name sets, disjoint from probe_pairs and
probe_conflict_floor):
 - 5 new templates x 10 name sets = 50 documents: t6 civil complaint (court filing), t7 football match report,
   t8 hospital nursing handover, t9 M&A press release, t10 thesis acknowledgements.
 - Each has coreference chains (full name / title+surname / first name / role noun), near-duplicate DIFFERENT people
   (Rosa Delgado vs Rosa Delgato), and ORGANISATIONS sharing a name with a PERSON (Delgado Freight LLC vs Marco
   Delgado; Harlan Group plc / "Harlan" vs Peter Harlan / Mr. Harlan).
 - Every mention surface is unique within a document (identical text would be pre-merged, DESIGN §5.7.1).
 - Every pair is asked as a keyed noul, ONE request per document. Wording differs from P10 only in naming
   organisations: "In the text, do `mention_a` and `mention_b` refer to the same entity (the same person or the
   same organization)?"
 - The whole set is sent TWICE, byte-identically (runs A and B). Every pair probability is stored.
Scoring (`analyse`): the PLAN rule verbatim ("largest value in {0.05, 0.10, ..., 0.45} such that same-entity pairs
at or below it are <= 2% of all same-entity pairs; if none qualifies, 0.05 and stop"); then per-component outcomes
under (a) Rev 5 two-directional, (b) internal-conflict only (Rev 4), (c) Rev 3 whole-array (any pair < 0.5 inside
any component -> whole array Unresolved), (d) plain connected components. Merges and splits are counted separately;
cascade statistics for the cross-component condition; arrays with >= 1 Unresolved component.
Usage: probe_out_of_sample.py run A | run B | analyse
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import asyncio, itertools, json, sys
from collections import Counter
from jevclient import Jev, save, RAW, fmt_rate, wilson

WORDING = "In the text, do `mention_a` and `mention_b` refer to the same entity (the same person or the same organization)?"

# ---------- t6: civil complaint ----------
S6 = [("Rosa", "Marco", "Delgado", "Delgato", "Freight", "Harris"), ("Irene", "Victor", "Castellano", "Castellani", "Roofing", "Pima"),
      ("Leah", "Aaron", "Brandt", "Brant", "Printing", "Lane"), ("Nadia", "Omar", "Haddad", "Hadad", "Catering", "Wayne"),
      ("Grace", "Henry", "Whitlock", "Whitlow", "Plumbing", "Boone"), ("Mei", "Wei", "Zhang", "Zheng", "Imports", "Kent"),
      ("Olga", "Ivan", "Petrov", "Petrova", "Auto Repair", "Clark"), ("Claire", "Luc", "Moreau", "Morel", "Bakery", "Otero"),
      ("Ingrid", "Lars", "Holm", "Holme", "Marine", "Door"), ("Fatima", "Yusuf", "Okafor", "Okafo", "Logistics", "Fulton")]


def t6(F, M, L, L2, Ind, county):
    text = (f"IN THE DISTRICT COURT OF {county.upper()} COUNTY\n{F} {L}, Plaintiff, v. {L} {Ind} LLC, Defendant.\nCOMPLAINT\n"
            f"1. Plaintiff {F} {L} is an individual residing in {county} County.\n"
            f"2. Defendant {L} {Ind} LLC (\"{L} {Ind}\") is a limited liability company. Its managing member is {M} {L}, "
            f"Plaintiff's former husband.\n"
            f"3. Ms. {L} worked for the company as a dispatcher from 2019 until March 2024, when Mr. {L} dismissed her without notice.\n"
            f"4. Plaintiff retained {F} {L2}, a local attorney. Attorney {L2} wrote to {L} {Ind} demanding the unpaid wages; "
            f"the managing member did not reply.\n"
            f"5. Defendant has refused to pay the wages owed. WHEREFORE, Plaintiff asks the Court to enter judgment against "
            f"the company.\nRespectfully submitted, Plaintiff's counsel.")
    M_ = [(f"{F} {L}", 1), (f"Ms. {L}", 1), ("Plaintiff", 1),
          (f"{L} {Ind} LLC", 2), (f"{L} {Ind}", 2), ("Defendant", 2), ("the company", 2),
          (f"{M} {L}", 3), (f"Mr. {L}", 3), ("the managing member", 3),
          (f"{F} {L2}", 4), (f"Attorney {L2}", 4), ("Plaintiff's counsel", 4)]
    return text, M_


# ---------- t7: football match report ----------
S7 = [("Tom", "Tommy", "Graham", "Ashford", "Ashworth", "Millbrook United"), ("Jack", "Jacko", "Neil", "Prestwick", "Prestwich", "Harbour City"),
      ("Sam", "Sammy", "Colin", "Chesney", "Chesnay", "Eastfield Rovers"), ("Luke", "Lukey", "Brian", "Kendrew", "Kendrow", "Riverside Athletic"),
      ("Owen", "Ozzy", "Martin", "Halden", "Holden", "Westgate Albion"), ("Callum", "Cal", "Stuart", "Dunmore", "Dunmoor", "Kingsway Rangers"),
      ("Ellis", "El", "Roy", "Marston", "Marsden", "Northbridge FC"), ("Josh", "Joshy", "Paul", "Redfern", "Redfearn", "Castleton United"),
      ("Kieran", "Kez", "Alan", "Thornbury", "Thornberry", "Lakeside Wanderers"), ("Mason", "Mase", "Derek", "Whitby", "Whitley", "Oakham Athletic")]


def t7(P, nick, M, S, S2, C1):
    text = (f"{C1} 2-1 {S} Town\n{C1} came from behind to beat {S} Town on Saturday. The visitors led at half-time through "
            f"their captain, {P} {S2}, who curled in a free kick. {P} {S}, the hosts' striker, levelled with a header on the hour "
            f"and then won it with a penalty in stoppage time. Despite his name, the striker has no connection to {S} Town. "
            f"{S2} said afterwards: \"We gave it away.\" The striker's father, {M} {S}, is the {C1} manager. The manager said "
            f"{nick}, as the squad call him, had been ill all week. The hosts move up to fifth; the visitors stay bottom.")
    M_ = [(f"{P} {S}", 1), ("the striker", 1), (nick, 1),
          (f"{S} Town", 2), ("the visitors", 2),
          (f"{P} {S2}", 3), (S2, 3), ("their captain", 3),
          (f"{M} {S}", 4), ("The manager", 4),
          (C1, 5), ("the hosts", 5)]
    return text, M_


# ---------- t8: hospital nursing handover ----------
S8 = [("Helen", "Ellen", "Park", "Samuel", "Parker"), ("Joan", "Jean", "Fisk", "Imran", "Fiske"), ("Mary", "Marie", "Holt", "Kwame", "Holtz"),
      ("Anne", "Anna", "Wren", "Priya", "Wrenn"), ("Doris", "Dora", "Kemp", "Tomasz", "Kempe"), ("Irene", "Irena", "Shaw", "Ade", "Shore"),
      ("Ruth", "Rita", "Barlow", "Wei", "Barlowe"), ("Vera", "Vesna", "Lund", "Omar", "Lunde"), ("Nora", "Norah", "Quinn", "Felix", "Quinne"),
      ("Alice", "Alicia", "Dean", "Ravi", "Deane")]


def t8(F, F2, L, D, L2):
    text = (f"Night handover - Ward 7B\nS: Mrs. {F} {L}, 81, bed 14, admitted yesterday from the {L} Road Clinic with a chest "
            f"infection. She prefers to be called {F}.\nB: Mrs. {L} lives alone. Her daughter, {F2} {L}, is next of kin; "
            f"Ms. {L} phoned at 21:00 and will visit in the morning.\nA: The patient's oxygen saturation improved overnight. "
            f"Dr. {D} {L2}, the registrar, reviewed her at 22:30; Dr. {L2} wants repeat bloods at 06:00.\n"
            f"R: The clinic has asked for a discharge summary. Please update her daughter if the patient deteriorates; the "
            f"registrar is on bleep 4471.")
    M_ = [(f"Mrs. {F} {L}", 1), (f"Mrs. {L}", 1), ("the patient", 1), (F, 1),
          (f"{F2} {L}", 2), ("her daughter", 2), (f"Ms. {L}", 2),
          (f"Dr. {D} {L2}", 3), (f"Dr. {L2}", 3), ("the registrar", 3),
          (f"{L} Road Clinic", 4), ("The clinic", 4)]
    return text, M_


# ---------- t9: M&A press release ----------
S9 = [("Harlan", "Harland", "Peter", "Petra", "warehouse robotics", "Brook & Co."), ("Mercer", "Merced", "Julian", "Juliana", "payroll software", "Aldgate Partners"),
      ("Calloway", "Galloway", "Frederick", "Frederica", "medical imaging sensors", "Fenwick Capital"), ("Stirling", "Sterling", "Andrew", "Andrea", "industrial valves", "Rowan Advisory"),
      ("Vance", "Vane", "George", "Georgina", "cybersecurity tools", "Castle Street Securities"), ("Lyle", "Lisle", "Robert", "Roberta", "cold-chain packaging", "Marlow & Finch"),
      ("Ostrander", "Ostrow", "Charles", "Charlotte", "drone mapping", "Greyfriars Capital"), ("Pryce", "Price", "Stephen", "Stephanie", "legal research software", "Tamar Partners"),
      ("Whitcombe", "Whitcomb", "Albert", "Alberta", "solar inverters", "Northgate Advisory"), ("Delacroix", "Delacroze", "Louis", "Louisa", "specialty coatings", "Quayside Capital")]


def t9(A, A2, Pf, Pf2, prod, bank):
    text = (f"FOR IMMEDIATE RELEASE\n{A} Group plc (\"{A}\" or \"the Group\") today announced a definitive agreement to acquire "
            f"{A2} Systems Inc. (\"{A2} Systems\"), a maker of {prod}, for $240 million in cash. {Pf} {A}, Chairman of the Group "
            f"and grandson of its founder, said the deal \"doubles our engineering base\". Mr. {A} will also join the board of the "
            f"combined business. The target's CEO, {Pf2} {A2}, will stay on to run the business as a division of the Group; "
            f"Ms. {A2} founded the company in 2011. The CEO said customers would see no change. The transaction is expected to "
            f"close in the first quarter of 2027, subject to approval by {A2} Systems shareholders. {A} was advised by {bank}; "
            f"the target was advised by its own counsel. The Chairman declined to comment on further acquisitions.")
    M_ = [(f"{A} Group plc", 1), (A, 1), ("the Group", 1),
          (f"{Pf} {A}", 2), (f"Mr. {A}", 2), ("The Chairman", 2),
          (f"{A2} Systems Inc.", 3), (f"{A2} Systems", 3), ("the target", 3),
          (f"{Pf2} {A2}", 4), (f"Ms. {A2}", 4), ("The CEO", 4),
          (bank, 5)]
    return text, M_


# ---------- t10: thesis acknowledgements ----------
S10 = [("Anna", "Lindqvist", "Lindquist", "Erik", "Nordvik Institute"), ("Maria", "Santos", "Santoro", "Paulo", "Coastal Research Institute"),
       ("Sarah", "Goldberg", "Goldman", "David", "Hollins Institute"), ("Yuki", "Tanaka", "Tanabe", "Hiro", "Kanto Materials Institute"),
       ("Ewa", "Nowak", "Novak", "Piotr", "Baltic Genomics Institute"), ("Priya", "Raman", "Ramani", "Arjun", "Deccan Ecology Institute"),
       ("Laura", "Bianchi", "Bianco", "Marco", "Alpine Climate Institute"), ("Chloe", "Martin", "Martens", "Hugo", "Loire Soil Institute"),
       ("Hannah", "Weber", "Webber", "Jonas", "Rhine Neuroscience Institute"), ("Amara", "Obi", "Obie", "Chidi", "Delta Water Institute")]


def t10(F, L, L2, M, Inst):
    text = (f"Acknowledgements\nI am deeply grateful to my supervisor, Professor {F} {L}, for her patience and guidance; {F} read "
            f"every draft of every chapter. This research was funded by the {L} Foundation, which, despite the name, has no "
            f"connection to my supervisor. I thank the Foundation, and especially its director, {M} {L}, a grandson of the "
            f"Foundation's benefactor, for his support. I also thank Dr. {F} {L2} of the {Inst} for access to her laboratory, and "
            f"Dr. {L2}'s technicians for training me. The Institute also hosted me for six months. Professor {L} and Dr. {L2} "
            f"co-supervised the final chapter. Finally, thank you to my family.")
    M_ = [(f"Professor {F} {L}", 1), ("my supervisor", 1), (F, 1), (f"Professor {L}", 1),
          (f"{L} Foundation", 2), ("the Foundation", 2),
          (f"{M} {L}", 3), ("its director", 3),
          (f"Dr. {F} {L2}", 4), (f"Dr. {L2}", 4),
          (Inst, 5), ("The Institute", 5)]
    return text, M_


# ---------- HARD (split-stress) set: epithets, acronyms, initials, e-mail addresses ----------
S11 = [("Amelia", "Millie", "Reyes-Whitford", "Whitford", 52, "Hollis Virology Institute", "HVI", "Denver"),
       ("Katarina", "Kat", "Novotna", "Novotny", 47, "Moravian Cancer Centre", "MCC", "Brno"),
       ("Theresa", "Tess", "Okonjo-Bell", "Bell", 58, "Coastal Vaccine Laboratory", "CVL", "Halifax"),
       ("Margot", "Mags", "Lefevre", "Lefebvre", 44, "Institut Rhone Sante", "IRS", "Lyon"),
       ("Susanna", "Zanna", "Ferreira", "Pereira", 61, "Atlantic Genome Centre", "AGC", "Porto"),
       ("Beatrix", "Trixie", "Van Dijk", "Van Dyke", 50, "Delta Infection Institute", "DII", "Utrecht"),
       ("Harriet", "Hattie", "Moncrieff", "Moncrief", 55, "Highland Health Institute", "HHI", "Inverness"),
       ("Josefina", "Josie", "Alvarado", "Alvaro", 49, "Andes Tropical Institute", "ATI", "Quito"),
       ("Rosalind", "Roz", "Achterberg", "Achterburg", 63, "Nordsee Research Centre", "NRC", "Bremen"),
       ("Philippa", "Pip", "Carrington", "Carington", 46, "Wessex Immunology Institute", "WII", "Bath")]


def t11(F, nick, L, L2, age, Inst, Acr, city):
    text = (f"When Dr. {F} {L} took over the {Inst} ({Acr}) in 2019, few expected the {age}-year-old virologist to last. "
            f"{L} had never run anything larger than a lab of six. Colleagues, who call her {nick}, say the turning point came "
            f"in 2021, when the director won the {Acr} a ten-year grant. Her former postdoc, Dr. {F} {L2}, now runs a rival "
            f"group in {city}; {L2} insists the institute \"owes everything to her\". {nick} laughs this off. Asked about "
            f"retirement, the virologist said she had \"at least one more grant in her\".")
    M_ = [(f"Dr. {F} {L}", 1), (L, 1), (f"the {age}-year-old virologist", 1), (nick, 1), ("the director", 1), ("the virologist", 1),
          (f"Dr. {F} {L2}", 2), (L2, 2), ("Her former postdoc", 2),
          (Inst, 3), (Acr, 3), ("the institute", 3)]
    return text, M_


S12 = [("Brightwater", "Hartley", "HBL", "Joseph", "Okonkwo", "Samuel", "Okonjo"), ("Kestrel", "Penrose", "PBL", "Diane", "Albright", "Donna", "Allbright"),
       ("Silverline", "Mcintyre", "MBL", "Hugh", "Farrant", "Hugo", "Farrand"), ("Oakridge", "Quigley", "QBL", "Nina", "Sorensen", "Nils", "Sorenson"),
       ("Harbourview", "Fenwick", "FBL", "Carl", "Ibsen", "Carla", "Ibson"), ("Meridian", "Tolland", "TBL", "Ruth", "Achebe", "Rufus", "Achebe-Cole"),
       ("Stonegate", "Bramley", "BBL", "Leon", "Duval", "Leona", "Duvall"), ("Crescent", "Ogilvy", "OBL", "Farah", "Siddiqui", "Faris", "Siddiqi"),
       ("Northfield", "Lambert", "LBL", "Owen", "Castell", "Olwen", "Castle"), ("Riverbend", "Whitmore", "WBL", "Tariq", "Hussain", "Tarik", "Husain")]


def t12(LL, T, TA, S1, S2, G1, G2):
    text = (f"THIS LEASE is made between {LL} Properties LLC (the \"Landlord\") and {T} Bakery Ltd (\"{TA}\" or the \"Tenant\").\n"
            f"1. {G1} {G2} (the \"Guarantor\") guarantees every obligation of the Tenant under this Lease.\n"
            f"2. The rent is payable monthly in advance to {LL} Properties LLC.\n"
            f"3. {TA} shall keep the premises clean; the roof and structure remain the responsibility of the Landlord.\n"
            f"4. Notices to the Landlord shall be sent to the attention of {S1} {S2}.\n"
            f"Signed for the Landlord by {S1[0]}. {S2}, Managing Member.\n"
            f"Signed by {G1} {G2} as Director of {TA}, and personally as the Guarantor.")
    M_ = [(f"{LL} Properties LLC", 1), ("the Landlord", 1),
          (f"{S1} {S2}", 2), (f"{S1[0]}. {S2}", 2), ("Managing Member", 2),
          (f"{T} Bakery Ltd", 3), (TA, 3), ("the Tenant", 3),
          (f"{G1} {G2}", 4), ("the Guarantor", 4), (f"Director of {TA}", 4)]
    return text, M_


S13 = [("Robert", "Bob", "Tillman", "Roberta", "Tilman", "Rebecca", "Corvid Analytics"), ("William", "Bill", "Hastings", "Wilhelmina", "Hasting", "Wendy", "Plover Systems"),
       ("Richard", "Rick", "Oduya", "Ricarda", "Oduye", "Rachel", "Tern Data"), ("Edward", "Ted", "Lomax", "Edwina", "Lomas", "Eleanor", "Heron Cloud"),
       ("Charles", "Chuck", "Pemberton", "Charlene", "Pemberton-Hale", "Clara", "Finch Software"), ("Theodore", "Theo", "Vasquez", "Theodora", "Vazquez", "Tanya", "Wren Logistics"),
       ("Nathaniel", "Nate", "Bishop", "Natalia", "Bishopp", "Naomi", "Kite Security"), ("Anthony", "Tony", "Russo", "Antonia", "Rosso", "Angela", "Swift Payroll"),
       ("Benjamin", "Ben", "Adeyemi", "Benedicta", "Adeyemo", "Bola", "Egret Health"), ("Frederick", "Fred", "Marchetti", "Federica", "Marchetto", "Fiona", "Osprey Media")]


def t13(F, nick, L, F2, L2, F3, Co):
    email = f"{F.lower()}.{L.lower()}@{Co.split()[0].lower()}.com"
    init = f"{F[0]}{L[0]}"
    text = (f"From: {F} {L} <{email}>\nTo: {F2} {L2}\nSubject: Re: contract renewal\n\n{F2}, thanks for the call. As discussed, "
            f"{Co} will hold the current price until June; our finance lead, {F3} {L}, will send the paperwork this week.\n-- {init}\n\n"
            f"> On Monday, Ms. {L2} wrote:\n> Hi {nick}, can the vendor confirm the price freeze in writing? Please copy "
            f"{F3} so the invoices match.")
    M_ = [(f"{F} {L}", 1), (email, 1), (init, 1), (nick, 1),
          (f"{F2} {L2}", 2), (f"Ms. {L2}", 2), (F2, 2),
          (Co, 3), ("the vendor", 3),
          (f"{F3} {L}", 4), ("our finance lead", 4), (F3, 4)]
    return text, M_


TEMPLATES_HARD = [(t11, S11), (t12, S12), (t13, S13)]


TEMPLATES = [(t6, S6), (t7, S7), (t8, S8), (t9, S9), (t10, S10)]


def build_docs(hard=False):
    docs = []
    for t, S in (TEMPLATES_HARD if hard else TEMPLATES):
        for s in S:
            text, M = t(*s)
            for m, _ in M:
                assert m in text, (t.__name__, m)
            assert len({m for m, _ in M}) == len(M), (t.__name__, "duplicate surface")
            docs.append((t.__name__, text, M))
    return docs


def questions(M):
    return {f"p{a}_{b}": {"type": "noul", "instructions": {"mention_a": M[a][0], "mention_b": M[b][0], "question": WORDING}}
            for a, b in itertools.combinations(range(len(M)), 2)}


async def run(tag, hard=False):
    docs = build_docs(hard); j = Jev(concurrency=8)
    res = await asyncio.gather(*[j.ask(text, questions(M)) for _, text, M in docs])
    out = []
    for (name, text, M), r in zip(docs, res):
        assert r["status"] == 200, r
        a = r["body"]["answers"]
        pairs = [{"a": x, "b": y, "ma": M[x][0], "mb": M[y][0], "gold_same": M[x][1] == M[y][1], "p": a[f"p{x}_{y}"]["noul"]}
                 for x, y in itertools.combinations(range(len(M)), 2)]
        out.append({"template": name, "text": text, "mentions": M, "pairs": pairs, "usage": r["usage"], "model": r.get("model")})
    await j.aclose(); save(f"r3_entity{'_hard' if hard else ''}_run{tag}", out)
    print("run", tag, "docs", len(out), "pairs", sum(len(d["pairs"]) for d in out), "requests", j.count)


# ---------------- analysis ----------------
GRID = [round(0.05 * k, 2) for k in range(1, 10)]


def comps(n, P):
    parent = list(range(n))
    def f(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for (x, y), p in P.items():
        if p > 0.5: parent[f(x)] = f(y)
    c = {}
    for i in range(n): c.setdefault(f(i), []).append(i)
    return sorted(sorted(v) for v in c.values())


def pkey(x, y): return (min(x, y), max(x, y))


def score_doc(doc, policy, floor=None):
    """Returns (list of (outcome, component), trigger info)."""
    M = doc["mentions"]; n = len(M)
    P = {(q["a"], q["b"]): q["p"] for q in doc["pairs"]}
    gold = {}
    for i, (_, e) in enumerate(M): gold.setdefault(e, []).append(i)
    gold_sets = [sorted(v) for v in gold.values()]
    C = comps(n, P)
    inside = lambda c: [P[(x, y)] for x, y in itertools.combinations(c, 2)]
    def truth(c):
        if c in gold_sets: return "correct"
        return "wrong_merge" if len({M[i][1] for i in c}) > 1 else "wrong_split"
    if policy == "rev3":
        if any(p < 0.5 for c in C for p in inside(c)):
            return [("unresolved", c, truth(c)) for c in C], None
        return [(truth(c), c, truth(c)) for c in C], None
    internal = {i for i, c in enumerate(C) if policy in ("internal", "rev5") and any(p <= floor for p in inside(c))}
    cross_pairs = []
    if policy == "rev5":
        for i, j in itertools.combinations(range(len(C)), 2):
            for x in C[i]:
                for y in C[j]:
                    p = P[pkey(x, y)]
                    if floor < p <= 0.5: cross_pairs.append((i, j, x, y, p))
    cross = {i for t in cross_pairs for i in t[:2]}
    res = [("unresolved" if (i in internal or i in cross) else truth(c), c, truth(c)) for i, c in enumerate(C)]
    info = {"internal": internal, "cross_pairs": cross_pairs, "cross_only": cross - internal, "C": C}
    return res, info


def analyse_run(docs, label):
    out = {"label": label, "docs": len(docs)}
    same = [q["p"] for d in docs for q in d["pairs"] if q["gold_same"]]
    diff = [q["p"] for d in docs for q in d["pairs"] if not q["gold_same"]]
    out["n_same"], out["n_diff"] = len(same), len(diff)
    edges = [0, .05, .10, .20, .30, .40, .50, .80, 1.0001]
    hist = lambda v: {f"[{edges[i]:.2f},{min(edges[i+1], 1):.2f})": sum(edges[i] <= x < edges[i + 1] for x in v) for i in range(len(edges) - 1)}
    out["hist_same"], out["hist_diff"] = hist(same), hist(diff)
    out["pair_acc"] = fmt_rate(sum(p > .5 for p in same) + sum(p <= .5 for p in diff), len(same) + len(diff))
    out["false_merge_pairs"] = fmt_rate(sum(p > .5 for p in diff), len(diff))
    out["false_split_pairs"] = fmt_rate(sum(p <= .5 for p in same), len(same))
    out["same_le"] = {f: f"{sum(p <= f + 1e-9 for p in same)}/{len(same)} = {sum(p <= f + 1e-9 for p in same)/len(same):.3%}" for f in GRID}
    out["diff_le"] = {f: f"{sum(p <= f + 1e-9 for p in diff)/len(diff):.3f}" for f in GRID}
    ok = [f for f in GRID if sum(p <= f + 1e-9 for p in same) / len(same) <= 0.02]
    out["selected_floor"] = max(ok) if ok else 0.05
    out["rule_stop"] = not ok
    # non-transitivity, clique completeness
    vt = tr = vd = cc = ct = 0
    for d in docs:
        P = {(q["a"], q["b"]): q["p"] for q in d["pairs"]}; n = len(d["mentions"]); v = 0
        for x, y, z in itertools.combinations(range(n), 3):
            s = [P[(x, y)] > .5, P[(y, z)] > .5, P[(x, z)] > .5]; tr += 1; v += sum(s) == 2
        vt += v; vd += v > 0
        g = {}
        for i, (_, e) in enumerate(d["mentions"]): g.setdefault(e, []).append(i)
        for gg in g.values():
            if len(gg) > 1: ct += 1; cc += all(P[(x, y)] > .5 for x, y in itertools.combinations(gg, 2))
    out["non_transitive"] = fmt_rate(vt, tr); out["docs_with_violation"] = fmt_rate(vd, len(docs))
    out["clique_completeness"] = fmt_rate(cc, ct)
    return out


def policy_table(docs, policy, floor):
    per = [score_doc(d, policy, floor) for d in docs]
    cnt = Counter(o for r, _ in per for o, _, _ in r); n = sum(cnt.values())
    arr_unres = sum(any(o == "unresolved" for o, _, _ in r) for r, _ in per)
    arr_silent = sum(any(o in ("wrong_merge", "wrong_split") for o, _, _ in r) for r, _ in per)
    arr_ok = sum(all(o == "correct" for o, _, _ in r) for r, _ in per)
    unres_truth = Counter(t for r, _ in per for o, _, t in r if o == "unresolved")
    row = {"components": n, "correct": fmt_rate(cnt["correct"], n), "unresolved": fmt_rate(cnt["unresolved"], n),
           "silent": fmt_rate(cnt["wrong_merge"] + cnt["wrong_split"], n), "merge": cnt["wrong_merge"], "split": cnt["wrong_split"],
           "unresolved_would_have_been": dict(unres_truth),
           "arrays_all_correct": fmt_rate(arr_ok, len(docs)), "arrays_with_unresolved": fmt_rate(arr_unres, len(docs)),
           "arrays_silently_wrong": fmt_rate(arr_silent, len(docs)),
           "by_template": {t: dict(Counter(o for d, (r, _) in zip(docs, per) if d["template"] == t for o, _, _ in r)) for t in sorted({d["template"] for d in docs})}}
    if policy == "rev5":
        # cascade: components blanked only by the cross condition
        blank_per_trigger, docs_single_multi, cross_only_total, cross_only_correct = [], 0, 0, 0
        for d, (r, info) in zip(docs, per):
            co = info["cross_only"]; cross_only_total += len(co)
            cross_only_correct += sum(1 for i in co if r[i][2] == "correct")
            for (i, j, x, y, p) in info["cross_pairs"]:
                blank_per_trigger.append(len({i, j} - info["internal"]))
            trig_comp_pairs = {(i, j) for (i, j, *_ ) in info["cross_pairs"]}
            if len(trig_comp_pairs) == 1 and len(co) >= 2: docs_single_multi += 1
        row["cascade"] = {"trigger_pairs": len(blank_per_trigger),
                          "components_newly_blanked_per_trigger_pair": dict(Counter(blank_per_trigger)),
                          "components_blanked_only_by_cross_condition": cross_only_total,
                          "of_which_would_have_been_correct": cross_only_correct,
                          "docs_where_ONE_uncertain_cross_link_blanks_>=2_components": docs_single_multi,
                          "docs_with_>=3_components_blanked": sum(sum(o == "unresolved" for o, _, _ in r) >= 3 for r, _ in per)}
    return row, per


def analyse():
    L = lambda n: json.loads((RAW / n).read_text())
    runs = {"A": (L("r3_entity_runA.json"), L("r3_entity_hard_runA.json")), "B": (L("r3_entity_runB.json"), L("r3_entity_hard_runB.json"))}
    rep = {}
    for run, (main, hard) in runs.items():
        for label, docs in (("MAIN", main), ("HARD", hard), ("ALL", main + hard)):
            base = analyse_run(docs, f"{label}_{run}"); fl = base["selected_floor"]
            base["policies"] = {}
            pols = [("plain_cc", "plain", None), ("rev3_whole_array", "rev3", None), (f"internal_only@{fl}", "internal", fl),
                    (f"REV5@{fl}(selected)", "rev5", fl), ("internal_only@0.3", "internal", 0.30), ("rev5@0.3(in-sample floor)", "rev5", 0.30)]
            pols += [(f"rev5@{g}", "rev5", g) for g in GRID if g not in (fl, 0.30)]
            for name, pol, f in pols:
                row, per = policy_table(docs, pol, f); base["policies"][name] = row
                if pol in ("rev5", "internal") and f in (fl, 0.30):
                    det = []
                    for d, (r, info) in zip(docs, per):
                        P = {(q["a"], q["b"]): q["p"] for q in d["pairs"]}
                        for o, c, t in r:
                            if o in ("wrong_merge", "wrong_split"):
                                cross = [P[pkey(x, y)] for x in c for y in range(len(d["mentions"])) if y not in c]
                                det.append({"template": d["template"], "kind": o, "component": [d["mentions"][k][0] for k in c],
                                            "min_internal": min([P[(x, y)] for x, y in itertools.combinations(c, 2)] or [None]),
                                            "max_cross": max(cross or [None])})
                    base.setdefault("silent_detail", {})[name] = det
            rep[f"{label}_{run}"] = base
    for label in ("MAIN", "HARD"):
        pa = [q["p"] for d in runs["A"][label == "HARD"] for q in d["pairs"]]; pb = [q["p"] for d in runs["B"][label == "HARD"] for q in d["pairs"]]
        rep[f"AB_{label}"] = {"pairs": len(pa), "max_abs_diff": round(max(abs(x - y) for x, y in zip(pa, pb)), 2),
                              "pairs_diff>0.10": sum(abs(x - y) > .10 for x, y in zip(pa, pb)),
                              "decision_flips(>0.5)": sum((x > .5) != (y > .5) for x, y in zip(pa, pb))}
    allA = runs["A"][0] + runs["A"][1]
    rep["lowest_same_A"] = sorted(((q["p"], d["template"], q["ma"], q["mb"]) for d in allA for q in d["pairs"] if q["gold_same"]))[:25]
    rep["highest_diff_A"] = sorted(((q["p"], d["template"], q["ma"], q["mb"]) for d in allA for q in d["pairs"] if not q["gold_same"]), reverse=True)[:25]
    (RAW / "r3_entity_analysis.json").write_text(json.dumps(rep, indent=1, default=str))
    for k, v in rep.items():
        if not isinstance(v, dict) or "policies" not in v: print(k, v); continue
        print("=====", k)
        for kk in ("n_same", "n_diff", "pair_acc", "false_merge_pairs", "false_split_pairs", "selected_floor", "rule_stop", "same_le",
                   "hist_same", "hist_diff", "non_transitive", "docs_with_violation", "clique_completeness"):
            print(" ", kk, v[kk])
        for p, sr in v["policies"].items():
            print(f"   {p:28s} C {sr['correct']:34s} U {sr['unresolved']:34s} S {sr['silent']:34s} merge {sr['merge']} split {sr['split']} | "
                  f"arrays>=1U {sr['arrays_with_unresolved']} arraysS {sr['arrays_silently_wrong']} | U-was {sr['unresolved_would_have_been']}"
                  + (f" | cascade {sr['cascade']}" if 'cascade' in sr else ""))
        print("  silent detail:", json.dumps(v.get("silent_detail", {})))


if __name__ == "__main__":
    if sys.argv[1] == "run": asyncio.run(run(sys.argv[2], len(sys.argv) > 3 and sys.argv[3] == "hard"))
    else: analyse()
