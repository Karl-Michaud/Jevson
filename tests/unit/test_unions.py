"""PLAN Phase 6: union discrimination, against fakes. Each exit criterion has a test named after it.

The fan-out measurement is live and opt-in: `tests/integration/test_live_union_fanout.py`.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Any, Literal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, Field

from jevson import (
    BackendError,
    BackendResponse,
    CompileError,
    Cost,
    DecidedBy,
    FakeBackend,
    Jevson,
    JevsonConfig,
    PreflightError,
    RefusalCode,
    Result,
    Unresolved,
    UnresolvedReason,
    compile_schema,
)
from jevson.compile.normalise import normalise_schema
from jevson.compile.unions import branch_texts, exclusive
from jevson.types import (
    Answer,
    ChoiceAnswer,
    DecisionNode,
    InvalidAnswer,
    PredicateAnswer,
    Question,
    StepNode,
)
from tests.adversarial.hostile_llm import ScriptedLLM

Script = Callable[[Question], Answer]


class Card(BaseModel):
    """Paid by payment card."""

    type: Literal["card"]
    network: Literal["visa", "mastercard"]
    contactless: bool = Field(description="the card payment was contactless")


class Bank(BaseModel):
    """Paid by bank transfer."""

    type: Literal["bank"]
    speed: Literal["instant", "standard"]


class Order(BaseModel):
    payment: Annotated[Card | Bank, Field(discriminator="type")]
    urgent: bool = Field(description="the order is urgent")


def picks(**choices: str) -> Script:
    """Answers a choice whose question names a key with the option whose text contains its value,
    at 0.9; any other choice takes its first option; predicates answer 0.9."""

    def answer(question: Question) -> Answer:
        if not question.options:
            return PredicateAnswer(question.name, 0.9)
        wanted = next((v for k, v in choices.items() if k in question.instructions), None)
        chosen = next((o for o in question.options if wanted and wanted in o.description), question.options[0])
        rest = 0.1 / (len(question.options) - 1)
        return ChoiceAnswer(question.name, chosen.id, {o.id: 0.9 if o is chosen else rest for o in question.options})

    return answer


LEVEL = JevsonConfig(union_fanout=False)
"""The strategy that executes only the selected branch's nodes; fan-out asks the others and discards them."""


def resolve(schema: object, backend: Any, *, config: JevsonConfig | None = None, **kwargs: Any) -> Result:
    llm = kwargs.pop("llm", None)
    jevson = Jevson(backend, llm=llm, config=config or JevsonConfig())
    return asyncio.run(jevson.aresolve(schema, "An order.", **kwargs))


def asked(backend: FakeBackend) -> list[list[str]]:
    return [[q.instructions for q in call.questions] for call in backend.calls]


def choice(graph: Any, node_id: str) -> DecisionNode:
    node = graph.nodes[node_id]
    assert isinstance(node, DecisionNode)
    return node


def obj(**properties: object) -> dict[str, object]:
    return {"type": "object", "properties": properties, "required": sorted(properties)}


# --- exit criteria ------------------------------------------------------------------------------


def test_a_union_resolves_its_discriminator_first_and_executes_only_the_selected_branch() -> None:
    backend = FakeBackend(default=picks(payment="Bank", speed="instant"))
    result = resolve(Order, backend, config=LEVEL)
    assert asked(backend) == [
        [
            "Which of these does the source describe as the payment?",
            "According to the source, is it true that the order is urgent?",
        ],
        ["Which of these is the speed?"],
    ]
    assert result.value == {"payment": {"type": "bank", "speed": "instant"}, "urgent": True}
    assert result.satisfies_schema
    assert result.complete
    assert list(result.decisions) == ["/payment#branch@0", "/urgent#predicate@0", "/payment|c1/speed#choice@0"]
    assert result.decided_by["/payment/type"] is DecidedBy.CODE
    assert result.cost.decision_requests == 2


def test_the_unselected_branchs_fields_never_appear_even_as_nulls() -> None:
    result = resolve(Order, FakeBackend(default=picks(payment="Card", network="visa")))
    assert result.value["payment"] == {"type": "card", "network": "visa", "contactless": True}
    assert "speed" not in json.dumps(result.value)
    assert not [k for k in [*result.decisions, *result.decided_by] if "speed" in k]


def test_an_unmappable_construct_in_any_branch_refuses_before_any_call() -> None:
    schema = obj(
        u={"anyOf": [obj(ok={"type": "boolean", "description": "it is ok"}), obj(free={"type": "string"})]},
        v={"oneOf": [{"enum": ["a", "b"]}, {"type": "array", "prefixItems": list[object]()}]},
    )
    backend = FakeBackend(default=picks())
    with pytest.raises(CompileError) as raised:
        resolve(schema, backend)
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [
        ("/v", RefusalCode.TUPLE_FIELD),
        ("/u/free", RefusalCode.UNBOUNDED_FIELD),
    ]
    assert backend.calls == []


def test_branches_identical_after_normalisation_refuse_as_undiscriminable() -> None:
    same = obj(flag={"type": "boolean", "description": "it is set"})
    with pytest.raises(CompileError) as raised:
        compile_schema(obj(u={"anyOf": [same, dict(same)]}))
    assert [(r.pointer, r.reason) for r in raised.value.reasons] == [("/u", RefusalCode.UNDISCRIMINABLE_UNION)]
    titled = obj(u={"anyOf": [same | {"title": "Person"}, same | {"title": "Company"}]})
    assert compile_schema(titled)  # a title tells them apart
    other = obj(other={"type": "boolean", "description": "it is set"})
    graph = compile_schema(obj(u={"anyOf": [same | {"title": "T"}, other | {"title": "T"}]}))
    assert [o.description for o in choice(graph, "/u#branch").options] == ["T (with flag)", "T (with other)"]


def test_a_nested_union_levels_correctly() -> None:
    inner = {
        "anyOf": [
            obj(alpha={"enum": ["x", "y"]}) | {"title": "Alpha"},
            obj(beta={"enum": ["p", "q"]}) | {"title": "Beta"},
        ]
    }
    flat = obj(flat={"enum": ["k", "l"]}) | {"title": "Flat"}
    schema = obj(outer={"anyOf": [obj(inner=inner) | {"title": "Nested"}, flat]})
    graph = compile_schema(schema, union_fanout=False)
    levels = [[d.id for d in level.decisions] for level in graph.levels()]
    assert levels == [
        ["/outer#branch"],
        ["/outer|c0/inner#branch", "/outer|c1/flat#choice"],
        ["/outer|c0/inner|c0/alpha#choice", "/outer|c0/inner|c1/beta#choice"],
    ]
    assert graph.nodes["/outer|c0/inner|c1/beta#choice"].branch == (
        ("/outer#branch", "c0"),
        ("/outer|c0/inner#branch", "c1"),
    )
    backend = FakeBackend(default=picks(outer="Nested", inner="Beta", beta="q"))
    result = resolve(schema, backend, config=LEVEL)
    assert result.value == {"outer": {"inner": {"beta": "q"}}}
    assert [len(call.questions) for call in backend.calls] == [1, 1, 1]
    assert result.satisfies_schema
    assert len(compile_schema(schema).levels()) == 1  # fan-out: one level, the same answer
    assert resolve(schema, FakeBackend(default=picks(outer="Nested", inner="Beta", beta="q"))).value == result.value


@pytest.mark.parametrize(
    ("script", "reason"),
    [
        (FakeBackend.tie(), UnresolvedReason.TIE),
        (lambda q: InvalidAnswer(q.name, "bad"), UnresolvedReason.INVALID_BACKEND_ANSWER),  # pyright: ignore[reportUnknownLambdaType, reportUnknownMemberType, reportUnknownArgumentType]
    ],
)
def test_a_tie_or_invalid_discriminator_leaves_the_whole_subtree_unresolved(script: Script, reason: str) -> None:
    def answer(question: Question) -> Answer:
        return script(question) if "payment" in question.instructions else picks()(question)

    backend = FakeBackend(default=answer)
    result = resolve(Order, backend)
    assert "/payment#branch@0" in result.decisions
    assert result.value == {"urgent": True}
    assert result.unresolved == (
        Unresolved("/payment", UnresolvedReason(reason)),
        Unresolved("/payment/contactless", UnresolvedReason.DEPENDENCY_UNRESOLVED),
        Unresolved("/payment/network", UnresolvedReason.DEPENDENCY_UNRESOLVED),
        Unresolved("/payment/speed", UnresolvedReason.DEPENDENCY_UNRESOLVED),
    )
    assert len(backend.calls) == 1, "no branch is executed"


def test_fan_out_vs_level_both_resolve_the_same_and_fan_out_saves_a_request() -> None:
    level = FakeBackend(default=picks(payment="Bank", speed="standard"))
    fanned = FakeBackend(default=picks(payment="Bank", speed="standard"))
    by_level = resolve(Order, level, config=LEVEL)
    by_fanout = resolve(Order, fanned)
    assert by_fanout.value == by_level.value
    assert by_fanout.decisions.keys() == by_level.decisions.keys()  # the Card answers were discarded
    assert [len(c.questions) for c in level.calls] == [2, 1]
    assert [len(c.questions) for c in fanned.calls] == [5]
    assert by_fanout.versions["union_fanout"] == "true"


# --- execution details --------------------------------------------------------------------------


class Summary(BaseModel):
    """A written note."""

    note: str = Field(json_schema_extra={"x-jevson": {"generate": {"criteria": ["is one sentence"]}}})


class Rating(BaseModel):
    """A rating."""

    good: bool = Field(description="the order went well")


class Review(BaseModel):
    review: Summary | Rating


def test_a_generate_step_in_an_unselected_branch_never_drafts_and_fan_out_keeps_its_level() -> None:
    graph = compile_schema(Review, union_fanout=True)
    step = graph.nodes["/review|c0/note#generate"]
    assert isinstance(step, StepNode)
    assert step.dependencies == {"/review#branch"}
    llm = ScriptedLLM(["One sentence."])
    result = resolve(Review, FakeBackend(default=picks(review="rating")), llm=llm)
    assert result.value == {"review": {"good": True}}
    assert llm.calls == []
    chosen = FakeBackend(default=picks(review="note"))
    result = resolve(Review, chosen, llm=llm)
    assert result.value == {"review": {"note": "One sentence."}}
    assert result.decided_by["/review/note"] is DecidedBy.LLM_DECISION


def test_no_node_id_or_state_key_indexes_a_branch_by_position() -> None:
    """R13: a branch qualifier is `|c<n>`, never `[n]`, in ids, questions, and the drafts keys."""
    graph = compile_schema(Review)
    assert not [n.id for n in graph.nodes.values() if "[" in n.id]
    assert not [n for n in graph.nodes.values() if isinstance(n, DecisionNode) and "[" in n.question]
    backend = FakeBackend(default=picks(review="note"))
    resolve(Review, backend, llm=ScriptedLLM(["One sentence."]))
    states = [json.loads(call.state) for call in backend.calls]
    assert "/review|c0/note#generate" in states[-1]["drafts"]
    assert not [key for state in states for key in state.get("drafts", {}) if "[" in key]


def test_a_known_discriminator_value_selects_its_branch_without_a_decision() -> None:
    backend = FakeBackend(default=picks(speed="instant"))
    result = resolve(Order, backend, known={"/payment/type": "bank"})
    assert result.value["payment"] == {"type": "bank", "speed": "instant"}
    assert result.decided_by["/payment/type"] is DecidedBy.CALLER
    assert "/payment#branch@0" not in result.decisions
    assert ["payment" in q for call in asked(backend) for q in call] == [False, False]


@pytest.mark.parametrize("config", [LEVEL, JevsonConfig()], ids=["level", "fanout"])
def test_a_known_field_inside_a_branch_is_used_only_if_that_branch_is_selected(config: JevsonConfig) -> None:
    known = {"/payment/network": "mastercard"}
    backend = FakeBackend(default=picks(payment="Card"))
    selected = resolve(Order, backend, known=known, config=config)
    assert not [q for call in asked(backend) for q in call if "network" in q]
    assert selected.value["payment"] == {"type": "card", "network": "mastercard", "contactless": True}
    assert selected.decided_by["/payment/network"] is DecidedBy.CALLER
    unselected = resolve(Order, FakeBackend(default=picks(payment="Bank")), known=known, config=config)
    assert unselected.value["payment"] == {"type": "bank", "speed": "instant"}


@pytest.mark.parametrize(
    ("known", "message"),
    [
        ({"/payment/type": "cash"}, "matches no branch"),
        ({"/payment/type": "card", "/payment/kind": "bank"}, "two branches"),
    ],
)
def test_known_branch_constants_must_select_exactly_one_branch(known: dict[str, Any], message: str) -> None:
    class Bank2(BaseModel):
        """Paid by bank transfer."""

        type: Literal["bank"]
        kind: Literal["bank"]
        speed: Literal["instant", "standard"]

    class Card2(BaseModel):
        """Paid by card."""

        type: Literal["card"]
        kind: Literal["card"]

    class Order2(BaseModel):
        payment: Card2 | Bank2

    backend = FakeBackend(default=picks())
    with pytest.raises(PreflightError, match=message):
        resolve(Order2, backend, known=known)
    assert backend.calls == []
    with pytest.raises(PreflightError, match="more than one"):
        resolve(
            obj(u={"anyOf": [obj(t={"const": "x"}) | {"title": "A"}, obj(t={"const": "x"})]}),
            backend,
            known={"/u/t": "x"},
        )


def test_a_required_constant_outside_a_union_is_committed_by_code() -> None:
    """Bug fix (ASTERION-37): before Phase 6 a required `Literal` with no default was omitted, so
    `.value` failed the schema and `model_validate`."""

    class Invoice(BaseModel):
        kind: Literal["invoice"]
        version: Literal[2] = 2
        paid: bool = Field(description="the invoice is paid")

    result = resolve(Invoice, FakeBackend(default=picks()))
    assert result.value == {"kind": "invoice", "paid": True}
    assert result.satisfies_schema
    assert result.decided_by["/kind"] is DecidedBy.CODE
    with pytest.raises(PreflightError, match="matches no"):
        resolve(Invoice, FakeBackend(default=picks()), known={"/kind": "receipt"})


def test_scalar_and_constant_branches_commit_at_the_union_pointer() -> None:
    schema = obj(
        shade={"anyOf": [{"enum": ["red", "blue"]}, {"type": "boolean", "description": "it is coloured"}]},
        switch={"anyOf": [{"const": "on"}, {"const": "off"}]},
        nest={
            "anyOf": [
                {"anyOf": [{"enum": ["a", "b"]}, {"type": "boolean", "description": "it nests"}]},
                {"const": "none"},
            ]
        },
    )
    graph = compile_schema(schema)
    assert [o.description for o in choice(graph, "/shade#branch").options] == ['one of "red", "blue"', "it is coloured"]
    assert [o.description for o in choice(graph, "/switch#branch").options] == ['"on"', '"off"']
    assert [o.description for o in choice(graph, "/nest#branch").options] == [
        'one of one of "a", "b" or it nests',
        '"none"',
    ]
    assert choice(graph, "/nest|c0#branch").branch == (("/nest#branch", "c0"),)
    result = resolve(schema, FakeBackend(default=picks(shade="red", switch="off", nest="one of")))
    assert result.value == {"shade": "red", "switch": "off", "nest": "a"}
    assert result.satisfies_schema


def test_an_overflowing_discriminator_leaves_its_branches_unresolved() -> None:
    class Overflowing:
        def __init__(self) -> None:
            self.calls = 0

        async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
            self.calls += 1
            if any("payment" in q.instructions for q in questions):
                raise BackendError("context_limit", "too long", Result({}, False, cost=Cost(decision_requests=1)))
            return BackendResponse(tuple(PredicateAnswer(q.name, 0.9) for q in questions), 1, "ok", "fake")

    result = resolve(Order, Overflowing())
    assert result.unresolved[0] == Unresolved("/payment", UnresolvedReason.BUDGET_EXCEEDED)
    assert {u.reason for u in result.unresolved[1:]} == {UnresolvedReason.DEPENDENCY_UNRESOLVED}
    assert result.value == {"urgent": True}


# --- compile details ----------------------------------------------------------------------------


def test_a_root_union_and_a_generative_union_refuse() -> None:
    with pytest.raises(CompileError) as raised:
        compile_schema({"anyOf": [obj(a={"type": "boolean"}), obj(b={"type": "boolean"})]})
    assert [r.reason for r in raised.value.reasons] == [RefusalCode.ROOT_UNION]
    generative = {"anyOf": [{"enum": ["a", "b"]}, {"type": "boolean"}], "x-jevson": {"generate": {"criteria": ["x"]}}}
    with pytest.raises(CompileError) as raised:
        compile_schema(obj(u=generative))
    assert [r.reason for r in raised.value.reasons] == [RefusalCode.GENERATE_FIELD_TYPE]


def test_exclusive_branches_may_share_a_question_but_other_nodes_may_not() -> None:
    shared = obj(tier={"enum": ["a", "b"], "x-jevson": {"question": "the tier"}})
    graph = compile_schema(obj(u={"anyOf": [shared | {"title": "One"}, shared | {"title": "Two"}]}))
    assert {"/u|c0/tier#choice", "/u|c1/tier#choice"} <= graph.nodes.keys()
    with pytest.raises(CompileError) as raised:
        compile_schema(
            obj(u={"anyOf": [shared | {"title": "One"}, obj(x={"type": "boolean"}) | {"title": "Two"}]}, v=shared)
        )
    assert RefusalCode.DUPLICATE_QUESTION in [r.reason for r in raised.value.reasons]
    assert exclusive((("d", "c0"),), (("d", "c1"),))
    assert not exclusive((("d", "c0"),), (("e", "c1"),))


def test_branch_texts_use_title_then_description_then_a_summary() -> None:
    union = dict(normalise_schema(obj(u={"anyOf": [
        obj(a={"type": "boolean"}) | {"title": "A", "description": "first"},
        obj(b={"type": "boolean"}) | {"description": "second"},
        {"type": "object", "properties": {"c": {"type": "boolean"}}},
        {"anyOf": [{"type": "integer"}, {"type": "boolean"}]},
    ]})).properties)["u"]  # fmt: skip
    assert branch_texts(union.branches) == (
        "A: first",
        "second",
        "an object with no required fields",
        "one of an integer or a boolean",
    )


def test_union_labels_are_scoped_like_any_other_field() -> None:
    def pair(name: str) -> Mapping[str, object]:
        branch = obj(a={"type": "boolean", "description": "a is set"}) | {"title": "A"}
        return obj(**{name: {"anyOf": [branch, {"enum": ["x", "y"]}]}})

    graph = compile_schema(obj(left=pair("kind"), right=pair("kind")))
    questions = sorted(
        n.question for n in graph.nodes.values() if isinstance(n, DecisionNode) and n.id.endswith("#branch")
    )
    assert questions == [
        "Which of these does the source describe as the left kind?",
        "Which of these does the source describe as the right kind?",
    ]


NESTED = obj(
    outer={
        "anyOf": [
            obj(
                inner={
                    "anyOf": [
                        obj(alpha={"enum": ["x", "y"]}) | {"title": "Alpha"},
                        obj(beta={"enum": ["p", "q"]}) | {"title": "Beta"},
                    ]
                }
            )
            | {"title": "Nested"},
            obj(flat={"enum": ["k", "l"]}) | {"title": "Flat"},
        ]
    }
)


@settings(derandomize=True, database=None, max_examples=60, deadline=None)
@given(st.lists(st.sampled_from(["c0", "c1", "tie"]), min_size=4, max_size=4), st.booleans())
def test_only_the_selected_path_is_ever_committed_or_recorded(answers: list[str], fanout: bool) -> None:
    """Whatever each question answers, under either strategy: every committed or recorded node lies on
    the selected path, a tie anywhere leaves exactly that subtree unresolved, and the result is sound."""
    script = iter(answers * 3)

    def answer(question: Question) -> Answer:
        pick = next(script)
        return FakeBackend.tie()(question) if pick == "tie" else FakeBackend.select(pick, 0.9)(question)

    result = resolve(NESTED, FakeBackend(default=answer), config=JevsonConfig(union_fanout=fanout))
    outer = result.decisions["/outer#branch@0"].selected
    inner = result.decisions.get("/outer|c0/inner#branch@0")
    allowed = {"c0": {"/outer|c0/inner#branch"}, "c1": {"/outer|c1/flat#choice"}}.get(str(outer), set())
    if outer == "c0" and inner is not None and inner.selected is not None:
        allowed.add(f"/outer|c0/inner|{inner.selected}/{'alpha' if inner.selected == 'c0' else 'beta'}#choice")
    assert {k.removesuffix("@0") for k in result.decisions} <= {"/outer#branch", *allowed}
    assert result.complete or result.unresolved[0].reason is UnresolvedReason.TIE
    assert result.complete == result.satisfies_schema
