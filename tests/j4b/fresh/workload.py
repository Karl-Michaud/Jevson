"""What one phase runs, read from the committed fixtures (design §2, §6.2; plan §7 "Phases").

`dev` runs the I-dev, P-dev and R-dev sets; `confirm` runs the I-set, the unchanged [P7] cases, the P-set and the
R-set. The I-set and [P7] run under the four library arms; the P-set and R-set under all eight configurations.
R-set documents are the phase's `picked.json` ids, read through `sources.load_rset_documents` (never
`redraft.documents()`, which drops the receipts; FEAS48-R10-1), and each is re-hashed against every R-set row's
`doc_sha256` before any spend (`FixtureDefect` on a mismatch; FEAS48-C1-2); each domain's three fields come from
`rset_fields.json`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tests.j4b import injection, redraft
from tests.j4b.fresh import arms, costs, judging, sources
from tests.j4b.fresh import build_fresh_sets as builder
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.sources import FixtureDefect

ROW_FILE = {"dev": {"iset": "iset_dev.jsonl", "pset": "pset_dev.jsonl", "rset": "rset_dev.jsonl"},
            "confirm": {"iset": "iset.jsonl", "pset": "pset.jsonl", "rset": "rset.jsonl"}}  # fmt: skip
FORM_FREE = "F0"
"""The I-set and [P7] have one criterion form; their units carry F0 (their cases read no `f1` text)."""


@dataclass(frozen=True)
class Workload:
    """One phase's cases by set, its R-set documents and fields, its units and its fixture rows."""

    phase: str
    cases: Mapping[str, Mapping[str, dict[str, Any]]]
    documents: Mapping[str, redraft.Document]
    fields: Mapping[str, Sequence[Mapping[str, Any]]]
    units: Mapping[str, Sequence[Unit]]
    rows: Mapping[str, Sequence[Mapping[str, Any]]]


def read_rows(name: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in (builder.FIXTURES / name).read_text(encoding="utf-8").splitlines() if line]


def iset_cases(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """Each I-set case: its injected draft beside its clean companion."""
    by_case: dict[str, dict[str, Mapping[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case"]), {})[str(row["role"])] = row
    return {case: judging.iset_case(pair["injected"], pair["companion"]) for case, pair in by_case.items()}


def rset_fields() -> dict[str, list[dict[str, Any]]]:
    """Each domain's fields in the order `rset_fields.json` lists them."""
    fields = builder.load_authored("rset_fields.json", (builder.FRESH / "rset_fields.json").read_text("utf-8"))
    by_domain: dict[str, list[dict[str, Any]]] = {}
    for key, spec in fields.items():
        by_domain.setdefault(key.split(".")[0], []).append(dict(spec))
    return by_domain


def check_documents(documents: Mapping[str, redraft.Document], rows: Sequence[Mapping[str, Any]], name: str) -> None:
    """Each R-set row's `doc_sha256` equals the SHA-256 of its document's UTF-8 text, or `FixtureDefect`."""
    for row in rows:
        digest = hashlib.sha256(documents[row["doc_id"]].text.encode("utf-8")).hexdigest()
        if digest != row["doc_sha256"]:
            raise FixtureDefect(f"{row['doc_id']}: the document's SHA-256 differs from {name}'s doc_sha256")


def load(phase: str) -> Workload:
    files = ROW_FILE[phase]
    rows = {name: read_rows(name) for name in files.values()}
    picked: dict[str, list[str]] = json.loads(builder.PICKED.read_text(encoding="utf-8"))
    cases: dict[str, dict[str, dict[str, Any]]] = {
        "iset": iset_cases(rows[files["iset"]]),
        "pset": {str(r["draft_id"]): dict(r) for r in rows[files["pset"]]},
    }
    if phase == "confirm":
        cases["p7"] = {str(c["case_id"]): c for c in injection.load_fixture()}
    documents = {d.doc_id: d for d in sources.load_rset_documents(picked[phase])}
    check_documents(documents, rows[files["rset"]], files["rset"])
    units: dict[str, list[Unit]] = {
        name: [Unit(name, key, arm, FORM_FREE) for key in cases[name] for arm in arms.LIBRARY_ARMS]
        for name in ("iset", "p7")
        if name in cases
    }
    units["pset"] = [Unit("pset", key, arm, form) for key in cases["pset"] for arm, form in arms.CONFIGURATIONS]
    units["rset"] = [Unit("rset", key, arm, form) for key in documents for arm, form in arms.CONFIGURATIONS]
    return Workload(phase, cases, documents, rset_fields(), units, rows)


def cost_inputs(w: Workload) -> costs.Split:
    """The design cost model's inputs from the built fixtures: case source lengths and document lengths."""
    return costs.Split(
        iset=[len(c["source"]) for c in w.cases["iset"].values()],
        pset=[len(c["source"]) for c in w.cases["pset"].values()],
        rset=[len(d.text) for d in w.documents.values()],
        p7="p7" in w.cases,
    )
