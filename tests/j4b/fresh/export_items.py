"""The grader's blind items and the held-back key, and the labels' way back (design §3 "Hand-off"; plan §4.1
`export_items.py`; STATS48-R4-4). Serialisation only: which drafts are graded under which form, the diagnostic
draw and the truth join are `grading.py`'s, frozen (STATS48B-R1-2).

- **Items.** Every `grading.uses` entry, deduplicated by (source, criterion texts, draft), so one truth applies to
  every configuration that produced the draft. The stream goes through `prepare_items.split`: random 48-bit ids
  and a shuffle, exactly `ITEM_KEYS` per item.
- **Key.** `key.jsonl` holds `prepare_items.split`'s rows and, per instance, every (configuration, draft id, role,
  form, admitted) that shares it; it stays in the run directory.
- **Chunks** of at most 72,000 characters of item JSON, newlines included, never splitting an item.
- **Labels** come back as `labels-NNN.jsonl`; every item is labelled exactly once with every criterion id
  (`records.label`), and `grading.rset_truths` joins them to the key.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tests.j4b.fresh import grading
from tests.j4b.fresh.constants import CHUNK_CHARS
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.workload import Workload
from tests.j4b.labelling import prepare_items
from tests.j4b.labelling.records import ITEM_KEYS, Label, label, read_jsonl


class ExportDefect(Exception):
    """An item over the chunk bound, or labels that do not cover the items exactly."""


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


def build_stream(w: Workload, records: Mapping[Unit, Mapping[str, Any]]) -> Stream:
    """Every graded use (`grading.uses`), deduplicated."""
    s = Stream()
    for u in grading.uses(w, records):
        s.add(u.source, u.field, u.criteria, u.draft, u.use)
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
