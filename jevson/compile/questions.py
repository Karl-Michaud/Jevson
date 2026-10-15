"""The versioned question templates of DESIGN §5.2 for class C decisions (docs/taxonomy.md §1.2).

The strings are byte-identical to `tests/phase0/templates.py`, the Phase 0 source of truth, so the
Phase 0 verdicts describe the library that ships; any change bumps `QUESTION_TEMPLATE_VERSION`. The
templates say "noul"; on the Decisions API that primitive is `predicate`, with the same wording.

A field's `{label}` (and a bool's `{predicate}`) is its `x-jevson.question`, else its
`description`, else its property name with underscores read as spaces; `title` is never used,
because Pydantic generates one from the name. The text is used verbatim, trimmed, with one trailing
`.` or `?` dropped because the template supplies its own `?`. Templates add no negation and never
reference state by position (R13).
"""

from __future__ import annotations

from jevson.compile.normalise import SchemaNode
from jevson.types import JSONValue

QUESTION_TEMPLATE_VERSION = "1.0.0"

ENUM_INSTRUCTIONS = "Which of these is the {label}?"
ENUM_OPTION = '"{value}"'
BOOL_INSTRUCTIONS = "According to the source, {predicate}?"
ORDINAL_INSTRUCTIONS = "Which level best describes the {label}?"


def label(name: str, node: SchemaNode) -> str:
    """The field's label: the first non-empty of its question, its description, and its name."""
    question = node.declaration.question if node.declaration is not None else None
    for text in (question, node.description, name.replace("_", " ")):
        trimmed = _trim(text or "")
        if trimmed:
            return trimmed
    return name


def enum_question(label: str) -> str:
    return ENUM_INSTRUCTIONS.format(label=label)


def bool_question(predicate: str) -> str:
    return BOOL_INSTRUCTIONS.format(predicate=predicate)


def ordinal_question(label: str) -> str:
    return ORDINAL_INSTRUCTIONS.format(label=label)


def option_description(value: JSONValue) -> str:
    """An enum option or an ordinal level, quoted as the template records it."""
    return ENUM_OPTION.format(value=value)


def _trim(text: str) -> str:
    text = text.strip()
    return text[:-1].rstrip() if text.endswith((".", "?")) else text
