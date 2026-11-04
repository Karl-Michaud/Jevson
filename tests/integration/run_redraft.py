"""The billed redraft-bar run (PLAN Phase 4, J4b): opt-in, never in CI. See `tests/j4b/redraft.py` for the method.

    uv run --frozen python -m tests.integration.run_redraft pilot   # the last PILOT_DOCS documents; discarded
    uv run --frozen python -m tests.integration.run_redraft main    # the rest, under the stopping rule

Documents are shuffled with `ORDER_SEED`; the pilot takes the last `PILOT_DOCS` of that order and the main run never
sees them. Every LLM response is recorded by `ReplayLLM` under `tests/j4b/recordings/redraft/`, so a rerun replays
the drafts exactly (the decision model is called again). Outputs go to tests/integration/out/redraft/<mode>/
(gitignored): `instances.jsonl` (every draft and verdict), and for the main run `run.jsonl` (the labelling set,
the format of `tests/j4b/labelling/records.py`) and `sampling.json`. Then, for the labeller:

    uv run --frozen python -m tests.j4b.labelling.prepare_items tests/integration/out/redraft/main/run.jsonl OUT
"""

from __future__ import annotations

import asyncio
import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jevson import DecisionsBackend
from jevson.llm.replay import ReplayLLM
from jevson.protocols import LLM
from jevson.types import JSONValue, LLMResponse, Message
from tests.integration.key import openai_key
from tests.integration.openai_chat import MODEL, OpenAIChatLLM
from tests.j4b import redraft as R
from tests.j4b.labelling.records import write_jsonl

ORDER_SEED = 20261016
SAMPLE_SEED = 4100
DECOY_SEED = 4101
PILOT_DOCS = 12
MIN_REJECTED = 110
MIN_ADMITTED = 100
ADMITTED_SAMPLE = 100
USD_PER_MILLION = {"decision_in": 0.10, "llm_in": 0.75, "llm_out": 4.50}  # D1; the chat model's published price
SPEND_CAP_USD = 8.0
OUT = Path(__file__).parent / "out/redraft"
RECORDINGS = Path(__file__).resolve().parents[1] / "j4b/recordings/redraft"


class Counted:
    """Adds an LLM's tokens to a `Spend` (the decoy calls, which run outside `Jevson`)."""

    def __init__(self, inner: LLM, spend: R.Spend) -> None:
        self._inner, self._spend = inner, spend

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        response = await self._inner.complete(messages, tool_schema)
        self._spend.llm_input_tokens += response.input_tokens
        self._spend.llm_output_tokens += response.output_tokens
        return response


def usd(spend: R.Spend) -> float:
    p = USD_PER_MILLION
    return (
        spend.decision_input_tokens * p["decision_in"]
        + spend.llm_input_tokens * p["llm_in"]
        + spend.llm_output_tokens * p["llm_out"]
    ) / 1e6


def ordered() -> list[R.Document]:
    docs = R.documents()
    random.Random(ORDER_SEED).shuffle(docs)
    return docs


def pilot_doc_ids() -> list[str]:
    """The documents the pilot used, read back from its output so the main run never sees them, whatever the pool."""
    rows = [json.loads(line) for line in (OUT / "pilot/instances.jsonl").read_text().splitlines() if line.strip()]
    return sorted({r["doc_id"] for r in rows})


async def run(mode: str, key: str) -> dict[str, Any]:
    docs = ordered()
    if mode == "pilot":
        chosen = docs[-PILOT_DOCS:]
    else:
        excluded = set(pilot_doc_ids())
        chosen = [d for d in docs if d.doc_id not in excluded]
    out = OUT / mode
    out.mkdir(parents=True, exist_ok=True)
    chat = OpenAIChatLLM(key)
    llm = ReplayLLM(chat, RECORDINGS, llm_id=MODEL)

    def progress(instances: list[R.Instance], done: int) -> None:
        s = R.summary(instances)
        print(f"{done} docs: {s['instances']} instances, {s['first_rejected']} rejected, {s['first_admitted']} kept")

    async with DecisionsBackend(api_key=key) as backend:
        floor = (10**9, 0) if mode == "pilot" else (MIN_REJECTED, MIN_ADMITTED)  # the pilot runs all its documents
        instances, done, spend = await R.collect(
            backend, llm, chosen, min_rejected=floor[0], min_admitted=floor[1], on_batch=progress
        )
        assert usd(spend) < SPEND_CAP_USD, f"spend ${usd(spend):.2f} over the cap"
        write_jsonl(out / "instances.jsonl", [R.instance_record(i) for i in instances])
        report: dict[str, Any] = {
            "mode": mode, "documents_processed": done, "documents_available": len(chosen), **R.summary(instances),
            "llm": MODEL, "llm_returned_models": sorted(chat.returned_models),
            "decision_models": sorted(spend.models), "decision_requests": spend.decision_requests,
        }  # fmt: skip
        if mode == "main":
            by_id = {d.doc_id: d for d in chosen}
            sampled = R.sample_admitted(instances, ADMITTED_SAMPLE, SAMPLE_SEED)
            rng = random.Random(DECOY_SEED)
            picked = [i for i in instances if i.instance_id in set(sampled)]
            counted = Counted(llm, spend)
            decoys: dict[str, str | None] = {}
            for inst in picked:  # in run order, so the decoy seed's draws are reproducible
                decoys[inst.instance_id] = await R.decoy(counted, by_id[inst.doc_id], inst, rng)
            rows = R.labelling_rows(instances, by_id, sampled, decoys)
            write_jsonl(out / "run.jsonl", rows)
            report["sampling"] = {
                "order_seed": ORDER_SEED, "pilot_docs_excluded": pilot_doc_ids(), "contracts_in_pool": R.CONTRACTS,
                "sample_seed": SAMPLE_SEED,
                "decoy_seed": DECOY_SEED, "stopping_rule": {"min_rejected": MIN_REJECTED, "min_admitted": MIN_ADMITTED},
                "first_drafts": len(instances), "admitted_first_drafts": report["first_admitted"],
                "by_group": R.populations(instances),
                "sampled_admitted_instance_ids": sampled, "decoys_null": sum(v is None for v in decoys.values()),
                "rows_by_role": {r: sum(x["role"] == r for x in rows) for r in ("first", "redraft", "decoy")},
            }  # fmt: skip
            (out / "sampling.json").write_text(json.dumps(report["sampling"], indent=1) + "\n")
        report["tokens"] = {"llm_in": spend.llm_input_tokens, "llm_out": spend.llm_output_tokens,
                            "decision_in": spend.decision_input_tokens}  # fmt: skip
        report["spend_usd"] = usd(spend)
        report["replay_hits"] = llm.hits
        (out / "report.json").write_text(json.dumps(report, indent=1) + "\n")
        return report


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("pilot", "main"):
        print(__doc__)
        return 2
    key = openai_key()
    if not key:
        print("needs OPENAI_API_KEY or .env")
        return 2
    print(json.dumps(asyncio.run(run(argv[0], key)), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
