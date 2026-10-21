"""Union branches at run time: which branch each discriminator selected, and what that opens.

A node inside union branches carries gates, `(discriminator id, option id)` pairs, outermost first
(`compile/unions.py`). It runs only when every gate is selected; a branch that was not selected is
skipped and leaves nothing in the result, not even a null. A discriminator that did not resolve
leaves its branches' nodes `Unresolved(dependency_unresolved)`.

Constants (`DecisionGraph.constants`) are committed by code as soon as their gates are open: at the
start for those outside every union, on selection for a branch's (its Pydantic tag, for example).
Known values for fields inside a branch are committed the same way, as `caller`.

`known=` (DESIGN §8): a known value for a branch constant selects that branch without a decision,
and must match exactly one branch's constant; a known value for a field inside a branch is used
only when that branch is selected. A known value at a union's own pointer that no constant matches is
a scalar branch's value (preflight checked it): it closes every branch of every union at that pointer,
so nothing below the union is asked.
"""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
from typing import Literal

from jevson.assemble.assembler import Committed, Outcome
from jevson.errors import PreflightError
from jevson.graph import DecisionGraph
from jevson.types import DecidedBy, Gates, JSONValue

Gate = Literal["open", "closed", "unresolved", "pending"]
_NO_BRANCH = ""
"""What a discriminator 'selected' when a known scalar value replaced its union: no option has this id."""


class Branches:
    def __init__(self, graph: DecisionGraph, known: Mapping[str, JSONValue]) -> None:
        self.constants = graph.constants
        self.selected: dict[str, str] = {}
        self.failed: set[str] = set()
        outside = {n.target for n in graph.nodes.values() if not n.branch}
        self.inside: dict[str, list[Gates]] = {}
        for node in graph.nodes.values():
            if node.branch and node.target not in outside:
                self.inside.setdefault(node.target, []).append(node.branch)
        gated = [*(n.branch for n in graph.nodes.values()), *(c.branch for c in self.constants)]
        discriminators = {d for gates in gated for d, _ in gates}
        self.unions: dict[str, list[str]] = {}
        """The discriminators of every union at a pointer (nested unions share it), by that pointer."""
        for discriminator in sorted(discriminators):
            self.unions.setdefault(graph.nodes[discriminator].target, []).append(discriminator)
        self.scalar = {n.target for n in graph.nodes.values() if n.branch and n.id not in discriminators}
        """Pointers a decided branch commits at: a scalar branch, or a field inside an object branch."""
        self.deferred = {p: v for p, v in known.items() if p in self.inside}
        """Known values for fields that exist only inside branches, committed if their branch runs."""
        for pointer, value in known.items():
            self._force(pointer, value)

    def gate(self, gates: Gates) -> Gate:
        """`pending` only under fan-out, while the discriminator is asked in the same request."""
        for discriminator, option in gates:
            if discriminator in self.failed:
                return "unresolved"
            chosen = self.selected.get(discriminator)
            if chosen is None:
                return "pending"
            if chosen != option:
                return "closed"
        return "open"

    def commit_open(self, outcomes: MutableMapping[str, Outcome]) -> None:
        """Commit every constant and deferred known value whose branch is now open."""
        for constant in self.constants:
            if constant.pointer not in outcomes and self.gate(constant.branch) == "open":
                outcomes[constant.pointer] = Committed(constant.pointer, constant.value, DecidedBy.CODE)
        for pointer, value in self.deferred.items():
            if pointer not in outcomes and any(self.gate(g) == "open" for g in self.inside[pointer]):
                outcomes[pointer] = Committed(pointer, value, DecidedBy.CALLER)

    def _force(self, pointer: str, value: JSONValue) -> None:
        at = [c for c in self.constants if c.pointer == pointer]
        matching = [c for c in at if type(c.value) is type(value) and c.value == value]
        if len(matching) == 1:
            self._select(matching[0].branch)
        elif matching or (at and pointer not in self.scalar):
            found = "matches no" if not matching else "matches more than one"
            raise PreflightError(f"known= value for {pointer!r} {found} branch constant, so it selects no branch")
        else:  # a decided field (the façade has checked its value), or a scalar branch's value at a union
            self._select(tuple((d, _NO_BRANCH) for d in self.unions.get(pointer, ())))

    def _select(self, gates: Gates) -> None:
        for discriminator, option in gates:
            if self.selected.setdefault(discriminator, option) != option:
                raise PreflightError(f"known= values select two branches of {discriminator}")
