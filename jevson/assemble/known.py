"""The preflight check of `known=` values (PLAN Phase 3, known values; DESIGN §8).

A known value is accepted only if it names a decided field (or a constant the executor checks), is
one of the field's declared values (an enum's options, a bool, distinct declared items for a
multi-label array, a string for a generative field, or null for a nullable field), and meets the
field's own JSON Schema constraints (`maxLength`, `pattern`, `format`, …, carried on the normalised
node, through a `$ref` too). Anything else raises `PreflightError` before any call. Each declaration
admits only values of its own kind and declared options, so a node compiled from one union branch never
vouches for a value against another branch's declaration. Union branches can declare the same pointer
differently; a branch that a known discriminator rules out (a known value for one of its constants that
differs from it) is not consulted, and among the rest a value is refused only if every declaration at its
pointer refuses it. The selected branch's own schema decides in final validation (DESIGN §8: a known value
inside a branch is used only if that branch is selected). For a Pydantic model only the emitted JSON
Schema is checked; field validators run in final validation (`satisfies_schema`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from jevson.assemble.validation import validator
from jevson.compile.normalise import Kind, SchemaNode
from jevson.errors import PreflightError
from jevson.graph import DecisionGraph
from jevson.types import DecisionKind, DecisionNode, JSONValue, StepNode


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
    fields = declarations(schema, known)
    every = declarations(schema, {})  # compile declares every node's target, so `every[target]` exists
    constants = {c.pointer for c in graph.constants}  # checked by the executor (`execute/branches.py`)
    for pointer, value in known.items():
        nodes = by_target.get(pointer)
        if nodes is None and pointer in constants:
            continue
        if nodes is None:
            raise PreflightError(f"known= names {pointer!r}, which is not a decided field")
        # () when a known discriminator rules out every branch that declares the pointer: refused
        open_ = fields.get(pointer, ())
        _check(pointer, value, nodes, open_, narrowed=len(open_) < len(every[pointer]))
    return dict(known)


def declarations(node: SchemaNode, known: Mapping[str, JSONValue]) -> dict[str, list[SchemaNode]]:
    """Every property's normalised node by pointer, one per union branch that declares it, leaving out
    every branch whose constant `known` gives a different value."""
    found: dict[str, list[SchemaNode]] = {}
    for _, child in node.properties:
        found.setdefault(child.pointer, []).append(child)
    branches = (b for b in node.branches if not _ruled_out(b, known))
    for child in (*(c for _, c in node.properties), *branches):  # a branch sits at its union's pointer
        for pointer, nodes in declarations(child, known).items():
            found.setdefault(pointer, []).extend(nodes)
    return found


def _ruled_out(branch: SchemaNode, known: Mapping[str, JSONValue]) -> bool:
    constants = (c for _, c in branch.properties if c.kind is Kind.CONSTANT and c.pointer in known)
    return any(not _same(known[c.pointer], c.values[0]) for c in constants)


def _same(value: JSONValue, declared: JSONValue) -> bool:
    return type(value) is type(declared) and value == declared


def _check(
    pointer: str,
    value: JSONValue,
    nodes: Sequence[DecisionNode | StepNode],
    fields: Sequence[SchemaNode],
    *,
    narrowed: bool,
) -> None:
    """Raise unless some declaration at `pointer` admits `value`: a declared value meeting its constraints.
    `narrowed` says a known discriminator left out a branch declaring `pointer`, which the message names."""
    declared = [f for f in fields if any(_allowed(n, f, value) for n in nodes)]
    if not declared:
        where = " in any union branch the known= values leave open" if narrowed else ""
        raise PreflightError(f"known= value for {pointer!r} is not one of the field's declared values{where}")
    broken = [sorted(str(e.message) for e in validator(dict(f.keywords)).iter_errors(value)) for f in declared]
    if all(broken):
        raise PreflightError(f"known= value for {pointer!r} fails its field schema: {'; '.join(broken[0])}")


def _allowed(node: DecisionNode | StepNode, field: SchemaNode, value: JSONValue) -> bool:
    """Whether `field` itself declares `value` and `node` decides a field of that kind."""
    if value is None:
        return field.nullable
    if isinstance(node, StepNode):
        return field.kind is Kind.STRING and isinstance(value, str)
    if node.member is not None:  # a multi-label enum array: distinct declared values
        return field.items is not None and _labels(field.items.values, value)
    if node.kind is DecisionKind.PREDICATE:
        return field.kind is Kind.BOOLEAN and isinstance(value, bool)
    if node.kind is DecisionKind.CHOICE:
        return field.kind is Kind.ENUM and any(_same(value, v) for v in field.values)
    return field.kind is Kind.INTEGER and any(_same(value, v) for v in node.values)  # a score's levels; the
    # field's own `minimum`/`maximum` are kept keywords, so another branch's range is checked in `_check`


def _labels(declared: Sequence[JSONValue], value: JSONValue) -> bool:
    items = cast("list[JSONValue]", value) if isinstance(value, list) else None
    return (
        items is not None
        and len(set(map(repr, items))) == len(items)
        and all(any(_same(item, v) for v in declared) for item in items)
    )
