"""A deterministic fake `Backend`, shipped as a testing tool.

Answers are scripted per question name. A script entry is a function from the asked `Question` to
an `Answer`; the static helpers build the common ones (a probability, a selected option, an exact
distribution, a tie, an abstention, a refusal). The fake records every call and never touches the
network or the clock.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from jevson.types import (
    NONE_OF_THESE,
    Answer,
    BackendResponse,
    ChoiceAnswer,
    DecisionKind,
    PredicateAnswer,
    Question,
    Refusal,
    ScoreAnswer,
)

Script = Callable[[Question], Answer]


@dataclass(frozen=True)
class FakeCall:
    state: str
    questions: tuple[Question, ...]
    model: str


class FakeBackend:
    def __init__(
        self,
        script: Mapping[str, Script] | None = None,
        *,
        default: Script | None = None,
        model: str = "fake-backend",
    ) -> None:
        self._script = dict(script or {})
        self._default = default
        self._model = model
        self.calls: list[FakeCall] = []

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        self.calls.append(FakeCall(state, tuple(questions), model))
        answers: list[Answer] = []
        for question in questions:
            script = self._script.get(question.name, self._default)
            if script is None:
                raise KeyError(f"FakeBackend has no script for question {question.name!r} and no default")
            answers.append(script(question))
        characters = len(state) + sum(len(q.instructions) for q in questions)
        return BackendResponse(
            answers=tuple(answers),
            input_tokens=math.ceil(characters / 4),
            request_id=f"fake-{len(self.calls)}",
            model=self._model,
        )

    # --- script helpers ---------------------------------------------------------------------

    @staticmethod
    def predicate(probability: float) -> Script:
        return lambda question: PredicateAnswer(question.name, probability)

    @staticmethod
    def select(option_id: str, probability: float = 1.0, confidence: float | None = None) -> Script:
        """Choose `option_id` with `probability`, the rest of the mass spread evenly over the others."""

        def answer(question: Question) -> Answer:
            if question.kind is DecisionKind.PREDICATE:
                raise ValueError(f"select() scripts a choice or score; {question.name!r} is a predicate")
            others = [option.id for option in question.options if option.id != option_id]
            rest = (1.0 - probability) / len(others)
            probabilities = dict.fromkeys(others, rest) | {option_id: probability}
            return _with_distribution(question, probabilities, option_id, confidence)

        return answer

    @staticmethod
    def distribution(
        probabilities: Mapping[str, float], *, choice: str | None = None, confidence: float | None = None
    ) -> Script:
        """Return exactly these probabilities. `choice` defaults to the most probable option."""
        chosen = choice if choice is not None else max(probabilities, key=lambda o: probabilities[o])
        return lambda question: _with_distribution(question, dict(probabilities), chosen, confidence)

    @staticmethod
    def tie() -> Script:
        """0.50 on a predicate; 0.50 / 0.50 on the first two options of a choice or score."""

        def answer(question: Question) -> Answer:
            if question.kind is DecisionKind.PREDICATE:
                return PredicateAnswer(question.name, 0.5)
            first, second, *rest = (option.id for option in question.options)
            probabilities = {first: 0.5, second: 0.5} | dict.fromkeys(rest, 0.0)
            return _with_distribution(question, probabilities, first, None)

        return answer

    @staticmethod
    def abstain(probability: float = 1.0) -> Script:
        return FakeBackend.select(NONE_OF_THESE, probability)

    @staticmethod
    def refuse() -> Script:
        return lambda question: Refusal(question.name)

    @staticmethod
    def answer(fixed: Answer) -> Script:
        """Return this answer verbatim, malformed or not."""
        return lambda question: fixed


def _with_distribution(
    question: Question, probabilities: dict[str, float], chosen: str, confidence: float | None
) -> Answer:
    if question.kind is DecisionKind.SCORE:
        index = {option.id: i for i, option in enumerate(question.options)}
        mean = sum(index.get(level, 0) * p for level, p in probabilities.items())
        return ScoreAnswer(question.name, mean, probabilities, confidence)
    return ChoiceAnswer(question.name, chosen, probabilities, confidence)
