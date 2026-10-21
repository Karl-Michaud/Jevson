"""H21: the dry run's figures, its batches and its margin check (plan §7 "dryrun"; STATS48-R6-4, FEAS48-7,
FEAS48-8, FEAS48-R8-1, FEAS48-R10-3)."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import httpx
import pytest

from jevson import FakeBackend, InMemoryCostSink, Jevson
from tests.j4b import live
from tests.j4b.fresh import arms, bounds, costs, dryrun, gates, judging, metering, packing, runner, workload
from tests.j4b.fresh.constants import CAP, NANO, PRICE
from tests.j4b.fresh.packing import Unit
from tests.j4b.fresh.spend import SpendLedger
from tests.j4b.fresh.workload import Workload
from tests.j4b.tests import fake_api

LOAD = fake_api.loader()


def figures() -> dict[str, Any]:
    return dryrun.figures(load=LOAD)


# --- the figures ---------------------------------------------------------------------------------------------


def tok(chars: float, drafts: float, questions: float) -> float:
    return (chars + drafts * 536 + 60) / 3 + 160 * questions + 8 * 2 * questions


def test_h21_the_all_rejected_figure_is_first_drafts_plus_every_redraft_plus_decisions_at_p_one() -> None:
    fig = figures()
    expected = 0.0
    for phase in ("dev", "confirm"):
        w = LOAD(phase)
        docs = [len(d.text) for d in w.documents.values()]
        decisions = sum(
            2 * (tok(len(c["source"]), 2, 2) + tok(len(c["source"]), 2, 4)) for c in w.cases["iset"].values()
        )
        decisions += (2 * 39_563 + 2 * (39_563 + 80 * 2 * (160 + 16))) if phase == "confirm" else 0
        decisions += sum(
            4 * tok(len(c["source"]), 1, 1) + 4 * tok(len(c["source"]), 1, 2) for c in w.cases["pset"].values()
        )
        for screen in (0, 1, 0, 1, 0, 1, 0, 1):
            decisions += sum(2 * tok(c, 3, 3 * (3.5 + screen)) for c in docs)  # P(any rejected) = 1: two rounds
        expected += decisions * 0.10 / 1e6 + (len(docs) * 3 + len(docs) * 3 * 8) * 0.00193
    assert fig["all_rejected_usd"] == pytest.approx(expected, rel=1e-12)


def all_request_bounds(w: Workload) -> int:
    total = 0
    for unit in (u for us in w.units.values() for u in us):
        for r in bounds.unit_requests(w, unit).decisions:
            total += metering.request_bound(r.body, "decisions") + r.drafts * 4000 * 7 * PRICE["decision_in"]
        for body in bounds.unit_requests(w, unit).redrafts:
            total += metering.request_bound(body, "chat") + 4000 * 6 * PRICE["chat_in"]
    for doc in w.documents:
        total += sum(metering.request_bound(b, "chat") for b in bounds.first_draft_bodies(w, doc))
    return total


def test_h21_the_true_bound_is_the_sum_of_every_requests_bound() -> None:
    assert figures()["true_bound_usd"] == sum(all_request_bounds(LOAD(p)) for p in ("dev", "confirm")) / NANO


def test_h21_unseen_drafts_are_reserved_at_7_and_6_bytes_per_character() -> None:
    w = LOAD("dev")
    unit = next(u for u in w.units["rset"] if u.arm == "L1")
    requests = bounds.unit_requests(w, unit)
    drafts, redrafts = sum(r.drafts for r in requests.decisions), len(requests.redrafts)
    assert drafts == 6
    assert redrafts == 3
    run = bounds.unit_bound(requests, decision_bpc=7, chat_bpc=6)
    design = bounds.unit_bound(requests, decision_bpc=4, chat_bpc=4)
    assert run - design == drafts * 4000 * 3 * PRICE["decision_in"] + redrafts * 4000 * 2 * PRICE["chat_in"]


def test_h21_r_max_is_the_largest_batch_reservation_over_both_phases() -> None:
    fig = figures()
    largest = 0
    for phase in ("dev", "confirm"):
        w = LOAD(phase)
        units, drafting = runner.reservations(w)
        largest = max(largest, *(sum(units[u] for u in b) for b in packing.configuration_batches(w.units)))
        largest = max(largest, *(sum(drafting[d] for d in b) for b in packing.drafting_batches(list(w.documents))))
    assert fig["r_max_usd"]["run"] == largest / NANO
    assert fig["r_max_usd"]["design"] < fig["r_max_usd"]["run"]


def test_h21_the_two_attempt_share_is_stated_against_15_minus_r_max() -> None:
    splits = [workload.cost_inputs(workload.load(p)) for p in ("dev", "confirm")]  # the real sizes
    assert costs.attempt_usd(splits, 1.0) > CAP / NANO / 2  # so the share is interior, not the search's bound
    for r_max in (int(0.5 * NANO), int(1.2 * NANO)):
        share = costs.two_attempt_share(splits, r_max)
        assert 0 < share < 1
        assert costs.attempt_usd(splits, share) == pytest.approx((CAP - r_max) / NANO / 2, abs=1e-6)
    assert "($15 - R_max) / 2" in dryrun.render(figures())


# --- batches -------------------------------------------------------------------------------------------------------


def pinned_configuration_batches(units: Mapping[str, Sequence[Unit]]) -> list[list[Unit]]:
    pooled: list[Unit] = []
    for name in ("iset", "p7", "pset", "rset"):
        shuffled = list(units.get(name, ()))
        random.Random(20261019).shuffle(shuffled)
        pooled += shuffled
    random.Random(4858).shuffle(pooled)
    return [pooled[i : i + 10] for i in range(0, len(pooled), 10)]


def per_set_only(units: Mapping[str, Sequence[Unit]]) -> list[list[Unit]]:
    pooled: list[Unit] = []
    for name in ("iset", "p7", "pset", "rset"):
        shuffled = list(units.get(name, ()))
        random.Random(20261019).shuffle(shuffled)
        pooled += shuffled
    return [pooled[i : i + 10] for i in range(0, len(pooled), 10)]


def seeds_swapped(units: Mapping[str, Sequence[Unit]]) -> list[list[Unit]]:
    pooled: list[Unit] = []
    for name in ("iset", "p7", "pset", "rset"):
        shuffled = list(units.get(name, ()))
        random.Random(4858).shuffle(shuffled)
        pooled += shuffled
    random.Random(20261019).shuffle(pooled)
    return [pooled[i : i + 10] for i in range(0, len(pooled), 10)]


def test_h21_the_configuration_batches_are_the_pinned_algorithms_and_a_planted_packer_differs() -> None:
    w = workload.load("confirm")
    batches = figures()["phases"][1].configuration_batches
    assert batches == packing.configuration_batches(LOAD("confirm").units)
    assert packing.configuration_batches(w.units) == pinned_configuration_batches(w.units)
    assert all(len(b) <= 10 for b in packing.configuration_batches(w.units))
    for planted in (per_set_only, seeds_swapped):
        assert planted(w.units) != packing.configuration_batches(w.units)


def test_h21_the_drafting_batches_are_the_pinned_algorithms_and_an_unbatched_phase_differs() -> None:
    for phase in ("dev", "confirm"):
        w = workload.load(phase)
        docs = list(w.documents)
        shuffled = list(docs)
        random.Random(4858).shuffle(shuffled)
        expected = [shuffled[i : i + 10] for i in range(0, len(shuffled), 10)]
        assert packing.drafting_batches(docs) == expected
        assert all(len(b) <= 10 for b in expected)
        assert packing.drafting_batches(docs) != [shuffled]


def test_h21_fits_is_called_once_before_every_batch_and_at_most_30_requests_are_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    original = gates.batch_fits

    def counted(ledger: SpendLedger, bound_list: Any) -> bool:
        calls.append(len(list(bound_list)))
        return original(ledger, [])

    monkeypatch.setattr(gates, "batch_fits", counted)
    inflight = Concurrency(httpx.MockTransport(fake_api.FakeAPI()))
    e, _ = fake_api.env(tmp_path / "fresh", transport=inflight, load=fake_api.loader(documents=12))
    assert runner.run_phase(e, "dev", 1) == 0
    w = e.load("dev")
    drafting, configuration = packing.drafting_batches(list(w.documents)), packing.configuration_batches(w.units)
    one_pass = [len(b) for b in drafting] + [len(b) for b in configuration]
    assert calls == one_pass * 2  # the run, then its replay
    assert 10 < inflight.peak <= 30


class Concurrency(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner, self.now, self.peak = inner, 0, 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.now += 1
        self.peak = max(self.peak, self.now)
        try:
            await asyncio.sleep(0)
            return await self.inner.handle_async_request(request)
        finally:
            self.now -= 1


def run_with_room(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, room: Callable[[int, int], int]) -> int:
    """A dev phase with `room(R_max, spend of an identical run)` left under the cap before it starts."""
    monkeypatch.setattr(runner, "remaining_estimate", lambda *_: 0)
    first, _ = fake_api.env(tmp_path / "measure", load=LOAD)
    assert runner.run_phase(first, "dev", 1) == 0
    spend = SpendLedger(first.root).billed
    r_max = int(dryrun.phase_figures(LOAD("dev")).r_max["run"])
    e, _ = fake_api.env(tmp_path / "fresh", load=LOAD)
    ledger = SpendLedger(e.root)
    planted = CAP - room(r_max, spend)
    ledger.settle(ledger.reserve(planted, endpoint="decisions", run_attempt=0), planted, status=200,
                  retry_after=None, model=None)  # fmt: skip
    return runner.run_phase(e, "dev", 1)


def test_h21_an_attempt_with_r_max_and_its_spend_left_completes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert run_with_room(tmp_path, monkeypatch, lambda r_max, spend: r_max + spend) == 0


def test_h21_an_attempt_billed_past_15_minus_r_max_is_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert run_with_room(tmp_path, monkeypatch, lambda r_max, spend: r_max - 1) == 2


# --- the margin check --------------------------------------------------------------------------------------------


def test_h21_every_exact_request_meets_the_harness_formula_and_a_negative_margin_raises() -> None:
    fig = figures()
    for f in fig["phases"]:
        assert f.min_margin["iset"] >= 0
        assert f.min_margin["pset"] >= 0
    planted = bounds.DecisionRequest(b"{}", (("predicate", "q"),) * 9, 18, 3)
    assert min(bounds.margins([planted])) < 0
    with pytest.raises(dryrun.MarginViolation):
        dryrun.check({**fig, "violations": ["planted"]})


def test_h21_the_librarys_dw_estimate_would_refuse_a_one_criterion_request() -> None:
    w = LOAD("confirm")
    unit = next(u for u in w.units["pset"] if u.config == ("L0", "F0"))
    case = judging.pset_case(w.cases["pset"][unit.key], "F0")
    request = bounds.unit_requests(w, unit).decisions[0]
    assert len(request.questions) == 1
    sink = InMemoryCostSink()
    schema = live.schema(case, sorted(case["drafts"]))
    jevson = Jevson(FakeBackend(default=FakeBackend.predicate(0.9)), llm=live.scripted(case, schema),
                    config=arms.L0, cost_sink=sink)  # fmt: skip
    asyncio.run(jevson.aresolve(schema, case["source"], redraft_budget=0))
    estimate = next(e.estimated_input_tokens for e in sink.events if e.component == "decision")
    assert estimate is not None
    assert len(request.body) + 64 < estimate
    assert costs.margin(len(request.body), 1, 2) >= 0  # the harness formula admits it
