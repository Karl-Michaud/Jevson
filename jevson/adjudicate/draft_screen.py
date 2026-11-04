"""The draft screen's pass rule (DESIGN §6.3; opt-in through `JevsonConfig.draft_screen`).

The screen asks whether a draft describes its own content or says that it meets a requirement, so its
polarity is the inverse of a criterion's: `true` means a self-claim was found. The draft passes only
when the answer commits `false` with p(true) below 0.45; a p(true) of 0.45 or more, a tie, a refusal
or an invalid answer fails it (an unanswered screen fails in `criteria.judge`, as any check does).
"""

from __future__ import annotations

from jevson.probabilities import interpret
from jevson.types import Answer, Decision, DecisionNode, Drafting, PredicateAnswer, Question

SCREEN_FAIL_HUNDREDTHS = 45
"""p(true) at or above this, in hundredths, fails the draft. A change bumps QUESTION_TEMPLATE_VERSION."""


def screen_passes(node: DecisionNode, answer: Answer, drafting: Drafting, tie_margin: int) -> tuple[Decision, bool]:
    """The screen's decision, and whether the draft passes it: a committed `false` below 0.45 only."""
    del drafting  # the screen has no declared minimum; the signature is every pass rule's
    decision = interpret(node, answer, tie_margin).decision
    passed = decision.selected is False and decision.distribution_hundredths["true"] < SCREEN_FAIL_HUNDREDTHS
    return decision, passed


def screen_passing(question: Question) -> Answer:
    """The answer that passes the screen (no self-claim found), for the offline dry run."""
    return PredicateAnswer(question.name, 0.0)
