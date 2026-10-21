"""Each set's schema and judge call (design §2.1-§2.4, §6.3; plan §4.1 `judging.py`).

The I-set, [P7] and P-set run with `redraft_budget = 0` and a `ScriptedLLM` (`live.py`, reused) that returns the
fixture's draft for each field, so the judge reads exactly the built text; the R-set runs with
`redraft_budget = 1` and the attempt's drafting LLM (plan §11 D12). No schema field has a description, so no
drafting prompt depends on it (plan §10 O8).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from jevson import Jevson, JevsonConfig, Result
from jevson.protocols import LLM, Backend
from tests.j4b import live
from tests.j4b.fresh.admission import COMPANION, INJECTED

REDRAFT_BUDGET = {"iset": 0, "p7": 0, "pset": 0, "rset": 1}
"""Per set: no redraft where admission of the drafted text is the measure; one on the real corpus (design §6.3)."""


def iset_case(injected: Mapping[str, Any], companion: Mapping[str, Any]) -> dict[str, Any]:
    """An I-set case in the [P7] fixture's shape: the injected draft beside its clean companion."""

    def draft(row: Mapping[str, Any], role: str) -> dict[str, Any]:
        return {
            "role": role,
            "draft": row["draft"],
            "criteria": [{"id": "k0", "statement": row["criterion"]}],
            "truth": {"k0": False},
        }

    return {
        "case_id": injected["case"],
        "source": injected["source"],
        "drafts": {INJECTED: draft(injected, "injected"), COMPANION: draft(companion, "clean_companion")},
    }


def pset_case(row: Mapping[str, Any], form: str) -> dict[str, Any]:
    """A P-set draft as a one-field case, criterion in `form` (F0 or F1)."""
    criterion = row["criterion_f0"] if form == "F0" else row["criterion_f1"]
    return {
        "case_id": row["draft_id"],
        "source": row["source"],
        "drafts": {
            INJECTED: {
                "role": "pset",
                "draft": row["draft"],
                "criteria": [{"id": "k0", "statement": criterion}],
                "truth": {},
            }
        },
    }


async def judge_case(backend: Backend, case: Mapping[str, Any], config: JevsonConfig, set_name: str) -> Result:
    """One scripted case under `config`, with its set's redraft budget."""
    schema = live.schema(case, sorted(case["drafts"]))
    jevson = Jevson(backend, llm=live.scripted(case, schema), config=config)
    return await jevson.aresolve(schema, case["source"], redraft_budget=REDRAFT_BUDGET[set_name])


def rset_schema(fields: Sequence[Mapping[str, Any]], form: str) -> dict[str, Any]:
    """A document's schema: its domain's three fields, each with its instructions and its criteria in `form`."""
    key = "f0" if form == "F0" else "f1"
    properties = {
        str(f["pointer"]).removeprefix("/"): {
            "type": "string",
            "x-jevson": {"generate": {"instructions": f["instructions"], "criteria": list(f[key])}},
        }
        for f in fields
    }
    return {"type": "object", "properties": properties, "required": sorted(properties)}


async def judge_document(
    backend: Backend, llm: LLM, text: str, *, fields: Sequence[Mapping[str, Any]], config: JevsonConfig, form: str
) -> Result:
    """One R-set document under one configuration, with one redraft."""
    jevson = Jevson(backend, llm=llm, config=config)
    return await jevson.aresolve(rset_schema(fields, form), text, redraft_budget=REDRAFT_BUDGET["rset"])
