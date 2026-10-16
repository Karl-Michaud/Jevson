"""Live stability on `/v1/decisions` (PLAN Phase 3 exit criterion; R15): opt-in, billed, never in CI.

Not in pyproject's `testpaths`. The key comes from `OPENAI_API_KEY`, else from the repository's
gitignored `.env`, read here by the harness and passed as `api_key=` (the library never reads `.env`):

    uv run --frozen pytest tests/integration/test_live_stability.py -m integration -s

Method, as PLAN Phase 3 states it:

- Decisions are the decided fields of the checked-in schemas (tests/fixtures/schemas) over real
  documents (tests/phase0/datasets/corpus): the 32 CUAD Yes/No booleans over the 12 shortest
  contracts, and `/severity` over all 44 support tickets. Each schema is reduced to the properties
  that compile on their own; the rest would refuse the whole schema in v0.
- A selection run keeps every decision whose top-two margin is >= 0.20; at least 100 must qualify.
- Two further runs resolve the same documents. A flip is any change of committed value, or between a
  value and `tie`, between those two runs; the test fails only if more than 2% flip.
- Every run goes through the synchronous `Jevson.resolve()` from 4 threads, so the library loop and
  the per-key limiter are exercised live too.
- Recorded in tests/integration/out/live_stability.json: the flip rate, the returned `model` strings,
  preflight's estimate against billed input tokens per request, refusals, ties, and spend.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest

from jevson import CompileError, CostEvent, DecisionsBackend, Jevson, Result
from jevson.compile.compiler import compile_schema
from jevson.probabilities import top_two_margin

ROOT = Path(__file__).resolve().parents[2]
SCHEMAS = ROOT / "tests/fixtures/schemas"
CORPUS = ROOT / "tests/phase0/datasets/corpus"
OUT = Path(__file__).parent / "out"
USD_PER_MILLION_INPUT = 0.10  # D1
SPEND_CAP_USD = 5.0
MIN_MARGIN = 20  # hundredths
MIN_DECISIONS = 100
MAX_FLIP_RATE = 0.02
CONTRACTS = 12


def _key() -> str:
    if key := os.environ.get("OPENAI_API_KEY"):
        return key
    env = ROOT / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENAI_API_KEY" and value.strip():
                return value.strip().strip("'\"")
    return ""


KEY = _key()
pytestmark = [pytest.mark.integration, pytest.mark.skipif(not KEY, reason="needs OPENAI_API_KEY or .env")]


def decided_part(name: str) -> dict[str, Any]:
    """The schema reduced to the top-level properties that compile on their own (none required)."""
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    defs = schema.get("$defs", {})
    kept: dict[str, Any] = {}
    for prop, sub in schema["properties"].items():
        try:
            compile_schema({"type": "object", "properties": {prop: sub}, "$defs": defs})
        except CompileError:
            continue
        kept[prop] = sub
    return {"type": "object", "properties": kept, "$defs": defs}


def documents() -> list[tuple[str, str, dict[str, Any]]]:
    """(doc_id, text, schema) in a fixed order: shortest contracts first, then every ticket."""
    rows = [json.loads(line) for line in (CORPUS / "manifest.jsonl").read_text().splitlines() if line]
    contract, ticket = decided_part("contract"), decided_part("support_ticket")
    contracts = sorted((r for r in rows if r["domain"] == "contract"), key=lambda r: (r["chars"], r["doc_id"]))
    tickets = sorted((r for r in rows if r["domain"] == "support_ticket"), key=lambda r: r["doc_id"])
    return [
        *((r["doc_id"], (CORPUS / r["path"]).read_text(), contract) for r in contracts[:CONTRACTS]),
        *((r["doc_id"], (CORPUS / r["path"]).read_text(), ticket) for r in tickets),
    ]


class Events:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.events: list[CostEvent] = []

    def record(self, cost_event: CostEvent) -> None:
        with self.lock:
            self.events.append(cost_event)


Outcome = tuple[str, Any]  # ("value", committed) or ("unresolved", reason)


def outcomes(result: Result) -> dict[str, tuple[Outcome, int]]:
    """Per decided pointer: its outcome and its top-two margin in hundredths (0 without a distribution)."""
    reasons = {u.pointer: str(u.reason) for u in result.unresolved}
    found: dict[str, tuple[Outcome, int]] = {}
    for decision in result.decisions.values():
        pointer = decision.target_pointer
        margin = top_two_margin(dict(decision.distribution_hundredths)) if decision.distribution_hundredths else 0
        outcome: Outcome = (
            ("value", decision.selected) if decision.selected is not None else ("unresolved", reasons[pointer])
        )
        found[pointer] = (outcome, margin)
    return found


def run(
    jevson: Jevson, docs: list[tuple[str, str, dict[str, Any]]], models: set[str]
) -> dict[tuple[str, str], tuple[Outcome, int]]:
    def one(doc: tuple[str, str, dict[str, Any]]) -> dict[tuple[str, str], tuple[Outcome, int]]:
        doc_id, text, schema = doc
        result = jevson.resolve(schema, text)
        models.update(result.model)  # R15: the returned model string(s)
        return {(doc_id, p): o for p, o in outcomes(result).items()}

    merged: dict[tuple[str, str], tuple[Outcome, int]] = {}
    with ThreadPoolExecutor(4) as pool:
        for part in pool.map(one, docs):
            merged |= part
    return merged


def spend(events: list[CostEvent]) -> int:
    return sum(e.input_tokens or 0 for e in events if e.component == "decision")


def test_live_stability() -> None:
    docs = documents()
    projected_tokens = 3 * sum(len(text) for _, text, _ in docs) // 3  # 3 runs; ~3 characters a token
    projected_usd = projected_tokens * USD_PER_MILLION_INPUT / 1e6
    print(f"projected: {projected_tokens} input tokens, ${projected_usd:.3f} (questions add a little)")
    assert projected_usd < SPEND_CAP_USD, "projection over the cap: ask before running"

    sink = Events()
    models: set[str] = set()
    with DecisionsBackend(api_key=KEY) as backend, Jevson(backend, cost_sink=sink) as jevson:
        selection = run(jevson, docs, models)
        after_selection = spend(sink.events)
        assert after_selection * 3 * USD_PER_MILLION_INPUT / 1e6 < SPEND_CAP_USD, "billed rate projects over the cap"
        chosen = sorted(k for k, (_, margin) in selection.items() if margin >= MIN_MARGIN)
        assert len(chosen) >= MIN_DECISIONS, f"only {len(chosen)} decisions reached a 0.20 margin"
        wanted = {doc_id for doc_id, _ in chosen}
        rerun = [d for d in docs if d[0] in wanted]
        second, third = run(jevson, rerun, models), run(jevson, rerun, models)

    flips = [k for k in chosen if second[k][0] != third[k][0]]
    drift = [k for k in chosen if selection[k][0] != second[k][0] or selection[k][0] != third[k][0]]
    every = [*selection.values(), *(second[k] for k in second), *(third[k] for k in third)]
    billed = [e for e in sink.events if e.component == "decision" and e.input_tokens]
    ratios = sorted((e.estimated_input_tokens or 0) / (e.input_tokens or 1) for e in billed)
    tokens = spend(sink.events)
    report = {
        "decisions_candidate": len(selection),
        "decisions_selected": len(chosen),
        "documents_rerun": len(rerun),
        "flips_run2_vs_run3": len(flips),
        "flip_rate": len(flips) / len(chosen),
        "flipped": [list(k) for k in flips],
        "selection_vs_later_changes": len(drift),
        "models": sorted(models),
        "requests": len(billed),
        "estimate_over_billed": {"min": ratios[0], "median": statistics.median(ratios), "max": ratios[-1]},
        "estimated_and_billed": sorted([e.estimated_input_tokens or 0, e.input_tokens or 0] for e in billed),
        "refusals": sum(1 for o, _ in every if o == ("unresolved", "refused")),
        "ties": sum(1 for o, _ in every if o == ("unresolved", "tie")),
        "decisions_total": len(every),
        "input_tokens": tokens,
        "spend_usd": tokens * USD_PER_MILLION_INPUT / 1e6,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / "live_stability.json").write_text(json.dumps(report, indent=1) + "\n")
    print(json.dumps(report, indent=1))
    assert len(flips) / len(chosen) <= MAX_FLIP_RATE
