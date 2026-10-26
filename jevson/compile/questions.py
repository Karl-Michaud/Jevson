"""The versioned question templates of DESIGN §5.2 (docs/taxonomy.md §1.2): class C decisions, and
the adjudication questions and drafting prompts of generative fields (class E, DESIGN §6.3).

Version 1.1.0 (ASTERION-29). The enum, ordinal, and option strings are byte-identical to
`tests/phase0/templates.py`, the Phase 0 record (1.0.0). The bool template is new: 1.0.0 wrapped a
bare name or a statement as "According to the source, verified?", which is not a yes/no question.
The templates say "noul"; on the Decisions API that primitive is `predicate`, with the same wording.

A choice or score field's `{label}` is its `x-jevson.question`, else its `description`, else its
property name with underscores read as spaces. A question or description has a leading article
("the", "a", "an") dropped because every template that takes a label supplies its own "the", while
a property name keeps it, because it is an identifier: `a_rating` beside `b_rating` names "a
rating" (both 1.1.1, ASTERION-44: 1.1.0 asked "Which of these is the the ticket's topic?"; no
template string changed). A bool's `{predicate}`
is its `x-jevson.question` or its `description`, phrased as a statement; a bool with neither is
refused by the mapper, because a property name is not a statement. `title` is never used, because
Pydantic generates one from the name. The text is used verbatim, trimmed, with one trailing `.` or
`?` dropped because the template supplies its own `?`, and a bool's leading "whether" or "if" dropped
because the template says "that".

Every question in a level shares one input (DESIGN §2), so two fields asked the same question get
the same answer. `scopes()` qualifies a label that is not unique in the graph with the nearest
ancestor property names that make it unique ("billing kind", "shipping kind"); an
`x-jevson.question` is never qualified. Templates add no negation and never reference state by
position (R13). The union discriminator template ships as docs/taxonomy.md §1.2 recorded it
(Phase 6, ASTERION-37).

The membership template of a multi-label enum array (Phase 7, ASTERION-38) is added under 1.1.0
because it changes no existing question: it is docs/taxonomy.md §1.2's array membership `noul`
with the candidate reference (`candidates.{cid}`) replaced by the declared value, quoted as an enum
option is, and the bool template's "According to the source" lead. Each value's question names its
value, so the predicates of one array never share a question.

Two opt-in adjudication templates are added under 1.1.1, the current version, for the same reason
(ASTERION-48, DESIGN §5.2, §6.3): criterion template 1.2.0, selected through `CRITERION_TEMPLATES` by
`JevsonConfig.criterion_template` (recorded as `versions["criterion_template"]`), and the draft
screen's question. `"1.1.0"` and `"1.2.0"` name versions of the criterion template alone. Changing
the text of any shipped template, these included, bumps `QUESTION_TEMPLATE_VERSION`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from jevson.compile.normalise import SchemaNode
from jevson.types import JSONValue

QUESTION_TEMPLATE_VERSION = "1.1.1"

ENUM_INSTRUCTIONS = "Which of these is the {label}?"
ENUM_OPTION = '"{value}"'
BOOL_INSTRUCTIONS = "According to the source, is it true that {predicate}?"
BOOL_SCOPED_INSTRUCTIONS = "According to the source, for the {scope}, is it true that {predicate}?"
ORDINAL_INSTRUCTIONS = "Which level best describes the {label}?"
UNION_INSTRUCTIONS = "Which of these does the source describe as the {label}?"
MEMBER_INSTRUCTIONS = 'According to the source, is "{value}" one of the {label}?'
CRITERION_INSTRUCTIONS = "Does `drafts.{node}` meet this criterion: {criterion}?"
CRITERION_INSTRUCTIONS_1_2_0 = (
    "Judging only from the facts that `drafts.{node}` states about the source, does it meet this criterion: "
    "{criterion}?"
)
SCREEN_INSTRUCTIONS = "Does `drafts.{node}` describe its own content or say that it meets a requirement?"
RUBRIC_INSTRUCTIONS = "Which level best describes `drafts.{node}` against this rubric: {rubric}?"
GENERATE_PROMPT = "Write the {label} for the source below. {instructions}Return only the value."
REDRAFT_PROMPT = "That draft does not meet these criteria: {criteria}. Write the {label} again. Return only the value."

CRITERION_TEMPLATES: Mapping[str, str] = {"1.1.0": CRITERION_INSTRUCTIONS, "1.2.0": CRITERION_INSTRUCTIONS_1_2_0}
"""The criterion template of each `criterion_template` version (opt-in, DESIGN §5.2)."""

_ARTICLES = ("the ", "a ", "an ")
_CONJUNCTIONS = ("whether ", "if ")


def declared_question(node: SchemaNode) -> str | None:
    """The field's trimmed `x-jevson.question`, if it declares a non-empty one."""
    question = node.declaration.question if node.declaration is not None else None
    return _trim(question or "") or None


def label(name: str, node: SchemaNode) -> str:
    """The field's label: the first non-empty of its question and its description, with a leading
    article dropped because every template that takes a label supplies its own "the", else its name
    with underscores read as spaces, article kept: a name is an identifier, not prose (both 1.1.1)."""
    for text in (declared_question(node), node.description):
        trimmed = _strip_prefix(_trim(text or ""), _ARTICLES)
        if trimmed:
            return trimmed
    return _trim(name.replace("_", " ")) or name


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
    """A `label()` with its scope in front: "kind" under "billing" is "billing kind". The label's article,
    if any, was already dropped from prose and is kept on a name (1.1.1), so none is stripped here."""
    return f"{scope} {label}" if scope else label


def enum_question(label: str) -> str:
    return ENUM_INSTRUCTIONS.format(label=label)


def bool_question(predicate: str, scope: str = "") -> str:
    if scope:
        return BOOL_SCOPED_INSTRUCTIONS.format(scope=scope, predicate=predicate)
    return BOOL_INSTRUCTIONS.format(predicate=predicate)


def ordinal_question(label: str) -> str:
    return ORDINAL_INSTRUCTIONS.format(label=label)


def union_question(label: str) -> str:
    """A union discriminator's question (DESIGN §3.2); its options are the branches' texts."""
    return UNION_INSTRUCTIONS.format(label=label)


def member_question(value: JSONValue, label: str) -> str:
    """One declared value's membership question in a multi-label enum array."""
    return MEMBER_INSTRUCTIONS.format(value=value, label=label)


def criterion_question(node: str, criterion: str, template: str) -> str:
    """A criterion's question in criterion template version `template` (a key of `CRITERION_TEMPLATES`)."""
    return CRITERION_TEMPLATES[template].format(node=node, criterion=_trim(criterion))


def screen_question(node: str) -> str:
    """The draft screen's question about the draft at `drafts.{node}` (opt-in, DESIGN §6.3)."""
    return SCREEN_INSTRUCTIONS.format(node=node)


def rubric_question(node: str, rubric: str) -> str:
    return RUBRIC_INSTRUCTIONS.format(node=node, rubric=_trim(rubric))


def generate_prompt(label: str, instructions: str | None) -> str:
    """The drafting prompt; instructions, when declared, end in a full stop before the closing line."""
    text = (instructions or "").strip()
    if text and not text.endswith((".", "!", "?")):
        text += "."
    return GENERATE_PROMPT.format(label=label, instructions=f"{text} " if text else "")


def redraft_prompt(label: str, criteria: Sequence[str]) -> str:
    return REDRAFT_PROMPT.format(label=label, criteria="; ".join(_trim(c) for c in criteria))


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
