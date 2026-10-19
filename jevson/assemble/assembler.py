"""Resolved graph -> JSON object, then validation against the original schema (DESIGN §6.1).

The input is one outcome per decided pointer: a committed value or an `Unresolved`. A pointer with
no outcome (an undeclared defaulted leaf, class A) is omitted so the caller's default applies. An
unresolved pointer omits its whole subtree, so an unresolved root yields `{}`; an `Unresolved` inside
it is still listed, so an unresolved union names its children `dependency_unresolved`. Nothing abstains in
v0, so `Result.absent` is always empty (DESIGN §5.6). `satisfies_schema` is computed by validation
(draft 2020-12), never inferred. `array_holes` are the unresolved values of an array that is still emitted
(`cardinality.py`), listed after the outcomes'.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, TypeAlias

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from jevson.result import Result
from jevson.types import (
    Cost,
    DecidedBy,
    Decision,
    JSONValue,
    Overflow,
    Provenance,
    Rejection,
    Unresolved,
    Violation,
)


@dataclass(frozen=True)
class Committed:
    pointer: str
    value: JSONValue
    decided_by: DecidedBy
    provenance: Provenance | None = None


Outcome: TypeAlias = Committed | Unresolved

_UNGATED = frozenset({DecidedBy.DIRECT, DecidedBy.LLM})


def assemble(
    schema: Mapping[str, Any],
    outcomes: Iterable[Outcome],
    *,
    decisions: Mapping[str, Decision] | None = None,
    cost: Cost | None = None,
    model: tuple[str, ...] = (),
    versions: Mapping[str, str] | None = None,
    overflow: tuple[Overflow, ...] = (),
    array_holes: tuple[Unresolved, ...] = (),
    rejections: tuple[Rejection, ...] = (),
) -> Result:
    by_pointer: dict[str, Outcome] = {}
    for outcome in outcomes:
        if outcome.pointer in by_pointer:
            raise ValueError(f"two outcomes for {outcome.pointer!r}")
        if outcome.pointer == "" and isinstance(outcome, Committed):
            raise ValueError("the root is never committed; it is assembled")
        by_pointer[outcome.pointer] = outcome
    holes = [p for p, o in by_pointer.items() if isinstance(o, Unresolved)]

    value: dict[str, JSONValue] = {}
    provenance: dict[str, Provenance] = {}
    decided_by: dict[str, DecidedBy] = {}
    unresolved: list[Unresolved] = []
    for pointer in sorted(by_pointer, key=_tokens):
        outcome = by_pointer[pointer]
        if any(_strictly_under(pointer, hole) for hole in holes):
            if isinstance(outcome, Unresolved):  # named, e.g. a union's children (DESIGN §6.1)
                unresolved.append(outcome)
            continue
        if isinstance(outcome, Unresolved):
            unresolved.append(outcome)
            continue
        *parents, name = _tokens(pointer)
        _container(value, parents)[name] = copy.deepcopy(outcome.value)
        decided_by[pointer] = outcome.decided_by
        if outcome.provenance is not None:
            provenance[pointer] = outcome.provenance

    unresolved += array_holes
    violations = _validate(schema, value)
    return Result(
        value=value,
        satisfies_schema=not violations,
        provenance=provenance,
        decided_by=decided_by,
        decisions=dict(decisions or {}),
        unresolved=tuple(unresolved),
        violations=tuple(violations),
        absent=(),
        ungated=tuple(p for p, by in decided_by.items() if by in _UNGATED),
        overflow=overflow,
        rejections=rejections,
        cost=cost or Cost(),
        model=model,
        versions=dict(versions or {}),
    )


def _validate(schema: Mapping[str, Any], value: dict[str, JSONValue]) -> list[Violation]:
    validator: Any = Draft202012Validator(schema)  # jsonschema's overloads are partially untyped
    errors: list[ValidationError] = list(validator.iter_errors(value))
    violations = [
        Violation("".join(f"/{_escape(str(t))}" for t in e.absolute_path), str(e.validator), e.message) for e in errors
    ]
    return sorted(violations, key=lambda v: (_tokens(v.pointer), v.keyword, v.message))


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


def _strictly_under(pointer: str, ancestor: str) -> bool:
    a, p = _tokens(ancestor), _tokens(pointer)
    return len(p) > len(a) and p[: len(a)] == a
