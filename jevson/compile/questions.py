"""The versioned question templates of DESIGN §5.2 for class C decisions (docs/taxonomy.md §1.2).

Version 1.1.0 (ASTERION-29). The enum, ordinal, and option strings are byte-identical to
`tests/phase0/templates.py`, the Phase 0 record (1.0.0). The bool template is new: 1.0.0 wrapped a
bare name or a statement as "According to the source, verified?", which is not a yes/no question.
The templates say "noul"; on the Decisions API that primitive is `predicate`, with the same wording.

A choice or score field's `{label}` is its `x-jevson.question`, else its `description`, else its
property name with underscores read as spaces. A bool's `{predicate}` is its `x-jevson.question` or
its `description`, phrased as a statement; a bool with neither is refused by the mapper, because a
property name is not a statement. `title` is never used, because Pydantic generates one from the
name. The text is used verbatim, trimmed, with one trailing `.` or `?` dropped because the template
supplies its own `?`, and a bool's leading "whether" or "if" dropped because the template says "that".

Every question in a level shares one input (DESIGN §2), so two fields asked the same question get
the same answer. `scopes()` qualifies a label that is not unique in the graph with the nearest
ancestor property names that make it unique ("billing kind", "shipping kind"); an
`x-jevson.question` is never qualified. Templates add no negation and never reference state by
position (R13).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from jevson.compile.normalise import SchemaNode
from jevson.types import JSONValue

QUESTION_TEMPLATE_VERSION = "1.1.0"

ENUM_INSTRUCTIONS = "Which of these is the {label}?"
ENUM_OPTION = '"{value}"'
BOOL_INSTRUCTIONS = "According to the source, is it true that {predicate}?"
BOOL_SCOPED_INSTRUCTIONS = "According to the source, for the {scope}, is it true that {predicate}?"
ORDINAL_INSTRUCTIONS = "Which level best describes the {label}?"

_ARTICLES = ("the ", "a ", "an ")
_CONJUNCTIONS = ("whether ", "if ")


def declared_question(node: SchemaNode) -> str | None:
    """The field's trimmed `x-jevson.question`, if it declares a non-empty one."""
    question = node.declaration.question if node.declaration is not None else None
    return _trim(question or "") or None


def label(name: str, node: SchemaNode) -> str:
    """The field's label: the first non-empty of its question, its description, and its name."""
    for text in (declared_question(node), node.description, name.replace("_", " ")):
        trimmed = _trim(text or "")
        if trimmed:
            return trimmed
    return name


def predicate(node: SchemaNode) -> str | None:
    """A bool's statement: its question, else its description, with a leading "whether"/"if" dropped."""
    for text in (declared_question(node), node.description):
        trimmed = _strip_prefix(_trim(text or ""), _CONJUNCTIONS)
        if trimmed:
            return trimmed
    return None


@dataclass(frozen=True)
class Labelled:
    """One decision's label, its ancestor property names (outermost first), and whether it is verbatim."""

    label: str
    ancestors: tuple[str, ...]
    verbatim: bool


def scopes(fields: Sequence[Labelled]) -> tuple[str, ...]:
    """Each field's scope: "" when its label is unique in `fields`, else the fewest nearest ancestor
    names (underscores read as spaces) that make it unique. A verbatim field is never scoped, and a
    field that runs out of ancestors keeps its widest scope; the compiler refuses what stays equal."""
    depths = [0] * len(fields)
    while True:
        keys = [_key(f, d) for f, d in zip(fields, depths, strict=True)]
        counts = Counter(keys)
        grow = [
            i for i, f in enumerate(fields) if counts[keys[i]] > 1 and not f.verbatim and depths[i] < len(f.ancestors)
        ]
        if not grow:
            return tuple(" ".join(_scope_words(f, d)) for f, d in zip(fields, depths, strict=True))
        for i in grow:
            depths[i] += 1


def scoped_label(label: str, scope: str) -> str:
    """A noun-phrase label with its scope in front: "the kind" under "billing" is "billing kind"."""
    return f"{scope} {_strip_prefix(label, _ARTICLES)}" if scope else label


def enum_question(label: str) -> str:
    return ENUM_INSTRUCTIONS.format(label=label)


def bool_question(predicate: str, scope: str = "") -> str:
    if scope:
        return BOOL_SCOPED_INSTRUCTIONS.format(scope=scope, predicate=predicate)
    return BOOL_INSTRUCTIONS.format(predicate=predicate)


def ordinal_question(label: str) -> str:
    return ORDINAL_INSTRUCTIONS.format(label=label)


def option_description(value: JSONValue) -> str:
    """An enum option or an ordinal level, quoted as the template records it."""
    return ENUM_OPTION.format(value=value)


def _key(field: Labelled, depth: int) -> tuple[tuple[str, ...], str]:
    """What must differ between two fields: the scope and the label, ignoring case and a leading article."""
    return _scope_words(field, depth), _strip_prefix(field.label, _ARTICLES).casefold()


def _scope_words(field: Labelled, depth: int) -> tuple[str, ...]:
    chosen = field.ancestors[len(field.ancestors) - depth :] if depth else ()
    return tuple(name.replace("_", " ") for name in chosen)


def _strip_prefix(text: str, prefixes: tuple[str, ...]) -> str:
    for prefix in prefixes:
        if text[: len(prefix)].casefold() == prefix:
            return text[len(prefix) :].lstrip()
    return text


def _trim(text: str) -> str:
    text = text.strip()
    return text[:-1].rstrip() if text.endswith((".", "?")) else text
