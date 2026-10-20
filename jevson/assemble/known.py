"""The preflight check of `known=` values (PLAN Phase 3, known values; DESIGN §8).

A known value is accepted only if it names a decided field (or a constant the executor checks), is
one of the field's declared values (an enum's options, a bool, distinct declared items for a
multi-label array, a string for a generative field, or null for a nullable field), and meets the
field's own JSON Schema constraints (`maxLength`, `pattern`, `format`, …, carried on the normalised
node, through a `$ref` too). Anything else raises `PreflightError` before any call. Union branches can
declare the same pointer differently, and preflight does not know which branch will be selected, so a
value is refused only if every declaration at its pointer refuses it; the selected branch's own schema
decides in final validation (DESIGN §8: a known value inside a branch is used only if that branch is
selected). For a Pydantic
model only the emitted JSON Schema is checked; field validators run in final validation
(`satisfies_schema`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from jevson.assemble.validation import validator
from jevson.compile.normalise import Kind, SchemaNode
from jevson.errors import PreflightError
from jevson.graph import DecisionGraph
from jevson.types import DecisionKind, DecisionNode, JSONValue, StepNode

_OPTIONAL = SchemaNode("", Kind.REFUSED, required=False)


def check_known(
    graph: DecisionGraph, schema: SchemaNode, known: Mapping[str, JSONValue] | None
) -> dict[str, JSONValue]:
    """The checked `known=` values by pointer, or `PreflightError` naming the first bad one."""
    if known is None:
        return {}
    if not isinstance(known, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise PreflightError("known= must map JSON pointers to values")
    by_target: dict[str, list[DecisionNode | StepNode]] = {}
    for node in graph.nodes.values():
        by_target.setdefault(node.target, []).append(node)
    fields = declarations(schema)
    constants = {c.pointer for c in graph.constants}  # checked by the executor (`execute/branches.py`)
    for pointer, value in known.items():
        nodes = by_target.get(pointer)
        if nodes is None and pointer in constants:
            continue
        if nodes is None:
            raise PreflightError(f"known= names {pointer!r}, which is not a decided field")
        _check(pointer, value, nodes, fields.get(pointer, [_OPTIONAL]))
    return dict(known)


def declarations(node: SchemaNode) -> dict[str, list[SchemaNode]]:
    """Every property's normalised node by pointer, one per union branch that declares it."""
    found: dict[str, list[SchemaNode]] = {}
    for _, child in node.properties:
        found.setdefault(child.pointer, []).append(child)
    for child in (*(c for _, c in node.properties), *node.branches):  # a branch sits at its union's pointer
        for pointer, nodes in declarations(child).items():
            found.setdefault(pointer, []).extend(nodes)
    return found


def _check(
    pointer: str, value: JSONValue, nodes: Sequence[DecisionNode | StepNode], fields: Sequence[SchemaNode]
) -> None:
    """Raise unless some declaration at `pointer` admits `value`: a declared value meeting its constraints."""
    declared = [f for f in fields if any(_allowed(n, f, value) for n in nodes)]
    if not declared:
        raise PreflightError(f"known= value for {pointer!r} is not one of the field's declared values")
    broken = [sorted(str(e.message) for e in validator(dict(f.keywords)).iter_errors(value)) for f in declared]
    if all(broken):
        raise PreflightError(f"known= value for {pointer!r} fails its field schema: {'; '.join(broken[0])}")


def _allowed(node: DecisionNode | StepNode, field: SchemaNode, value: JSONValue) -> bool:
    if value is None:
        return field.nullable
    if isinstance(node, StepNode):
        return isinstance(value, str)
    if node.member is not None:  # a multi-label enum array: distinct declared values
        declared = field.items.values if field.items is not None else ()
        items = cast("list[JSONValue]", value) if isinstance(value, list) else None
        return (
            items is not None
            and len(set(map(repr, items))) == len(items)
            and all(any(type(item) is type(v) and item == v for v in declared) for item in items)
        )
    if node.kind is DecisionKind.PREDICATE:
        return isinstance(value, bool)
    return any(type(value) is type(v) and value == v for v in node.values)
