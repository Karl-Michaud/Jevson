"""The decision graph: nodes, dependency edges, acyclicity, and topological levelling (R3, R11).

A level is the unit of execution: its step nodes run first (in dependency order), then its decision
nodes go to the backend as one batched request. A node's level index counts the decision nodes on
its longest dependency path, so a decision always lands in a later level than every decision it
depends on, and a step lands in the level whose decisions consume it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from jevson.errors import CompileError, RefusalCode, RefusalReason
from jevson.types import Constant, DecisionNode, StepNode

Node: TypeAlias = DecisionNode | StepNode


@dataclass(frozen=True)
class Level:
    index: int
    steps: tuple[StepNode, ...]
    """In dependency order: a step may consume another step of the same level."""
    decisions: tuple[DecisionNode, ...]


class DecisionGraph:
    """An acyclic graph of decision and step nodes, checked at construction, plus the constants code
    commits (they are not nodes: nothing decides them)."""

    def __init__(self, nodes: Iterable[Node], constants: Iterable[Constant] = ()) -> None:
        self.constants: tuple[Constant, ...] = tuple(constants)
        self._nodes: dict[str, Node] = {}
        problems: list[RefusalReason] = []
        for node in nodes:
            if node.id in self._nodes:
                problems.append(RefusalReason(node.id, RefusalCode.DUPLICATE_NODE_ID, "two nodes share this id"))
            self._nodes[node.id] = node
        for node in self._nodes.values():
            for dependency in sorted(node.dependencies - self._nodes.keys()):
                problems.append(
                    RefusalReason(node.id, RefusalCode.UNKNOWN_DEPENDENCY, f"depends on missing node {dependency}")
                )
        if problems:
            raise CompileError(problems)
        self._levels = self._level(self._topological_order())

    @property
    def nodes(self) -> Mapping[str, Node]:
        return dict(self._nodes)

    def levels(self) -> tuple[Level, ...]:
        return self._levels

    def _topological_order(self) -> list[str]:
        """Kahn's algorithm, stable in insertion order; a leftover node means a cycle, named in full."""
        waiting = {node_id: set(node.dependencies) for node_id, node in self._nodes.items()}
        order = [node_id for node_id, deps in waiting.items() if not deps]
        for node_id in order:  # the list grows while it is walked
            for other, deps in waiting.items():
                if node_id in deps:
                    deps.discard(node_id)
                    if not deps:
                        order.append(other)
        if len(order) < len(self._nodes):
            # Every leftover node waits on another leftover node, so following them must repeat.
            path = [next(node_id for node_id, deps in waiting.items() if deps)]
            while (step := min(waiting[path[-1]])) not in path:
                path.append(step)
            cycle = path[path.index(step) :]
            joined = " -> ".join([*cycle, cycle[0]])
            raise CompileError([RefusalReason(node_id, RefusalCode.DEPENDENCY_CYCLE, joined) for node_id in cycle])
        return order

    def _level(self, order: list[str]) -> tuple[Level, ...]:
        index: dict[str, int] = {}
        for node_id in order:
            index[node_id] = max(
                (index[d] + isinstance(self._nodes[d], DecisionNode) for d in self._nodes[node_id].dependencies),
                default=0,
            )
        steps = [n for node_id in order if isinstance(n := self._nodes[node_id], StepNode)]
        # Decisions in one level never depend on each other, so they keep insertion order.
        decisions = [n for n in self._nodes.values() if isinstance(n, DecisionNode)]
        return tuple(
            Level(i, tuple(s for s in steps if index[s.id] == i), tuple(d for d in decisions if index[d.id] == i))
            for i in range(max(index.values(), default=-1) + 1)
        )
