"""PLAN Phase 1: the fake backend resolves a hand-built graph and the assembler produces a valid object.

There is no executor yet (Phase 3), so `run` below plays its part: steps run from a table, each
level's decisions go to the backend as one request of opaque-named questions, and each answer is
read with `interpret`.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from pydantic import BaseModel

from jevson import FakeBackend, Result
from jevson.assemble.assembler import Abstained, Committed, Outcome, assemble
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.types import (
    NONE_OF_THESE,
    Candidate,
    DecidedBy,
    Decision,
    DecisionKind,
    DecisionNode,
    DeclaredOption,
    JSONValue,
    Option,
    OptionSource,
    Question,
    Span,
    StepKind,
    StepNode,
    Unresolved,
    UnresolvedReason,
)

SOURCE = "Invoice from Acme Corp to Globex. Paid in full. Software licences."


class Invoice(BaseModel):
    vendor: str
    paid: bool
    category: Literal["software", "hardware"]
    rating: int


ENUM_VALUES: dict[str, JSONValue] = {"o0": "software", "o1": "hardware"}
CANDIDATES = {
    "/vendor#extract": [
        Candidate("c0", "Acme Corp", Span("doc", 13, 22)),
        Candidate("c1", "Globex", Span("doc", 26, 32)),
    ]
}


def build_graph() -> DecisionGraph:
    vendor_options = (*(Option(c.id, c.text) for c in CANDIDATES["/vendor#extract"]), Option(NONE_OF_THESE, "none"))
    return DecisionGraph(
        [
            StepNode("/vendor#extract", StepKind.EXTRACT, "/vendor"),
            DecisionNode(
                "/vendor#choice",
                DecisionKind.CHOICE,
                "Which is the complete vendor?",
                OptionSource.CANDIDATE_SPANS,
                "/vendor",
                vendor_options,
                frozenset({"/vendor#extract"}),
            ),
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


def value_of(node: DecisionNode, selected: str | bool) -> tuple[JSONValue, Span | DeclaredOption | None]:
    if node.option_source is OptionSource.CANDIDATE_SPANS:
        candidate = next(c for cs in CANDIDATES.values() for c in cs if c.id == selected)
        return candidate.text, candidate.span
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
            elif reading.status == "abstained":
                spans = tuple(c.span for c in CANDIDATES["/vendor#extract"])
                outcomes.append(Abstained(node.target, spans, reading.abstain_probability))
            else:
                assert reading.reason is not None
                outcomes.append(Unresolved(node.target, reading.reason))
    return assemble(schema, outcomes, source_selected=graph.source_selected_targets(), decisions=decisions)


def test_the_fake_backend_resolves_a_hand_built_graph_into_a_valid_object() -> None:
    backend = FakeBackend(
        {
            "q0": FakeBackend.select("c0", 0.90),
            "q1": FakeBackend.predicate(0.97),
            "q2": FakeBackend.select("o0", 0.88),
            "q3": FakeBackend.distribution({"l1": 0.0, "l2": 0.05, "l3": 0.1, "l4": 0.7, "l5": 0.15}),
        }
    )
    result = run(build_graph(), backend)
    assert result.value == {"vendor": "Acme Corp", "paid": True, "category": "software", "rating": 4}
    assert (result.complete, result.satisfies_schema) == (True, True)
    assert Invoice.model_validate(result.value).vendor == "Acme Corp"
    assert SOURCE[13:22] == "Acme Corp"
    assert result.provenance["/vendor"] == Span("doc", 13, 22)
    assert result.provenance["/category"] == DeclaredOption("o0")
    assert set(result.decisions) == {"/vendor#choice@0", "/paid#predicate@0", "/category#choice@0", "/rating#score@0"}
    assert result.decisions["/vendor#choice@0"].distribution_hundredths == {"c0": 90, "c1": 5, NONE_OF_THESE: 5}
    # Two levels, so two requests: the first holds the three independent decisions.
    assert [len(call.questions) for call in backend.calls] == [3, 1]


def test_a_refused_vendor_is_unresolved_refused_not_absent() -> None:
    backend = FakeBackend({"q0": FakeBackend.refuse()}, default=FakeBackend.tie())
    result = run(build_graph(), backend)
    assert ("/vendor", "refused") in {(u.pointer, u.reason) for u in result.unresolved}
    assert result.absent == ()
    assert "vendor" not in result.value
    assert result.complete is False


def test_an_abstained_required_vendor_is_unresolved_abstained() -> None:
    backend = FakeBackend({"q0": FakeBackend.abstain(0.9)}, default=FakeBackend.predicate(0.9))
    graph = DecisionGraph([n for n in build_graph().nodes.values() if n.id.startswith(("/vendor", "/paid"))])
    result = run(graph, backend)
    assert result.unresolved == (
        Unresolved("/vendor", UnresolvedReason.ABSTAINED, tuple(c.span for c in CANDIDATES["/vendor#extract"]), 90),
    )
    assert result.value == {"paid": True}
