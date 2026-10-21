"""Build the fresh fixtures of the ASTERION-48/-58 measurement from the authored data (design §2, §6.1).

Usage: uv run --frozen python -m tests.j4b.fresh.build_fresh_sets   (rewrites tests/j4b/fixtures/fresh/)

Reads the three authored JSON files with `json.loads` (never as code), builds the six row files and writes
`summary.json`, the pure output of `summarise` over the row files and the committed `picked.json`. The build stops
on the first `FixtureDefect` of the code checker or a leakage predicate; it never drops a case.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.j4b.fresh import leakage, truth
from tests.j4b.fresh.canonical import canonical_file, canonical_row
from tests.j4b.fresh.iset_rows import Sources, iset_rows
from tests.j4b.fresh.pset_rows import pset_rows
from tests.j4b.fresh.sources import FixtureDefect, load_rset_documents

FRESH = Path(__file__).resolve().parent
FIXTURES = FRESH.parents[0] / "fixtures" / "fresh"
AUTHORED = ("iset_wordings.json", "pset_templates.json", "rset_fields.json")
PICKED = FRESH / "picked.json"
ROW_FILES = ("iset.jsonl", "iset_dev.jsonl", "pset.jsonl", "pset_dev.jsonl", "rset.jsonl", "rset_dev.jsonl")
STRING_SETS = {"iset_wordings.json": "iset", "pset_templates.json": "pset", "rset_fields.json": "rset"}
Row = dict[str, Any]


def load_authored(name: str, text: str) -> dict[str, dict[str, Any]]:
    """An authored file's records; it must be exactly `canonical_file` of them, so no byte lies outside a record."""
    records = json.loads(text)
    if text != canonical_file(records):
        raise FixtureDefect(f"non-canonical {name}")
    return records


WORDING = {"iset": ("criterion", "claim", "companion"), "pset": ("f0", "f1", "self_claim", "benign", "benign_object")}
"""The authored wording the code checker's guard and the leakage predicates read (design §2.1, §2.2, §2.5)."""


def strings(authored: Mapping[str, Mapping[str, Mapping[str, Any]]]) -> dict[str, str]:
    """Every I-set and P-set wording string, keyed `<set>#<record id>.<attribute>`."""
    out: dict[str, str] = {}
    for name, records in authored.items():
        set_name = STRING_SETS[name]
        for record_id, record in records.items():
            for attribute in WORDING.get(set_name, ()):
                if attribute in record:
                    out[f"{set_name}#{record_id}.{attribute}"] = str(record[attribute])
    return out


def rset_rows(fields: Mapping[str, Mapping[str, Any]], picked: Mapping[str, list[str]]) -> dict[str, list[Row]]:
    """One row per (picked document, field of its domain), with the SHA-256 of the document text."""
    out: dict[str, list[Row]] = {}
    for phase, name in (("confirm", "rset.jsonl"), ("dev", "rset_dev.jsonl")):
        out[name] = []
        for doc in load_rset_documents(picked[phase]):
            digest = hashlib.sha256(doc.text.encode("utf-8")).hexdigest()
            for field_id in sorted(f for f in fields if f.startswith(f"{doc.domain}.")):
                pointer = fields[field_id]["pointer"]
                out[name].append({"set": name.removesuffix(".jsonl"), "draft_id": f"{doc.doc_id}{pointer}",
                                  "doc_id": doc.doc_id, "doc_sha256": digest, "domain": doc.domain,
                                  "field": field_id, "pointer": pointer})  # fmt: skip
    return out


def build(authored: Mapping[str, Mapping[str, Any]], picked: Mapping[str, list[str]]) -> dict[str, list[Row]]:
    sources = Sources()
    rows = {**iset_rows(authored["iset_wordings.json"], sources), **pset_rows(authored["pset_templates.json"], sources)}
    rows |= rset_rows(authored["rset_fields.json"], picked)
    return {name: rows[name] for name in ROW_FILES}


def row_bytes(rows: list[Row]) -> bytes:
    return "".join(canonical_row(r) for r in rows).encode("utf-8")


def _counts(rows: Mapping[str, list[Row]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, file_rows in rows.items():
        counted: dict[str, Counter[str]] = {}
        for row in file_rows:
            for key in ("label", "role", "verb", "echo", "topic", "value", "position", "pattern", "domain", "benign",
                        "targeted_self_claim", "field"):  # fmt: skip
                if key in row:
                    counted.setdefault(key, Counter())[str(row[key])] += 1
        out[name] = {"rows": len(file_rows), **{k: dict(sorted(c.items())) for k, c in sorted(counted.items())}}
    return out


def summarise(row_file_bytes: Mapping[str, bytes], picked_bytes: bytes) -> str:
    """The summary of the built fixtures: SHA-256 of every row file and of `picked.json`, and counts per factor
    level and stratum. A pure function of the bytes, so `pins.check` can re-derive it."""
    rows = {n: [json.loads(line) for line in b.decode("utf-8").splitlines()] for n, b in row_file_bytes.items()}
    sha = {n: hashlib.sha256(b).hexdigest() for n, b in sorted(row_file_bytes.items())}
    return canonical_file({"sha256": {**sha, "picked.json": hashlib.sha256(picked_bytes).hexdigest()},
                           "counts": _counts(rows)})  # fmt: skip


def main() -> int:
    authored = {name: load_authored(name, (FRESH / name).read_text(encoding="utf-8")) for name in AUTHORED}
    picked_bytes = PICKED.read_bytes()
    rows = build(authored, json.loads(picked_bytes))
    truth.require(rows, strings(authored))
    leakage.require(rows, strings(authored))
    FIXTURES.mkdir(parents=True, exist_ok=True)
    data = {name: row_bytes(file_rows) for name, file_rows in rows.items()}
    for name, payload in data.items():
        (FIXTURES / name).write_bytes(payload)
    (FIXTURES / "summary.json").write_text(summarise(data, picked_bytes), encoding="utf-8")
    print({name: len(file_rows) for name, file_rows in rows.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
