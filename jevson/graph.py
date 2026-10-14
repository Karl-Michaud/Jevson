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

from jevson.errors import CompileError, RefusalReason
from jevson.types import DecisionNode, OptionSource, StepNode

Node: TypeAlias = DecisionNode | StepNode


@dataclass(frozen=True)
class Level:
    index: int
    steps: tuple[StepNode, ...]
    """In dependency order: a step may consume another step of the same level."""
    decisions: tuple[DecisionNode, ...]


class DecisionGraph:
    """An acyclic graph of decision and step nodes, checked at construction."""

    def __init__(self, nodes: Iterable[Node]) -> None:
        self._nodes: dict[str, Node] = {}
        problems: list[RefusalReason] = []
        for node in nodes:
            if node.id in self._nodes:
                problems.append(RefusalReason(node.id, "duplicate_node_id", "two nodes share this id"))
            self._nodes[node.id] = node
        for node in self._nodes.values():
            for dependency in sorted(node.dependencies - self._nodes.keys()):
                problems.append(RefusalReason(node.id, "unknown_dependency", f"depends on missing node {dependency}"))
        if problems:
            raise CompileError(problems)
        cycle = self._find_cycle()
        if cycle:
            path = " -> ".join([*cycle, cycle[0]])
            raise CompileError([RefusalReason(node_id, "dependency_cycle", path) for node_id in cycle])
        self._levels = self._level()

    @property
    def nodes(self) -> Mapping[str, Node]:
        return dict(self._nodes)

    def levels(self) -> tuple[Level, ...]:
        return self._levels

    def source_selected_targets(self) -> frozenset[str]:
        """Target pointers of class D (source-selected) decisions, for the assembler (DESIGN §5.6)."""
        return frozenset(
            node.target
            for node in self._nodes.values()
            if isinstance(node, DecisionNode) and node.option_source is OptionSource.CANDIDATE_SPANS
        )

    def _find_cycle(self) -> list[str]:
        """Iterative depth-first search; returns the node ids on one cycle, or [] if acyclic."""
        state: dict[str, int] = {}  # 1 = on the current path, 2 = finished
        for root in self._nodes:
            if root in state:
                continue
            path: list[str] = [root]
            pending = [iter(sorted(self._nodes[root].dependencies))]
            state[root] = 1
            while pending:
                child = next(pending[-1], None)
                if child is None:
                    state[path.pop()] = 2
                    pending.pop()
                elif state.get(child) == 1:
                    return path[path.index(child) :]
                elif child not in state:
                    state[child] = 1
                    path.append(child)
                    pending.append(iter(sorted(self._nodes[child].dependencies)))
        return []

    def _level(self) -> tuple[Level, ...]:
        index: dict[str, int] = {}
        order: list[str] = []  # topological, stable in insertion order (Kahn)
        waiting = {node_id: len(node.dependencies) for node_id, node in self._nodes.items()}
        dependents: dict[str, list[str]] = {node_id: [] for node_id in self._nodes}
        for node_id, node in self._nodes.items():
            for dependency in node.dependencies:
                dependents[dependency].append(node_id)
        ready = [node_id for node_id, count in waiting.items() if count == 0]
        while ready:
            node_id = ready.pop(0)
            order.append(node_id)
            for dependent in dependents[node_id]:
                waiting[dependent] -= 1
                if waiting[dependent] == 0:
                    ready.append(dependent)
        for node_id in order:
            index[node_id] = max(
                (index[d] + isinstance(self._nodes[d], DecisionNode) for d in self._nodes[node_id].dependencies),
                default=0,
            )
        steps = [n for node_id in order if isinstance(n := self._nodes[node_id], StepNode)]
        # Decisions in one level never depend on each other, so they keep insertion order.
        decisions = [n for n in self._nodes.values() if isinstance(n, DecisionNode)]
        return tuple(
            Level(
                i,
                tuple(s for s in steps if index[s.id] == i),
                tuple(d for d in decisions if index[d.id] == i),
            )
            for i in range(max(index.values(), default=-1) + 1)
        )
