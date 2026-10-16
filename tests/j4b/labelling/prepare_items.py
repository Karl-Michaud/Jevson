"""Split a J4b run record into the labeller's items and the held-back key.

Usage: uv run --frozen python -m tests.j4b.labelling.prepare_items RUN.jsonl OUT_DIR [--seed N]

Writes OUT_DIR/items.jsonl (give this to the labeller) and OUT_DIR/key.jsonl (keep it away from the labeller until
labelling is finished). Item ids are random and items are shuffled, so neither the id nor the file order carries the
draft's role or verdict. `--seed` exists for tests; leave it unset for a real run.
"""

from __future__ import annotations

import argparse
import random
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tests.j4b.labelling.records import check_run_row, criterion_ids, read_jsonl, write_jsonl


def split(run: Sequence[dict[str, Any]], rng: random.Random) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items: list[dict[str, Any]] = []
    key: list[dict[str, Any]] = []
    used: set[str] = set()
    for n, row in enumerate(run, 1):
        check_run_row(row, n)
        item_id = None
        if row["draft"] is not None:
            item_id = f"{rng.getrandbits(48):012x}"
            while item_id in used:  # pragma: no cover - a 48-bit collision
                item_id = f"{rng.getrandbits(48):012x}"
            used.add(item_id)
            items.append(
                {
                    "id": item_id,
                    "source": row["source"],
                    "field": row["field"],
                    "criteria": [{"id": c["id"], "statement": c["statement"]} for c in row["criteria"]],
                    "draft": row["draft"],
                }
            )
        key.append(
            {
                "item_id": item_id,
                "instance_id": row["instance_id"],
                "role": row["role"],
                "admitted": row["admitted"],
                "criterion_ids": list(criterion_ids(row["criteria"])),
            }
        )
    rng.shuffle(items)
    return items, key


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--seed", type=int, default=None)
    a = ap.parse_args(argv)
    rng = random.Random(a.seed if a.seed is not None else secrets.randbits(64))
    items, key = split(read_jsonl(a.run), rng)
    a.out.mkdir(parents=True, exist_ok=True)
    write_jsonl(a.out / "items.jsonl", items)
    write_jsonl(a.out / "key.jsonl", key)
    print(f"{len(items)} items to label -> {a.out / 'items.jsonl'}; key -> {a.out / 'key.jsonl'} (do not share)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
