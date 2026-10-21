"""The grader's blind items and the held-back key, and the labels' way back (design §3 "Hand-off"; plan §4.1
`export_items.py`; STATS48-R4-4).

- **Items.** Every R-set first draft is graded against its field's `F0` criteria (truth) and `F1` criteria (the
  sanity count; it never sets truth), and every redraft against `F0`. A malformed draft is never an item. Items are
  deduplicated by (source, criterion texts, draft), so one truth applies to every configuration that produced the
  draft. The 96 diagnostic P-set items (`diagnostic_ids`, always drawn from the committed confirm P-set) are added
  with their `F0` criterion. The stream goes
  through `prepare_items.split`: random 48-bit ids and a shuffle, exactly `ITEM_KEYS` per item.
- **Key.** `key.jsonl` holds `prepare_items.split`'s rows and, per instance, every (configuration, draft id, role,
  form, admitted) that shares it; it stays in the run directory.
- **Chunks** of at most 72,000 characters of item JSON, newlines included, never splitting an item.
- **Labels** come back as `labels-NNN.jsonl`; every item is labelled exactly once with every criterion id
  (`records.label`), and `rset_truths` joins them to the key.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.j4b.fresh import rules, workload
from tests.j4b.fresh.bar_inputs import RFirst
from tests.j4b.fresh.constants import CHUNK_CHARS, DIAGNOSTIC_SEED
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.workload import Workload
from tests.j4b.labelling import prepare_items
from tests.j4b.labelling.records import ITEM_KEYS, Label, label, read_jsonl

PATTERN_SPLIT = (16, 16, 32, 32, 32)
DIAGNOSTIC_PER_LABEL = 48
"""48 PASS and 48 FAIL, allocated over the five patterns in proportion to the 16/16/32/32/32 pair split."""


class ExportDefect(Exception):
    """An item over the chunk bound, or labels that do not cover the items exactly."""


def draft_id(doc_id: str, pointer: str) -> str:
    return f"{doc_id}/{pointer.removeprefix('/')}"


@dataclass
class Stream:
    """Deduplicated grading instances: (source, criteria, draft) -> the run row and every use of it."""

    rows: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])
    uses: dict[str, list[dict[str, Any]]] = field(default_factory=dict[str, list[dict[str, Any]]])

    def add(self, source: str, field_name: str, criteria: Sequence[str], draft: str, use: Mapping[str, Any]) -> str:
        instance = hashlib.sha256(json.dumps([source, list(criteria), draft]).encode()).hexdigest()[:24]
        if instance not in self.rows:
            self.rows[instance] = {
                "instance_id": instance, "role": "first", "admitted": False, "source": source, "field": field_name,
                "criteria": [{"id": f"c{i}", "statement": c} for i, c in enumerate(criteria)], "draft": draft,
            }  # fmt: skip
        self.uses.setdefault(instance, []).append(dict(use))
        return instance


def allocation() -> list[int]:
    return [DIAGNOSTIC_PER_LABEL * k // sum(PATTERN_SPLIT) for k in PATTERN_SPLIT]


def diagnostic_ids(pset_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The 96 diagnostic drafts: `random.Random(4858)`; per pattern, in order of first appearance, PASS then
    FAIL, `allocation()` drafts each, drawn from that pattern's sorted draft ids."""
    rng, patterns = random.Random(DIAGNOSTIC_SEED), list(dict.fromkeys(str(r["pattern"]) for r in pset_rows))
    if len(patterns) != len(PATTERN_SPLIT):
        raise ExportDefect(f"expected {len(PATTERN_SPLIT)} P-set patterns, found {len(patterns)}")
    chosen: list[str] = []
    for pattern, k in zip(patterns, allocation(), strict=True):
        for verdict in ("PASS", "FAIL"):
            pool = sorted(str(r["draft_id"]) for r in pset_rows if r["pattern"] == pattern and r["label"] == verdict)
            chosen += rng.sample(pool, k)
    return chosen


def build_stream(w: Workload, outcomes: Mapping[Unit, Mapping[str, Any]]) -> Stream:
    """Every R-set draft's items and the diagnostic items, deduplicated."""
    s = Stream()
    for unit, record in sorted(outcomes.items(), key=lambda kv: (kv[0].key, kv[0].arm, kv[0].form)):
        if unit.set_name != "rset":
            continue
        doc = w.documents[unit.key]
        for spec in w.fields[doc.domain]:
            pointer, got = str(spec["pointer"]), record["fields"][str(spec["pointer"])]
            did, config = draft_id(doc.doc_id, pointer), f"{unit.arm}{unit.form}"
            use = {"set": "rset", "config": config, "draft_id": did}
            first = {**use, "role": "first", "admitted": got["first_admitted"]}
            if got["first"] is not None:
                s.add(doc.text, pointer, spec["f0"], got["first"], {**first, "form": "F0"})
                s.add(doc.text, pointer, spec["f1"], got["first"], {**first, "form": "F1"})
            if got["redraft"] is not None:
                redraft = {**use, "role": "redraft", "admitted": got["redraft_admitted"], "form": "F0"}
                s.add(doc.text, pointer, spec["f0"], got["redraft"], redraft)
    by_id = {str(r["draft_id"]): r for r in workload.read_rows(workload.ROW_FILE["confirm"]["pset"])}
    for did in diagnostic_ids(list(by_id.values())):
        row = by_id[did]
        use = {"set": "diagnostic", "draft_id": did, "code_verdict": row["label"] == "PASS", "form": "F0"}
        s.add(row["source"], "/summary", [row["criterion_f0"]], row["draft"], use)
    return s


def export(s: Stream, rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(items, key): `prepare_items.split` over the stream, each key row carrying its instance's uses."""
    items, key = prepare_items.split(list(s.rows.values()), rng)
    for row in key:
        row["uses"] = s.uses[row["instance_id"]]
    if any(frozenset(item) != ITEM_KEYS for item in items):
        raise ExportDefect("an item holds a key other than ITEM_KEYS")
    return items, key


def chunks(items: Sequence[Mapping[str, Any]], bound: int = CHUNK_CHARS) -> list[str]:
    """`items.jsonl` cut, in order, into chunks of at most `bound` characters, never splitting an item."""
    out: list[str] = []
    current = ""
    for item in items:
        line = json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
        if len(line) > bound:
            raise ExportDefect(f"item {item['id']} is {len(line)} characters, over the {bound}-character bound")
        if len(current) + len(line) > bound:
            out.append(current)
            current = ""
        current += line
    return [*out, current] if current else out


def write(directory: Path, items: Sequence[Mapping[str, Any]], key: Sequence[Mapping[str, Any]]) -> list[Path]:
    """`items.jsonl`, `key.jsonl` and the chunk files `chunks/items-NNN.jsonl` under `directory`."""
    (directory / "chunks").mkdir(parents=True, exist_ok=False)
    lines = "".join(json.dumps(i, ensure_ascii=False, sort_keys=True) + "\n" for i in items)
    (directory / "items.jsonl").write_text(lines, encoding="utf-8")
    (directory / "key.jsonl").write_text(
        "".join(json.dumps(k, ensure_ascii=False, sort_keys=True) + "\n" for k in key), encoding="utf-8"
    )
    paths: list[Path] = []
    for n, text in enumerate(chunks(items), 1):
        path = directory / "chunks" / f"items-{n:03d}.jsonl"
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths


def read_labels(labels_dir: Path, items: Sequence[Mapping[str, Any]]) -> dict[str, Label]:
    """Every item labelled exactly once, with exactly its criterion ids, each a boolean."""
    found: dict[str, Label] = {}
    for path in sorted(labels_dir.glob("labels-*.jsonl")):
        for obj in read_jsonl(path):
            got = label(obj)
            if got.item_id in found:
                raise ExportDefect(f"item {got.item_id} is labelled twice")
            found[got.item_id] = got
    expected = {str(i["id"]): {str(c["id"]) for c in i["criteria"]} for i in items}
    if set(found) != set(expected):
        raise ExportDefect(f"labels cover {len(found)} items, not the {len(expected)} exported")
    for item_id, ids in expected.items():
        if set(found[item_id].criteria) != ids:
            raise ExportDefect(f"item {item_id}: labelled criteria differ from the item's")
    return found


def truths(key: Sequence[Mapping[str, Any]], labels: Mapping[str, Label]) -> dict[tuple[str, str, str, str], bool]:
    """(config, draft id, role, form) -> the grader's truth, for every R-set use of a labelled item."""
    out: dict[tuple[str, str, str, str], bool] = {}
    for row in key:
        if row["item_id"] is None:
            continue
        for use in row["uses"]:
            if use["set"] == "rset":
                out[(use["config"], use["draft_id"], use["role"], use["form"])] = labels[row["item_id"]].satisfies
    return out


def rset_truths(
    w: Workload, outcomes: Mapping[Unit, Mapping[str, Any]], truth: Mapping[tuple[str, str, str, str], bool]
) -> dict[rules.Config, dict[str, RFirst]]:
    """`Outcomes.rset`: per configuration and draft, admissions with F0 truth (a malformed draft is never true)."""
    out: dict[rules.Config, dict[str, RFirst]] = {}
    for unit, record in outcomes.items():
        if unit.set_name != "rset":
            continue
        for pointer, got in record["fields"].items():
            did, config = draft_id(unit.key, pointer), f"{unit.arm}{unit.form}"
            out.setdefault((unit.arm, unit.form), {})[did] = RFirst(
                got["first_admitted"], got["redraft_admitted"],
                truth.get((config, did, "first", "F0"), False), truth.get((config, did, "redraft", "F0"), False),
            )  # fmt: skip
    return out


def secondaries(key: Sequence[Mapping[str, Any]], labels: Mapping[str, Label]) -> dict[str, Any]:
    """The grader's agreement with the code checker on the diagnostic items, and the F0/F1 disagreement of R-set
    first drafts in each direction, with the F1-but-not-F0 drafts listed (design §3; never re-labelled)."""
    agree = total = 0
    forms: dict[tuple[str, str], dict[str, bool]] = {}
    for row in key:
        if row["item_id"] is None:
            continue
        satisfied = labels[row["item_id"]].satisfies
        for use in row["uses"]:
            if use["set"] == "diagnostic":
                total, agree = total + 1, agree + (satisfied == use["code_verdict"])
            elif use["role"] == "first":
                forms.setdefault((use["config"], use["draft_id"]), {})[use["form"]] = satisfied
    f1_only = sorted({d for (_, d), v in forms.items() if v.get("F1") and v.get("F0") is False})
    f0_only = sorted({d for (_, d), v in forms.items() if v.get("F0") and v.get("F1") is False})
    disagreement = {"f1_not_f0": len(f1_only), "f0_not_f1": len(f0_only), "f1_not_f0_drafts": f1_only}
    return {"diagnostic_agreement": {"agree": agree, "of": total}, "f0_f1_disagreement": disagreement}
