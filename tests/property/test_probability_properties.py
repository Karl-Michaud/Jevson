"""Properties of the probability rules over arbitrary (including hostile) answers."""

from __future__ import annotations

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from jevson.probabilities import interpret, sums_to_one, to_hundredths, top_two_margin
from jevson.types import (
    ChoiceAnswer,
    DecisionKind,
    DecisionNode,
    Option,
    OptionSource,
    PredicateAnswer,
    UnresolvedReason,
)

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=500)
BOOL = DecisionNode("/b#predicate", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/b")
probabilities = st.floats(0, 1)
any_float = st.floats(allow_nan=True, allow_infinity=True)
two_decimals = st.integers(0, 100).map(lambda h: h / 100)
margins = st.integers(0, 99)


def choice_node(k: int) -> DecisionNode:
    options = tuple(Option(f"c{i}", f"c{i}") for i in range(k))
    return DecisionNode("/c#choice", DecisionKind.CHOICE, "q", OptionSource.SCHEMA_ENUM, "/c", options)


@DETERMINISTIC
@given(probabilities)
def test_hundredths_are_the_nearest_integer_hundredth(p: float) -> None:
    h = to_hundredths(p)
    assert 0 <= h <= 100
    assert abs(h - p * 100) <= 0.5


@DETERMINISTIC
@given(two_decimals, margins)
def test_predicate_ties_are_exactly_the_band_and_mirror_symmetric(p: float, margin: int) -> None:
    h = round(p * 100)
    result = interpret(BOOL, PredicateAnswer("q0", p), margin)
    mirrored = interpret(BOOL, PredicateAnswer("q0", (100 - h) / 100), margin)
    if abs(2 * h - 100) <= margin:
        assert result.reason is mirrored.reason is UnresolvedReason.TIE
    else:
        assert result.decision.selected is (h > 50)
        assert mirrored.decision.selected is (h < 50)


@DETERMINISTIC
@given(any_float, margins)
def test_predicates_never_raise_and_commit_only_probabilities(p: float, margin: int) -> None:
    result = interpret(BOOL, PredicateAnswer("q0", p), margin)
    if result.status == "committed":
        assert 0.0 <= p <= 1.0


@st.composite
def choice_answers(draw: st.DrawFn) -> tuple[DecisionNode, ChoiceAnswer]:
    k = draw(st.integers(2, 12))
    node = choice_node(k)
    ids = [o.id for o in node.options]
    raw = {i: draw(st.one_of(two_decimals, any_float)) for i in ids}
    if draw(st.booleans()):  # often a well-formed distribution: hundredths that sum to 100
        cuts = sorted(draw(st.lists(st.integers(0, 100), min_size=k - 1, max_size=k - 1)))
        raw = {i: (b - a) / 100 for i, a, b in zip(ids, [0, *cuts], [*cuts, 100], strict=True)}
    chosen = draw(st.sampled_from([*ids, "unknown"]))
    return node, ChoiceAnswer("q0", chosen, raw, draw(st.one_of(st.none(), any_float)))


@DETERMINISTIC
@given(choice_answers(), margins)
def test_choices_never_raise_and_commit_only_valid_clear_argmaxes(
    case: tuple[DecisionNode, ChoiceAnswer], margin: int
) -> None:
    node, answer = case
    result = interpret(node, answer, margin)
    hundredths = result.decision.distribution_hundredths
    assert all(0 <= h <= 100 for h in hundredths.values())
    if result.status == "committed":
        assert sums_to_one(answer.probabilities)
        assert top_two_margin(hundredths) > margin
        assert result.decision.selected == answer.choice == max(hundredths, key=lambda o: hundredths[o])
    else:
        assert result.reason in (UnresolvedReason.TIE, UnresolvedReason.INVALID_BACKEND_ANSWER)
        assert result.decision.selected is None


@DETERMINISTIC
@given(st.lists(two_decimals, min_size=1, max_size=255))
def test_the_sum_check_is_exact_on_two_decimal_values(values: list[float]) -> None:
    total = sum(Decimal(repr(v)) for v in values)
    assert sums_to_one({f"o{i}": v for i, v in enumerate(values)}) == (abs(total - 1) <= Decimal("0.01"))
