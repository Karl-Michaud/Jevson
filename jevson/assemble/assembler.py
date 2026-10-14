"""Resolved graph -> JSON object, then validation against the original schema.

The input is one outcome per target pointer: a committed value, an abstention (class D only), or an
`Unresolved`. Absence follows DESIGN §5.6:

| field                              | abstention yields | recorded in                          |
|------------------------------------|-------------------|--------------------------------------|
| not required                       | key omitted       | absent                               |
| required and nullable              | null              | absent                               |
| required and not nullable          | key omitted       | unresolved (abstained/no_candidates) |

A refusal is an `Unresolved(refused)` outcome and never passes through this table. An object is
abstained when it has a class D descendant, and every one abstained; the root never is. An
unresolved pointer omits its whole subtree, so an unresolved root yields `{}`. `satisfies_schema`
is computed by validation (draft 2020-12), never inferred.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from jevson.result import Result
from jevson.types import (
    Absent,
    Cost,
    DecidedBy,
    Decision,
    JSONValue,
    Overflow,
    Provenance,
    Rejection,
    Span,
    Unresolved,
    UnresolvedReason,
    Violation,
)

Schema: TypeAlias = Mapping[str, Any]


@dataclass(frozen=True)
class Committed:
    pointer: str
    value: JSONValue
    decided_by: DecidedBy
    provenance: Provenance | None = None


@dataclass(frozen=True)
class Abstained:
    """A source-selected field chose `none_of_these`, or its extractor found no candidates."""

    pointer: str
    candidates_seen: tuple[Span, ...] = ()
    abstain_probability: int | None = None
    no_candidates: bool = False


Outcome: TypeAlias = Committed | Abstained | Unresolved

_UNGATED = frozenset({DecidedBy.DIRECT, DecidedBy.LLM})


def assemble(
    schema: Schema,
    outcomes: Iterable[Outcome],
    *,
    source_selected: frozenset[str] = frozenset(),
    decisions: Mapping[str, Decision] | None = None,
    cost: Cost | None = None,
    model: tuple[str, ...] = (),
    versions: Mapping[str, str] | None = None,
    overflow: tuple[Overflow, ...] = (),
    rejections: tuple[Rejection, ...] = (),
) -> Result:
    """`source_selected` names the target pointers of class D decisions (from the graph)."""
    by_pointer: dict[str, Outcome] = {}
    for outcome in outcomes:
        if outcome.pointer in by_pointer:
            raise ValueError(f"two outcomes for {outcome.pointer!r}")
        if outcome.pointer == "" and not isinstance(outcome, Unresolved):
            raise ValueError("the root is never committed or abstained")
        by_pointer[outcome.pointer] = outcome
    kept = _abstain_objects(_drop_under_unresolved(by_pointer), source_selected)

    value: dict[str, JSONValue] = {}
    provenance: dict[str, Provenance] = {}
    decided_by: dict[str, DecidedBy] = {}
    unresolved: list[Unresolved] = []
    absent: list[Absent] = []
    for pointer in sorted(kept, key=_tokens):
        outcome = kept[pointer]
        if isinstance(outcome, Committed):
            _set(value, pointer, copy.deepcopy(outcome.value))
            decided_by[pointer] = outcome.decided_by
            if outcome.provenance is not None:
                provenance[pointer] = outcome.provenance
        elif isinstance(outcome, Unresolved):
            unresolved.append(outcome)
            _ensure_parent(value, pointer)
        else:
            required, nullable = _requiredness(schema, pointer)
            seen, p = outcome.candidates_seen, outcome.abstain_probability
            if required and not nullable:
                reason = UnresolvedReason.NO_CANDIDATES if outcome.no_candidates else UnresolvedReason.ABSTAINED
                unresolved.append(Unresolved(pointer, reason, seen, p))
                _ensure_parent(value, pointer)
            else:
                absent.append(Absent(pointer, seen, p))
                if required:
                    _set(value, pointer, None)
                else:
                    _ensure_parent(value, pointer)

    violations = _validate(schema, value)
    return Result(
        value=value,
        satisfies_schema=not violations,
        provenance=provenance,
        decided_by=decided_by,
        decisions=dict(decisions or {}),
        unresolved=tuple(unresolved),
        violations=tuple(violations),
        absent=tuple(absent),
        ungated=tuple(p for p, by in decided_by.items() if by in _UNGATED),
        overflow=overflow,
        rejections=rejections,
        cost=cost or Cost(),
        model=model,
        versions=dict(versions or {}),
    )


def _validate(schema: Schema, value: dict[str, JSONValue]) -> list[Violation]:
    validator: Any = Draft202012Validator(schema)  # jsonschema's overloads are partially untyped
    errors: list[ValidationError] = list(validator.iter_errors(value))
    violations = [
        Violation("".join(f"/{_escape(str(t))}" for t in e.absolute_path), str(e.validator), e.message) for e in errors
    ]
    return sorted(violations, key=lambda v: (_tokens(v.pointer), v.keyword, v.message))


def _drop_under_unresolved(outcomes: dict[str, Outcome]) -> dict[str, Outcome]:
    holes = [p for p, o in outcomes.items() if isinstance(o, Unresolved)]
    return {p: o for p, o in outcomes.items() if not any(_strictly_under(p, hole) for hole in holes)}


def _abstain_objects(outcomes: dict[str, Outcome], source_selected: frozenset[str]) -> dict[str, Outcome]:
    """Collapse each abstained object (outermost first) into one abstention at its own pointer."""
    objects = {ancestor for pointer in source_selected for ancestor in _ancestors(pointer)}
    collapsed: list[str] = []
    for obj in sorted(objects, key=lambda p: (len(_tokens(p)), p)):
        if obj in outcomes or any(_strictly_under(obj, outer) for outer in collapsed):
            continue  # the object has its own outcome (e.g. unresolved), or an outer one collapsed
        below = sorted(p for p in source_selected if _strictly_under(p, obj))
        if not all(isinstance(outcomes.get(p), Abstained) for p in below):
            continue  # one committed, is unresolved (e.g. refused), or was dropped under a hole
        seen = tuple(span for p in below for span in cast(Abstained, outcomes[p]).candidates_seen)
        outcomes = {p: o for p, o in outcomes.items() if not _strictly_under(p, obj)}
        outcomes[obj] = Abstained(obj, seen)
        collapsed.append(obj)
    return outcomes


def _requiredness(schema: Schema, pointer: str) -> tuple[bool, bool]:
    """(required in its parent object, nullable) for the field at `pointer`."""
    *parents, name = _tokens(pointer)
    node = _resolve(schema, schema)
    for token in parents:
        node = _resolve(schema, node.get("properties", {}).get(token, {}))
    field_schema: Schema = node.get("properties", {}).get(name, {})
    return name in node.get("required", ()), _nullable(schema, field_schema)


def _resolve(root: Schema, node: Schema) -> Schema:
    """Follow local `$ref`s and unwrap `Optional[T]` (`anyOf`/`oneOf` with one non-null branch)."""
    for _ in range(64):  # a bound, so a self-referencing $ref cannot loop
        if "$ref" in node:
            node = _follow(root, str(node["$ref"]))
            continue
        branches = [b for b in _branches(node) if not _is_null(root, b)]
        if len(branches) != 1:
            return node
        node = branches[0]
    raise ValueError("schema $ref chain too deep")


def _nullable(root: Schema, node: Schema) -> bool:
    node = _follow(root, str(node["$ref"])) if "$ref" in node else node
    return _is_null(root, node) or any(_is_null(root, b) for b in _branches(node))


def _branches(node: Schema) -> list[Schema]:
    return cast(list[Schema], node.get("anyOf", node.get("oneOf", [])))


def _is_null(root: Schema, node: Schema) -> bool:
    node = _follow(root, str(node["$ref"])) if "$ref" in node else node
    kind = node.get("type")
    return kind == "null" or (isinstance(kind, list) and "null" in kind)


def _follow(root: Schema, ref: str) -> Schema:
    if not ref.startswith("#"):
        raise ValueError(f"only local $refs are supported, got {ref!r}")
    node: Any = root
    for token in _tokens(ref[1:]):
        node = node[token]
    return cast(Schema, node)


def _set(target: dict[str, JSONValue], pointer: str, value: JSONValue) -> None:
    *parents, name = _tokens(pointer)
    _container(target, parents)[name] = value


def _ensure_parent(target: dict[str, JSONValue], pointer: str) -> None:
    if pointer:
        _container(target, _tokens(pointer)[:-1])


def _container(target: dict[str, JSONValue], tokens: list[str]) -> dict[str, JSONValue]:
    node = target
    for token in tokens:
        child = node.setdefault(token, {})
        if not isinstance(child, dict):
            raise ValueError(f"cannot place a value under the leaf at /{token}")
        node = child
    return node


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise ValueError(f"not a JSON pointer: {pointer!r}")
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _ancestors(pointer: str) -> list[str]:
    """Proper, non-root ancestors of `pointer`."""
    tokens = _tokens(pointer)
    return ["".join(f"/{_escape(t)}" for t in tokens[:i]) for i in range(1, len(tokens))]


def _strictly_under(pointer: str, ancestor: str) -> bool:
    a, p = _tokens(ancestor), _tokens(pointer)
    return len(p) > len(a) and p[: len(a)] == a
