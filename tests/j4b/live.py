"""J4b's live runs: STUBS until J4a (ASTERION-32) merges.

J4a is still building the generate step, adjudication and the redraft loop, so the calls below are deliberately not
written against guessed interfaces. The only interface assumed is the `LLM` protocol already on staging
(`jevson.protocols.LLM`). Both runs are opt-in integration runs that read OPENAI_API_KEY from Jevson/.env; the library
never reads it.

TODO(J4b), injection regression:
  1. For each case in `injection.load_fixture()`, build one schema with two `x-jevson.generate` string fields,
     `/summary` and `/companion_summary`, each declaring its case's `criteria[*].statement`.
  2. Adjudicate both drafts (`drafts[field]["draft"]`, as the LLM's output, e.g. through `ReplayLLM`) in one level
     under the keyed layout of DESIGN §5.2 (`drafts: {node id: draft}`), with `redraft_budget=0`.
  3. Collect `judged[case_id][field][criterion_id] = passed` and call `injection.regression(cases, judged)`.
  4. If it fails, rerun each draft alone (single-draft layout); if that passes, adjudication issues one call per
     draft (PLAN Phase 4). Record the counts in docs/EVIDENCE.md.
TODO(J4b), redraft bar:
  1. Choose fields and sources so that at least 100 first drafts are rejected (PLAN Phase 4 asks for >= 100).
  2. Resolve with `redraft_budget=1` through a real `LLM` adapter and write one run row per draft in the format of
     `labelling/records.py` (role first/redraft, admitted, criteria; a null draft when no draft was produced).
  3. `python -m tests.j4b.labelling.prepare_items run.jsonl out/`, hand `out/items.jsonl` to the labeller, then
     `python -m tests.j4b.labelling.score out/key.jsonl labels.jsonl`.
"""

from __future__ import annotations

from pathlib import Path

from jevson.protocols import LLM


async def run_injection_regression(llm: LLM, out: Path) -> None:
    raise NotImplementedError("J4b: needs J4a's generate step and adjudication (see the module docstring)")


async def collect_redraft_run(llm: LLM, out: Path) -> None:
    raise NotImplementedError("J4b: needs J4a's redraft loop (see the module docstring)")
