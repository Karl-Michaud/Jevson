"""What an adjudication node tests, and by which pass rule (DESIGN §6.3).

A generative field's `Drafting.checks` lists one `Check` per adjudication node, in declared order:
its criteria, then its rubric. The rule travels with the check, so
`adjudicate/criteria.py` judges each one by its rule's `PassRule` and never by the node's kind.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CheckRule(StrEnum):
    """How a check's answer is judged: a criterion passes at p ≥ 0.56, a rubric at its declared
    minimum level."""

    CRITERION = "criterion"
    RUBRIC = "rubric"


@dataclass(frozen=True)
class Check:
    """One adjudication node of a generated field: its id, the text `Result.rejections` names when it
    fails (and the redraft prompt passes back), and the rule that judges it. `rule` has no default:
    a rubric judged as a criterion would fail every answer."""

    node_id: str
    text: str
    rule: CheckRule
