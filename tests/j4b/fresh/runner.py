"""The runner's commands, `dev`, `confirm`, `void` and the attempt half of `score` (plan §7; design §6.2-§6.4).

`tests/integration/run_fresh.py` parses arguments and calls these; every rule lives in the modules they call
(`pins`, `attempts`, `gates`, `requeue`, `spend`, `metering`, `phases`), and this module only orders them:

1. take `run.lock` (a stale lock is reported and replaced), check the pins, check the attempt rules;
2. the start gate: spend so far + this attempt's remaining estimate at a 60% rejection share fits under $15;
3. `start.json` (pins, `harness_commit`, every configuration's `JevsonConfig`), then the drafting phase and the
   configuration phase, the model strings checked per endpoint after every batch;
4. a full replay of the phase from its records, which must miss nothing;
5. `complete.json`, written last.

A guard stop (cap, usage over bound, model-string change, replay miss) writes `void.json` with that reason at the
stop. Exhausted re-queues and a first-draft gate violation are harness defects: the attempt is left incomplete,
with the failing unit named, for `void --reason harness_defect`. `confirm` prints only spend, request and
drafting-call counts summed over every configuration, and model strings; `dev` also prints the P-dev churn.
"""

from __future__ import annotations

import asyncio
import dataclasses
import hashlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from tests.j4b.build_injection_fixture import FIXTURE as P7_FIXTURE
from tests.j4b.fresh import admission, arms, bounds, costs, gates, phases, requeue, workload
from tests.j4b.fresh.attempts import Attempts, Refused, RunLock
from tests.j4b.fresh.constants import NANO
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.fresh.workload import Workload

Sleep = Callable[[float], Awaitable[object]]
PinCheck = Callable[[str, int], Mapping[str, Any]]
"""(command, attempt) -> the pins record (`pins.check(...).record()`), or raises `PinMismatch`."""
DEFECTS = (requeue.RequeuesExhausted, phases.GateViolation)


class ModelStringChange(Exception):
    """A returned `model` string differs from the attempt's first one on the same endpoint (plan §11 D6)."""


@dataclass
class Env:
    """What a command runs against; tests pass `tmp_path`, a mock transport and no-op sleeps."""

    root: Path
    pins: PinCheck
    transport: httpx.AsyncBaseTransport | None = None
    key: Callable[[], str] = lambda: ""
    sleep: Sleep = asyncio.sleep
    """The runner's own re-queue waits."""
    client_sleep: Sleep = asyncio.sleep
    """The clients' retry backoff and rate limiter."""
    load: Callable[[str], Workload] = workload.load
    out: Callable[[str], None] = print
    p7_fixture: Path = P7_FIXTURE
    """The [P7] fixture, hashed into `confirm/start.json` and re-checked by `score` (H29, STATS48-R8-1)."""


def configurations() -> dict[str, dict[str, Any]]:
    return {arm: dataclasses.asdict(config) for arm, config in arms.LIBRARY_ARMS.items()}


def remaining_estimate(env: Env, phase: str) -> int:
    """The start gate's figure for what is left of this attempt: dev + confirm at dev, confirm at confirm."""
    left = ("dev", "confirm") if phase == "dev" else ("confirm",)
    return int(costs.start_gate_usd([workload.cost_inputs(env.load(p)) for p in left]) * NANO)


def check_models(ledger: SpendLedger, n: int) -> None:
    for endpoint, found in phases.model_strings(ledger, n).items():
        if len(found) > 1:
            raise ModelStringChange(f"{endpoint} returned {sorted(found)} in attempt {n}")


def reservations(w: Workload) -> tuple[dict[Unit, int], dict[str, int]]:
    """Every configuration unit's and drafting unit's reservation, computed before any request (7 and 6 bytes per
    unseen draft character)."""
    units = {u: bounds.unit_bound(bounds.unit_requests(w, u), decision_bpc=7, chat_bpc=6)
             for us in w.units.values() for u in us}  # fmt: skip
    return units, {d: bounds.drafting_bound(w, d) for d in w.documents}


async def run_attempt_phase(
    env: Env, ledger: SpendLedger, w: Workload, directory: Path, *, n: int,
    reserved: tuple[Mapping[Unit, int], Mapping[str, int]],
) -> dict[Unit, Any]:  # fmt: skip
    units, drafting = reserved
    c = phases.clients(directory, ledger, key=env.key(), transport=env.transport or httpx.AsyncHTTPTransport(),
                       run_attempt=n, sleep=env.client_sleep)  # fmt: skip

    def guard() -> None:
        check_models(ledger, n)

    keys = await phases.drafting_phase(c, ledger, w, bound=drafting.__getitem__, sleep=env.sleep, after_batch=guard)
    judged = await phases.configuration_phase(
        c, ledger, w, keys, bound=units.__getitem__, sleep=env.sleep, after_batch=guard
    )
    return admission.records(judged)


async def replay(ledger: SpendLedger, w: Workload, directory: Path, sleep: Sleep) -> dict[Unit, Any]:
    """The phase from its records only; any miss raises `ReplayMiss` (design §6.2, R15)."""
    c = phases.replay_clients(directory)
    keys = await phases.drafting_phase(c, ledger, w, bound=lambda _: 0, sleep=sleep)
    return admission.records(await phases.configuration_phase(c, ledger, w, keys, bound=lambda _: 0, sleep=sleep))


def guard_reason(error: Exception, ledger: SpendLedger) -> str | None:
    if isinstance(error, requeue.CapStop):
        return "usage_over_bound" if ledger.violation is not None else "cap_stop"
    if isinstance(error, requeue.ReplayMiss):
        return "replay_miss"
    if isinstance(error, ModelStringChange):
        return "model_string_change"
    return None


def counts(ledger: SpendLedger, since: int) -> dict[str, int]:
    """HTTP attempts and spend of this phase, summed over every configuration (never per configuration)."""
    settled = list(ledger.settles(since))
    return {
        "decision_requests": sum(s.endpoint == "decisions" for s in settled),
        "drafting_calls": sum(s.endpoint == "chat" for s in settled),
        "spend_nano": sum(s.billed for s in settled),
    }


def churn(outcomes: Mapping[Unit, Any], rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """The P-dev template churn of each configuration against (L0, F0): the share of template pairs with any
    draft whose admission differs (design §5, "Churn on the dev set"); information only."""
    admitted = {(u.arm, u.form, u.key): o["admitted"] for u, o in outcomes.items() if u.set_name == "pset"}
    pairs: dict[str, list[str]] = {}
    for row in rows:
        pairs.setdefault(str(row["pair"]), []).append(str(row["draft_id"]))
    out: dict[str, float] = {}
    for arm, form in arms.CONFIGURATIONS:
        changed = sum(any(admitted[(arm, form, d)] != admitted[("L0", "F0", d)] for d in ids) for ids in pairs.values())
        out[f"{arm}{form}"] = changed / len(pairs) if pairs else 0.0
    return out


def _start(env: Env, a: Attempts, phase: str, n: int, ledger: SpendLedger) -> tuple[Mapping[str, Any], Path]:
    pins = env.pins(phase, n)
    a.check_start(n, phase)
    if not gates.start_gate(ledger, remaining_estimate(env, phase)):
        raise Refused(f"start gate: spend ${ledger.billed / NANO:.2f} + this attempt's 60% estimate passes the cap")
    record = {"pins": dict(pins), "harness_commit": pins["harness_commit"], "configurations": configurations()}
    if phase == "confirm":
        record["p7_sha256"] = hashlib.sha256(env.p7_fixture.read_bytes()).hexdigest()
    return pins, a.start(n, phase, record)


def run_phase(env: Env, phase: str, n: int) -> int:
    """`dev --attempt n` or `confirm --attempt n`: 0 complete, 2 voided by a guard, 3 a harness defect."""
    with RunLock(env.root) as lock:
        if lock.stale is not None:
            env.out(f"run.lock named pid {lock.stale}, which is not running: stale, replaced")
        a, ledger = Attempts(env.root), SpendLedger(env.root)
        pins, directory = _start(env, a, phase, n, ledger)
        w, since = env.load(phase), ledger.position()
        reserved = reservations(w)
        try:
            outcomes = asyncio.run(run_attempt_phase(env, ledger, w, directory, n=n, reserved=reserved))
            check_models(ledger, n)
            asyncio.run(replay(ledger, w, directory, env.sleep))
        except DEFECTS as defect:
            env.out(f"harness defect, attempt {n} left incomplete: {defect}; void it with --reason harness_defect")
            return 3
        except (requeue.CapStop, requeue.ReplayMiss, ModelStringChange) as stop:
            reason = str(guard_reason(stop, ledger))
            a.write_void(n, reason, {"phase": phase, "detail": str(stop)})
            env.out(f"attempt {n} void: {reason} ({stop})")
            return 2
        summary: dict[str, Any] = {**counts(ledger, since), "units": len(outcomes)}
        summary["model_strings"] = {k: sorted(v) for k, v in phases.model_strings(ledger, n).items()}
        a.finish(n, phase, {"pins": dict(pins), "harness_commit": pins["harness_commit"], **summary})
        env.out(render_summary(phase, n, summary, ledger))
        if phase == "dev":
            env.out(f"P-dev template churn against (L0, F0): {churn(outcomes, w.rows['pset_dev.jsonl'])}")
        return 0


def render_summary(phase: str, n: int, summary: Mapping[str, Any], ledger: SpendLedger) -> str:
    return (
        f"attempt {n} {phase} complete: {summary['decision_requests']} decision requests and "
        f"{summary['drafting_calls']} drafting calls over all configurations; spend this phase "
        f"${summary['spend_nano'] / NANO:.4f}, over every attempt ${ledger.billed / NANO:.4f}; "
        f"model strings {summary['model_strings']}"
    )


def void(env: Env, n: int, reason: str, *, note: str | None, test: Callable[[], Mapping[str, Any]] | None) -> int:
    """`void --attempt n --reason harness_defect`: the only void entered by hand (single-look items 5, 11, 12)."""
    with RunLock(env.root) as lock:
        if lock.stale is not None:
            env.out(f"run.lock named pid {lock.stale}, which is not running: stale, replaced")
        a = Attempts(env.root)
        if a.analysis_started() is not None:
            raise Refused("the analysis has started: no attempt is voided")
        if reason not in ("harness_defect",):
            raise Refused(f"{reason!r}: only harness_defect is voided by hand (closed list: design §6.4)")
        a.hand_void(n, reason, note=note, test=test)
        env.out(f"attempt {n} void: {reason}")
        return 0


def outcomes_of(w: Workload, directory: Path, *, partial: bool) -> dict[Unit, Any]:
    """Replay a phase's records; with `partial`, keep only the units that replay (a void attempt's report)."""
    if not partial:
        return asyncio.run(replay(SpendLedger(directory / ".no-spend"), w, directory, _no_wait))
    c, keys = phases.replay_clients(directory), phases.first_keys(w)
    kept: dict[Unit, Any] = {}
    for unit in (u for us in w.units.values() for u in us):
        try:
            kept[unit] = admission.record(asyncio.run(phases.run_unit(c, w, keys, unit)))
        except Exception:  # a unit that does not replay is simply not recorded
            continue
    return kept


async def _no_wait(_: float) -> None:
    return None
