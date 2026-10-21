"""`export` and `score`: the grader's items from a complete confirm phase, and the single look (plan §7 single-look
items 1, 4, 7, 12(b); design §3, §6.2, §6.4).

`export` replays `attempt-N/confirm/` from its records and writes `attempt-N/confirm/export/` (items, key, chunks);
it prints only counts summed over every configuration. `score` first writes `analysis-started.json` (the SHA-256
of every label file, `items.jsonl` and `key.jsonl`, the confirm directory's tree hash, `harness_commit` and the
pins), then replays `attempt-N/confirm/` only, joins the labels, runs `adopt_48` and `decide_58`, and writes
`analysis.json` with `report(...)`. Afterwards every void attempt is reported, never decided on (item 12(b)).
`inconclusive` is the single look when no attempt is complete and not void (design §6.4, plan §11 D19).
"""

from __future__ import annotations

import hashlib
import json
import random
import secrets
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tests.j4b import injection
from tests.j4b.fresh import bar_inputs, export_items, grading, report, rules, runner
from tests.j4b.fresh.attempts import Attempts, Refused, RunLock, read_record, tree_hash, write_record
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.workload import Workload
from tests.j4b.labelling.records import read_jsonl


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(env: runner.Env, n: int) -> int:
    with RunLock(env.root):
        a = Attempts(env.root)
        if not a.complete(n) or a.void(n) is not None:
            raise Refused(f"attempt {n} is not a complete, non-void attempt")
        confirm = a.phase_dir(n, "confirm")
        w = env.load("confirm")
        outcomes = runner.outcomes_of(w, confirm, partial=False)
        items, key = export_items.export(export_items.build_stream(w, outcomes), _rng())
        paths = export_items.write(confirm / "export", items, key)
        done = confirm / "export"
        env.out(f"attempt {n}: {len(items)} items in {len(paths)} chunks; items.jsonl {_sha(done / 'items.jsonl')}, "
                f"key.jsonl {_sha(done / 'key.jsonl')} (the key stays in the run directory)")  # fmt: skip
        return 0


def _rng() -> random.Random:
    """Unseeded: item ids and order carry nothing a reader could use (design §3 step 1)."""
    return random.Random(secrets.randbits(64))


def outcomes(w: Workload, raw: Mapping[Unit, Mapping[str, Any]],
             rset: Mapping[rules.Config, Mapping[str, bar_inputs.RFirst]]) -> bar_inputs.Outcomes:  # fmt: skip
    """`bar_inputs.Outcomes` from replayed unit records."""
    iset: dict[str, dict[str, bool]] = {}
    p7: dict[str, dict[str, Any]] = {}
    pset: dict[rules.Config, dict[str, bool]] = {}
    for unit, record in raw.items():
        if unit.set_name == "iset":
            iset.setdefault(unit.arm, {})[unit.key] = record["flipped"]
        elif unit.set_name == "p7":
            p7.setdefault(unit.arm, {})[unit.key] = record["verdicts"]
        elif unit.set_name == "pset":
            pset.setdefault(unit.config, {})[unit.key] = record["admitted"]
    return bar_inputs.Outcomes(iset=iset, p7=p7, pset=pset, rset=rset)


def truncations(raw: Mapping[Unit, Mapping[str, Any]]) -> dict[str, int]:
    """Malformed (truncated) drafts per configuration (design §6.3)."""
    out: dict[str, int] = {}
    for unit, record in raw.items():
        if unit.set_name == "rset":
            name = f"{unit.arm}{unit.form}"
            out[name] = out.get(name, 0) + sum(f["malformed"] for f in record["fields"].values())
    return out


def start_record(a: Attempts, n: int, pins: Mapping[str, Any]) -> dict[str, Any]:
    confirm = a.phase_dir(n, "confirm")
    labels = sorted((confirm / "labels").glob("labels-*.jsonl"))
    if not labels:
        raise Refused(f"attempt {n} has no labels under confirm/labels/")
    return {
        "pins": dict(pins), "harness_commit": pins["harness_commit"], "confirm_tree_sha256": tree_hash(confirm),
        "items_sha256": _sha(confirm / "export" / "items.jsonl"), "key_sha256": _sha(confirm / "export" / "key.jsonl"),
        "labels_sha256": {p.name: _sha(p) for p in labels},
    }  # fmt: skip


def score(env: runner.Env, n: int) -> int:
    with RunLock(env.root):
        a = Attempts(env.root)
        pins = env.pins("score", n)
        if a.analysis_started() is not None:
            raise Refused("the analysis has already run: score runs once, ever")
        a.score_target(n)
        p7_cases = p7_fixture(env, a.phase_dir(n, "confirm"))
        a.begin_analysis(n, start_record(a, n, pins))
        decision = decide(env.load("confirm"), a.phase_dir(n, "confirm"), p7_cases)
        write_record(env.root / "analysis.json", decision, exclusive=True)
        env.out(json.dumps({k: decision[k] for k in ("asterion_48", "asterion_58")}, sort_keys=True))
        voided = void_reports(env, a)
        write_record(env.root / "void-reports.json", {"attempts": voided}, exclusive=True)
        return 0


def inconclusive(env: runner.Env) -> int:
    """`inconclusive`: with no complete non-void attempt, write both tickets' pre-registered outcome (design §6.4;
    plan §11 D19, H33): "inconclusive (spend cap)" when the last attempt was stopped at the cap or the start gate
    refused the next one, otherwise "inconclusive (no complete attempt: <each attempt's void reason>)". It is the
    single look: `analysis-started.json` first, then `analysis.json`, then the void reports; it runs once, ever."""
    with RunLock(env.root):
        a = Attempts(env.root)
        if a.analysis_started() is not None:
            raise Refused("the analysis has already run: the outcome is written once, ever")
        states = a.no_complete_attempt()
        refused = read_record(env.root / runner.START_GATE_REFUSED)
        if not states and refused is None:
            raise Refused("no attempt has run and the start gate has refused none: nothing to conclude")
        last = a.void(a.numbers()[-1]) if states else None
        cap_stopped = refused is not None or (last is not None and last["reason"] == "cap_stop")
        outcome = rules.no_attempt_outcome(states, cap_stopped=cap_stopped)
        a.begin_analysis(None, {"attempts": states, "cap_stopped": cap_stopped, "start_gate_refused": refused})
        decision: dict[str, Any] = {
            "asterion_48": {"adopted": None, "outcome": outcome},
            "asterion_58": {"shipped": None, "outcome": outcome, "strata_kept": []},
            "attempts": states,
        }
        write_record(env.root / "analysis.json", decision, exclusive=True)
        env.out(json.dumps({k: decision[k] for k in ("asterion_48", "asterion_58")}, sort_keys=True))
        write_record(env.root / "void-reports.json", {"attempts": void_reports(env, a)}, exclusive=True)
        return 0


def p7_fixture(env: runner.Env, confirm: Path) -> list[dict[str, Any]]:
    """The [P7] cases, loaded only after the fixture re-hashes to `confirm/start.json`'s record (H29)."""
    recorded = (read_record(confirm / "start.json") or {}).get("p7_sha256")
    if _sha(env.p7_fixture) != recorded:
        raise Refused("the [P7] fixture differs from the one recorded at confirm/start.json")
    return injection.load_fixture(env.p7_fixture)


def decide(w: Workload, confirm: Path, p7_cases: list[dict[str, Any]]) -> dict[str, Any]:
    raw = runner.outcomes_of(w, confirm, partial=False)
    items, key = read_jsonl(confirm / "export" / "items.jsonl"), read_jsonl(confirm / "export" / "key.jsonl")
    labels = export_items.read_labels(confirm / "labels", items)
    rset = grading.rset_truths(raw, grading.truths(key, labels))
    inputs = bar_inputs.BarInputs(w.rows, outcomes(w, raw, rset))
    readings = bar_inputs.DataReadings(inputs, p7_cases)
    adopted, outcome_48 = rules.adopt_48(readings)
    shipped, outcome_58, kept = rules.decide_58(readings, adopted)
    fields = {str(r["draft_id"]): str(r["field"]) for r in w.rows["rset.jsonl"]}
    extras = {**grading.secondaries(key, labels), "truncations": truncations(raw)}
    return {
        "asterion_48": {"adopted": adopted, "outcome": outcome_48},
        "asterion_58": {"shipped": list(shipped) if shipped else None, "outcome": outcome_58, "strata_kept": kept},
        "report": report.report(inputs, p7_cases=p7_cases, rset_fields=fields, extras=extras),
    }


def void_reports(env: runner.Env, a: Attempts) -> list[dict[str, Any]]:
    """Item 12(b): every void attempt, complete or not, over its code-truth bars only; never decides anything. Its
    R-set admissions are joined with no truth (every draft untrue), which the report reads only for the (L0, F0)
    rejected count (plan D15): a void report has no R-set bars."""
    out: list[dict[str, Any]] = []
    for m in a.numbers():
        void = a.void(m)
        confirm = a.phase_dir(m, "confirm")
        if void is None or not confirm.exists():
            continue
        w = env.load("confirm")
        raw = runner.outcomes_of(w, confirm, partial=True)
        inputs = bar_inputs.build(w.rows, outcomes(w, raw, grading.rset_truths(raw, {})), partial=True)
        cases = [c for c in injection.load_fixture(env.p7_fixture)
                 if all(c["case_id"] in v for v in inputs.outcomes.p7.values())]  # fmt: skip
        out.append({"attempt": m, "voided": void["voided"], "reason": void["reason"], "label": "voided, non-deciding",
                    "report": report.report(inputs, p7_cases=cases, rset_fields={})})  # fmt: skip
    return out
