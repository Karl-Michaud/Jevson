"""The dry run: the figures Karl approves before any paid request (plan §7 "dryrun", §12; design §6.3).

No network and no key. It builds every unit of both phases from the committed fixtures, runs each once through
Jevson offline (`bounds.py`), and prints: the decision-request counts per set and in total, issued and after
deduplication; first drafts and the largest possible number of drafting calls; the expected, 60% and all-rejected
figures of the design's cost model and the true bound (the sum of every request's bound); R_max as the design
states it (4 bytes per character) beside the reservation the runner uses (7 decision, 6 chat); the share up to
which two attempts fit at each R_max; and the minimum decision-bound margin per set. Every figure is printed
first; then, if any request's margin is negative, `check` raises `MarginViolation` naming them, so the run is
refused before any spend. An R-set request cannot be built exactly before its drafts exist: it is built with
placeholder drafts of a few characters, the shortest a draft can be, so its margin is the worst case.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tests.j4b.fresh import bounds, costs, packing, workload
from tests.j4b.fresh.constants import CAP, NANO
from tests.j4b.fresh.workload import Workload

SETS = ("iset", "p7", "pset", "rset")
CAP_SENTENCE = (
    "The $15 cap, not the true bound, limits an attempt: every HTTP attempt is reserved at its bound and refused "
    "when spend + open reservations + its bound would pass $15."
)


class MarginViolation(Exception):
    """A decision request whose bytes + 64 fall below the harness formula: the run would under-reserve it."""


@dataclass
class PhaseFigures:
    phase: str
    issued: dict[str, int] = field(default_factory=dict[str, int])
    distinct: dict[str, int] = field(default_factory=dict[str, int])
    first_drafts: int = 0
    max_drafting_calls: int = 0
    true_bound: int = 0
    r_max: dict[str, int] = field(default_factory=dict[str, int])
    min_margin: dict[str, int] = field(default_factory=dict[str, int])
    violations: list[str] = field(default_factory=list[str])
    configuration_batches: list[list[packing.Unit]] = field(default_factory=list[list[packing.Unit]])
    drafting_batches: list[list[str]] = field(default_factory=list[list[str]])


def _margins(f: PhaseFigures, unit: packing.Unit, requests: bounds.UnitRequests) -> None:
    worst = min(bounds.margins(requests.decisions))
    f.min_margin[unit.set_name] = min(worst, f.min_margin.get(unit.set_name, worst))
    if worst < 0:
        f.violations.append(f"{f.phase} {unit.set_name} {unit.key} {unit.arm}{unit.form}: margin {worst} tokens")


def phase_figures(w: Workload) -> PhaseFigures:
    f = PhaseFigures(w.phase)
    per_unit: dict[packing.Unit, bounds.UnitRequests] = {}
    seen: set[bytes] = set()
    for name in SETS:
        f.issued[name], before = 0, len(seen)
        for unit in w.units.get(name, ()):
            requests = per_unit[unit] = bounds.unit_requests(w, unit)
            f.issued[name] += len(requests.decisions)
            seen |= {r.key for r in requests.decisions}
            _margins(f, unit, requests)
        f.distinct[name] = len(seen) - before
    f.first_drafts = sum(len(w.fields[d.domain]) for d in w.documents.values())
    f.max_drafting_calls = f.first_drafts + sum(len(r.redrafts) for u, r in per_unit.items() if u.set_name == "rset")
    f.configuration_batches = packing.configuration_batches(w.units)
    f.drafting_batches = packing.drafting_batches(list(w.documents))
    drafting = {d: bounds.drafting_bound(w, d) for d in w.documents}
    for label, (dec, chat) in {"design": (4, 4), "run": (7, 6)}.items():
        priced = {u: bounds.unit_bound(r, decision_bpc=dec, chat_bpc=chat) for u, r in per_unit.items()}
        largest = max(sum(priced[u] for u in b) for b in f.configuration_batches)
        f.r_max[label] = max(largest, *(sum(drafting[d] for d in b) for b in f.drafting_batches))
        if label == "run":
            f.true_bound = sum(priced.values()) + sum(drafting.values())
    return f


def figures(
    phases: Sequence[str] = ("dev", "confirm"), load: Callable[[str], Workload] = workload.load
) -> dict[str, Any]:
    loads = [load(p) for p in phases]
    per_phase = [phase_figures(w) for w in loads]
    splits = [workload.cost_inputs(w) for w in loads]
    r_max = {k: max(f.r_max[k] for f in per_phase) for k in ("design", "run")}
    return {
        "phases": per_phase,
        "expected_usd": costs.expected_usd(splits),
        "start_gate_usd": costs.start_gate_usd(splits),
        "all_rejected_usd": costs.attempt_usd(splits, 1.0),
        "true_bound_usd": sum(f.true_bound for f in per_phase) / NANO,
        "r_max_usd": {k: v / NANO for k, v in r_max.items()},
        "two_attempt_share": {k: costs.two_attempt_share(splits, v) for k, v in r_max.items()},
        "violations": [v for f in per_phase for v in f.violations],
    }


def check(fig: Mapping[str, Any]) -> None:
    """Raise before any spend if a decision request's bytes + 64 fall below the harness formula (FEAS48-7)."""
    if fig["violations"]:
        shown = "\n  ".join(fig["violations"][:20])
        raise MarginViolation(f"{len(fig['violations'])} units have a request with a negative margin:\n  {shown}")


def _phase_lines(f: PhaseFigures) -> list[str]:
    lines = [f"[{f.phase}]"]
    for name in SETS:
        if f.issued.get(name):
            lines.append(f"  {name:5s} decision requests: {f.issued[name]:6d} issued, {f.distinct[name]:6d} distinct")
    lines.append(f"  total decision requests: {sum(f.issued.values())} issued, {sum(f.distinct.values())} distinct")
    lines.append(f"  first drafts {f.first_drafts}; drafting calls at most {f.max_drafting_calls}")
    lines.append(f"  batches: {len(f.drafting_batches)} drafting (<= 10 documents), "
                 f"{len(f.configuration_batches)} configuration (<= 10 units)")  # fmt: skip
    lines.append(f"  true bound ${f.true_bound / NANO:.3f}")
    margins = ", ".join(f"{k} {v}" for k, v in f.min_margin.items())
    lines.append(f"  minimum decision-bound margin (tokens; R-set with placeholder drafts): {margins}")
    lines.append(f"  units with a negative margin: {len(f.violations)}")
    return lines


def render(fig: Mapping[str, Any]) -> str:
    lines: list[str] = []
    for f in fig["phases"]:
        lines += _phase_lines(f)
    r, share = fig["r_max_usd"], fig["two_attempt_share"]
    lines += [
        "[one attempt: dev + confirm]",
        "  R-set redraft counts assume every first draft is rejected (the most requests); the rest are exact.",
        f"  expected (design cost model, assumed rejection shares) ${fig['expected_usd']:.2f}",
        f"  start-gate figure (redrafts at 60% everywhere) ${fig['start_gate_usd']:.2f}",
        f"  all-rejected figure at $0.00193 per drafting call ${fig['all_rejected_usd']:.2f}",
        f"  true bound (sum of every request's bound) ${fig['true_bound_usd']:.2f}",
        f"  R_max as the design states it (4 bytes per character) ${r['design']:.3f}; "
        f"as the runner reserves (7 decision, 6 chat) ${r['run']:.3f}",
        f"  two attempts fit at one rejection share s <= {share['design']:.3f} (design R_max) / "
        f"{share['run']:.3f} (runner R_max), from (${CAP / NANO:.0f} - R_max) / 2",
        f"  {CAP_SENTENCE}",
    ]
    return "\n".join(lines)
