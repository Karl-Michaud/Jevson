"""DESIGN §4.2: each normalised field → a class and a primitive, or a named refusal.

| field | becomes |
|---|---|
| object | its properties, recursively; an object's own default never makes it class A |
| constant; a leaf with a default and no deciding `x-jevson` key (DESIGN §3.5) | class A: no node |
| `bool` with a question or description | `predicate` (the tie band is `probabilities.interpret`'s) |
| `bool` with neither | `bool_predicate_missing`: a property name is not a statement |
| string/int enum, 2-255 values | `choice` over opaque ids `c0…cN` in declared order |
| integer range declared `ordinal: true`, 2-10 levels | `score`, levels lowest first |
| any other string, number, decimal, integer, or scalar array | `unbounded_field` (class G), or |
|  | `source_selection_dropped` when a `default_extractor` is set |
| array of enum (multi-label) | `not_yet_supported` until Phase 7, with or without a default |
| string declaring `generate` (with or without a default) | a `generate` step + criteria (`generative.py`) |
| any other field declaring `generate` | `generate_field_type`: class E is a string (generative lists are class G) |

Subtrees the normaliser refused (`Kind.REFUSED`) are skipped, and a field whose `source` or
malformed `generate` `declarations.py` already refused gets no second reason; every new refusal goes to the
same `Refusals`, so one `CompileError` names every pointer (R14).

Questions are rendered after the whole tree is mapped, because a label that is not unique in the
graph is qualified by its ancestor property names (`questions.scopes`).
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from decimal import Decimal

from jevson.compile import questions
from jevson.compile.declarations import GenerateDeclaration
from jevson.compile.generative import generative_nodes
from jevson.compile.nodes import node_id, option_id
from jevson.compile.normalise import Kind, SchemaNode
from jevson.compile.refusal import Refusals
from jevson.errors import RefusalCode
from jevson.types import (
    MAX_OPTIONS,
    DecisionKind,
    DecisionNode,
    JSONValue,
    Option,
    OptionSource,
    ProvenanceKind,
    StepNode,
)

MIN_LEVELS, MAX_LEVELS = 2, 10
MAX_ORDINAL_SPAN = 10_000
"""An ordinal range wider than this is refused before its levels are listed."""


def map_tree(
    root: SchemaNode, refusals: Refusals, *, default_extractor: str | None
) -> tuple[DecisionNode | StepNode, ...]:
    """The class C decision nodes of a normalised tree in schema order, then the generative fields'
    steps and adjudication nodes; problems go to `refusals`."""
    if root.kind is Kind.REFUSED:
        return ()
    if root.kind is not Kind.OBJECT:
        refusals.add(root.pointer, RefusalCode.MALFORMED_SCHEMA, "the root must be an object schema")
        return ()
    mapper = _Mapper(refusals, default_extractor)
    mapper.object(root, ())
    scopes = questions.scopes([p.labelled for p in mapper.pending])
    return (*(p.render(scope) for p, scope in zip(mapper.pending, scopes, strict=True)), *mapper.generated)


@dataclass(frozen=True)
class _Pending:
    """A mapped decision whose question waits for its scope."""

    node: SchemaNode
    kind: DecisionKind
    labelled: questions.Labelled
    values: tuple[JSONValue, ...] = ()

    def render(self, scope: str) -> DecisionNode:
        node_ref = node_id(self.node.pointer, self.kind)
        if self.kind is DecisionKind.PREDICATE:
            question = questions.bool_question(self.labelled.label, scope)
            return DecisionNode(node_ref, self.kind, question, OptionSource.PREDICATE, self.node.pointer)
        label = questions.scoped_label(self.labelled.label, scope)
        if self.kind is DecisionKind.SCORE:
            question = questions.ordinal_question(label)
        else:
            question = questions.enum_question(label)
        return DecisionNode(
            node_ref,
            self.kind,
            question,
            OptionSource.SCHEMA_ENUM,
            self.node.pointer,
            tuple(Option(option_id(i), questions.option_description(v)) for i, v in enumerate(self.values)),
            provenance=ProvenanceKind.DECLARED_OPTION,
            values=self.values,
        )


class _Mapper:
    def __init__(self, refusals: Refusals, default_extractor: str | None) -> None:
        self.refusals = refusals
        self.default_extractor = default_extractor
        self.pending: list[_Pending] = []
        self.generated: list[DecisionNode | StepNode] = []

    def refuse(self, node: SchemaNode, code: RefusalCode, message: str) -> None:
        self.refusals.add(node.pointer, code, message)

    def object(self, node: SchemaNode, ancestors: tuple[str, ...]) -> None:
        for name, child in node.properties:
            generated = child.declaration is not None and child.declaration.declares_generate
            if child.kind is Kind.OBJECT and not generated:
                self.object(child, (*ancestors, name))
            elif child.kind is not Kind.REFUSED and (generated or child.kind is not Kind.CONSTANT):
                self.field(name, child, ancestors)

    def field(self, name: str, node: SchemaNode, ancestors: tuple[str, ...]) -> None:
        declaration = node.declaration
        if declaration is not None and (declaration.declares_source or declaration.declares_generate):
            if declaration.generate is not None:
                self.generative(name, node, declaration.generate)
            return None  # otherwise declarations.py refused it: source_selection_dropped, or malformed
        items = node.items
        if items is not None and items.kind is Kind.REFUSED:
            return
        if items is not None and items.kind is Kind.ENUM:
            return self.refuse(node, RefusalCode.NOT_YET_SUPPORTED, "multi-label enum arrays are lifted in Phase 7")
        ordinal = declaration is not None and declaration.ordinal
        if ordinal and node.kind is not Kind.INTEGER:
            return self.refuse(node, RefusalCode.ORDINAL_LEVELS, "ordinal: true needs an integer range")
        if node.has_default and not (declaration is not None and declaration.decides):
            return  # class A: omitted, so the caller's default applies
        verbatim = questions.declared_question(node) is not None
        labelled = questions.Labelled(questions.label(name, node), ancestors, verbatim)
        if node.kind is Kind.BOOLEAN:
            self.boolean(node, labelled)
        elif node.kind is Kind.ENUM:
            self.enum(node, labelled)
        elif ordinal:
            self.ordinal(node, labelled)
        else:
            self.unbounded(node)
        return None

    def generative(self, name: str, node: SchemaNode, declared: GenerateDeclaration) -> None:
        if node.kind is not Kind.STRING:
            return self.refuse(
                node,
                RefusalCode.GENERATE_FIELD_TYPE,
                f"x-jevson.generate drafts one string; this field is {node.kind} (generative lists are class G)",
            )
        self.generated += generative_nodes(node.pointer, questions.label(name, node), declared)
        return None

    def boolean(self, node: SchemaNode, labelled: questions.Labelled) -> None:
        """A bool is labelled by its statement, never its name: "verified" is not something to ask about."""
        statement = questions.predicate(node)
        if statement is None:
            return self.refuse(
                node,
                RefusalCode.BOOL_PREDICATE_MISSING,
                "a decided bool needs a statement to ask about; declare x-jevson.question or a description "
                "such as 'the invoice is paid'",
            )
        self.pending.append(_Pending(node, DecisionKind.PREDICATE, replace(labelled, label=statement)))
        return None

    def enum(self, node: SchemaNode, labelled: questions.Labelled) -> None:
        if not all(isinstance(v, str | int) and not isinstance(v, bool) for v in node.values):
            return self.refuse(node, RefusalCode.ENUM_VALUE_TYPE, "enum values must be strings or integers")
        if len(node.values) > MAX_OPTIONS:
            return self.refuse(node, RefusalCode.ENUM_SIZE, f"{len(node.values)} values; a choice takes 2-255")
        self.pending.append(_Pending(node, DecisionKind.CHOICE, labelled, node.values))
        return None

    def ordinal(self, node: SchemaNode, labelled: questions.Labelled) -> None:
        levels = _levels(node.keywords)
        if levels is None or not MIN_LEVELS <= len(levels) <= MAX_LEVELS:
            found = "an unbounded range" if levels is None else f"{len(levels)} levels"
            return self.refuse(node, RefusalCode.ORDINAL_LEVELS, f"an ordinal needs 2-10 levels; found {found}")
        self.pending.append(_Pending(node, DecisionKind.SCORE, labelled, levels))
        return None

    def unbounded(self, node: SchemaNode) -> None:
        if self.default_extractor is not None:
            self.refuse(
                node,
                RefusalCode.SOURCE_SELECTION_DROPPED,
                f"default_extractor {self.default_extractor!r} would source-select this field, and Phase 0r "
                "dropped source selection [Q2, Q9]; declare `generate`, or make the field an enum, instead",
            )
        else:
            self.refuse(
                node,
                RefusalCode.UNBOUNDED_FIELD,
                "class G: an unbounded value with no default and no `generate`; declare one, or make it an enum",
            )


def _levels(keywords: Mapping[str, object]) -> tuple[JSONValue, ...] | None:
    """The integers an ordinal range allows, lowest first; None when a bound is missing or too wide.

    `minimum`/`exclusiveMinimum` and `maximum`/`exclusiveMaximum` combine to the tighter bound, and
    a positive `multipleOf` keeps only its multiples, so every level passes final validation."""
    lows = [math.ceil(v) for v in _numbers(keywords, "minimum")]
    lows += [math.floor(v) + 1 for v in _numbers(keywords, "exclusiveMinimum")]
    highs = [math.floor(v) for v in _numbers(keywords, "maximum")]
    highs += [math.ceil(v) - 1 for v in _numbers(keywords, "exclusiveMaximum")]
    if not lows or not highs or min(highs) - max(lows) > MAX_ORDINAL_SPAN:
        return None
    steps = [Decimal(repr(s)) for s in _numbers(keywords, "multipleOf") if s > 0]  # exact: 3 % 0.1 is not 0.0
    return tuple(v for v in range(max(lows), min(highs) + 1) if all(Decimal(v) % s == 0 for s in steps))


def _numbers(keywords: Mapping[str, object], key: str) -> list[float]:
    value = keywords.get(key)
    if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value):
        return [float(value)]
    return []
