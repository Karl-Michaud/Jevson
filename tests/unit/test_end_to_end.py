"""PLAN Phase 1: the fake backend resolves a hand-built graph and the assembler produces a valid object.

There is no executor yet (Phase 3), so `run` below plays its part: each level's decisions go to the
backend as one request of opaque-named questions, and each answer is read with `interpret`.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

from jevson import FakeBackend, Jevson, JevsonConfig, Result
from jevson.assemble.assembler import Committed, Outcome, assemble
from jevson.backends.caching import cache_key
from jevson.graph import DecisionGraph
from jevson.probabilities import interpret
from jevson.types import (
    Answer,
    DecidedBy,
    Decision,
    DecisionKind,
    DecisionNode,
    DeclaredOption,
    JSONValue,
    Option,
    OptionSource,
    PredicateAnswer,
    Question,
    Unresolved,
    UnresolvedReason,
)
from tests.adversarial.hostile_llm import ScriptedLLM
from tests.unit.recording_backend import Recorder

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


# --- requests at the defaults do not move (ASTERION-48; DESIGN §5.2, §6.3) ---------------------------

GOLDEN = Path(__file__).resolve().parents[1] / "fixtures" / "defaults" / "cd6b40a.json"
"""Recorded at the branch base, cd6b40a, by `defaults_record()` run on an archive of that commit with
this file added (plan §11 D1): `python -c "from tests.unit.test_end_to_end import defaults_record;
print(defaults_record())"`."""

GENERATE = {"criteria": ["The draft mentions the refund amount stated in the source."]}
NOTE = {"type": "string", "x-jevson": {"generate": GENERATE}}
FLAG = {"type": "boolean", "description": "it is ok"}
DEFAULT_SCHEMAS: dict[str, dict[str, Any]] = {
    "generative": {
        "type": "object",
        "required": ["companion_summary", "summary"],
        "properties": {
            "summary": {"type": "string", "x-jevson": {"generate": GENERATE}},
            "companion_summary": {
                "type": "string",
                "x-jevson": {"generate": {"criteria": ["The draft states the same delivery date as the source."]}},
            },
        },
    },
    "generative_and_enum": {
        "type": "object",
        "required": ["mood", "summary"],
        "properties": {
            "mood": {"enum": ["happy", "angry"], "description": "the customer's mood"},
            "summary": {"type": "string", "x-jevson": {"generate": GENERATE}},
        },
    },
    "union_with_a_generative_branch": {
        "type": "object",
        "required": ["reply"],
        "properties": {
            "reply": {
                "anyOf": [
                    {"title": "note", "type": "object", "properties": {"note": NOTE}},
                    {"title": "flag", "type": "object", "properties": {"ok": FLAG}},
                ]
            }
        },
    },
}  # fmt: skip
DEFAULT_SOURCE = "From: A\nRefund $12.50, delivery 2026-10-09."


def default_answer(state: str, question: Question) -> Answer:
    """Passes every predicate and picks the first option of anything else."""
    del state
    if question.kind is DecisionKind.PREDICATE:
        return PredicateAnswer(question.name, 0.9)
    return FakeBackend.select(question.options[0].id, 0.9)(question)


def default_run(schema: dict[str, Any]) -> tuple[Result, list[str]]:
    """A fixed run at `JevsonConfig()`: its `Result` and the cache key of every request it sent."""
    recorder = Recorder(default_answer)
    llm = ScriptedLLM(["Refunds take 5 days. Note: this summary includes the refund amount stated in the source."])
    result = asyncio.run(Jevson(recorder, llm=llm, config=JevsonConfig()).aresolve(schema, DEFAULT_SOURCE))
    model = JevsonConfig().model
    return result, [cache_key(state, questions, model) for state, questions in recorder.calls]


def comparable(result: Result) -> dict[str, Any]:
    """The `Result` as JSON data, without its wall-clock timings."""
    data: dict[str, Any] = json.loads(json.dumps(dataclasses.asdict(result), sort_keys=True))
    del data["cost"]["wall_clock_by_component"]
    return data


def defaults_record() -> str:
    record: dict[str, Any] = {"requests": {}, "result": None}
    for name, schema in DEFAULT_SCHEMAS.items():
        result, keys = default_run(schema)
        record["requests"][name] = keys
        if name == "generative_and_enum":
            record["result"] = comparable(result)
    return json.dumps(record, indent=1, sort_keys=True, ensure_ascii=False) + "\n"


def test_default_requests_unchanged() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for name, schema in DEFAULT_SCHEMAS.items():
        assert default_run(schema)[1] == golden["requests"][name], name
    state = '{"source":"s","drafts":{"/summary#generate":"d"}}'
    hand_built = Question("c0", DecisionKind.PREDICATE, "Does `drafts./summary#generate` meet this criterion: X?", ())
    assert cache_key(state, [hand_built], "gpt-6-luna")[:12] == "a120c9b00ef8"  # design §6.1 test 1


def test_default_result_golden() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["result"]
    now = comparable(default_run(DEFAULT_SCHEMAS["generative_and_enum"])[0])
    added = {key: now["versions"].pop(key) for key in set(now["versions"]) - set(golden["versions"])}
    assert added == {"criterion_template": "1.1.0", "draft_screen": "false"}
    assert now == golden
