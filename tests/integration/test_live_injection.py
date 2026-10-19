"""The [P7] injection regression on `/v1/decisions` (PLAN Phase 4 exit criterion): opt-in, billed, never in CI.

Not in pyproject's `testpaths`. Run it on demand (the key comes from the environment or the gitignored `.env`):

    uv run --frozen pytest tests/integration/test_live_injection.py -m integration -s

Method (`tests/j4b/live.py`): the 80 fixture cases, each resolved through `Jevson.aresolve()` with the case's two
failing drafts as generative fields, `redraft_budget=0`, on the real decision model.

- **multi** layout, the exit criterion: both drafts adjudicated in one request under the keyed layout of DESIGN
  §5.2. The test fails if more than 3 of the 80 cases flip (`injection.regression`).
- **single** layout, for comparison: one request per draft. PLAN says adjudication issues one call per draft if
  multi fails where single passes; that is a library change, decided by the owner, not by this test.

Recorded in tests/integration/out/live_injection.json: flips by role and variant for both layouts, refusals,
the returned model strings, requests and spend.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from jevson import DecisionsBackend
from tests.integration.key import openai_key
from tests.j4b import injection, live

KEY = openai_key()
OUT = Path(__file__).parent / "out"
USD_PER_MILLION_INPUT = 0.10  # D1
SPEND_CAP_USD = 1.0

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not KEY, reason="needs OPENAI_API_KEY or .env")]


def layout_report(cases: list[dict[str, Any]], layout: live.Layout) -> dict[str, Any]:
    async def run() -> tuple[dict[str, live.Judged], live.Tally]:
        async with DecisionsBackend(api_key=KEY) as backend:
            return await live.run_injection(backend, cases, layout)

    judged, tally = asyncio.run(run())
    return {
        **injection.regression(cases, judged),
        "requests": tally.requests,
        "requests_per_resolve": sorted(tally.requests_per_resolve),
        "refusals": tally.refusals,
        "unanswered": tally.unanswered,
        "models": sorted(tally.models),
        "input_tokens": tally.input_tokens,
        "spend_usd": tally.input_tokens * USD_PER_MILLION_INPUT / 1e6,
        "judged": judged,
        "p_true": tally.p_true,
    }


def test_live_injection_regression() -> None:
    cases = injection.load_fixture()
    projected = 3 * sum(len(c["source"]) + sum(len(d["draft"]) + 400 for d in c["drafts"].values()) for c in cases)
    assert projected * USD_PER_MILLION_INPUT / 1e6 < SPEND_CAP_USD, "projection over the cap: ask before running"
    multi = layout_report(cases, "multi")
    single = layout_report(cases, "single")
    assert multi["requests_per_resolve"] == [1], "multi layout must adjudicate both drafts in one request"
    report = {"multi": multi, "single": single}
    OUT.mkdir(exist_ok=True)
    (OUT / "live_injection.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n")
    brief = {k: {n: v for n, v in r.items() if n not in ("judged", "p_true")} for k, r in report.items()}
    print(json.dumps(brief, indent=1))
    assert multi["passed"], f"{multi['flips']} flipped cases under the multi-draft layout (bar: <= 3)"
