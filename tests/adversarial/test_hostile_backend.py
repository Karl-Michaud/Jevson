"""PLAN §4.2 `malformed responses` and `invalid values`, against DecisionsBackend's wire parsing."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from jevson import BackendError, InvalidAnswer, PredicateAnswer, UnresolvedReason
from jevson.probabilities import interpret
from jevson.types import Answer
from tests.adversarial.hostile_backend import (
    ANSWERS,
    ENVELOPES,
    MODEL,
    NODES,
    QUESTIONS,
    VALUES,
    backend,
    envelope,
    good_answers,
    serving,
)


def ask(body: Any) -> tuple[Answer, ...]:
    return asyncio.run(backend(serving(body)).ask("source", QUESTIONS, MODEL)).answers


@pytest.mark.parametrize("behaviour", ENVELOPES)
def test_an_unreadable_200_is_a_backend_error(behaviour: str) -> None:
    with pytest.raises(BackendError) as raised:
        ask(ENVELOPES[behaviour])
    assert raised.value.code == "unparseable_response"
    assert raised.value.cost.decision_requests == 1
    assert raised.value.cost.decision_request_ids == ("req-1",)
    assert raised.value.result.satisfies_schema is False


@pytest.mark.parametrize("behaviour", ANSWERS)
def test_a_malformed_answer_is_invalid_for_that_question_only(behaviour: str) -> None:
    answers, bad = ANSWERS[behaviour]
    parsed = ask(envelope(answers))
    assert isinstance(parsed[bad], InvalidAnswer)
    assert parsed[bad].name == QUESTIONS[bad].name
    assert [i for i, a in enumerate(parsed) if isinstance(a, InvalidAnswer)] == [bad]
    reason = interpret(NODES[QUESTIONS[bad].name], parsed[bad], 10).reason
    assert reason is UnresolvedReason.INVALID_BACKEND_ANSWER


@pytest.mark.parametrize("behaviour", VALUES)
def test_an_invalid_value_never_commits(behaviour: str) -> None:
    answers, node, reason = VALUES[behaviour]
    parsed = {a.name: a for a in ask(envelope(answers))}
    result = interpret(NODES[node], parsed[node], 10)
    assert result.status == "unresolved"
    assert result.reason == UnresolvedReason(reason)
    assert result.decision.selected is None


def test_extra_keys_are_ignored() -> None:
    body = envelope(None)
    body["answers"] = [
        {"type": "predicate", "name": "q0", "probability": 0.9, "rationale": "x"},
        {"type": "choice", "name": "q1", "choice": "c1", "confidence": 0.7, "logits": [],
         "probabilities": [{"value": "c0", "probability": 0.2, "x": 1}, {"value": "c1", "probability": 0.8}]},
        {"type": "score", "name": "q2", "score": 2, "confidence": None,
         "probabilities": [{"label": "l0", "probability": 0}, {"label": "l1", "probability": 0},
                           {"label": "l2", "probability": 1}]},
    ]  # fmt: skip
    body["extra"] = True
    parsed = ask(body)
    assert not [a for a in parsed if isinstance(a, InvalidAnswer)]
    assert [interpret(NODES[q.name], a, 10).status for q, a in zip(QUESTIONS, parsed, strict=True)] == ["committed"] * 3


def test_a_refusal_resolves_to_refused_and_the_others_still_answer() -> None:
    body = envelope([{"type": "predicate", "name": "q0", "probability": 0.9}, {"type": "refusal", "name": "q1"}])
    levels = [{"label": f"l{i}", "probability": p} for i, p in enumerate((0, 0, 1))]
    body["answers"].append({"type": "score", "name": "q2", "score": 2, "probabilities": levels})
    paid, vendor, quality = ask(body)
    assert interpret(NODES["vendor"], vendor, 10).reason is UnresolvedReason.REFUSED
    assert interpret(NODES["paid"], paid, 10).status == "committed"
    assert interpret(NODES["quality"], quality, 10).decision.selected == "l2"


def test_answers_out_of_question_order_are_invalid_where_they_moved() -> None:
    paid, vendor, quality = good_answers()
    parsed = ask(envelope([paid, quality, vendor]))
    assert isinstance(parsed[0], PredicateAnswer)
    assert [type(a) for a in parsed[1:]] == [InvalidAnswer, InvalidAnswer]
    assert isinstance(parsed[1], InvalidAnswer)
    assert "position 2, question at 1" in parsed[1].detail
