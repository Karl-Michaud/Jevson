"""`x-jevson.generate` → a `generate` step plus its adjudication nodes (DESIGN §3.5, §6.3).

A generative field compiles to the step `<pointer>#generate`, one criterion `predicate`
`<pointer>#criterion:<i>` per declared criterion, and, when a rubric is declared, one `score`
`<pointer>#rubric` over its levels; every adjudication node depends on the step, so it lands in the
step's level and reads the draft at `drafts.<step id>` (DESIGN §5.2). A field with no criteria and
no rubric is the step alone: its draft is admitted ungated (`decided_by = llm`, listed in `Result.ungated`).
"""

from __future__ import annotations

from jevson.compile import questions
from jevson.compile.declarations import GenerateDeclaration
from jevson.compile.nodes import option_id, role_id
from jevson.types import DecisionKind, DecisionNode, Drafting, Option, OptionSource, StepKind, StepNode

DEFAULT_MAX_DRAFT_CHARS = 4000


def generative_nodes(
    pointer: str, label: str, declared: GenerateDeclaration, id_pointer: str | None = None
) -> tuple[StepNode | DecisionNode, ...]:
    """The step and its adjudication nodes, step first; ids use `id_pointer` (a union branch's
    qualified pointer, `unions.py`) when given."""
    named = id_pointer or pointer
    step_id = role_id(named, "generate")
    after = frozenset({step_id})
    checks: list[tuple[str, str]] = []
    nodes: list[DecisionNode] = []
    for index, criterion in enumerate(declared.criteria):
        node = DecisionNode(
            role_id(named, f"criterion:{index}"),
            DecisionKind.PREDICATE,
            questions.criterion_question(step_id, criterion),
            OptionSource.PREDICATE,
            pointer,
            dependencies=after,
        )
        nodes.append(node)
        checks.append((node.id, criterion))
    minimum = None
    if declared.rubric is not None:
        rubric = declared.rubric
        levels = tuple(
            Option(option_id(i), questions.option_description(level)) for i, level in enumerate(rubric.levels)
        )
        node = DecisionNode(
            role_id(named, "rubric"),
            DecisionKind.SCORE,
            questions.rubric_question(step_id, rubric.description),
            OptionSource.SCHEMA_RUBRIC,
            pointer,
            levels,
            dependencies=after,
        )
        nodes.append(node)
        checks.append((node.id, f"{rubric.description} (at least {rubric.minimum!r})"))
        minimum = option_id(rubric.levels.index(rubric.minimum))
    drafting = Drafting(
        questions.generate_prompt(label, declared.instructions),
        label,
        declared.max_draft_chars or DEFAULT_MAX_DRAFT_CHARS,
        tuple(checks),
        minimum,
    )
    return (StepNode(step_id, StepKind.GENERATE, pointer, drafting=drafting), *nodes)
