"""Declared checks → one verdict per draft (DESIGN §6.3).

Each criterion is a `predicate` that passes at p ≥ 0.56; a criterion inside the tie margin, refused,
answered invalidly, or never answered (its request overflowed) counts as failed. A field's criteria
and rubric are asked together, in one batched request over the keyed drafts layout, which holds
adjudication questions only (DESIGN §5.2; split only by DESIGN §8.2).

Each check is judged by its rule's `PassRule` from `PASS_RULES`, carried on the check itself
(`jevson/checks.py`). The opt-in draft screen, asked in the same request, has the inverted rule: it
**fails** the draft at p ≥ 0.45, on a tie, a refusal, an invalid answer or no answer
(`adjudicate/draft_screen.py`). A new rule is one registry entry, holding its pass test and the
answer that passes it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from jevson.adjudicate import draft_screen
from jevson.adjudicate.rubrics import rubric_passes
from jevson.checks import CheckRule
from jevson.probabilities import interpret
from jevson.types import Answer, Decision, DecisionNode, Drafting, PredicateAnswer, Question, ScoreAnswer

PASS_HUNDREDTHS = 56


@dataclass(frozen=True)
class PassRule:
    """How one rule judges its check, and the answer that passes it (used by the offline dry run)."""

    passes: Callable[[DecisionNode, Answer, Drafting, int], tuple[Decision, bool]]
    """The check's decision and whether the draft passes it, given its answer and the tie margin."""
    passing: Callable[[Question], Answer]
    """An answer, named `question.name`, that passes this check."""


def criterion_passes(node: DecisionNode, answer: Answer, tie_margin: int) -> tuple[Decision, bool]:
    reading = interpret(node, answer, tie_margin)
    decision = reading.decision
    passed = decision.selected is True and decision.distribution_hundredths["true"] >= PASS_HUNDREDTHS
    return decision, passed


def _criterion(node: DecisionNode, answer: Answer, drafting: Drafting, tie_margin: int) -> tuple[Decision, bool]:
    del drafting  # a criterion has no declared minimum
    return criterion_passes(node, answer, tie_margin)


def _rubric(node: DecisionNode, answer: Answer, drafting: Drafting, tie_margin: int) -> tuple[Decision, bool]:
    minimum = drafting.rubric_minimum or node.options[0].id  # compiled rubrics always declare one
    return rubric_passes(node, answer, minimum, tie_margin)


def _criterion_passing(question: Question) -> Answer:
    return PredicateAnswer(question.name, 1.0)


def _rubric_passing(question: Question) -> Answer:
    top = question.options[-1].id
    probabilities = {option.id: float(option.id == top) for option in question.options}
    return ScoreAnswer(question.name, float(len(question.options) - 1), probabilities)


PASS_RULES: Mapping[CheckRule, PassRule] = {
    CheckRule.CRITERION: PassRule(_criterion, _criterion_passing),
    CheckRule.RUBRIC: PassRule(_rubric, _rubric_passing),
    CheckRule.SCREEN: PassRule(draft_screen.screen_passes, draft_screen.screen_passing),
}
"""Every check rule's pass test and passing answer; `judge` and `dry_run` read only this."""


def judge(
    drafting: Drafting, nodes: Mapping[str, DecisionNode], answers: Mapping[str, Answer | None], tie_margin: int
) -> tuple[dict[str, Decision], tuple[str, ...]]:
    """Every check's decision by node id, and the texts of the checks that failed, in declared order.

    `answers` maps each adjudication node id to its answer, or None when it was never answered."""
    decisions: dict[str, Decision] = {}
    failing: list[str] = []
    for check in drafting.checks:
        node, answer = nodes[check.node_id], answers.get(check.node_id)
        if answer is None:
            failing.append(check.text)
            continue
        decision, passed = PASS_RULES[check.rule].passes(node, answer, drafting, tie_margin)
        decisions[check.node_id] = decision
        if not passed:
            failing.append(check.text)
    return decisions, tuple(failing)
