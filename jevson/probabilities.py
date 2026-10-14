"""Probability rules: the raw sum check, integer hundredths, the argmax check, and the tie margin.

DESIGN §2.1: an answer is invalid if its raw probabilities sum outside 1 ± 0.01; the check runs
before rounding, then every probability is stored as integer hundredths. The selected option is the
argmax in hundredths; a vendor `choice` naming another option outside the tie band is invalid.
DESIGN §6.2: a committing decision whose top two outcomes differ by at most the margin is a tie.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from jevson.types import (
    Answer,
    ChoiceAnswer,
    Decision,
    DecisionKind,
    DecisionNode,
    PredicateAnswer,
    Refusal,
    ScoreAnswer,
    UnresolvedReason,
)

SUM_TOLERANCE = Decimal("0.01")

Status = Literal["committed", "unresolved"]


def is_probability(value: float) -> bool:
    return math.isfinite(value) and 0.0 <= value <= 1.0


def to_hundredths(probability: float) -> int:
    """Round a probability in [0, 1] to integer hundredths."""
    if not is_probability(probability):
        raise ValueError(f"not a probability: {probability!r}")
    return round(probability * 100)


def sums_to_one(probabilities: Mapping[str, float]) -> bool:
    """The raw sum is within 1 ± 0.01, computed exactly on the values as the API printed them.

    `Decimal(repr(p))` reads each float as its shortest decimal form, so 0.33 + 0.33 + 0.33 is
    exactly 0.99, not 0.98999…, and the bound is tested without float error.
    """
    total = sum((Decimal(repr(p)) for p in probabilities.values()), Decimal(0))
    return abs(total - 1) <= SUM_TOLERANCE


def top_two_margin(hundredths: Mapping[str, int]) -> int:
    ranked = sorted(hundredths.values(), reverse=True)
    return ranked[0] - ranked[1]


def argmax(hundredths: Mapping[str, int]) -> str:
    """The most probable option; on equal hundredths the first in option order (a tie anyway)."""
    return max(hundredths, key=lambda option: hundredths[option])


@dataclass(frozen=True)
class Interpretation:
    """One answer read against its node: `committed` carries `decision.selected`, `unresolved` a reason."""

    decision: Decision
    status: Status
    reason: UnresolvedReason | None = None


def interpret(node: DecisionNode, answer: Answer, tie_margin: int) -> Interpretation:
    """Read one backend answer for one decision node. Never raises on a malformed answer."""
    if isinstance(answer, Refusal):
        return _unresolved(node, UnresolvedReason.REFUSED)
    if node.kind is DecisionKind.PREDICATE and isinstance(answer, PredicateAnswer):
        return _predicate(node, answer, tie_margin)
    if node.kind is DecisionKind.CHOICE and isinstance(answer, ChoiceAnswer):
        return _distribution(node, answer, tie_margin, vendor_choice=answer.choice)
    if node.kind is DecisionKind.SCORE and isinstance(answer, ScoreAnswer):
        if not (math.isfinite(answer.score) and 0 <= answer.score <= len(node.options) - 1):
            return _unresolved(node, UnresolvedReason.INVALID_BACKEND_ANSWER)
        return _distribution(node, answer, tie_margin, vendor_choice=None)
    return _unresolved(node, UnresolvedReason.INVALID_BACKEND_ANSWER)


def _predicate(node: DecisionNode, answer: PredicateAnswer, tie_margin: int) -> Interpretation:
    if not is_probability(answer.probability):
        return _unresolved(node, UnresolvedReason.INVALID_BACKEND_ANSWER)
    true = to_hundredths(answer.probability)
    distribution = {"true": true, "false": 100 - true}
    if abs(2 * true - 100) <= tie_margin:
        return _unresolved(node, UnresolvedReason.TIE, distribution)
    return _committed(node, true > 50, distribution, None)


def _distribution(
    node: DecisionNode, answer: ChoiceAnswer | ScoreAnswer, tie_margin: int, vendor_choice: str | None
) -> Interpretation:
    raw = answer.probabilities
    valid = (
        set(raw) == {option.id for option in node.options}
        and all(is_probability(p) for p in raw.values())
        and sums_to_one(raw)
        and (answer.confidence is None or is_probability(answer.confidence))
        and (vendor_choice is None or vendor_choice in raw)
    )
    if not valid:
        return _unresolved(node, UnresolvedReason.INVALID_BACKEND_ANSWER)
    distribution = {option.id: to_hundredths(raw[option.id]) for option in node.options}
    if top_two_margin(distribution) <= tie_margin:
        return _unresolved(node, UnresolvedReason.TIE, distribution, answer.confidence)
    selected = argmax(distribution)
    if vendor_choice is not None and vendor_choice != selected:
        return _unresolved(node, UnresolvedReason.INVALID_BACKEND_ANSWER, distribution, answer.confidence)
    return _committed(node, selected, distribution, answer.confidence)


def _committed(
    node: DecisionNode, selected: str | bool, distribution: dict[str, int], confidence: float | None
) -> Interpretation:
    return Interpretation(Decision(node.kind, selected, distribution, confidence, node.target), "committed")


def _unresolved(
    node: DecisionNode,
    reason: UnresolvedReason,
    distribution: dict[str, int] | None = None,
    confidence: float | None = None,
) -> Interpretation:
    decision = Decision(node.kind, None, distribution or {}, confidence, node.target)
    return Interpretation(decision, "unresolved", reason)
