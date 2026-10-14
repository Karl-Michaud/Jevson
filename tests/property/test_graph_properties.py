"""PLAN §4.3: levelling preserves every node exactly once and respects every edge."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from jevson.errors import CompileError
from jevson.graph import DecisionGraph, Node
from jevson.types import DecisionKind, DecisionNode, OptionSource, StepKind, StepNode

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=300)


@st.composite
def dags(draw: st.DrawFn) -> list[Node]:
    """A random DAG: node i may depend only on nodes before it; inserted in a random order."""
    size = draw(st.integers(0, 25))
    nodes: list[Node] = []
    for i in range(size):
        deps = frozenset(f"n{j}" for j in draw(st.sets(st.integers(0, i - 1), max_size=4))) if i else frozenset()
        if draw(st.booleans()):
            nodes.append(DecisionNode(f"n{i}", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, f"/n{i}", (), deps))
        else:
            kind = draw(st.sampled_from(StepKind))
            nodes.append(StepNode(f"n{i}", kind, f"/n{i}", deps))
    return draw(st.permutations(nodes))


@DETERMINISTIC
@given(dags())
def test_levels_preserve_every_node_exactly_once_and_respect_every_edge(nodes: list[Node]) -> None:
    levels = DecisionGraph(nodes).levels()
    placed = [n.id for level in levels for n in (*level.steps, *level.decisions)]
    assert sorted(placed) == sorted(n.id for n in nodes)
    assert len(placed) == len(set(placed))

    where = {n.id: (level.index, 0, i) for level in levels for i, n in enumerate(level.steps)}
    where |= {n.id: (level.index, 1, 0) for level in levels for n in level.decisions}
    kinds = {n.id: n for n in nodes}
    for node in nodes:
        for dep in node.dependencies:
            if isinstance(kinds[dep], DecisionNode):
                assert where[dep][0] < where[node.id][0], f"{node.id} must follow decision {dep} by a level"
            else:
                assert where[dep] < where[node.id], f"{node.id} must run after step {dep}"
    assert all(level.decisions or level.steps for level in levels)


@DETERMINISTIC
@given(dags(), st.data())
def test_closing_any_path_into_a_cycle_is_rejected_with_a_real_cycle(nodes: list[Node], data: st.DataObject) -> None:
    edges = [(node.id, dep) for node in nodes for dep in node.dependencies]
    if not edges:
        return
    node_id, dep = data.draw(st.sampled_from(sorted(edges)))
    by_id = {n.id: n for n in nodes}
    looped = by_id[dep]
    by_id[dep] = (
        DecisionNode(
            looped.id,
            looped.kind,
            looped.question,
            looped.option_source,
            looped.target,
            (),
            looped.dependencies | {node_id},
        )
        if isinstance(looped, DecisionNode)
        else StepNode(looped.id, looped.kind, looped.target, looped.dependencies | {node_id})
    )
    with pytest.raises(CompileError) as raised:
        DecisionGraph(by_id.values())
    cycle = [r.pointer for r in raised.value.reasons]
    assert {r.reason for r in raised.value.reasons} == {"dependency_cycle"}
    for current, following in zip(cycle, [*cycle[1:], cycle[0]], strict=True):
        assert following in by_id[current].dependencies
