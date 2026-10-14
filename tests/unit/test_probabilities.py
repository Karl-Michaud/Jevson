"""The probability rules, with PLAN Phase 1's examples as literal cases."""

from __future__ import annotations

import math

import pytest

from jevson.probabilities import interpret, sums_to_one, to_hundredths
from jevson.types import (
    Answer,
    ChoiceAnswer,
    DecisionKind,
    DecisionNode,
    Option,
    OptionSource,
    PredicateAnswer,
    Refusal,
    ScoreAnswer,
    UnresolvedReason,
)

MARGIN = 10
BOOL = DecisionNode("/paid#predicate", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/paid")
ENUM3 = DecisionNode(
    "/tier#choice",
    DecisionKind.CHOICE,
    "q",
    OptionSource.SCHEMA_ENUM,
    "/tier",
    (Option("o0", "gold"), Option("o1", "silver"), Option("o2", "bronze")),
)
SCORE = DecisionNode(
    "/rating#score",
    DecisionKind.SCORE,
    "q",
    OptionSource.SCHEMA_RUBRIC,
    "/rating",
    tuple(Option(f"l{i}", str(i)) for i in range(5)),
)


def choice(*probabilities: float, chosen: str | None = None, confidence: float | None = None) -> ChoiceAnswer:
    raw = {f"o{i}": p for i, p in enumerate(probabilities)}
    return ChoiceAnswer("q0", chosen or max(raw, key=lambda k: raw[k]), raw, confidence)


# --- PLAN Phase 1 exit criterion: probabilities ----------------------------------------------


def test_a_distribution_summing_to_0_99_with_k3_is_accepted() -> None:
    result = interpret(ENUM3, choice(0.70, 0.20, 0.09), MARGIN)
    assert result.status == "committed"
    assert result.decision.selected == "o0"
    assert result.decision.distribution_hundredths == {"o0": 70, "o1": 20, "o2": 9}


def test_three_thirds_summing_to_0_99_pass_the_sum_check() -> None:
    assert sums_to_one({"a": 0.33, "b": 0.33, "c": 0.33})


def test_a_distribution_summing_to_0_95_is_an_invalid_answer() -> None:
    result = interpret(ENUM3, choice(0.70, 0.20, 0.05), MARGIN)
    assert (result.status, result.reason) == ("unresolved", UnresolvedReason.INVALID_BACKEND_ANSWER)
    assert result.decision.selected is None


@pytest.mark.parametrize(
    ("p", "status", "selected"),
    [
        (0.45, "unresolved", None),
        (0.50, "unresolved", None),
        (0.55, "unresolved", None),
        (0.56, "committed", True),
        (0.44, "committed", False),
        (1.0, "committed", True),
        (0.0, "committed", False),
    ],
)
def test_bool_tie_band(p: float, status: str, selected: bool | None) -> None:
    result = interpret(BOOL, PredicateAnswer("q0", p), MARGIN)
    assert result.status == status
    assert result.decision.selected is selected
    if status == "unresolved":
        assert result.reason is UnresolvedReason.TIE
    assert result.decision.distribution_hundredths == {"true": round(p * 100), "false": 100 - round(p * 100)}


def test_a_choice_at_52_42_06_is_a_tie() -> None:
    result = interpret(ENUM3, choice(0.52, 0.42, 0.06), MARGIN)
    assert (result.status, result.reason) == ("unresolved", UnresolvedReason.TIE)
    assert result.decision.distribution_hundredths == {"o0": 52, "o1": 42, "o2": 6}


def test_a_choice_just_outside_the_margin_commits() -> None:
    assert interpret(ENUM3, choice(0.53, 0.42, 0.05), MARGIN).decision.selected == "o0"


def test_a_vendor_choice_naming_a_non_argmax_option_outside_the_margin_is_invalid() -> None:
    result = interpret(ENUM3, choice(0.80, 0.15, 0.05, chosen="o1"), MARGIN)
    assert (result.status, result.reason) == ("unresolved", UnresolvedReason.INVALID_BACKEND_ANSWER)


def test_a_vendor_choice_naming_a_non_argmax_option_inside_the_margin_is_a_tie() -> None:
    result = interpret(ENUM3, choice(0.50, 0.45, 0.05, chosen="o1"), MARGIN)
    assert result.reason is UnresolvedReason.TIE


def test_the_raw_sum_is_checked_before_rounding() -> None:
    # 200 options at 0.005 each round to 1 hundredth each (sum 2.00), yet the raw sum is 1.00.
    assert sums_to_one({f"o{i}": 0.005 for i in range(200)})
    # Raw values just outside the tolerance fail even though they round to a valid-looking set.
    assert not sums_to_one({"a": 0.504, "b": 0.485})
    assert sums_to_one({"a": 0.505, "b": 0.485})


# --- refusal ---------------------------------------------------------------------------------


@pytest.mark.parametrize("node", [BOOL, ENUM3, SCORE])
def test_a_refusal_is_unresolved_refused_never_an_option_or_an_abstention(node: DecisionNode) -> None:
    result = interpret(node, Refusal("q0"), MARGIN)
    assert (result.status, result.reason) == ("unresolved", UnresolvedReason.REFUSED)
    assert result.decision.selected is None
    assert result.decision.distribution_hundredths == {}


def test_a_choice_commits_with_its_confidence_and_target() -> None:
    result = interpret(ENUM3, choice(0.91, 0.05, 0.04, confidence=0.8), MARGIN)
    assert (result.status, result.decision.selected, result.decision.vendor_confidence) == ("committed", "o0", 0.8)
    assert result.decision.target_pointer == "/tier"


# --- score -----------------------------------------------------------------------------------


def test_a_score_commits_the_most_probable_level_not_the_rounded_mean() -> None:
    # p = [.40, 0, 0, 0, .60]: the vendor mean is 2.40, which rounds to level 2; the value is level 4.
    answer = ScoreAnswer("q0", 2.4, {"l0": 0.40, "l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.60})
    result = interpret(SCORE, answer, MARGIN)
    assert (result.status, result.decision.selected) == ("committed", "l4")


def test_a_score_inside_the_margin_is_a_tie() -> None:
    answer = ScoreAnswer("q0", 2.0, {"l0": 0.5, "l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.5})
    assert interpret(SCORE, answer, MARGIN).reason is UnresolvedReason.TIE


@pytest.mark.parametrize("score", [-0.1, 4.1, math.nan, math.inf])
def test_a_score_outside_the_level_range_is_invalid(score: float) -> None:
    answer = ScoreAnswer("q0", score, {"l0": 1.0, "l1": 0.0, "l2": 0.0, "l3": 0.0, "l4": 0.0})
    assert interpret(SCORE, answer, MARGIN).reason is UnresolvedReason.INVALID_BACKEND_ANSWER


# --- malformed answers -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("node", "answer"),
    [
        (BOOL, PredicateAnswer("q0", math.nan)),
        (BOOL, PredicateAnswer("q0", 1.2)),
        (BOOL, PredicateAnswer("q0", -0.1)),
        (BOOL, choice(0.6, 0.4)),
        (ENUM3, PredicateAnswer("q0", 0.9)),
        (ENUM3, ChoiceAnswer("q0", "o0", {"o0": 0.9, "o1": 0.1})),
        (ENUM3, ChoiceAnswer("q0", "o0", {"o0": 0.9, "o1": 0.05, "o2": 0.03, "o9": 0.02})),
        (ENUM3, ChoiceAnswer("q0", "o9", {"o0": 0.9, "o1": 0.05, "o2": 0.05})),
        (ENUM3, ChoiceAnswer("q0", "o0", {"o0": 1.5, "o1": -0.25, "o2": -0.25})),
        (ENUM3, ChoiceAnswer("q0", "o0", {"o0": math.nan, "o1": 0.5, "o2": 0.5})),
        (ENUM3, choice(0.9, 0.05, 0.05, confidence=1.5)),
        (SCORE, choice(0.9, 0.1)),
    ],
)
def test_malformed_answers_are_invalid_backend_answers(node: DecisionNode, answer: Answer) -> None:
    result = interpret(node, answer, MARGIN)
    assert (result.status, result.reason) == ("unresolved", UnresolvedReason.INVALID_BACKEND_ANSWER)


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.01, 1.01])
def test_to_hundredths_refuses_non_probabilities(value: float) -> None:
    with pytest.raises(ValueError, match="not a probability"):
        to_hundredths(value)


def test_to_hundredths_rounds_two_decimal_values_exactly() -> None:
    assert [to_hundredths(p) for p in (0.29, 0.57, 0.58, 0.07, 1.0, 0.0)] == [29, 57, 58, 7, 100, 0]


def test_the_tie_margin_is_configurable() -> None:
    assert interpret(ENUM3, choice(0.52, 0.42, 0.06), 5).decision.selected == "o0"
    assert interpret(BOOL, PredicateAnswer("q0", 0.53), 0).decision.selected is True
