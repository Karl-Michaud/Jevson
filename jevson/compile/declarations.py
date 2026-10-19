"""The `x-jevson` keyword: parse, validate, refuse unknown keys (DESIGN §3.5).

In v0, `source` always refuses with `source_selection_dropped` (Phase 0r **[Q2, Q9]**), whatever its
extractor and keys, so its contents are not validated. `generate` is validated here and compiled
by `compile/generative.py` (Phase 4). `order` has no value v0 can consume: `semantic` is out of v0
(R7), and `source` is R7's order for arrays of spans, dropped with source selection (v0's
multi-label enum arrays are in declared enum order), so both refuse rather than being ignored.
"""

from __future__ import annotations

from dataclasses import dataclass

from jevson.compile.refusal import Refusals
from jevson.compile.untyped import as_list, as_object, as_text
from jevson.errors import RefusalCode

KEYWORD = "x-jevson"
KEYS = frozenset({"source", "generate", "ordinal", "order", "question"})
GENERATE_KEYS = frozenset({"criteria", "rubric", "instructions", "max_draft_chars"})
MIN_LEVELS, MAX_LEVELS = 2, 10

SOURCE_ORDER_DROPPED_MESSAGE = (
    "x-jevson.order: source refuses in v0: source order applies to arrays of spans, which Phase 0r "
    "dropped with source selection [Q2, Q9]; v0's enum arrays are in declared enum order, so remove the key"
)
SOURCE_DROPPED_MESSAGE = (
    "x-jevson.source refuses in v0: Phase 0r dropped source selection on the Decisions API (abstention "
    "0.527, in the stop band) [Q2, Q9]; declare `generate`, or make the field an enum, instead"
)


@dataclass(frozen=True)
class Rubric:
    levels: tuple[str, ...]
    minimum: str
    description: str
    """What is being rated, e.g. "how faithfully the summary reflects the source" (DESIGN §3.5)."""


@dataclass(frozen=True)
class GenerateDeclaration:
    criteria: tuple[str, ...] = ()
    rubric: Rubric | None = None
    instructions: str | None = None
    max_draft_chars: int | None = None


@dataclass(frozen=True)
class FieldDeclaration:
    """One field's parsed `x-jevson`. Refused keys are recorded in `Refusals`, never dropped silently."""

    question: str | None = None
    ordinal: bool = False
    generate: GenerateDeclaration | None = None
    declares_source: bool = False
    declares_generate: bool = False
    """True when `generate` is present, even if it was malformed and refused (so `generate` is None)."""

    @property
    def decides(self) -> bool:
        """True when a declared key asks for the field to be decided (DESIGN §3.5)."""
        return self.question is not None or self.ordinal or self.generate is not None or self.declares_source


@dataclass(frozen=True)
class _Report:
    """Adds one field's declaration problems to `refusals`, all at the field's pointer."""

    refusals: Refusals
    pointer: str

    def __call__(self, message: str, code: RefusalCode = RefusalCode.MALFORMED_DECLARATION) -> None:
        self.refusals.add(self.pointer, code, message)


def parse_declaration(raw: object, pointer: str, refusals: Refusals) -> FieldDeclaration | None:
    """Parse the `x-jevson` value found on the field at `pointer`; every problem goes to `refusals`."""
    bad = _Report(refusals, pointer)
    items = as_object(raw)
    if items is None:
        bad("x-jevson must be an object")
        return None
    for key in sorted(items.keys() - KEYS):
        bad(f"unknown x-jevson key {key!r}", RefusalCode.UNKNOWN_DECLARATION_KEY)

    question = items.get("question")
    if question is not None and as_text(question) is None:
        bad("x-jevson.question must be non-empty text")
    ordinal = items.get("ordinal", False)
    if not isinstance(ordinal, bool):
        bad("x-jevson.ordinal must be true or false")
    order = items.get("order")
    if order == "semantic":
        bad("x-jevson.order: semantic is out of v0 (R7); remove the key", RefusalCode.SEMANTIC_ORDER)
    elif order == "source":
        bad(SOURCE_ORDER_DROPPED_MESSAGE, RefusalCode.SOURCE_SELECTION_DROPPED)
    elif "order" in items:
        bad("x-jevson.order must be 'source' or 'semantic'")

    declares_source = "source" in items
    if declares_source:
        bad(SOURCE_DROPPED_MESSAGE, RefusalCode.SOURCE_SELECTION_DROPPED)
    generate = _generate(items["generate"], bad) if "generate" in items else None
    if declares_source and "generate" in items:
        bad("a field can declare source or generate, not both", RefusalCode.SOURCE_AND_GENERATE)

    return FieldDeclaration(
        question=as_text(question),
        ordinal=ordinal is True,
        generate=generate,
        declares_source=declares_source,
        declares_generate="generate" in items,
    )


def _generate(raw: object, bad: _Report) -> GenerateDeclaration | None:
    items = as_object(raw)
    if items is None:
        bad("x-jevson.generate must be an object")
        return None
    unknown = sorted(items.keys() - GENERATE_KEYS)
    for key in unknown:
        bad(f"unknown x-jevson.generate key {key!r}", RefusalCode.UNKNOWN_DECLARATION_KEY)
    criteria = _texts(items.get("criteria", []))
    rubric = _rubric(items["rubric"]) if "rubric" in items else None
    rubric_items = as_object(items.get("rubric"))
    undescribed = rubric_items is not None and as_text(rubric_items.get("description")) is None
    instructions = items.get("instructions")
    max_chars = items.get("max_draft_chars")
    malformed = [
        message
        for failed, message in (
            (criteria is None, "x-jevson.generate.criteria must be a list of non-empty texts"),
            (
                "rubric" in items and rubric is None and not undescribed,
                "x-jevson.generate.rubric must be {description: non-empty text naming what is rated, "
                "levels: 2-10 distinct texts, minimum: one of them}",
            ),
            (
                instructions is not None and as_text(instructions) is None,
                "x-jevson.generate.instructions must be non-empty text",
            ),
            (
                max_chars is not None and not _positive_int(max_chars),
                "x-jevson.generate.max_draft_chars must be a positive integer",
            ),
        )
        if failed
    ]
    for message in malformed:
        bad(message)
    if undescribed:
        bad(
            "x-jevson.generate.rubric needs a description naming what is rated, e.g. 'how faithfully the "
            "summary reflects the source'",
            RefusalCode.RUBRIC_DESCRIPTION_MISSING,
        )
    if unknown or malformed or undescribed:
        return None
    return GenerateDeclaration(
        criteria=criteria or (),
        rubric=rubric,
        instructions=as_text(instructions),
        max_draft_chars=max_chars if isinstance(max_chars, int) else None,
    )


def _positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _rubric(raw: object) -> Rubric | None:
    items = as_object(raw) or {}
    levels, minimum = _texts(items.get("levels")), items.get("minimum")
    description = as_text(items.get("description"))
    if (
        description is None
        or levels is None
        or not MIN_LEVELS <= len(levels) <= MAX_LEVELS
        or len(set(levels)) != len(levels)
        or not isinstance(minimum, str)
        or minimum not in levels
        or items.keys() - {"levels", "minimum", "description"}
    ):
        return None
    return Rubric(levels, minimum, description)


def _texts(raw: object) -> tuple[str, ...] | None:
    """A list of non-blank texts, or None if it is not one."""
    values = as_list(raw)
    texts = tuple(t for v in values or [] if (t := as_text(v)) is not None)
    return texts if values is not None and len(texts) == len(values) else None
