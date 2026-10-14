from __future__ import annotations

import pytest

from jevson.errors import CompileError
from jevson.graph import DecisionGraph
from jevson.types import NONE_OF_THESE, DecisionKind, DecisionNode, Option, OptionSource, StepKind, StepNode


def predicate(node_id: str, *deps: str) -> DecisionNode:
    return DecisionNode(
        node_id, DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, f"/{node_id}", (), frozenset(deps)
    )


def candidate_choice(node_id: str, *deps: str) -> DecisionNode:
    opts = (Option("c0", "a"), Option(NONE_OF_THESE, "none"))
    return DecisionNode(
        node_id, DecisionKind.CHOICE, "q", OptionSource.CANDIDATE_SPANS, f"/{node_id}", opts, frozenset(deps)
    )


def step(node_id: str, *deps: str, kind: StepKind = StepKind.EXTRACT) -> StepNode:
    return StepNode(node_id, kind, f"/{node_id}", frozenset(deps))


def shape(graph: DecisionGraph) -> list[tuple[list[str], list[str]]]:
    return [([s.id for s in level.steps], [d.id for d in level.decisions]) for level in graph.levels()]


def test_diamond_of_decisions_levels_correctly() -> None:
    #   a -> b, a -> c, (b, c) -> d
    graph = DecisionGraph([predicate("d", "b", "c"), predicate("b", "a"), predicate("c", "a"), predicate("a")])
    assert shape(graph) == [([], ["a"]), ([], ["b", "c"]), ([], ["d"])]


def test_decisions_and_steps_level_around_each_other() -> None:
    # Independent decisions and extract-dependent decisions share one level (one request);
    # a generate step waiting on a decision opens a later level with its criterion.
    graph = DecisionGraph(
        [
            step("vendor_extract"),
            candidate_choice("vendor", "vendor_extract"),
            predicate("is_paid"),
            predicate("kind"),
            step("summary_generate", "kind", kind=StepKind.GENERATE),
            predicate("summary_criterion", "summary_generate"),
        ]
    )
    assert shape(graph) == [
        (["vendor_extract"], ["vendor", "is_paid", "kind"]),
        (["summary_generate"], ["summary_criterion"]),
    ]


def test_a_diamond_through_steps_keeps_steps_before_their_consumers() -> None:
    # s1 -> (s2, x) ; (s2, x) -> y ; s2 is a step in the same level as s1
    graph = DecisionGraph([predicate("y", "s2", "x"), step("s2", "s1"), predicate("x", "s1"), step("s1")])
    assert shape(graph) == [(["s1", "s2"], ["x"]), ([], ["y"])]


def test_empty_graph_has_no_levels() -> None:
    assert DecisionGraph([]).levels() == ()


@pytest.mark.parametrize(
    ("nodes", "cycle"),
    [
        ([predicate("a", "a")], ["a"]),
        ([predicate("a", "b"), predicate("b", "a")], ["a", "b"]),
        ([predicate("x"), predicate("a", "c", "x"), step("b", "a"), predicate("c", "b")], ["a", "c", "b"]),
    ],
)
def test_a_cycle_is_rejected_at_construction_naming_its_nodes(nodes: list[DecisionNode], cycle: list[str]) -> None:
    with pytest.raises(CompileError) as raised:
        DecisionGraph(nodes)
    reasons = raised.value.reasons
    assert {r.reason for r in reasons} == {"dependency_cycle"}
    assert [r.pointer for r in reasons] == cycle
    assert " -> ".join([*cycle, cycle[0]]) in str(raised.value)


def test_duplicate_ids_and_unknown_dependencies_are_rejected_together() -> None:
    with pytest.raises(CompileError) as raised:
        DecisionGraph([predicate("a"), predicate("a"), predicate("b", "missing")])
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [
        ("a", "duplicate_node_id"),
        ("b", "unknown_dependency"),
    ]


def test_source_selected_targets_are_the_candidate_choices() -> None:
    graph = DecisionGraph([step("e"), candidate_choice("v", "e"), predicate("p")])
    assert graph.source_selected_targets() == frozenset({"/v"})
    assert set(graph.nodes) == {"e", "v", "p"}
