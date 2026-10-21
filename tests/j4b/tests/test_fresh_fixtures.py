"""H13: the fresh fixtures' freshness and shape (design §2.1-§2.3, §2.6; plan §4.1, FEAS48-R5-7, FEAS48-R10-1).

Each check is a function returning its problems, run on the build (no problem) and on each planted violation the
plan names (at least one problem).
"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import random
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import pytest

from tests.j4b import redraft
from tests.j4b.fresh import build_fresh_sets as builder
from tests.j4b.fresh.pins import canonical_file
from tests.j4b.fresh.sources import SEED, load_rset_documents
from tests.j4b.tests import fresh_data

Records = dict[str, dict[str, Any]]
Rows = dict[str, list[dict[str, Any]]]
VERBS = ["mentions", "includes", "names", "states", "states_same"]
ECHOES, TOPICS, VALUES = ["verbatim", "paraphrase", "generic"], ["yes", "no"], ["amount", "date", "name", "identifier"]
PAIRS = [["return_email", "travel_change"], ["return_email", "billing_dispute"], ["travel_change", "billing_dispute"]]


def cell_index(record: Mapping[str, Any]) -> int:
    """The pinned order echo > verb > topic > value (FEAS48-R5-7)."""
    e, v = ECHOES.index(record["echo"]), VERBS.index(record["verb"])
    t, k = TOPICS.index(record["topic"]), VALUES.index(record["value"])
    return ((e * 5 + v) * 2 + t) * 4 + k


def iset_problems(records: Records, rows: Rows) -> list[str]:
    problems: list[str] = []
    cells = {k: r for k, r in records.items() if k.startswith("c")}
    if sorted(cell_index(r) for r in cells.values()) != list(range(120)):
        problems.append("the 120 cells are not the 5 x 3 x 2 x 4 factorial")
    for cid, r in {**cells, **{k: v for k, v in records.items() if k.startswith("d")}}.items():
        i = r["cell_index"]
        if i != cell_index(r) or r["position"] != ["note", "parenthetical", "natural"][i % 3]:
            problems.append(f"{cid}: cell index or claim position off the pinned rule")
        if r["domain_pair"] != PAIRS[(i // 3) % 3]:
            problems.append(f"{cid}: domain pair off the pinned rule")
    for field in ("criterion", "claim"):
        if len({r[field] for r in cells.values()}) != 120:
            problems.append(f"two cells share a {field} string")
    dev = sorted(r["cell_index"] for k, r in records.items() if k.startswith("d"))
    if dev != sorted(random.Random(SEED).sample(range(120), 32)):
        problems.append("the I-dev cells are not random.Random(20261019).sample(range(120), 32)")
    problems += _iset_rows(rows)
    return problems


def _iset_rows(rows: Rows) -> list[str]:
    problems: list[str] = []
    confirm = rows["iset.jsonl"]
    by_cell: dict[str, list[dict[str, Any]]] = {}
    for row in confirm:
        by_cell.setdefault(row["cell"], []).append(row)
    if len(by_cell) != 121 or len({r["case"] for r in confirm}) != 256:
        problems.append("not 121 cells and 256 cases")
    for cell, cell_rows in by_cell.items():
        cases = {r["case"]: [x["role"] for x in cell_rows if x["case"] == r["case"]] for r in cell_rows}
        if any(sorted(roles) != ["companion", "injected"] for roles in cases.values()):
            problems.append(f"{cell}: a case without both drafts")
        domains = {r["domain"] for r in cell_rows if r["role"] == "injected"}
        if cell != "replica" and (len(domains) != 2 or sorted(domains) != sorted(cell_rows[0]["domain_pair"])):
            problems.append(f"{cell}: its two cases are not on its two domains")
    replica = {r["source"] for r in by_cell.get("replica", [])}
    others = {r["source"] for r in confirm if r["cell"] != "replica"}
    if len(replica) != 16 or replica & others:
        problems.append("the replica's 16 cases are not on 16 fresh sources")
    if len({(r["cell"], r["case"]) for r in rows["iset_dev.jsonl"]}) != 64:
        problems.append("I-dev is not 32 cells x 2 cases")
    return problems


def balance_problems(records: Records) -> list[str]:
    """Claim position against echo and domain pair: 13 or 14 cells; against verb 8, topic 20, value 10."""
    cells = [r for k, r in records.items() if k.startswith("c")]
    problems: list[str] = []
    for factor, allowed in (("echo", {13, 14}), ("domain_pair", {13, 14}), ("verb", {8}), ("topic", {20}),
                            ("value", {10})):  # fmt: skip
        table = Counter((r["position"], json.dumps(r[factor])) for r in cells)
        if set(table.values()) - allowed or len(table) != 3 * len({json.dumps(r[factor]) for r in cells}):
            problems.append(f"claim position x {factor}: {sorted(set(table.values()))}")
    return problems


def pset_problems(records: Records, rows: Rows) -> list[str]:
    problems: list[str] = []
    confirm = [r for k, r in records.items() if k.startswith("p")]
    sizes = Counter(r["pattern"] for r in confirm)
    if sizes != {"plain": 16, "as_given": 16, "negated": 32, "disjunction": 32, "universal": 32}:
        problems.append(f"pattern split {dict(sizes)}")
    dev = [r for k, r in sorted(records.items()) if k.startswith("q")]
    if [r["pattern"] for r in dev] != ["plain", "as_given", "negated", "negated", "disjunction", "disjunction",
                                       "universal", "universal"]:  # fmt: skip
        problems.append("P-dev is not 1/1/2/2/2 per pattern")
    if [r["benign_index"] for r in dev] != random.Random(SEED).sample(range(128), 8):
        problems.append("P-dev benign combinations are not random.Random(20261019).sample(range(128), 8)")
    if sorted(r["benign_index"] for r in confirm) != list(range(128)):
        problems.append("the 128 benign wordings are not the full factorial, one per pair")
    for name, pairs in (("pset.jsonl", 128), ("pset_dev.jsonl", 8)):
        per_pair = Counter((r["pair"], r["label"], r["benign"], r["targeted_self_claim"]) for r in rows[name])
        expected = {"PASS": {True: 3, False: 3}, "FAIL": {True: 4, False: 2}}
        for (pair, label, benign, claim), n in per_pair.items():
            flag = benign if label == "PASS" else claim
            if n != expected[label][flag]:
                problems.append(f"{pair}: {label} drafts not 6 with 3 benign / 4 self-claims")
        if len({r["pair"] for r in rows[name]}) != pairs or len({r["source"] for r in rows[name]}) != pairs * 12:
            problems.append(f"{name}: not {pairs} pairs on {pairs * 12} distinct sources")
    return problems


def rset_problems(
    rows: Rows, picked: Mapping[str, Sequence[str]], loader: Callable[[Sequence[str]], list[Any]]
) -> list[str]:
    problems: list[str] = []
    manifest = {r["doc_id"]: r for r in map(json.loads, (redraft.CORPUS / "manifest.jsonl").read_text().splitlines())}
    sizes = {"confirm": {"receipt": 26, "contract": 18, "product_listing": 20, "resume": 14, "support_ticket": 12,
                         "medical_intake": 10},
             "dev": {"receipt": 8, "contract": 6, "product_listing": 6, "resume": 4, "support_ticket": 3,
                     "medical_intake": 3}}  # fmt: skip
    for phase, name, units in (("confirm", "rset.jsonl", 300), ("dev", "rset_dev.jsonl", 90)):
        docs = loader(picked[phase])
        if [d.doc_id for d in docs] != list(picked[phase]) or len(set(picked[phase])) != len(picked[phase]):
            problems.append(f"{phase}: the loader does not return exactly the picked documents in order")
            continue
        digests = {r["doc_id"]: r["doc_sha256"] for r in rows[name]}
        for doc in docs:
            raw = (redraft.CORPUS / manifest[doc.doc_id]["path"]).read_bytes().decode("utf-8")
            if doc.text != raw or digests.get(doc.doc_id) != hashlib.sha256(raw.encode("utf-8")).hexdigest():
                problems.append(f"{doc.doc_id}: text or digest differs from the corpus")
        if dict(Counter(d.domain for d in docs)) != sizes[phase]:
            problems.append(f"{phase}: per-domain counts {dict(Counter(d.domain for d in docs))}")
        if len(rows[name]) != units or Counter(Counter(r["doc_id"] for r in rows[name]).values()) != {3: units // 3}:
            problems.append(f"{phase}: not {units} first-draft units at three fields per document")
    return problems


# --- on the build -------------------------------------------------------------------------------------


def test_h13_the_build_has_the_designs_shape() -> None:
    authored, rows = fresh_data.authored(), fresh_data.rows()
    assert iset_problems(authored["iset_wordings.json"], rows) == []
    assert balance_problems(authored["iset_wordings.json"]) == []
    assert pset_problems(authored["pset_templates.json"], rows) == []
    assert rset_problems(rows, fresh_data.picked(), load_rset_documents) == []


def test_h13_summary_and_authored_files_are_canonical_and_derived() -> None:
    data = {name: (builder.FIXTURES / name).read_bytes() for name in builder.ROW_FILES}
    picked = builder.PICKED.read_bytes()
    summary = (builder.FIXTURES / "summary.json").read_text(encoding="utf-8")
    assert summary == builder.summarise(data, picked)
    sha = json.loads(summary)["sha256"]
    assert sha["picked.json"] == hashlib.sha256(picked).hexdigest()
    assert all(sha[n] == hashlib.sha256(b).hexdigest() for n, b in data.items())
    for name in builder.AUTHORED:
        text = (builder.FRESH / name).read_text(encoding="utf-8")
        assert text == canonical_file(json.loads(text))
    for name, payload in data.items():
        assert payload == builder.row_bytes(fresh_data.rows()[name])


def test_h13_rebuilding_from_the_authored_data_gives_the_committed_rows() -> None:
    rows = builder.build(fresh_data.authored(), fresh_data.picked())
    assert {n: builder.row_bytes(r) for n, r in rows.items()} == {
        n: (builder.FIXTURES / n).read_bytes() for n in builder.ROW_FILES
    }


def test_h13_the_j4b_fields_are_copied_verbatim_and_no_field_has_a_description() -> None:
    fields = fresh_data.authored()["rset_fields.json"]
    for domain, specs in redraft.DOMAINS.items():
        for spec in specs:
            record = fields[f"{domain}.{spec.pointer.removeprefix('/')}"]
            assert (record["origin"], record["pointer"], record["instructions"]) == (
                "j4b",
                spec.pointer,
                spec.instructions,
            )
            assert record["f0"] == list(spec.criteria)
    assert sorted(Counter(k.split(".")[0] for k in fields).values()) == [3] * 6
    assert not [k for k, r in fields.items() if "description" in r]


# --- planted violations, each caught ------------------------------------------------------------------


def _iset() -> Records:
    return copy.deepcopy(fresh_data.authored()["iset_wordings.json"])


def _plant_idev_seed(records: Records) -> None:
    other = sorted(random.Random(1).sample(range(120), 32))
    for (key, record), index in zip(
        sorted((k, r) for k, r in records.items() if k.startswith("d")), other, strict=True
    ):
        records[key] = {**record, "cell_index": index}


def _plant_duplicate(records: Records) -> None:
    records["c001"] = {**records["c000"], "criterion": records["c001"]["criterion"], "claim": records["c001"]["claim"]}


@pytest.mark.parametrize(
    "plant",
    [
        _plant_idev_seed,
        _plant_duplicate,
        lambda r: r["c007"].update(position="note"),
        lambda r: r["c010"].update(domain_pair=["return_email", "return_email"]),
        lambda r: r["c011"].update(claim=r["c012"]["claim"]),
    ],
    ids=[
        "I-dev drawn with another seed",
        "duplicated combination",
        "wrong claim position",
        "both cases in one domain",
        "two cells share a claim",
    ],
)
def test_h13_planted_i_set_violations_are_caught(plant: Callable[[Records], None]) -> None:
    records = _iset()
    plant(records)
    assert iset_problems(records, fresh_data.rows())


def test_h13_planted_row_violations_are_caught() -> None:
    rows = fresh_data.copy_rows()
    case = next(r for r in rows["iset.jsonl"] if r["cell"] == "c003" and r["role"] == "injected")
    twin = next(r for r in rows["iset.jsonl"] if r["cell"] == "c003" and r["case"] != case["case"])
    case["domain"] = twin["domain"]
    assert iset_problems(_iset(), rows)
    rows = fresh_data.copy_rows()
    replica = next(r for r in rows["iset.jsonl"] if r["cell"] == "replica")
    replica["source"] = rows["iset.jsonl"][0]["source"]
    assert iset_problems(_iset(), rows)


@pytest.mark.parametrize(
    "order",
    [
        lambda i: (i // 3 % 4, i // 24, i // 12 % 2, i % 3),
        lambda i: (i // 6 % 4, i // 24, i // 3 % 2, i % 3),
    ],
    ids=["echo enumerated fastest", "verb > value > topic > echo"],
)
def test_h13_another_enumeration_order_or_an_aliased_domain_breaks_the_balance(
    order: Callable[[int], tuple[int, ...]],
) -> None:
    records = _iset()
    for key, record in records.items():
        if key.startswith("c"):
            i = record["cell_index"]
            value, verb, topic, echo = order(i)
            record.update(value=VALUES[value], verb=VERBS[verb], topic=TOPICS[topic], echo=ECHOES[echo])
    assert balance_problems(records)
    aliased = _iset()
    for key, record in aliased.items():
        if key.startswith("c"):
            record["domain_pair"] = PAIRS[record["cell_index"] % 3]
    assert balance_problems(aliased)


@pytest.mark.parametrize(
    "plant",
    [
        lambda r: r["q007"].update(pattern="plain"),
        lambda r: r["q000"].update(benign_index=(r["q000"]["benign_index"] + 1) % 128),
        lambda r: r["p020"].update(pattern="plain"),
    ],
    ids=["P-dev split 2/2/2/1/1", "P-dev benign draw off the seed", "pattern split off 16/16/32/32/32"],
)
def test_h13_planted_p_set_violations_are_caught(plant: Callable[[Records], None]) -> None:
    records = copy.deepcopy(fresh_data.authored()["pset_templates.json"])
    plant(records)
    assert pset_problems(records, fresh_data.rows())


def test_h13_an_r_set_loader_built_on_j4b_documents_drops_the_receipts() -> None:
    by_id = {d.doc_id: d for d in redraft.documents()}

    def j4b_loader(ids: Sequence[str]) -> list[Any]:
        return [by_id[i] for i in ids if i in by_id]

    assert len(j4b_loader(fresh_data.picked()["confirm"])) == 74
    assert rset_problems(fresh_data.rows(), fresh_data.picked(), j4b_loader)
    assert rset_problems(fresh_data.rows(), fresh_data.picked(), lambda ids: load_rset_documents(list(ids)[::-1]))


def test_h13_every_balance_count_matches_the_plan() -> None:
    cells = [r for k, r in fresh_data.authored()["iset_wordings.json"].items() if k.startswith("c")]
    by = {f: Counter((r["position"], json.dumps(r[f])) for r in cells) for f in ("echo", "domain_pair", "verb")}
    assert set(by["echo"].values()) <= {13, 14}
    assert set(by["domain_pair"].values()) <= {13, 14}
    assert set(by["verb"].values()) == {8}
    assert list(itertools.islice(sorted(cell_index(r) for r in cells), 3)) == [0, 1, 2]
