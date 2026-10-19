"""PLAN Phase 7: multi-label enum arrays, against the fake backend. Each exit criterion has a test
named after it; the rest pin the edges (unions, known=, budget, the template)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

import pytest
from pydantic import BaseModel, Field

from jevson import (
    CompileError,
    DecidedBy,
    FakeBackend,
    Jevson,
    JevsonConfig,
    Overflow,
    PreflightError,
    RefusalCode,
    Result,
    SchemaViolation,
    Unresolved,
    UnresolvedReason,
    compile_schema,
)
from jevson.assemble.assembler import Committed, Outcome
from jevson.assemble.cardinality import fold
from jevson.compile.questions import QUESTION_TEMPLATE_VERSION, member_question
from jevson.types import Answer, Decision, DecisionKind, DecisionNode, OptionSource, PredicateAnswer, Question

Script = Callable[[Question], Answer]


class Ticket(BaseModel):
    topics: list[Literal["billing", "technical", "account"]] = Field(description="topics of the ticket")


def resolve(schema: object, backend: FakeBackend, *, config: JevsonConfig | None = None, **kwargs: Any) -> Result:
    return asyncio.run(Jevson(backend, config=config or JevsonConfig()).aresolve(schema, "A ticket.", **kwargs))


def by_value(answers: Mapping[str, Script], default: Script | None = None) -> FakeBackend:
    """A fake that answers each membership question by the value it names."""

    def answer(question: Question) -> Answer:
        for value, script in answers.items():
            if f'"{value}"' in question.instructions:
                return script(question)
        if default is None:
            raise KeyError(question.instructions)
        return default(question)

    return FakeBackend(default=answer)


def members(schema: object) -> list[DecisionNode]:
    return [n for n in compile_schema(schema).nodes.values() if isinstance(n, DecisionNode) and n.member is not None]


def refusals(schema: object) -> list[tuple[str, str]]:
    with pytest.raises(CompileError) as caught:
        compile_schema(schema)
    return [(r.pointer, r.reason) for r in caught.value.reasons]


# --- exit criteria ---------------------------------------------------------------------------


def test_enum_arrays_compile_to_three_membership_predicates_in_one_level() -> None:
    graph = compile_schema(Ticket)
    (level,) = graph.levels()
    assert [n.id for n in level.decisions] == ["/topics#member:c0", "/topics#member:c1", "/topics#member:c2"]
    assert {n.kind for n in level.decisions} == {DecisionKind.PREDICATE}
    assert {n.option_source for n in level.decisions} == {OptionSource.PREDICATE}
    assert {n.target for n in level.decisions} == {"/topics"}
    assert [n.member for n in level.decisions] == ["billing", "technical", "account"]
    assert level.decisions[1].question == 'According to the source, is "technical" one of the topics of the ticket?'
    assert not [n.id for n in level.decisions if "[" in n.id or "[" in n.question]  # R13


def test_enum_arrays_emit_accepted_values_in_declared_order_whatever_the_probabilities_order() -> None:
    backend = by_value(
        {
            "account": FakeBackend.predicate(0.99),
            "billing": FakeBackend.predicate(0.7),
            "technical": FakeBackend.predicate(0.1),
        }
    )
    result = resolve(Ticket, backend)
    assert result.value == {"topics": ["billing", "account"]}
    assert len(backend.calls) == 1
    assert len(backend.calls[0].questions) == 3
    assert result.complete
    assert result.satisfies_schema
    assert result.decided_by == {"/topics": DecidedBy.DECISION}
    assert result.decisions["/topics#member:c2@0"].target_pointer == "/topics"
    assert result.overflow == ()


def test_max_items_2_with_three_accepted_values_keeps_the_first_two_and_records_the_third_in_overflow() -> None:
    class Capped(BaseModel):
        topics: Annotated[list[Literal["billing", "technical", "account"]], Field(max_length=2)]

    backend = by_value(
        {
            "billing": FakeBackend.predicate(0.6),
            "technical": FakeBackend.predicate(0.95),
            "account": FakeBackend.predicate(0.9),
        }
    )
    result = resolve(Capped, backend)
    assert result.value == {"topics": ["billing", "technical"]}
    assert result.overflow == (Overflow("/topics", (), (90,), ("account",)),)
    assert result.satisfies_schema
    assert result.complete


def test_array_holes_a_tied_value_is_one_unresolved_tie_naming_it_and_the_others_are_emitted() -> None:
    backend = by_value(
        {"billing": FakeBackend.predicate(0.9), "technical": FakeBackend.tie(), "account": FakeBackend.predicate(0.8)}
    )
    result = resolve(Ticket, backend)
    assert result.value == {"topics": ["billing", "account"]}
    assert result.unresolved == (Unresolved("/topics", UnresolvedReason.TIE, detail="membership of 'technical'"),)
    assert not result.complete


def test_array_holes_a_refused_membership_is_one_unresolved_refused_the_same_way() -> None:
    backend = by_value({"account": FakeBackend.refuse()}, default=FakeBackend.predicate(0.2))
    result = resolve(Ticket, backend)
    assert result.value == {"topics": []}
    assert result.unresolved == (Unresolved("/topics", UnresolvedReason.REFUSED, detail="membership of 'account'"),)


def test_unique_items_holds_by_construction() -> None:
    class Unique(BaseModel):
        topics: Annotated[
            list[Literal["billing", "technical", "account"]], Field(json_schema_extra={"uniqueItems": True})
        ]

    result = resolve(Unique, FakeBackend(default=FakeBackend.predicate(0.9)))
    assert result.value == {"topics": ["billing", "technical", "account"]}
    assert result.satisfies_schema


def test_min_items_the_accepted_values_do_not_meet_is_a_violation_not_a_padded_array() -> None:
    class AtLeastTwo(BaseModel):
        topics: Annotated[list[Literal["billing", "technical", "account"]], Field(min_length=2)]

    backend = by_value({"technical": FakeBackend.predicate(0.9)}, default=FakeBackend.predicate(0.1))
    result = resolve(AtLeastTwo, backend)
    assert result.value == {"topics": ["technical"]}
    assert not result.satisfies_schema
    assert [(v.pointer, v.keyword) for v in result.violations if v.keyword != "model_validate"] == [
        ("/topics", "minItems")
    ]


def test_an_array_declaring_order_semantic_refuses() -> None:
    class Semantic(BaseModel):
        topics: list[Literal["a", "b"]] = Field(json_schema_extra={"x-jevson": {"order": "semantic"}})

    assert refusals(Semantic) == [("/topics", RefusalCode.SEMANTIC_ORDER)]


def test_an_array_declaring_order_source_refuses_because_its_order_is_the_declared_enum_order() -> None:
    class Source(BaseModel):
        topics: list[Literal["a", "b"]] = Field(json_schema_extra={"x-jevson": {"order": "source"}})

    assert refusals(Source) == [("/topics", RefusalCode.SOURCE_SELECTION_DROPPED)]


def test_an_array_of_unbounded_items_refuses_with_source_selection_dropped_if_it_declares_a_source() -> None:
    class Unbounded(BaseModel):
        names: list[str]
        sourced: list[str] = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "llm"}}})

    assert sorted(refusals(Unbounded)) == [
        ("/names", RefusalCode.UNBOUNDED_FIELD),
        ("/sourced", RefusalCode.SOURCE_SELECTION_DROPPED),
    ]
    with pytest.raises(CompileError) as caught:
        compile_schema(
            {"type": "object", "properties": {"n": {"type": "array", "items": {"type": "string"}}}}, frozenset(), "llm"
        )
    assert [(r.pointer, r.reason) for r in caught.value.reasons] == [("/n", RefusalCode.SOURCE_SELECTION_DROPPED)]


def test_an_array_of_objects_still_refuses_with_its_own_named_reason() -> None:
    class Line(BaseModel):
        kind: Literal["a", "b"]

    class Lines(BaseModel):
        lines: list[Line]

    assert refusals(Lines) == [("/lines", RefusalCode.ARRAY_OF_OBJECTS)]


def test_output_is_deterministic_across_runs_with_the_fake_backend() -> None:
    def run() -> Result:
        backend = by_value(
            {
                "billing": FakeBackend.predicate(0.8),
                "technical": FakeBackend.tie(),
                "account": FakeBackend.predicate(0.7),
            }
        )
        result = resolve(Ticket, backend, config=JevsonConfig())
        return result

    first, second = run(), run()
    assert first.value == second.value
    assert first.unresolved == second.unresolved
    assert first.overflow == second.overflow
    assert first.decisions == second.decisions


# --- edges -----------------------------------------------------------------------------------


def test_fake_backend_predicate_scripts_membership_questions_by_name() -> None:
    backend = FakeBackend(
        {"q0": FakeBackend.predicate(0.1), "q1": FakeBackend.predicate(0.9), "q2": FakeBackend.predicate(0.9)}
    )
    assert resolve(Ticket, backend).value == {"topics": ["technical", "account"]}
    assert all(isinstance(a, Question) for a in backend.calls[0].questions)
    assert isinstance(FakeBackend.predicate(0.5)(backend.calls[0].questions[0]), PredicateAnswer)


def test_integer_enum_arrays_keep_their_integer_values() -> None:
    class Ints(BaseModel):
        levels: list[Literal[1, 2, 3]]

    result = resolve(Ints, by_value({"2": FakeBackend.predicate(0.9)}, default=FakeBackend.predicate(0.1)))
    assert result.value == {"levels": [2]}


def test_an_array_with_no_decided_value_is_not_emitted_only_its_holes() -> None:
    result = resolve(Ticket, FakeBackend(default=FakeBackend.tie()))
    assert result.value == {}
    assert [u.detail for u in result.unresolved] == [
        "membership of 'billing'",
        "membership of 'technical'",
        "membership of 'account'",
    ]


def test_a_required_array_with_a_hole_raises_when_raise_on_unresolved_required() -> None:
    backend = by_value({"billing": FakeBackend.tie()}, default=FakeBackend.predicate(0.9))
    with pytest.raises(SchemaViolation) as caught:
        resolve(Ticket, backend, config=JevsonConfig(raise_on_unresolved_required=True))
    assert caught.value.result.value == {"topics": ["technical", "account"]}


def test_known_array_replaces_its_membership_questions() -> None:
    backend = FakeBackend()
    result = resolve(Ticket, backend, known={"/topics": ["account"]})
    assert result.value == {"topics": ["account"]}
    assert backend.calls == []
    assert result.decided_by == {"/topics": DecidedBy.CALLER}
    for bad in (["refund"], ["account", "account"], "account", [1]):
        with pytest.raises(PreflightError):
            resolve(Ticket, FakeBackend(), known={"/topics": bad})


def test_oversized_enum_arrays_and_non_scalar_values_refuse() -> None:
    many = {"type": "array", "items": {"enum": [f"v{i}" for i in range(256)]}}
    mixed = {"type": "array", "items": {"enum": ["a", 1.5]}}
    twice = {"type": "array", "items": {"enum": ["a", "b", "a"]}}
    properties = {"many": many, "mixed": mixed, "twice": twice}
    schema = {"type": "object", "properties": properties, "required": list(properties)}
    assert refusals(schema) == [
        ("/many", RefusalCode.ENUM_SIZE),
        ("/mixed", RefusalCode.ENUM_VALUE_TYPE),
        ("/twice", RefusalCode.INDISTINGUISHABLE_OPTIONS),
    ]


class NullableTopics(BaseModel):
    topics: list[Literal["refund", "account"] | None] = Field(description="the topics the ticket raises")


@pytest.mark.parametrize(
    "items",
    [
        {"enum": ["refund", "account", None]},
        {"anyOf": [{"enum": ["refund", "account"]}, {"type": "null"}]},
    ],
)
def test_a_null_in_a_multi_label_items_enum_refuses_loudly(items: dict[str, object]) -> None:
    # R14: a membership predicate cannot ask whether "null" is one of the values; never strip it silently.
    schema = {"type": "object", "properties": {"topics": {"type": "array", "items": items}}, "required": ["topics"]}
    assert refusals(schema) == [("/topics", RefusalCode.ENUM_VALUE_TYPE)]
    assert refusals(NullableTopics) == [("/topics", RefusalCode.ENUM_VALUE_TYPE)]


class Email(BaseModel):
    """Contacted by email."""

    kind: Literal["email"]
    topics: list[Literal["billing", "account"]] = Field(description="topics raised")


class Phone(BaseModel):
    """Contacted by phone."""

    kind: Literal["phone"]
    urgent: bool = Field(description="the call was urgent")


class Contact(BaseModel):
    channel: Email | Phone = Field(description="contact channel")


def test_arrays_inside_union_branches_are_qualified_and_run_only_when_selected() -> None:
    nodes = members(Contact)
    assert [n.id for n in nodes] == ["/channel|c0/topics#member:c0", "/channel|c0/topics#member:c1"]
    assert {n.target for n in nodes} == {"/channel/topics"}

    def answer(question: Question) -> Answer:
        if question.kind is DecisionKind.CHOICE:
            return FakeBackend.select("c0")(question)
        return FakeBackend.predicate(0.9 if '"account"' in question.instructions else 0.1)(question)

    result = resolve(Contact, FakeBackend(default=answer))
    assert result.value == {"channel": {"kind": "email", "topics": ["account"]}}
    assert result.complete


def test_an_unresolved_discriminator_leaves_the_array_one_dependency_unresolved() -> None:
    result = resolve(Contact, FakeBackend(default=FakeBackend.tie()))
    assert Unresolved("/channel/topics", UnresolvedReason.DEPENDENCY_UNRESOLVED) in result.unresolved
    assert [u for u in result.unresolved if u.pointer == "/channel/topics"] == [
        Unresolved("/channel/topics", UnresolvedReason.DEPENDENCY_UNRESOLVED)
    ]


def test_an_enum_array_that_is_itself_a_union_branch_keeps_the_union_hole_alone() -> None:
    branch = {"type": "array", "items": {"enum": ["a", "b"]}, "description": "labels"}
    schema = {
        "type": "object",
        "properties": {"x": {"anyOf": [branch, {"type": "boolean", "description": "the item is flagged"}]}},
        "required": ["x"],
    }
    result = resolve(schema, FakeBackend(default=FakeBackend.tie()))
    assert [u.pointer for u in result.unresolved] == ["/x"]

    def pick_array(question: Question) -> Answer:
        if question.kind is DecisionKind.CHOICE:
            return FakeBackend.select("c0")(question)
        return FakeBackend.predicate(0.9)(question)

    assert resolve(schema, FakeBackend(default=pick_array)).value == {"x": ["a", "b"]}


def test_two_enum_arrays_with_one_label_are_scoped_by_their_ancestors() -> None:
    class Part(BaseModel):
        tags: list[Literal["x", "y"]]

    class Two(BaseModel):
        billing: Part
        shipping: Part

    questions = [n.question for n in members(Two)]
    assert questions[0] == 'According to the source, is "x" one of the billing tags?'
    assert questions[2] == 'According to the source, is "x" one of the shipping tags?'


def test_the_membership_template_is_recorded_under_the_current_version() -> None:
    assert QUESTION_TEMPLATE_VERSION == "1.1.2"
    assert member_question(3, "levels") == 'According to the source, is "3" one of the levels?'


def test_a_membership_node_must_be_a_predicate() -> None:
    with pytest.raises(ValueError, match="membership node is a predicate"):
        DecisionNode("/t#member:c0", DecisionKind.CHOICE, "q", OptionSource.SCHEMA_ENUM, "/t", member="a")


def test_fold_leaves_other_outcomes_and_reads_overflow_probabilities_from_the_decisions() -> None:
    node = DecisionNode(
        "/t#member:c0", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/t", member="a", max_items=0
    )
    outcomes: dict[str, Outcome] = {
        "/o": Committed("/o", 1, DecidedBy.DECISION),
        node.id: Committed("/t", True, DecidedBy.DECISION),
    }

    decisions = {f"{node.id}@0": Decision(DecisionKind.PREDICATE, True, {"true": 80, "false": 20}, None, "/t")}
    folded, holes, overflow = fold([node], outcomes, decisions)
    assert folded == [Committed("/o", 1, DecidedBy.DECISION), Committed("/t", [], DecidedBy.DECISION)]
    assert holes == ()
    assert overflow == (Overflow("/t", (), (80,), ("a",)),)
