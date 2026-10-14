"""PLAN Phase 1: the fake backend resolves a hand-built graph and the assembler produces a valid object.

There is no executor yet (Phase 3), so `run` below plays its part: each level's decisions go to the
backend as one request of opaque-named questions, and each answer is read with `interpret`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel

from jevson import FakeBackend, Result
from jevson.assemble.assembler import Committed, Outcome, assemble
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.types import (
    DecidedBy,
    Decision,
    DecisionKind,
    DecisionNode,
    DeclaredOption,
    JSONValue,
    Option,
    OptionSource,
    Question,
    Unresolved,
    UnresolvedReason,
)

SOURCE = "Invoice from Acme Corp. Paid in full. Software licences."


class Invoice(BaseModel):
    paid: bool
    category: Literal["software", "hardware"]
    rating: int
    note: str = "none"


ENUM_VALUES: dict[str, JSONValue] = {"o0": "software", "o1": "hardware"}


def build_graph() -> DecisionGraph:
    return DecisionGraph(
        [
            DecisionNode("/paid#predicate", DecisionKind.PREDICATE, "Is it paid?", OptionSource.PREDICATE, "/paid"),
            DecisionNode(
                "/category#choice",
                DecisionKind.CHOICE,
                "Which category?",
                OptionSource.SCHEMA_ENUM,
                "/category",
                (Option("o0", "software"), Option("o1", "hardware")),
            ),
            # A second level: the rating depends on the category decision.
            DecisionNode(
                "/rating#score",
                DecisionKind.SCORE,
                "How clear is it?",
                OptionSource.SCHEMA_RUBRIC,
                "/rating",
                tuple(Option(f"l{i}", str(i)) for i in range(1, 6)),
                frozenset({"/category#choice"}),
            ),
        ]
    )


def value_of(node: DecisionNode, selected: str | bool) -> tuple[JSONValue, DeclaredOption | None]:
    if node.option_source is OptionSource.SCHEMA_ENUM:
        return ENUM_VALUES[str(selected)], DeclaredOption(str(selected))
    if node.option_source is OptionSource.SCHEMA_RUBRIC:
        return int(str(selected)[1:]), DeclaredOption(str(selected))
    return selected, None


def run(graph: DecisionGraph, backend: FakeBackend) -> Result:
    schema: dict[str, Any] = Invoice.model_json_schema(mode="validation")
    outcomes: list[Outcome] = []
    decisions: dict[str, Decision] = {}
    asked = 0
    for level in graph.levels():
        names = {node.id: f"q{asked + i}" for i, node in enumerate(level.decisions)}
        asked += len(level.decisions)
        questions = [Question(names[n.id], n.kind, n.question, n.options) for n in level.decisions]
        response = asyncio.run(backend.ask(SOURCE, questions, "gpt-6-luna"))
        for node, answer in zip(level.decisions, response.answers, strict=True):
            reading = interpret(node, answer, tie_margin=10)
            decisions[f"{node.id}@0"] = reading.decision
            if reading.status == "committed":
                assert reading.decision.selected is not None
                value, provenance = value_of(node, reading.decision.selected)
                outcomes.append(Committed(node.target, value, DecidedBy.DECISION, provenance))
            else:
                assert reading.reason is not None
                outcomes.append(Unresolved(node.target, reading.reason))
    return assemble(schema, outcomes, decisions=decisions, versions={"question_templates": "0"})


def test_the_fake_backend_resolves_a_hand_built_graph_into_a_valid_object() -> None:
    backend = FakeBackend(
        {
            "q0": FakeBackend.predicate(0.97),
            "q1": FakeBackend.select("o0", 0.88),
            "q2": FakeBackend.distribution({"l1": 0.0, "l2": 0.05, "l3": 0.1, "l4": 0.7, "l5": 0.15}),
        }
    )
    result = run(build_graph(), backend)
    assert result.value == {"paid": True, "category": "software", "rating": 4}
    assert (result.complete, result.satisfies_schema) == (True, True)
    assert Invoice.model_validate(result.value).note == "none"
    assert result.provenance == {"/category": DeclaredOption("o0"), "/rating": DeclaredOption("l4")}
    assert set(result.decisions) == {"/paid#predicate@0", "/category#choice@0", "/rating#score@0"}
    assert result.decisions["/category#choice@0"].distribution_hundredths == {"o0": 88, "o1": 12}
    assert result.absent == ()
    # Two levels, so two requests: the first holds the two independent decisions.
    assert [len(call.questions) for call in backend.calls] == [2, 1]


def test_a_refusal_is_unresolved_refused_never_absent_or_an_option() -> None:
    backend = FakeBackend({"q1": FakeBackend.refuse()}, default=FakeBackend.predicate(0.9))
    graph = DecisionGraph([n for n in build_graph().nodes.values() if n.id != "/rating#score"])
    result = run(graph, backend)
    assert result.unresolved == (Unresolved("/category", UnresolvedReason.REFUSED),)
    assert result.decisions["/category#choice@0"].selected is None
    assert result.value == {"paid": True}
    assert result.absent == ()
    assert result.complete is False
