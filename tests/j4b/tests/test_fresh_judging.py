"""H14, H29, H31: judging and the one flip definition (design §2.1, §2.4; plan §4.1 `admission.py`, `judging.py`)."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from jevson import FakeBackend, JevsonConfig, Result
from jevson.compile.questions import SCREEN_INSTRUCTIONS
from jevson.types import Answer, PredicateAnswer, Question
from tests.j4b import injection, live
from tests.j4b.fresh import admission, arms, judging
from tests.j4b.tests import fresh_data

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=60, deadline=None)


def by_check(criterion: float, screen: float) -> FakeBackend:
    """Every criterion answered `criterion`, every draft screen answered `screen`."""

    def answer(question: Question) -> Answer:
        is_screen = question.instructions == SCREEN_INSTRUCTIONS.format(node=question.instructions.split("`")[1][7:])
        return PredicateAnswer(question.name, screen if is_screen else criterion)

    return FakeBackend(default=answer)


def iset_case(case_id: str = "c000-a") -> dict[str, Any]:
    rows = [r for r in fresh_data.rows()["iset.jsonl"] if r["case"] == case_id]
    injected = next(r for r in rows if r["role"] == "injected")
    companion = next(r for r in rows if r["role"] == "companion")
    return judging.iset_case(injected, companion)


def run(case: dict[str, Any], backend: FakeBackend, config: JevsonConfig, set_name: str = "iset") -> Result:
    return asyncio.run(judging.judge_case(backend, case, config, set_name))


# --- H14: a draft the screen fails does not flip -------------------------------------------------------


def test_h14_a_screen_failed_draft_does_not_flip_but_todays_judge_reports_a_flip() -> None:
    case = iset_case()
    result = run(case, by_check(0.90, 0.90), arms.L1)
    assert not admission.case_flipped(result)
    assert result.cost.redrafts == 0
    assert judging.REDRAFT_BUDGET["iset"] == 0
    verdicts = admission.criterion_verdicts(result, case)
    assert verdicts == {"/companion_summary": {"k0": False}, "/summary": {"k0": False}}
    today = asyncio.run(live.judge(by_check(0.90, 0.90), case, sorted(case["drafts"]), live.Tally()))
    assert today["/summary"] == {"k0": True}  # live.judge cannot see the screen
    assert admission.case_flipped(run(case, by_check(0.90, 0.90), arms.L0))  # without the screen it flips


def test_h14_the_screen_question_is_asked_under_l1_and_l3_only() -> None:
    for name, config in arms.LIBRARY_ARMS.items():
        backend = by_check(0.10, 0.10)
        run(iset_case(), backend, config)
        screens = [q for call in backend.calls for q in call.questions if "describe its own content" in q.instructions]
        assert len(screens) == (2 if name in ("L1", "L3") else 0)


# --- H29: [P7] through admission under each arm, budget 0 ------------------------------------------------


def test_h29_p7_runs_through_admission_and_the_regression_is_unchanged() -> None:
    assert hashlib.sha256(Path(injection.__file__).read_bytes()).hexdigest() == (
        "cacd80f5073eeffd926496c7e02d1bdb29eabb62ed00ff1ef54ecf210dbd28a2"  # git show e239c2f:tests/j4b/injection.py
    )
    assert judging.REDRAFT_BUDGET["p7"] == 0
    cases = injection.load_fixture()[:8]
    for config in arms.LIBRARY_ARMS.values():
        judged = {
            c["case_id"]: admission.criterion_verdicts(run(c, by_check(0.10, 0.10), config, "p7"), c) for c in cases
        }
        assert injection.regression(cases, judged)["flips"] == 0
    flipped = {
        c["case_id"]: admission.criterion_verdicts(run(c, by_check(0.90, 0.10), arms.L1, "p7"), c) for c in cases
    }
    assert injection.regression(cases, flipped)["flips"] == 8
    screened = {
        c["case_id"]: admission.criterion_verdicts(run(c, by_check(0.90, 0.90), arms.L1, "p7"), c) for c in cases
    }
    assert injection.regression(cases, screened)["flips"] == 0


# --- H31: flip aggregation ------------------------------------------------------------------------------


def test_h31_cells_count_once_and_the_replica_counts_its_cases_for_pc() -> None:
    assert admission.flipped_cells({"c000": [True, False]}) == 1
    assert admission.flipped_cells({"c000": [False, False], "c001": [False, True]}) == 1
    for k in range(1, 17):
        replica = {"replica": [i < k for i in range(16)], "c000": [False, False]}
        assert admission.flipped_cells(replica) == 1
        assert admission.replica_flipped_cases(replica) == k


def test_h31_a_companion_only_flip_counts() -> None:
    def companion_passes(question: Question) -> Answer:
        return PredicateAnswer(question.name, 0.90 if "same" in question.instructions else 0.10)

    case = iset_case()
    result = run(case, FakeBackend(default=companion_passes), arms.L0)
    assert not admission.admitted(result, admission.INJECTED)
    assert admission.admitted(result, admission.COMPANION)
    assert admission.case_flipped(result)


@DETERMINISTIC
@given(
    st.sampled_from(sorted(arms.LIBRARY_ARMS)),
    st.sampled_from([0.10, 0.45, 0.50, 0.56, 0.90]),
    st.sampled_from([0.10, 0.45, 0.50, 0.56, 0.90]),
    st.sampled_from(["c000-a", "c057-b", "c119-a", "replica-03"]),
)
def test_h31_admitted_equals_all_verdicts_for_every_draft(
    arm: str, criterion: float, screen: float, case_id: str
) -> None:
    case = iset_case(case_id)
    result = run(case, by_check(criterion, screen), arms.LIBRARY_ARMS[arm])
    verdicts = admission.criterion_verdicts(result, case)
    for field in case["drafts"]:
        assert admission.admitted(result, field) == all(verdicts[field].values())


@pytest.mark.parametrize("form", ["F0", "F1"])
def test_pset_cases_read_the_criterion_of_their_form(form: str) -> None:
    row = next(r for r in fresh_data.rows()["pset.jsonl"] if r["criterion_f0"] != r["criterion_f1"])
    backend = FakeBackend(default=FakeBackend.predicate(0.9))
    run(judging.pset_case(row, form), backend, arms.L0, "pset")
    [call] = backend.calls
    assert row["criterion_f0" if form == "F0" else "criterion_f1"].rstrip(".") in call.questions[0].instructions
