"""A rubric `score` passes when its most probable level is at least the declared minimum (DESIGN §6.3).

A tie counts as passed only when every level inside the tie margin of the top is at or above the
minimum; a tie that straddles the minimum, a refusal, or an invalid answer counts as failed.
"""

from __future__ import annotations

from jevson.probabilities import interpret
from jevson.types import Answer, Decision, DecisionNode, UnresolvedReason


def rubric_passes(node: DecisionNode, answer: Answer, minimum: str, tie_margin: int) -> tuple[Decision, bool]:
    reading = interpret(node, answer, tie_margin)
    levels = [option.id for option in node.options]
    floor = levels.index(minimum)
    decision = reading.decision
    if reading.status == "committed":
        return decision, levels.index(str(decision.selected)) >= floor
    if reading.reason is not UnresolvedReason.TIE:
        return decision, False
    top = max(decision.distribution_hundredths.values())
    tied = [level for level, p in decision.distribution_hundredths.items() if top - p <= tie_margin]
    return decision, all(levels.index(level) >= floor for level in tied)
