"""Declared criteria → one verdict per draft (DESIGN §6.3).

Each criterion is a `predicate` that passes at p ≥ 0.56; a criterion inside the tie margin, refused,
answered invalidly, or never answered (its request overflowed) counts as failed. A field's criteria
and rubric are asked together, in one batched request over the keyed drafts layout (DESIGN §5.2).
"""

from __future__ import annotations

from collections.abc import Mapping

from jevson.adjudicate.rubrics import rubric_passes
from jevson.probabilities import interpret
from jevson.types import Answer, Decision, DecisionKind, DecisionNode, Drafting

PASS_HUNDREDTHS = 56


def criterion_passes(node: DecisionNode, answer: Answer, tie_margin: int) -> tuple[Decision, bool]:
    reading = interpret(node, answer, tie_margin)
    decision = reading.decision
    passed = decision.selected is True and decision.distribution_hundredths["true"] >= PASS_HUNDREDTHS
    return decision, passed


def judge(
    drafting: Drafting, nodes: Mapping[str, DecisionNode], answers: Mapping[str, Answer | None], tie_margin: int
) -> tuple[dict[str, Decision], tuple[str, ...]]:
    """Every check's decision by node id, and the texts of the checks that failed, in declared order.

    `answers` maps each adjudication node id to its answer, or None when it was never answered."""
    decisions: dict[str, Decision] = {}
    failing: list[str] = []
    for node_id, text in drafting.checks:
        node, answer = nodes[node_id], answers.get(node_id)
        if answer is None:
            failing.append(text)
            continue
        if node.kind is DecisionKind.SCORE:
            minimum = drafting.rubric_minimum or node.options[0].id  # compiled rubrics always declare one
            decision, passed = rubric_passes(node, answer, minimum, tie_margin)
        else:
            decision, passed = criterion_passes(node, answer, tie_margin)
        decisions[node_id] = decision
        if not passed:
            failing.append(text)
    return decisions, tuple(failing)
