"""Write the canary's two dummy chunks: `items-001.jsonl` (three small items) and `items-002.jsonl` (synthetic items
packed to just under the 72,000-character chunk bound). Deterministic; no network.

Usage: python -m tests.j4b.fresh.grader.canary.make_canary OUT_DIR
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

from tests.j4b.fresh import export_items
from tests.j4b.fresh.constants import CHUNK_CHARS

WORDS = ("receipt", "refund", "order", "total", "customer", "delivery", "payment", "invoice", "account", "item")


def item(rng: random.Random, n: int, size: int) -> dict[str, object]:
    source = " ".join(rng.choice(WORDS) for _ in range(size // 8)).capitalize() + "."
    return {"id": f"{n:012x}", "source": source, "field": "/summary",
            "criteria": [{"id": "c0", "statement": "The draft states the total as given in the source."}],
            "draft": "The total is as stated."}  # fmt: skip


def full_chunk(rng: random.Random) -> list[dict[str, object]]:
    """6,000-character items while they fit, then the largest last item that still fits in one chunk."""
    items: list[dict[str, object]] = []
    size = 6000
    while size >= 8:
        candidate = [*items, item(random.Random(len(items)), len(items) + 100, size)]
        if len(export_items.chunks(candidate)) == 1:
            items = candidate
        else:
            size //= 2
    return items


def main(argv: list[str] | None = None) -> int:
    out = Path((argv or sys.argv[1:])[0])
    rng = random.Random(72000)
    small = [item(rng, n, 400) for n in range(1, 4)]
    for name, items in (("items-001.jsonl", small), ("items-002.jsonl", full_chunk(rng))):
        text = export_items.chunks(items)[0]
        assert len(text) <= CHUNK_CHARS
        (out / name).write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
