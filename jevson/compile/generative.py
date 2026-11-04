"""`x-jevson.generate` → a `generate` step plus its adjudication nodes (DESIGN §3.5, §6.3).

A generative field compiles to the step `<pointer>#generate`, one criterion `predicate`
`<pointer>#criterion:<i>` per declared criterion, and, when a rubric is declared, one `score`
`<pointer>#rubric` over its levels; every adjudication node depends on the step, so it lands in the
step's level and reads the draft at `drafts.<step id>` (DESIGN §5.2). With the opt-in draft screen
(`GenerativeOptions.draft_screen`), a field that declares a criterion or a rubric also gets the
predicate `<pointer>#screen`, last (`compile/draft_screen.py`). A field with no criteria and no rubric
is the step alone, screen or not: its draft is admitted ungated (`decided_by = llm`, listed in
`Result.ungated`).
"""

from __future__ import annotations

from dataclasses import dataclass

from jevson.checks import Check, CheckRule
from jevson.compile import draft_screen, questions
from jevson.compile.declarations import GenerateDeclaration
from jevson.compile.nodes import option_id, role_id
from jevson.types import DecisionKind, DecisionNode, Drafting, Option, OptionSource, StepKind, StepNode

DEFAULT_MAX_DRAFT_CHARS = 4000


@dataclass(frozen=True)
class GenerativeOptions:
    """The opt-in adjudication options `compile_schema` passes down (DESIGN §5.2, §6.3); no defaults
    here, so `JevsonConfig`'s are the only ones."""

    criterion_template: str
    draft_screen: bool


def generative_nodes(
    pointer: str, label: str, declared: GenerateDeclaration, options: GenerativeOptions, id_pointer: str | None = None
) -> tuple[StepNode | DecisionNode, ...]:
    """The step and its adjudication nodes, step first; ids use `id_pointer` (a union branch's
    qualified pointer, `unions.py`) when given."""
    # Length (~47 lines, over the ~40 convention): the step, its criteria and its rubric are built in
    # declared order against one step id, and each node depends on that step.
    named = id_pointer or pointer
    step_id = role_id(named, "generate")
    nodes, checks, minimum = _adjudication_nodes(step_id, pointer, named, declared, options)
    drafting = Drafting(
        questions.generate_prompt(label, declared.instructions),
        label,
        declared.max_draft_chars or DEFAULT_MAX_DRAFT_CHARS,
        checks,
        minimum,
    )
    return (StepNode(step_id, StepKind.GENERATE, pointer, drafting=drafting), *nodes)


def _adjudication_nodes(
    step_id: str, pointer: str, named: str, declared: GenerateDeclaration, options: GenerativeOptions
) -> tuple[list[DecisionNode], tuple[Check, ...], str | None]:
    """The field's criteria, then its rubric, then (opt-in, only after a declared check) the draft
    screen: the nodes, their checks in that order, and the rubric's minimum level id, if any."""
    after = frozenset({step_id})
    checks: list[Check] = []
    nodes: list[DecisionNode] = []
    for index, criterion in enumerate(declared.criteria):
        question = questions.criterion_question(step_id, criterion, options.criterion_template)
        node_id = role_id(named, f"criterion:{index}")
        nodes.append(DecisionNode(node_id, DecisionKind.PREDICATE, question, OptionSource.PREDICATE, pointer,
                                  dependencies=after))  # fmt: skip
        checks.append(Check(node_id, criterion, CheckRule.CRITERION))
    minimum = None
    if declared.rubric is not None:
        rubric = declared.rubric
        levels = tuple(
            Option(option_id(i), questions.option_description(level)) for i, level in enumerate(rubric.levels)
        )
        question = questions.rubric_question(step_id, rubric.description)
        node_id = role_id(named, "rubric")
        nodes.append(DecisionNode(node_id, DecisionKind.SCORE, question, OptionSource.SCHEMA_RUBRIC, pointer, levels,
                                  dependencies=after))  # fmt: skip
        checks.append(Check(node_id, f"{rubric.description} (at least {rubric.minimum!r})", CheckRule.RUBRIC))
        minimum = option_id(rubric.levels.index(rubric.minimum))
    if options.draft_screen and checks:
        screen, check = draft_screen.screen_node(step_id, pointer, named)
        nodes.append(screen)
        checks.append(check)
    return nodes, tuple(checks), minimum
