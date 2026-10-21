"""H24-H26, H28, H36: the grader's items, chunks, labels and truth (design §3; STATS48-R4-4)."""

from __future__ import annotations

import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import export_items, runner, scoring, workload
from tests.j4b.fresh.constants import CHUNK_CHARS
from tests.j4b.labelling.records import ITEM_KEYS, Label
from tests.j4b.tests import fake_api

LEAK = re.compile(r"\bL[0-3]\b|L[0-3]F[01]|\bF[01]\b|#criterion|#screen|\b0\.\d+\b|\bprobability\b")


def leaks(item: dict[str, Any]) -> list[str]:
    """Every configuration name, criterion form, node suffix or probability in an item's own strings."""
    texts = [
        item["field"],
        item["draft"],
        *(c["statement"] for c in item["criteria"]),
        *(c["id"] for c in item["criteria"]),
    ]
    return [m.group(0) for t in texts for m in LEAK.finditer(t)]


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> tuple[runner.Env, list[dict[str, Any]], list[dict[str, Any]]]:
    load = fake_api.loader(documents=4)
    e, _ = fake_api.env(tmp_path_factory.mktemp("export") / "fresh", load=load)
    e.p7_fixture = fake_api.p7_subset(e.root, load("confirm"))
    assert runner.run_phase(e, "dev", 1) == 0
    assert runner.run_phase(e, "confirm", 1) == 0
    assert scoring.export(e, 1) == 0
    out = e.root / "attempt-1" / "confirm" / "export"
    items = [json.loads(line) for line in (out / "items.jsonl").read_text().splitlines()]
    key = [json.loads(line) for line in (out / "key.jsonl").read_text().splitlines()]
    return e, items, key


# --- H24 ------------------------------------------------------------------------------------------------------


def test_h24_every_item_is_exactly_item_keys_and_carries_nothing_of_the_judge(exported: Any) -> None:
    _, items, key = exported
    assert items
    assert all(frozenset(i) == ITEM_KEYS for i in items)
    assert [leaks(i) for i in items if leaks(i)] == []
    planted = {**items[0], "draft": items[0]["draft"] + " (L2F1, p=0.83)"}
    assert leaks(planted)
    assert sum(len(k["uses"]) for k in key) > len(items)  # deduplication shared items across configurations


def test_h24_the_f0_and_f1_versions_of_a_draft_are_two_unrelated_items(exported: Any) -> None:
    _, items, key = exported
    by_item = {k["item_id"]: k for k in key}
    forms: dict[str, set[str]] = {}
    for item in items:
        for use in by_item[item["id"]]["uses"]:
            if use["set"] == "rset" and use["role"] == "first":
                forms.setdefault(item["draft"], set()).add(f"{use['form']}:{item['id']}")
    split = [v for v in forms.values() if len({x.split(":")[1] for x in v}) == 2]
    assert split, "some first draft has F0 and F1 criteria that differ"
    ids = [i["id"] for i in items]
    assert all(len(set(i)) == len(i) for i in [ids])


def test_h24_key_rows_join_every_use_and_stay_out_of_the_items(exported: Any) -> None:
    e, items, key = exported
    assert {k["item_id"] for k in key} == {i["id"] for i in items}
    uses = [u for k in key for u in k["uses"]]
    assert {u["set"] for u in uses} == {"rset", "diagnostic"}
    assert all({"config", "draft_id", "role", "form", "admitted"} <= set(u) for u in uses if u["set"] == "rset")
    chunks = sorted((e.root / "attempt-1" / "confirm" / "export" / "chunks").iterdir())
    assert (
        "".join(c.read_text() for c in chunks)
        == (e.root / "attempt-1" / "confirm" / "export" / "items.jsonl").read_text()
    )


# --- H25: chunks --------------------------------------------------------------------------------------------------


def test_h25_real_sized_items_chunk_under_the_bound_and_never_split() -> None:
    texts = [d.text for p in ("confirm", "dev") for d in workload.load(p).documents.values()]
    items = [{"id": f"{n:012x}", "source": t, "field": "/f", "criteria": [{"id": "c0", "statement": "x"}],
              "draft": "d" * 3187} for n, t in enumerate(texts)]  # fmt: skip
    chunks = export_items.chunks(items)
    assert all(len(c) <= CHUNK_CHARS for c in chunks)
    assert [json.loads(line)["id"] for c in chunks for line in c.splitlines()] == [i["id"] for i in items]
    by_count = [
        "".join(json.dumps(i, sort_keys=True) + "\n" for i in items[k : k + 20]) for k in range(0, len(items), 20)
    ]
    assert max(map(len, by_count)) > CHUNK_CHARS  # chunking by count would not hold the bound
    with pytest.raises(export_items.ExportDefect, match="over the"):
        export_items.chunks([{**items[0], "source": "s" * CHUNK_CHARS}])


# --- H26: labels -------------------------------------------------------------------------------------------------


def write_labels(directory: Path, labels: list[dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "labels-001.jsonl").write_text("".join(json.dumps(x) + "\n" for x in labels))


def test_h26_label_import_rejects_a_missing_a_duplicated_and_a_non_boolean_label(tmp_path: Path) -> None:
    items = [{"id": "a", "criteria": [{"id": "c0"}, {"id": "c1"}]}, {"id": "b", "criteria": [{"id": "c0"}]}]
    good = [{"id": "a", "criteria": {"c0": True, "c1": False}}, {"id": "b", "criteria": {"c0": True}}]
    write_labels(tmp_path / "ok", good)
    assert set(export_items.read_labels(tmp_path / "ok", items)) == {"a", "b"}
    for name, labels in {
        "missing": good[:1],
        "duplicated": [*good, good[1]],
        "criterion": [{"id": "a", "criteria": {"c0": True}}, good[1]],
    }.items():
        write_labels(tmp_path / name, labels)
        with pytest.raises(export_items.ExportDefect):
            export_items.read_labels(tmp_path / name, items)
    write_labels(tmp_path / "bool", [{"id": "a", "criteria": {"c0": "yes", "c1": False}}, good[1]])
    with pytest.raises(ValueError, match="true or false"):
        export_items.read_labels(tmp_path / "bool", items)


# --- H28: truth -------------------------------------------------------------------------------------------------


def test_h28_rset_truth_is_the_f0_items_label_for_every_configuration_and_f1_never_sets_it(exported: Any) -> None:
    e, items, key = exported
    by_item = {k["item_id"]: k for k in key}
    labels = {}
    for item in items:
        forms = {u.get("form") for u in by_item[item["id"]]["uses"]}
        verdict = forms != {"F1"}  # every F1-only item says False, every item with an F0 use says True
        labels[item["id"]] = Label(item["id"], {c["id"]: verdict for c in item["criteria"]}, "")
    truth = export_items.truths(key, labels)
    assert truth
    assert all(v for (_, _, _, form), v in truth.items() if form == "F0")
    w = e.load("confirm")
    outcomes = runner.outcomes_of(w, e.root / "attempt-1" / "confirm", partial=False)
    rset = export_items.rset_truths(w, outcomes, truth)
    firsts = [r for per_config in rset.values() for r in per_config.values()]
    assert firsts
    assert all(r.first_true for r in firsts)
    shared = Counter(len({u["config"] for u in k["uses"] if u.get("role") == "first"}) for k in key)
    assert max(shared) == 8  # one truth for every configuration that produced the draft


# --- H36: diagnostic items --------------------------------------------------------------------------------------


def test_h36_96_diagnostic_items_stratified_and_reproducible(exported: Any) -> None:
    _, _, key = exported
    rows = workload.read_rows("pset.jsonl")
    ids = export_items.diagnostic_ids(rows)
    by_id = {r["draft_id"]: r for r in rows}
    assert len(ids) == 96 == len(set(ids))
    counts = Counter((by_id[i]["pattern"], by_id[i]["label"]) for i in ids)
    patterns = list(dict.fromkeys(r["pattern"] for r in rows))
    assert [counts[(p, "PASS")] for p in patterns] == [6, 6, 12, 12, 12] == [counts[(p, "FAIL")] for p in patterns]
    assert export_items.diagnostic_ids(rows) == ids
    rng, redrawn = random.Random(4858), []  # the pinned draw, re-run independently
    for pattern, k in zip(patterns, (6, 6, 12, 12, 12), strict=True):
        for verdict in ("PASS", "FAIL"):
            redrawn += rng.sample(
                sorted(r["draft_id"] for r in rows if (r["pattern"], r["label"]) == (pattern, verdict)), k
            )
    assert redrawn == ids
    diagnostic = [u for k in key for u in k["uses"] if u["set"] == "diagnostic"]
    assert sorted(u["draft_id"] for u in diagnostic) == sorted(ids)
    assert all(u["form"] == "F0" and u["code_verdict"] == (by_id[u["draft_id"]]["label"] == "PASS") for u in diagnostic)


def planted_draw(rows: list[dict[str, Any]], seed: int, split: tuple[int, int]) -> list[str]:
    rng = random.Random(seed)
    passing = sorted(r["draft_id"] for r in rows if r["label"] == "PASS")
    failing = sorted(r["draft_id"] for r in rows if r["label"] == "FAIL")
    return rng.sample(passing, split[0]) + rng.sample(failing, split[1])


def test_h36_a_draw_with_another_seed_or_split_differs() -> None:
    rows = workload.read_rows("pset.jsonl")
    ids = export_items.diagnostic_ids(rows)
    assert planted_draw(rows, 4859, (48, 48)) != ids
    assert planted_draw(rows, 4858, (50, 46)) != ids
    assert export_items.allocation() == [6, 6, 12, 12, 12]
