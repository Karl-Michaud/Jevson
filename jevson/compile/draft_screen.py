"""The draft screen's compile half (DESIGN §6.3; opt-in through `JevsonConfig.draft_screen`).

A generated field that declares a criterion or a rubric gets one more adjudication node,
`<pointer>#screen`: a predicate asking whether the draft describes its own content or says that it
meets a requirement. It depends on the field's `generate` step, so it is asked in that field's
adjudication request (DESIGN §5.2). Its `Check` carries the rejection text that `Result.rejections`
names and the redraft prompt passes back, and the inverted pass rule (`adjudicate/draft_screen.py`).
"""

from __future__ import annotations

from jevson.checks import Check, CheckRule
from jevson.compile import questions
from jevson.compile.nodes import role_id
from jevson.types import DecisionKind, DecisionNode, OptionSource

SCREEN_REJECTION = "The draft speaks only about the source, not about itself or the requirements it meets"
"""Named in `rejections` when the screen fails a draft; worded as the requirement the draft failed, so
it reads correctly in the redraft prompt. A change bumps QUESTION_TEMPLATE_VERSION (DESIGN §5.2)."""


def screen_node(step_id: str, pointer: str, named: str) -> tuple[DecisionNode, Check]:
    """The screen predicate of the field whose step is `step_id`, and its check; `named` is the pointer
    its id uses (a union branch's qualified pointer, `unions.py`)."""
    node = DecisionNode(
        role_id(named, "screen"),
        DecisionKind.PREDICATE,
        questions.screen_question(step_id),
        OptionSource.PREDICATE,
        pointer,
        dependencies=frozenset({step_id}),
    )
    return node, Check(node.id, SCREEN_REJECTION, CheckRule.SCREEN)
