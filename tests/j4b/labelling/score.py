"""Join the labels with the held-back key and compute the redraft bar (PLAN Phase 4, last exit criterion).

Usage: uv run --frozen python -m tests.j4b.labelling.score KEY.jsonl LABELS.jsonl [--out report.json]

A draft *truly satisfies* its criteria when the labeller answered yes to every one; it *violates* them when any
answer is no. A null draft (no draft was produced) is not admitted and is never labelled.

- A: redrafts admitted and truly satisfying / redrafts (bar: >= 10%)
- B: redrafts admitted while violating / redrafts
- C: first drafts admitted while violating / first drafts
- B - C with Newcombe's unpaired interval (bar: B - C <= 2 points); redrafts and first drafts are distinct drafts
- paired: over instances whose first draft was rejected, truly-satisfies(redraft) - truly-satisfies(first draft),
  with Newcombe's paired interval; this is the "paired difference from first drafts"
The default `redraft_budget` stays 1 only if A >= 0.10 and B - C <= 0.02 (point estimates); otherwise it becomes 0.
Decoy drafts are labelled for blinding only and are excluded from every number.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from tests.j4b.labelling.intervals import newcombe_paired, newcombe_unpaired, wilson
from tests.j4b.labelling.records import KeyRow, Label, key_row, label, read_jsonl

MIN_REJECTED = 100
A_FLOOR = 0.10
B_MINUS_C_CEILING = 0.02


def join(key: Sequence[KeyRow], labels: Sequence[Label]) -> dict[str, Label]:
    """Labels by item id; every labelled key row must have exactly one complete label, and nothing else."""
    by_id: dict[str, Label] = {}
    for lab in labels:
        if lab.item_id in by_id:
            raise ValueError(f"item {lab.item_id} is labelled twice")
        by_id[lab.item_id] = lab
    wanted = {r.item_id: r for r in key if r.item_id is not None}
    unknown = sorted(set(by_id) - set(wanted))
    missing = sorted(set(wanted) - set(by_id))
    if unknown or missing:
        raise ValueError(f"labels do not match the key: {len(missing)} unlabelled, {len(unknown)} unknown ids")
    for item_id, row in wanted.items():
        if set(by_id[item_id].criteria) != set(row.criterion_ids):
            raise ValueError(f"item {item_id}: labelled criteria differ from the item's criteria")
    return by_id


def _satisfies(row: KeyRow, labels: Mapping[str, Label]) -> bool:
    return row.item_id is not None and labels[row.item_id].satisfies


def _instances(key: Sequence[KeyRow]) -> dict[str, dict[str, KeyRow]]:
    out: dict[str, dict[str, KeyRow]] = {}
    for r in key:
        if r.role == "decoy":
            continue
        slot = out.setdefault(r.instance_id, {})
        if r.role in slot:
            raise ValueError(f"instance {r.instance_id} has two {r.role} drafts")
        slot[r.role] = r
    for iid, slot in out.items():
        if "first" not in slot:
            raise ValueError(f"instance {iid} has no first draft")
        if "redraft" in slot and slot["first"].admitted:
            raise ValueError(f"instance {iid} has a redraft although its first draft was admitted")
    return out


def _rate(k: int, n: int) -> dict[str, Any]:
    return {"k": k, "n": n, **asdict(wilson(k, n))}


def score(key: Sequence[KeyRow], labels: Sequence[Label]) -> dict[str, Any]:
    by_id = join(key, labels)
    inst = _instances(key)
    firsts = [s["first"] for s in inst.values()]
    redrafts = [s["redraft"] for s in inst.values() if "redraft" in s]
    rejected = [s for s in inst.values() if not s["first"].admitted]
    if not redrafts:
        raise ValueError("no redrafts: nothing to score")

    a_k = sum(r.admitted and _satisfies(r, by_id) for r in redrafts)
    b_k = sum(r.admitted and not _satisfies(r, by_id) for r in redrafts)
    c_k = sum(r.admitted and not _satisfies(r, by_id) for r in firsts)
    diff = newcombe_unpaired(b_k, len(redrafts), c_k, len(firsts))

    # Paired over rejected instances: outcome 1 = the redraft truly satisfies, outcome 2 = the first draft does.
    # An instance whose budget produced no redraft row has a redraft that does not satisfy.
    cells = {"both": 0, "only_redraft": 0, "only_first": 0, "neither": 0}
    for s in rejected:
        red = "redraft" in s and _satisfies(s["redraft"], by_id)
        fst = _satisfies(s["first"], by_id)
        cells["both" if red and fst else "only_redraft" if red else "only_first" if fst else "neither"] += 1
    paired = newcombe_paired(cells["both"], cells["only_redraft"], cells["only_first"], cells["neither"])

    a = a_k / len(redrafts)
    keep = a >= A_FLOOR and diff.estimate <= B_MINUS_C_CEILING
    return {
        "instances": len(inst),
        "first_drafts": len(firsts),
        "rejected_first_drafts": len(rejected),
        "redrafts": len(redrafts),
        "A_redraft_admitted_and_satisfies": _rate(a_k, len(redrafts)),
        "B_redraft_admitted_while_violating": _rate(b_k, len(redrafts)),
        "C_first_admitted_while_violating": _rate(c_k, len(firsts)),
        "B_minus_C": asdict(diff),
        "paired_satisfies_redraft_minus_first": {**cells, **asdict(paired)},
        "bar": {
            "A_at_least": A_FLOOR,
            "B_minus_C_at_most": B_MINUS_C_CEILING,
            "redraft_budget_default": 1 if keep else 0,
            "counts_for_the_exit_criterion": len(rejected) >= MIN_REJECTED,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("key", type=Path)
    ap.add_argument("labels", type=Path)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)
    report = score([key_row(r) for r in read_jsonl(a.key)], [label(r) for r in read_jsonl(a.labels)])
    text = json.dumps(report, indent=1)
    if a.out is not None:
        a.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if not report["bar"]["counts_for_the_exit_criterion"]:
        print(
            f"warning: fewer than {MIN_REJECTED} rejected first drafts; the bar needs at least that many",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
