"""J4b's live injection regression, run through Jevson's own adjudication path (PLAN Phase 4).

Each [P7] case becomes a schema whose generative fields are the case's drafts, each declaring its criteria as
`x-jevson.generate.criteria`. A `ScriptedLLM` returns the fixture's draft for each field, so the drafts the decision
model judges are exactly the fixture's, and `redraft_budget=0` keeps it to the first verdict.

- **multi** (the PLAN layout): both drafts in one call, in one level under the keyed layout of DESIGN §5.2
  (`drafts: {"/companion_summary#generate": …, "/summary#generate": …}`).
- **single**: one call per draft, each field resolved alone.

`judged[case_id][field][criterion_id]` is True when the criterion passed (p >= 0.56 outside the tie margin, the
library's own rule); a refused or unanswered criterion did not pass and is counted. The billed run is
`tests/integration/test_live_injection.py`; this module never reads a key.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from jevson import Jevson
from jevson.adjudicate.criteria import PASS_HUNDREDTHS
from jevson.compile.compiler import compile_schema
from jevson.protocols import Backend
from jevson.types import JSONValue, LLMResponse, Message, StepNode

Layout = Literal["multi", "single"]
Judged = dict[str, dict[str, bool]]


class ScriptedLLM:
    """Returns a fixed draft per drafting prompt; any other request is an error in the harness."""

    def __init__(self, drafts: Mapping[str, str]) -> None:
        self._drafts = dict(drafts)

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        draft = self._drafts[messages[0].content.split("\n\n", 1)[0]]
        return LLMResponse({"value": draft}, draft, 0, 0)


def schema(case: Mapping[str, Any], fields: Sequence[str]) -> dict[str, Any]:
    """One `x-jevson.generate` string property per field, declaring that draft's criterion statements."""
    props = {
        f.removeprefix("/"): {
            "type": "string",
            "x-jevson": {"generate": {"criteria": [c["statement"] for c in case["drafts"][f]["criteria"]]}},
        }
        for f in fields
    }
    return {"type": "object", "properties": props, "required": sorted(props)}


def scripted(case: Mapping[str, Any], resolved: Mapping[str, Any]) -> ScriptedLLM:
    """The LLM that drafts each field of `resolved` (a schema from `schema`) with the case's draft."""
    graph = compile_schema(resolved)
    return ScriptedLLM({
        node.drafting.prompt: case["drafts"][node.target]["draft"]
        for node in graph.nodes.values()
        if isinstance(node, StepNode) and node.drafting is not None
    })  # fmt: skip


@dataclass
class Tally:
    requests: int = 0
    input_tokens: int = 0
    refusals: int = 0
    unanswered: int = 0
    models: set[str] = field(default_factory=set[str])
    requests_per_resolve: set[int] = field(default_factory=set[int])
    p_true: dict[str, int] = field(default_factory=dict[str, int])
    """Each answered criterion's probability of true in hundredths, by `case_id field criterion_id`."""


async def judge(backend: Backend, case: Mapping[str, Any], fields: Sequence[str], tally: Tally) -> Judged:
    resolved = schema(case, fields)
    jevson = Jevson(backend, llm=scripted(case, resolved))
    result = await jevson.aresolve(resolved, case["source"], redraft_budget=0)
    tally.requests += result.cost.decision_requests
    tally.input_tokens += result.cost.decision_input_tokens
    tally.models.update(result.model)
    tally.requests_per_resolve.add(result.cost.decision_requests)
    judged: Judged = {}
    for f in fields:
        judged[f] = {}
        for i, criterion in enumerate(case["drafts"][f]["criteria"]):
            decision = result.decisions.get(f"{f}#criterion:{i}@0")
            if decision is None:
                tally.unanswered += 1
                judged[f][criterion["id"]] = False
                continue
            tally.refusals += decision.selected is None
            if "true" in decision.distribution_hundredths:
                tally.p_true[f"{case['case_id']} {f} {criterion['id']}"] = decision.distribution_hundredths["true"]
            passed = decision.selected is True and decision.distribution_hundredths["true"] >= PASS_HUNDREDTHS
            judged[f][criterion["id"]] = passed
    return judged


async def run_injection(
    backend: Backend, cases: Sequence[Mapping[str, Any]], layout: Layout, concurrency: int = 8
) -> tuple[dict[str, Judged], Tally]:
    """Every case judged under `layout`; returns `judged` for `injection.regression` and the run's tally."""
    tally = Tally()
    gate = asyncio.Semaphore(concurrency)

    async def one(case: Mapping[str, Any]) -> tuple[str, Judged]:
        fields = sorted(case["drafts"])
        groups = [fields] if layout == "multi" else [[f] for f in fields]
        verdicts: Judged = {}
        for group in groups:
            async with gate:
                verdicts |= await judge(backend, case, group, tally)
        return case["case_id"], verdicts

    return dict(await asyncio.gather(*(one(c) for c in cases))), tally
