"""A deterministic fake attempt's outcomes over the committed fixtures, for the bar-input and report tests."""

from __future__ import annotations

import hashlib
from typing import Any

from tests.j4b import injection
from tests.j4b.fresh import arms
from tests.j4b.fresh.bar_inputs import Outcomes, RFirst
from tests.j4b.tests import fresh_data


def bit(*parts: str) -> bool:
    """A fixed pseudo-random bit of `parts`, so every configuration's outcome is reproducible and distinct."""
    return hashlib.sha256("|".join(parts).encode()).digest()[0] % 5 == 0


def outcomes(drop: float = 0.0) -> Outcomes:
    """Every configuration's outcome: a PASS draft rejected and a FAIL draft admitted 1 time in 5, by draft and
    configuration; `drop` leaves out that share of each configuration's recorded units (a void attempt)."""
    rows = fresh_data.rows()

    def kept(*parts: str) -> bool:
        return hashlib.sha256(("keep|" + "|".join(parts)).encode()).digest()[1] / 256 >= drop

    pset = {
        c: {
            r["draft_id"]: (r["label"] == "PASS") != bit(c[0], c[1], r["draft_id"])
            for r in rows["pset.jsonl"]
            if kept(c[0], c[1], r["draft_id"])
        }
        for c in arms.CONFIGURATIONS
    }
    rset = {
        c: {
            r["draft_id"]: RFirst(
                not bit("first", *c, r["draft_id"]),
                bit("redraft", *c, r["draft_id"]),
                not bit("truth", r["draft_id"]),
                bit("rtruth", *c, r["draft_id"]),
            )
            for r in rows["rset.jsonl"]
            if kept(c[0], c[1], r["draft_id"])
        }
        for c in arms.CONFIGURATIONS
    }
    iset = {
        a: {
            r["case"]: bit("flip", a, r["case"]) and a == "L0"
            for r in rows["iset.jsonl"]
            if r["role"] == "injected" and kept(a, r["case"])
        }
        for a in arms.LIBRARY_ARMS
    }
    p7: dict[str, Any] = {
        a: {
            c["case_id"]: {f: dict.fromkeys(spec["truth"], False) for f, spec in c["drafts"].items()}
            for c in injection.load_fixture()
        }
        for a in arms.LIBRARY_ARMS
    }
    return Outcomes(iset=iset, p7=p7, pset=pset, rset=rset)


def decisive() -> Outcomes:
    """A complete attempt that clears the RB run level and PC and reaches every bar, built so that each bar decides
    (T48-1): today's library (L0, F0) rejects every PASS draft of the `negated` stratum, which F1 fixes, and 120 of
    the 300 R-set first drafts, each redrafted, admitted and true; M2 (L2) never admits a redraft, so it fails RB;
    M1 (L1) also rejects every `universal` PASS draft, so it fails FRR-NI; M1+M2 (L3) behaves as L0 and is adopted.
    So a decision that read RB, FRR-NI, FRR-T or FRR-Fi wrongly, or against another reference, changes the outcome."""
    rows = fresh_data.rows()
    rejected = {r["draft_id"] for r in sorted(rows["rset.jsonl"], key=lambda r: r["draft_id"])[:120]}

    def admitted(arm: str, form: str, row: dict[str, Any]) -> bool:
        if row["label"] == "FAIL":
            return False
        return not ((row["pattern"] == "negated" and form == "F0") or (arm == "L1" and row["pattern"] == "universal"))

    def first(arm: str, draft_id: str) -> RFirst:
        if draft_id not in rejected:
            return RFirst(True, False, True, False)
        return RFirst(False, arm != "L2", True, arm != "L2")

    pset = {(a, f): {r["draft_id"]: admitted(a, f, r) for r in rows["pset.jsonl"]} for a, f in arms.CONFIGURATIONS}
    rset = {
        (a, f): {r["draft_id"]: first(a, r["draft_id"]) for r in rows["rset.jsonl"]} for a, f in arms.CONFIGURATIONS
    }
    iset = {
        a: {r["case"]: a == "L0" and r["cell"] == "replica" for r in rows["iset.jsonl"] if r["role"] == "injected"}
        for a in arms.LIBRARY_ARMS
    }
    p7: dict[str, Any] = {
        a: {
            c["case_id"]: {f: dict.fromkeys(spec["truth"], False) for f, spec in c["drafts"].items()}
            for c in injection.load_fixture()
        }
        for a in arms.LIBRARY_ARMS
    }
    return Outcomes(iset=iset, p7=p7, pset=pset, rset=rset)
