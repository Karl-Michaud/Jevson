"""Builds the work lists handed to the extractor and labelling agents, and the probe 4 passages.

    uv run python -m tests.phase0.datasets.tasks extraction <out dir>
    uv run python -m tests.phase0.datasets.tasks passages <out dir>
"""
from __future__ import annotations

import json
import pathlib
import sys

from tests.phase0.datasets import fields as FL
from tests.phase0.datasets.models import CORPUS, DocRecord, doc_text, load_manifest

PASSAGE_MAX = 6000
# entity types probed per domain for probe 4 (docs/taxonomy.md §2.4): contracts yield an organization passage
# (the opening) and a person passage (the closing); other domains one passage of the listed type
PASSAGE_TYPES = {"contract": ("organization", "person"), "medical_intake": ("person",),
                 "product_listing": ("organization",), "resume": ("person",), "support_ticket": ("person",)}
MIDDLE_MIN_CHARS = 12000   # contracts longer than this also yield a middle organization passage


def middle_window(text: str, limit: int = PASSAGE_MAX) -> tuple[int, int]:
    """A paragraph-aligned window of at most ``limit`` characters starting near the middle of the text."""
    start = text.find("\n\n", len(text) // 2 - limit // 2)
    start = start + 2 if start >= 0 else len(text) // 2 - limit // 2
    end = text.rfind("\n\n", start, start + limit)
    return start, end if end > start else start + limit


def window(text: str, from_end: bool, limit: int = PASSAGE_MAX) -> tuple[int, int]:
    """A paragraph-aligned window of at most ``limit`` characters at the start (or end) of the text."""
    if len(text) <= limit:
        return 0, len(text)
    if not from_end:
        cut = text.rfind("\n\n", 0, limit)
        return 0, cut if cut > 0 else limit
    start = text.find("\n\n", len(text) - limit)
    return (start + 2 if start >= 0 else len(text) - limit), len(text)


def extraction_tasks(docs: dict[str, DocRecord]) -> list[dict]:
    out = []
    for d in sorted(docs.values(), key=lambda r: r.doc_id):
        if d.pool != "main":
            continue
        out.append({"doc_id": d.doc_id, "domain": d.domain, "path": f"tests/phase0/datasets/corpus/{d.path}",
                    "fields": [{"field_id": f.field_id, "label": f.label, "guidance": f.guidance}
                               for f in FL.for_domain(d.domain)]})
    return out


def passages(docs: dict[str, DocRecord], root: pathlib.Path = CORPUS) -> list[dict]:
    out = []
    for d in sorted(docs.values(), key=lambda r: r.doc_id):
        types = PASSAGE_TYPES.get(d.domain, ())
        text = doc_text(d, root)
        for i, et in enumerate(types):
            s, e = window(text, from_end=(i == 1))
            out.append({"passage_id": f"{d.doc_id}#{et}", "doc_id": d.doc_id, "domain": d.domain, "entity_type": et,
                        "start": s, "end": e, "path": f"tests/phase0/datasets/corpus/{d.path}"})
        if d.domain == "contract" and len(text) > MIDDLE_MIN_CHARS:
            s, e = middle_window(text)
            out.append({"passage_id": f"{d.doc_id}#organization-middle", "doc_id": d.doc_id, "domain": d.domain,
                        "entity_type": "organization", "start": s, "end": e,
                        "path": f"tests/phase0/datasets/corpus/{d.path}"})
    return out


def main(argv: list[str], root: pathlib.Path = CORPUS) -> int:
    if len(argv) != 2 or argv[0] not in ("extraction", "passages"):
        print("usage: tasks <extraction|passages> <out dir>", file=sys.stderr)
        return 2
    docs = load_manifest(root)
    items = extraction_tasks(docs) if argv[0] == "extraction" else passages(docs, root)
    out = pathlib.Path(argv[1])
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{argv[0]}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
    print(f"{argv[0]}: {len(items)} items")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
