"""The three files of the redraft-bar measurement and their validation.

- **Run record** (`run.jsonl`, written by J4b's collector): one row per draft, with the decision model's verdict.
  `{"instance_id", "role": "first" | "redraft" | "decoy", "source", "field", "criteria": [{"id", "statement"}],
  "draft": str | null, "admitted": bool}`. A `null` draft is an LLM output that produced no draft (malformed,
  over-length, or a repeat that was not re-adjudicated): it is never labelled and counts as not admitted.
- **Items** (`items.jsonl`, the only file the labeller's tool reads): `{"id", "source", "field", "criteria", "draft"}`
  and nothing else; no role, no instance, no verdict.
- **Key** (`key.jsonl`, never opened by the tool): the item id joined back to the run record.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

ROLES = ("first", "redraft", "decoy")
ITEM_KEYS = frozenset({"id", "source", "field", "criteria", "draft"})


@dataclass(frozen=True)
class KeyRow:
    item_id: str | None  # None when the draft was null and so never became an item
    instance_id: str
    role: str
    admitted: bool
    criterion_ids: tuple[str, ...]


@dataclass(frozen=True)
class Label:
    item_id: str
    criteria: Mapping[str, bool]
    note: str

    @property
    def satisfies(self) -> bool:
        return all(self.criteria.values())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError(f"{path}:{n}: expected a JSON object")
            rows.append(cast(dict[str, Any], obj))
    return rows


def write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), "utf-8")


def check_run_row(row: Mapping[str, Any], n: int) -> None:
    where = f"run row {n}"
    if row.get("role") not in ROLES:
        raise ValueError(f"{where}: role must be one of {ROLES}")
    if not isinstance(row.get("instance_id"), str) or not isinstance(row.get("admitted"), bool):
        raise ValueError(f"{where}: needs a string instance_id and a bool admitted")
    if row.get("draft") is None and row["admitted"]:
        raise ValueError(f"{where}: a null draft cannot be admitted")
    criteria = row.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError(f"{where}: needs a non-empty criteria list")


def criterion_ids(criteria: Iterable[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(str(c["id"]) for c in criteria)


def key_row(obj: Mapping[str, Any]) -> KeyRow:
    return KeyRow(obj["item_id"], obj["instance_id"], obj["role"], obj["admitted"], tuple(obj["criterion_ids"]))


def label(obj: Mapping[str, Any]) -> Label:
    crit = obj.get("criteria")
    if not isinstance(obj.get("id"), str) or not isinstance(crit, dict):
        raise ValueError(f"label needs a string id and a criteria object: {obj!r}")
    crit = cast(dict[str, Any], crit)
    if not all(isinstance(v, bool) for v in crit.values()):
        raise ValueError(f"label {obj['id']}: every criterion must be true or false")
    return Label(obj["id"], cast(dict[str, bool], crit), str(obj.get("note", "")))
