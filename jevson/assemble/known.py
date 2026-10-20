"""The preflight check of `known=` values (PLAN Phase 3, known values; DESIGN §8).

A known value is accepted only if it names a decided field (or a constant the executor checks), is
one of the field's declared values (an enum's options, a bool, distinct declared items for a
multi-label array, a string for a generative field, or null for a nullable field), and meets the
field's own JSON Schema constraints (`maxLength`, `pattern`, `format`, …, carried on the normalised
node, through a `$ref` too). Anything else raises `PreflightError` before any call. For a Pydantic
model only the emitted JSON Schema is checked; field validators run in final validation
(`satisfies_schema`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from jevson.assemble.validation import validator
from jevson.compile.normalise import Kind, SchemaNode
from jevson.errors import PreflightError
from jevson.graph import DecisionGraph
from jevson.types import DecisionKind, DecisionNode, JSONValue, StepNode

_OPTIONAL = SchemaNode("", Kind.REFUSED, required=False)


def check_known(
    graph: DecisionGraph, fields: Mapping[str, SchemaNode], known: Mapping[str, JSONValue] | None
) -> dict[str, JSONValue]:
    """The checked `known=` values by pointer, or `PreflightError` naming the first bad one."""
    if known is None:
        return {}
    if not isinstance(known, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise PreflightError("known= must map JSON pointers to values")
    by_target: dict[str, DecisionNode | StepNode] = {}
    for node in graph.nodes.values():
        if isinstance(node, StepNode) or node.target not in by_target:
            by_target[node.target] = node  # a generative field is known by its step
    constants = {c.pointer for c in graph.constants}  # checked by the executor (`execute/branches.py`)
    for pointer, value in known.items():
        node = by_target.get(pointer)
        if node is None and pointer in constants:
            continue
        if node is None:
            raise PreflightError(f"known= names {pointer!r}, which is not a decided field")
        field = fields.get(pointer, _OPTIONAL)
        if not _allowed(node, field, value):
            raise PreflightError(f"known= value for {pointer!r} is not one of the field's declared values")
        broken = sorted(str(e.message) for e in validator(dict(field.keywords)).iter_errors(value))
        if broken:
            raise PreflightError(f"known= value for {pointer!r} fails its field schema: {'; '.join(broken)}")
    return dict(known)


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
