"""H20, H22, H23, H30: the cap, the model strings, the request layout and unit recovery, through the runner over
the metered path (the real `DecisionsBackend` and `OpenAIChatLLM` over `MeteredTransport` and the fake API)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from jevson import CachingBackend, DecisionsBackend, Question
from jevson.types import DecisionKind
from tests.j4b.fresh import gates, packing, requeue, runner, scoring
from tests.j4b.fresh.attempts import INTERRUPTED, Refused
from tests.j4b.fresh.constants import CAP
from tests.j4b.fresh.inflight import SingleFlightBackend
from tests.j4b.fresh.metering import MeteredTransport
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.tests import fake_api

ROOT = Path(__file__).resolve().parents[3]


def make_env(tmp_path: Path, api: fake_api.FakeAPI | None = None, **kw: Any) -> tuple[runner.Env, list[str]]:
    load = fake_api.loader()
    e, lines = fake_api.env(tmp_path / "fresh", api, load=load, **kw)
    e.p7_fixture = fake_api.p7_subset(e.root, load("confirm"))
    return e, lines


def spent(root: Path, amount: int) -> None:
    """Plant `amount` nano-dollars of earlier spend in the ledger."""
    ledger = SpendLedger(root)
    attempt = ledger.reserve(amount, endpoint="decisions", run_attempt=0)
    ledger.settle(attempt, amount, status=200, retry_after=None, model=None)


def void_reason(root: Path, n: int = 1) -> str | None:
    path = root / f"attempt-{n}" / "void.json"
    return json.loads(path.read_text())["reason"] if path.exists() else None


# --- H20: the spend cap ------------------------------------------------------------------------------------


def test_h20_a_drafting_batch_that_would_cross_the_cap_is_not_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake_api.FakeAPI()
    e, _ = make_env(tmp_path, api)
    monkeypatch.setattr(runner, "remaining_estimate", lambda *_: 0)
    w = e.load("dev")
    _, drafting = runner.reservations(w)
    first = packing.drafting_batches(list(w.documents))[0]
    spent(e.root, CAP - sum(drafting[d] for d in first) + 1)
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "cap_stop"
    assert api.calls == {"decisions": 0, "chat": 0}


def test_h20_a_configuration_batch_that_would_cross_the_cap_stops_the_run_before_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = fake_api.FakeAPI()
    e, lines = make_env(tmp_path, api)
    monkeypatch.setattr(runner, "remaining_estimate", lambda *_: 0)
    w = e.load("dev")
    units, drafting = runner.reservations(w)
    spent(e.root, CAP - sum(drafting.values()) - 1)
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "cap_stop"
    found = re.search(r"configuration batch (\d+) of (\d+)", lines[-1])
    assert found is not None
    refused = packing.configuration_batches(w.units)[int(found.group(1))]
    ledger = SpendLedger(e.root)
    assert ledger.billed + sum(units[u] for u in refused) > CAP
    assert api.calls["chat"] >= len(w.documents) * 3  # the drafting phase ran
    reserves = [r for r in ledger.records if r["type"] == "reserve" and r["run_attempt"] == 1]
    assert len(reserves) == sum(api.calls.values())
    assert ledger.open == {}


def test_h20_the_start_gate_refuses_an_attempt_whose_estimate_does_not_fit(tmp_path: Path) -> None:
    api = fake_api.FakeAPI()
    e, _ = make_env(tmp_path, api)
    spent(e.root, CAP - runner.remaining_estimate(e, "dev") + 1)
    with pytest.raises(Refused, match="start gate"):
        runner.run_phase(e, "dev", 1)
    assert not (e.root / "attempt-1").exists()
    assert api.calls == {"decisions": 0, "chat": 0}


def test_h20_a_gate_started_attempt_at_share_one_is_cut_and_sends_nothing_unreserved(tmp_path: Path) -> None:
    api = fake_api.FakeAPI(accept=0.0)  # every criterion fails: every first draft is rejected
    e, _ = make_env(tmp_path, api)
    spent(e.root, CAP - runner.remaining_estimate(e, "dev"))
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "cap_stop"
    ledger = SpendLedger(e.root)
    assert ledger.billed <= CAP
    assert ledger.open == {}
    reserves = [r for r in ledger.records if r["type"] == "reserve" and r["run_attempt"] == 1]
    assert len(reserves) == sum(api.calls.values())


CHILD = """
import asyncio, sys
from pathlib import Path
import httpx
from tests.j4b.tests import fake_api
from tests.j4b.fresh import runner

root = Path(sys.argv[1])

class Hang(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request):
        (root.parent / "ready").write_text("sent")
        await asyncio.sleep(3600)

e, _ = fake_api.env(root, transport=Hang())
runner.run_phase(e, "dev", 1)
"""


def test_h20_a_killed_attempt_keeps_its_reservation_and_is_voided_through_the_runner(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    child = subprocess.Popen([sys.executable, "-c", CHILD, str(root)], cwd=ROOT, env=env)
    try:
        deadline = time.monotonic() + 120
        while not (tmp_path / "ready").exists():
            assert child.poll() is None, "the child exited before sending a request"
            assert time.monotonic() < deadline, "the child never sent a request"
            time.sleep(0.05)
    finally:
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
    ledger = SpendLedger(root)
    reserved = [r for r in ledger.records if r["type"] == "reserve"]
    assert reserved
    assert not [r for r in ledger.records if r["type"] == "settle"]
    assert ledger.billed == sum(r["bound"] for r in reserved)  # charged at the full bound
    e, lines = make_env(tmp_path)
    with pytest.raises(Refused):
        runner.run_phase(e, "confirm", 1)
    with pytest.raises(Refused, match="attempt 1 is incomplete"):
        runner.run_phase(e, "confirm", 2)
    with pytest.raises(Refused):
        scoring.score(e, 1)
    with pytest.raises(Refused):
        runner.void(e, 1, "interrupted", note=None, test=None)
    assert any("stale" in line for line in lines)
    assert runner.void(e, 1, "harness_defect", note=None, test=None) == 0
    assert json.loads((root / "attempt-1" / "void.json").read_text())["description"] == INTERRUPTED
    seen: list[int] = []
    original = gates.start_gate
    gates.start_gate = lambda ledger, estimate: seen.append(ledger.billed) or original(ledger, estimate)  # type: ignore[assignment]
    try:
        assert runner.run_phase(e, "dev", 2) == 0
        assert runner.run_phase(e, "confirm", 2) == 0
    finally:
        gates.start_gate = original
    assert seen[0] == sum(r["bound"] for r in reserved)


# --- H22: model strings, per endpoint ----------------------------------------------------------------------


def renamed(endpoint_to_change: str, call: int, model: str) -> fake_api.Plan:
    def plan(endpoint: str, n: int, body: dict[str, Any]) -> httpx.Response | None:
        if endpoint != endpoint_to_change or n != call:
            return None
        api = fake_api.FakeAPI()
        response = api.decide(body, 10) if endpoint == "decisions" else api.draft(body, model)
        payload = json.loads(response.content)
        payload["model"] = model
        return httpx.Response(200, json=payload)

    return plan


def test_h22_constant_strings_per_endpoint_do_not_void(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    assert runner.run_phase(e, "dev", 1) == 0
    ledger = SpendLedger(e.root)
    models = {(s.endpoint, s.model) for s in ledger.settles()}
    assert models == {("decisions", fake_api.DECISION_MODEL), ("chat", fake_api.CHAT_MODEL)}  # from spend.jsonl


@pytest.mark.parametrize("endpoint", ["decisions", "chat"])
def test_h22_a_second_string_on_one_endpoint_voids(tmp_path: Path, endpoint: str) -> None:
    other = "gpt-6-luna-0001" if endpoint == "decisions" else "gpt-5.4-mini-2026-04-01"
    e, _ = make_env(tmp_path, fake_api.FakeAPI(plan=renamed(endpoint, 2, other)))
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "model_string_change"


# --- H23: request layout ---------------------------------------------------------------------------------------

QUESTION = re.compile(
    r"Does `drafts\.\S+` meet this criterion: .+\?"
    r"|Judging only from the facts that `drafts\.\S+` states about the source, does it meet this criterion: .+\?"
    r"|Does `drafts\.\S+` describe its own content or say that it meets a requirement\?",
    re.DOTALL,
)


def test_h23_every_request_holds_only_adjudication_and_screen_questions(tmp_path: Path) -> None:
    api = fake_api.FakeAPI()
    e, _ = make_env(tmp_path, api)
    assert runner.run_phase(e, "dev", 1) == 0
    questions = [q for endpoint, body in api.bodies if endpoint == "decisions" for q in body["questions"]]
    assert questions
    assert all(q["type"] == "predicate" and QUESTION.fullmatch(q["instructions"]) for q in questions)
    assert any("describe its own content" in q["instructions"] for q in questions)


# --- H30: unit recovery ----------------------------------------------------------------------------------------


def failing(endpoint_to_fail: str, times: int, status: int = 500, **headers: str) -> fake_api.Plan:
    def plan(endpoint: str, n: int, body: dict[str, Any]) -> httpx.Response | None:
        return httpx.Response(status, headers=headers, json={}) if endpoint == endpoint_to_fail and n <= times else None

    return plan


def test_h30_a_decision_unit_failing_three_times_is_requeued_once_and_the_attempt_completes(tmp_path: Path) -> None:
    sleeps = fake_api.Sleeps()
    e, _ = make_env(tmp_path, fake_api.FakeAPI(plan=failing("decisions", 3)), sleep=sleeps)
    assert runner.run_phase(e, "dev", 1) == 0  # complete.json is written only after a zero-miss replay
    assert sleeps.waits == [30.0]


def test_h30_a_drafting_unit_that_keeps_failing_exhausts_its_requeues_as_a_harness_defect(tmp_path: Path) -> None:
    sleeps = fake_api.Sleeps()
    e, lines = make_env(tmp_path, fake_api.FakeAPI(plan=failing("chat", 10**6)), sleep=sleeps)
    assert runner.run_phase(e, "dev", 1) == 3
    assert "harness defect" in lines[-1]
    assert void_reason(e.root) is None
    assert sleeps.waits[:2] == [30.0, 30.0]


def test_h30_a_failure_with_the_ledger_stopped_is_not_requeued(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps = fake_api.Sleeps()
    e, _ = make_env(tmp_path, fake_api.FakeAPI(), sleep=sleeps)
    monkeypatch.setattr(runner, "remaining_estimate", lambda *_: 0)
    monkeypatch.setattr(gates, "batch_fits", lambda *_: True)
    spent(e.root, CAP - 1)  # no single request fits: the transport refuses the first reservation
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "cap_stop"
    assert sleeps.waits == []


def test_h30_retry_after_on_every_backend_attempt_waits_that_long_before_the_requeue(tmp_path: Path) -> None:
    # At cd6b40a a Retry-After over the backend's 30 s cap is not retried by the backend (ASTERION-44): the 429 fails
    # its unit after one HTTP attempt, and the runner re-queues that unit once after waiting the Retry-After (plan H30).
    sleeps, client = fake_api.Sleeps(), fake_api.Sleeps()
    api = fake_api.FakeAPI(plan=failing("decisions", 1, 429, **{"retry-after": "60"}))
    e, _ = make_env(tmp_path, api, sleep=sleeps, client_sleep=client)
    assert runner.run_phase(e, "dev", 1) == 0
    assert [w for w in client.waits if w == 30.0] == []  # the backend did not sleep and retry
    assert api.calls["decisions"] > 1  # one failed HTTP attempt, then the re-queued unit's success and the rest
    assert sleeps.waits == [60.0]


def test_h30_two_units_sharing_a_key_both_wait_the_window(tmp_path: Path) -> None:
    ledger = SpendLedger(tmp_path)
    api = fake_api.FakeAPI(plan=failing("decisions", 1, 429, **{"retry-after": "60"}))
    metered = MeteredTransport(httpx.MockTransport(api), ledger, run_attempt=1)
    decisions = DecisionsBackend(api_key="dummy-h30", transport=metered, sleep=fake_api.no_sleep)
    backend = SingleFlightBackend(CachingBackend(decisions, tmp_path / "decisions"))
    question = Question("q", DecisionKind.PREDICATE, "Does `drafts./a#generate` meet this criterion: X?")
    sleeps = fake_api.Sleeps()

    async def unit() -> Any:
        return await backend.ask('{"source": "s"}', [question], "gpt-6-luna")

    async def both() -> list[Any]:
        return await asyncio.gather(*(requeue.run_unit(f"u{i}", unit, ledger, sleeps) for i in range(2)))

    assert len(asyncio.run(both())) == 2
    assert api.calls["decisions"] == 2  # one shared failing request (1 HTTP attempt at cd6b40a), then one success
    assert sleeps.waits == [60.0, 60.0]


# --- H33: with no complete attempt, the `inconclusive` command writes the pre-registered outcome --------------


def outcomes_written(root: Path) -> tuple[str, str]:
    analysis = json.loads((root / "analysis.json").read_text())
    assert analysis["asterion_48"]["adopted"] is None
    assert analysis["asterion_58"]["shipped"] is None
    assert analysis["asterion_58"]["strata_kept"] == []
    return analysis["asterion_48"]["outcome"], analysis["asterion_58"]["outcome"]


def test_h33_a_cap_stopped_last_attempt_is_inconclusive_spend_cap(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path, fake_api.FakeAPI(accept=0.0))
    spent(e.root, CAP - runner.remaining_estimate(e, "dev"))
    assert runner.run_phase(e, "dev", 1) == 2
    assert void_reason(e.root) == "cap_stop"
    assert scoring.inconclusive(e) == 0
    assert outcomes_written(e.root) == ("inconclusive (spend cap)",) * 2
    assert (e.root / "analysis-started.json").exists()
    with pytest.raises(Refused, match="once"):
        scoring.inconclusive(e)


def test_h33_a_start_gate_refusal_is_inconclusive_spend_cap(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    spent(e.root, CAP - runner.remaining_estimate(e, "dev") + 1)
    with pytest.raises(Refused, match="start gate"):
        runner.run_phase(e, "dev", 1)
    assert scoring.inconclusive(e) == 0
    assert outcomes_written(e.root) == ("inconclusive (spend cap)",) * 2


def test_h33_voids_below_the_cap_name_their_reasons(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    for n in (1, 2):
        assert runner.run_phase(e, "dev", n) == 0
        assert runner.void(e, n, "harness_defect", note=None, test=None) == 0
    assert scoring.inconclusive(e) == 0
    expected = "inconclusive (no complete attempt: attempt 1: harness_defect; attempt 2: harness_defect)"
    assert outcomes_written(e.root) == (expected, expected)
    reports = json.loads((e.root / "void-reports.json").read_text())["attempts"]
    assert reports == []  # neither void attempt reached confirm


def test_h33_the_command_refuses_while_an_attempt_can_still_be_scored_or_voided(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    with pytest.raises(Refused, match="no attempt"):
        scoring.inconclusive(e)
    assert runner.run_phase(e, "dev", 1) == 0
    (e.root / "attempt-1" / "dev" / "complete.json").unlink()
    with pytest.raises(Refused, match="void it first"):
        scoring.inconclusive(e)
    assert not (e.root / "analysis-started.json").exists()
