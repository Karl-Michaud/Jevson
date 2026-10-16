"""Unions: a discriminator `choice` over the branches, then only the selected branch (DESIGN §3.2).

A union with two or more non-null branches (`anyOf`, `oneOf`, Pydantic's discriminated unions)
compiles to one `choice`, `<pointer>#branch`, asked with the union template of docs/taxonomy.md §1.2
and no `none_of_these` (v0). Every branch is mapped like any other subtree, so every refusal in any
branch is found before a call (R14); its nodes carry the gate `(discriminator id, option id)` and,
in the default strategy, depend on the discriminator, so they run one level later and only when
their branch is selected. With `union_fanout`, a union whose branches hold only decisions puts them
in the discriminator's level instead, and the executor discards the unselected branches' answers.

**Node ids.** Two branches can decide the same instance pointer, so a node inside a branch is
named by its pointer with `|<option id>` after the union's pointer: `/payment|c1/kind#choice`.
`|` is not a JSON pointer escape (`~0`, `~1`), not the `#role` suffix, and not the `@n` attempt
suffix, and it reads as a qualifier rather than an index (R13).

**Option text** (one per branch, plain text): `title: description` when the branch has both, else
whichever it has, else a summary of its shape (`with name, email` for an object's required
properties). Branches whose text collides get the summary appended; branches still identical after
that are undiscriminable and refuse. Pydantic titles every model with its class name.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from jevson.compile import questions
from jevson.compile.nodes import option_id, role_id
from jevson.compile.normalise import Kind, SchemaNode
from jevson.types import DecisionKind, DecisionNode, Gates, Option, OptionSource

SEPARATOR = "|"


@dataclass(frozen=True)
class Branching:
    """Where the mapper is: the gates above it, the unions they belong to, and what a node there
    depends on (the innermost level-mode discriminator, else nothing)."""

    gates: Gates = ()
    unions: tuple[str, ...] = ()
    after: frozenset[str] = frozenset()

    def qualify(self, pointer: str) -> str:
        """The id form of `pointer`: `|<option>` after each enclosing union's pointer, innermost first,
        so an outer insertion never shifts an inner one."""
        for union, (_, option) in reversed(list(zip(self.unions, self.gates, strict=True))):
            pointer = f"{union}{SEPARATOR}{option}{pointer[len(union) :]}"
        return pointer

    def enter(self, union: SchemaNode, index: int, *, fanout: bool) -> Branching:
        discriminator = role_id(self.qualify(union.pointer), "branch")
        gate = (discriminator, option_id(index))
        after = self.after if fanout and all(pure(b) for b in union.branches) else frozenset({discriminator})
        return Branching((*self.gates, gate), (*self.unions, union.pointer), after)


@dataclass(frozen=True)
class PendingUnion:
    """A discriminator whose question waits for its scope, like `mapping._Pending`."""

    node: SchemaNode
    labelled: questions.Labelled
    texts: tuple[str, ...]
    at: Branching

    def render(self, scope: str) -> DecisionNode:
        label = questions.scoped_label(self.labelled.label, scope)
        return DecisionNode(
            role_id(self.at.qualify(self.node.pointer), "branch"),
            DecisionKind.CHOICE,
            questions.union_question(label),
            OptionSource.SCHEMA_UNION,
            self.node.pointer,
            tuple(Option(option_id(i), text) for i, text in enumerate(self.texts)),
            dependencies=self.at.after,
            branch=self.at.gates,
        )


def branch_texts(branches: Sequence[SchemaNode]) -> tuple[str, ...] | None:
    """One option text per branch, or None when two branches cannot be told apart."""
    texts = [_described(b) or _summary(b) for b in branches]
    counts = Counter(texts)
    texts = [
        f"{t} ({_summary(b)})" if counts[t] > 1 and t != _summary(b) else t
        for t, b in zip(texts, branches, strict=True)
    ]
    return tuple(texts) if len(set(texts)) == len(texts) else None


def exclusive(a: Gates, b: Gates) -> bool:
    """True when no selection runs both: they sit in different branches of one union."""
    chosen = dict(a)
    return any(chosen.get(discriminator, option) != option for discriminator, option in b)


def pure(node: SchemaNode) -> bool:
    """True when nothing in the subtree declares `generate`: every node in it is a decision."""
    if node.declaration is not None and node.declaration.declares_generate:
        return False
    children = [child for _, child in node.properties] + list(node.branches)
    return all(pure(child) for child in children)


def _described(node: SchemaNode) -> str:
    title, description = (" ".join((t or "").split()) for t in (node.title, node.description))
    return f"{title}: {description}" if title and description else title or description


def _summary(node: SchemaNode) -> str:
    if node.kind is Kind.OBJECT:
        names = [name for name, child in node.properties if child.required]
        return f"with {', '.join(names)}" if names else "an object with no required fields"
    if node.kind is Kind.ENUM:
        return "one of " + ", ".join(questions.option_description(v) for v in node.values)
    if node.kind is Kind.CONSTANT:
        return questions.option_description(node.values[0])
    if node.kind is Kind.UNION:
        return "one of " + " or ".join(_described(b) or _summary(b) for b in node.branches)
    kind = node.kind.value
    return f"{'an' if kind[0] in 'aeiou' else 'a'} {kind}"
