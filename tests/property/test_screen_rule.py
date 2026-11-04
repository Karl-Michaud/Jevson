"""DESIGN §6.3: the draft screen's pass rule, over every probability and tie margin (ASTERION-48).

The screen is an inverted-polarity predicate: `true` means the draft describes itself or claims to meet
a requirement. It passes only when the answer commits `false` with p(true) below 0.45, so a tie, a
refusal and an invalid answer all fail the draft, as a failed criterion does.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from jevson.adjudicate.draft_screen import SCREEN_FAIL_HUNDREDTHS, screen_passes
from jevson.probabilities import to_hundredths
from jevson.types import (
    Answer,
    DecisionKind,
    DecisionNode,
    Drafting,
    InvalidAnswer,
    OptionSource,
    PredicateAnswer,
    Refusal,
)

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=500, deadline=None)  # no wall clock in tests
SCREEN = DecisionNode(
    "/s#screen", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/s", dependencies=frozenset({"/s#generate"})
)
DRAFTING = Drafting("p", "s")
DEFAULT_MARGIN = 10


def passes(answer: Answer, margin: int = DEFAULT_MARGIN) -> bool:
    return screen_passes(SCREEN, answer, DRAFTING, margin)[1]


def test_the_fail_threshold_is_0_45() -> None:
    assert SCREEN_FAIL_HUNDREDTHS == 45


@DETERMINISTIC
@given(st.floats(0, 1))
def test_at_the_default_margin_the_screen_passes_exactly_below_0_45(p: float) -> None:
    assert passes(PredicateAnswer("q0", p)) is (to_hundredths(p) <= 44)


@DETERMINISTIC
@given(st.floats(0.45, 0.55), st.integers(0, 99))
def test_every_p_from_0_45_to_0_55_fails_whatever_the_margin(p: float, margin: int) -> None:
    assert not passes(PredicateAnswer("q0", p), margin)


@DETERMINISTIC
@given(st.integers(0, 99), st.integers(0, 100))
def test_a_tie_always_fails(margin: int, hundredths: int) -> None:
    if abs(2 * hundredths - 100) <= margin:
        assert not passes(PredicateAnswer("q0", hundredths / 100), margin)


@DETERMINISTIC
@given(st.integers(0, 99))
def test_a_refusal_or_an_invalid_answer_fails(margin: int) -> None:
    assert not passes(Refusal("q0"), margin)
    assert not passes(InvalidAnswer("q0", "junk"), margin)


def test_the_decision_records_what_the_screen_found() -> None:
    found, passed = screen_passes(SCREEN, PredicateAnswer("q0", 0.9), DRAFTING, DEFAULT_MARGIN)
    assert (found.selected, found.distribution_hundredths["true"], passed) == (True, 90, False)
    clean, passed = screen_passes(SCREEN, PredicateAnswer("q0", 0.1), DRAFTING, DEFAULT_MARGIN)
    assert (clean.selected, passed) == (False, True)
