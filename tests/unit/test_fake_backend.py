from __future__ import annotations

import asyncio

import pytest

from jevson import Backend, FakeBackend
from jevson.types import (
    NONE_OF_THESE,
    ChoiceAnswer,
    DecisionKind,
    Option,
    PredicateAnswer,
    Question,
    Refusal,
    ScoreAnswer,
)

BOOL = Question("q0", DecisionKind.PREDICATE, "Is it paid?")
CHOICE = Question("q1", DecisionKind.CHOICE, "Which?", (Option("c0", "Acme"), Option("c1", "Globex")))
CANDIDATES = Question("q2", DecisionKind.CHOICE, "Which?", (Option("c0", "Acme"), Option(NONE_OF_THESE, "none")))
SCORE = Question("q3", DecisionKind.SCORE, "How good?", tuple(Option(f"l{i}", str(i)) for i in range(3)))


def ask(backend: FakeBackend, *questions: Question, state: str = "source") -> tuple[object, ...]:
    return asyncio.run(backend.ask(state, questions, "gpt-6-luna")).answers


def test_fake_backend_satisfies_the_backend_protocol() -> None:
    backend: Backend = FakeBackend()
    assert isinstance(backend, Backend)


def test_predicate_select_and_distribution() -> None:
    backend = FakeBackend(
        {
            "q0": FakeBackend.predicate(0.8),
            "q1": FakeBackend.select("c1", 0.9, confidence=0.7),
            "q3": FakeBackend.distribution({"l0": 0.1, "l1": 0.2, "l2": 0.7}),
        }
    )
    paid, which, score = ask(backend, BOOL, CHOICE, SCORE)
    assert paid == PredicateAnswer("q0", 0.8)
    assert which == ChoiceAnswer("q1", "c1", {"c0": pytest.approx(0.1), "c1": 0.9}, 0.7)
    assert isinstance(score, ScoreAnswer)
    assert score.probabilities == {"l0": 0.1, "l1": 0.2, "l2": 0.7}
    assert score.score == pytest.approx(1.6)


def test_distribution_can_name_a_non_argmax_choice() -> None:
    backend = FakeBackend({"q1": FakeBackend.distribution({"c0": 0.9, "c1": 0.1}, choice="c1")})
    (answer,) = ask(backend, CHOICE)
    assert isinstance(answer, ChoiceAnswer)
    assert answer.choice == "c1"


def test_ties_abstentions_and_refusals() -> None:
    backend = FakeBackend(
        {"q0": FakeBackend.tie(), "q1": FakeBackend.tie(), "q2": FakeBackend.abstain(0.95), "q3": FakeBackend.refuse()}
    )
    paid, which, candidate, score = ask(backend, BOOL, CHOICE, CANDIDATES, SCORE)
    assert paid == PredicateAnswer("q0", 0.5)
    assert which == ChoiceAnswer("q1", "c0", {"c0": 0.5, "c1": 0.5}, None)
    assert isinstance(candidate, ChoiceAnswer)
    assert candidate.choice == NONE_OF_THESE
    assert candidate.probabilities[NONE_OF_THESE] == 0.95
    assert score == Refusal("q3")


def test_tie_on_a_score_spreads_over_the_first_two_levels() -> None:
    (answer,) = ask(FakeBackend(default=FakeBackend.tie()), SCORE)
    assert isinstance(answer, ScoreAnswer)
    assert answer.probabilities == {"l0": 0.5, "l1": 0.5, "l2": 0.0}


def test_a_fixed_answer_is_returned_verbatim() -> None:
    malformed = ChoiceAnswer("q1", "nonsense", {"x": 2.0})
    assert ask(FakeBackend({"q1": FakeBackend.answer(malformed)}), CHOICE) == (malformed,)


def test_calls_are_recorded_and_responses_are_deterministic() -> None:
    backend = FakeBackend(default=FakeBackend.predicate(0.9), model="fake-v2")
    first = asyncio.run(backend.ask("abcd" * 10, [BOOL], "gpt-6-luna"))
    second = asyncio.run(backend.ask("abcd" * 10, [BOOL], "gpt-6-luna"))
    assert (first.request_id, second.request_id) == ("fake-1", "fake-2")
    assert first.model == "fake-v2"
    assert first.answers == second.answers
    assert first.input_tokens == 13  # ceil((40 + 11) / 4)
    assert [call.model for call in backend.calls] == ["gpt-6-luna", "gpt-6-luna"]
    assert backend.calls[0].questions == (BOOL,)


def test_an_unscripted_question_without_a_default_raises() -> None:
    with pytest.raises(KeyError, match="no script for question 'q0'"):
        ask(FakeBackend(), BOOL)


def test_select_refuses_a_predicate_question() -> None:
    with pytest.raises(ValueError, match="is a predicate"):
        ask(FakeBackend({"q0": FakeBackend.select("c0")}), BOOL)
