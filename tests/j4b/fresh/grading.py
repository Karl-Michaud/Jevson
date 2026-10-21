"""What the grader grades, under which criterion form, and how its labels become each bar's truth (design §3
"Truth form", "Hand-off"; STATS48B-R1-2). Frozen at the pre-registration; `export_items.py` only serialises.

- **Uses.** Every R-set first draft is graded against its field's `F0` criteria (`TRUTH_FORM`, the truth) and its
  `F1` criteria (`SANITY_FORM`, the sanity count; it never sets truth), and every redraft against `F0`. A malformed
  draft (null text) is never graded. The 96 diagnostic P-set drafts (`diagnostic_ids`, always drawn from the
  committed confirm P-set by `random.Random(4858)`) are graded with their `F0` criterion.
- **Truth.** `truths` maps each R-set use of a labelled item to the grader's verdict; `rset_truths` joins it to the
  recorded admissions under `TRUTH_FORM` only (a draft with no labelled F0 item is never true).
- **Secondaries.** The grader's agreement with the code checker on the diagnostic items, and the F0/F1 disagreement
  of R-set first drafts in each direction (never re-labelled).
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tests.j4b.fresh import rules, workload
from tests.j4b.fresh.bar_inputs import RFirst
from tests.j4b.fresh.constants import DIAGNOSTIC_SEED
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.workload import Workload
from tests.j4b.labelling.records import Label

TRUTH_FORM, SANITY_FORM = "F0", "F1"
PATTERN_SPLIT = (16, 16, 32, 32, 32)
DIAGNOSTIC_PER_LABEL = 48
"""48 PASS and 48 FAIL, allocated over the five patterns in proportion to the 16/16/32/32/32 pair split."""


class DiagnosticDefect(Exception):
    """The committed confirm P-set does not have the five patterns the diagnostic draw is allocated over."""


@dataclass(frozen=True)
class Use:
    """One draft graded against one criterion list, and the run row it stands for."""

    source: str
    field: str
    criteria: Sequence[str]
    draft: str
    use: Mapping[str, Any]


def draft_id(doc_id: str, pointer: str) -> str:
    return f"{doc_id}/{pointer.removeprefix('/')}"


def allocation() -> list[int]:
    return [DIAGNOSTIC_PER_LABEL * k // sum(PATTERN_SPLIT) for k in PATTERN_SPLIT]


def diagnostic_ids(pset_rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """The 96 diagnostic drafts: `random.Random(4858)`; per pattern, in order of first appearance, PASS then
    FAIL, `allocation()` drafts each, drawn from that pattern's sorted draft ids."""
    rng, patterns = random.Random(DIAGNOSTIC_SEED), list(dict.fromkeys(str(r["pattern"]) for r in pset_rows))
    if len(patterns) != len(PATTERN_SPLIT):
        raise DiagnosticDefect(f"expected {len(PATTERN_SPLIT)} P-set patterns, found {len(patterns)}")
    chosen: list[str] = []
    for pattern, k in zip(patterns, allocation(), strict=True):
        for verdict in ("PASS", "FAIL"):
            pool = sorted(str(r["draft_id"]) for r in pset_rows if r["pattern"] == pattern and r["label"] == verdict)
            chosen += rng.sample(pool, k)
    return chosen


def uses(w: Workload, records: Mapping[Unit, Mapping[str, Any]]) -> Iterator[Use]:
    """Every graded use: each R-set draft under the forms above, then the diagnostic drafts."""
    for unit, record in sorted(records.items(), key=lambda kv: (kv[0].key, kv[0].arm, kv[0].form)):
        if unit.set_name != "rset":
            continue
        doc = w.documents[unit.key]
        for spec in w.fields[doc.domain]:
            pointer, got = str(spec["pointer"]), record["fields"][str(spec["pointer"])]
            run = {"set": "rset", "config": f"{unit.arm}{unit.form}", "draft_id": draft_id(doc.doc_id, pointer)}
            first = {**run, "role": "first", "admitted": got["first_admitted"]}
            if got["first"] is not None:
                yield Use(doc.text, pointer, spec["f0"], got["first"], {**first, "form": TRUTH_FORM})
                yield Use(doc.text, pointer, spec["f1"], got["first"], {**first, "form": SANITY_FORM})
            if got["redraft"] is not None:
                redraft = {**run, "role": "redraft", "admitted": got["redraft_admitted"], "form": TRUTH_FORM}
                yield Use(doc.text, pointer, spec["f0"], got["redraft"], redraft)
    by_id = {str(r["draft_id"]): r for r in workload.read_rows(workload.ROW_FILE["confirm"]["pset"])}
    for did in diagnostic_ids(list(by_id.values())):
        row = by_id[did]
        use = {"set": "diagnostic", "draft_id": did, "code_verdict": row["label"] == "PASS", "form": TRUTH_FORM}
        yield Use(row["source"], "/summary", [row["criterion_f0"]], row["draft"], use)


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
    records: Mapping[Unit, Mapping[str, Any]], truth: Mapping[tuple[str, str, str, str], bool]
) -> dict[rules.Config, dict[str, RFirst]]:
    """`Outcomes.rset`: per configuration and draft, admissions with `TRUTH_FORM` truth (a malformed or unlabelled
    draft is never true)."""
    out: dict[rules.Config, dict[str, RFirst]] = {}
    for unit, record in records.items():
        if unit.set_name != "rset":
            continue
        for pointer, got in record["fields"].items():
            did, config = draft_id(unit.key, pointer), f"{unit.arm}{unit.form}"
            out.setdefault((unit.arm, unit.form), {})[did] = RFirst(
                got["first_admitted"], got["redraft_admitted"],
                truth.get((config, did, "first", TRUTH_FORM), False),
                truth.get((config, did, "redraft", TRUTH_FORM), False),
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
    f1_only = sorted({d for (_, d), v in forms.items() if v.get(SANITY_FORM) and v.get(TRUTH_FORM) is False})
    f0_only = sorted({d for (_, d), v in forms.items() if v.get(TRUTH_FORM) and v.get(SANITY_FORM) is False})
    disagreement = {"f1_not_f0": len(f1_only), "f0_not_f1": len(f0_only), "f1_not_f0_drafts": f1_only}
    return {"diagnostic_agreement": {"agree": agree, "of": total}, "f0_f1_disagreement": disagreement}
