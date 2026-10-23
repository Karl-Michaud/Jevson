"""Request-layout test doubles (DESIGN §5.2, §8.2) — NOT shipped.

`Recorder` is a `Backend` that answers through a callable and records every request, rejected ones
too. `draft_reads` says which drafting step each question of a schema adjudicates, taken from the
compiled graph (a decision node that depends on a drafting step), never from template text, so a
template change cannot misclassify a question. `check_isolation` is the layout invariant over the
recorded requests.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from jevson.compile.compiler import compile_schema
from jevson.errors import BackendError
from jevson.result import Result
from jevson.types import Answer, BackendResponse, Cost, DecisionNode, Option, Question, StepNode

Call = tuple[str, tuple[Question, ...]]
Key = tuple[str, tuple[Option, ...]]
"""A question's text and options: how a sent question is matched to its compiled node."""


def key(question: Question) -> Key:
    return (question.instructions, question.options)


class Recorder:
    """A `Backend` that answers each question with `answer(state, question)`, records every request,
    and rejects with `context_limit` any request `reject` picks."""

    def __init__(
        self,
        answer: Callable[[str, Question], Answer],
        reject: Callable[[str, Sequence[Question]], bool] = lambda state, questions: False,
    ) -> None:
        self.answer, self.reject = answer, reject
        self.calls: list[Call] = []

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        self.calls.append((state, tuple(questions)))
        if self.reject(state, questions):
            raise BackendError("context_limit", "too long", Result({}, False, cost=Cost(decision_requests=1)))
        answers = tuple(self.answer(state, q) for q in questions)
        return BackendResponse(answers, 10, f"r{len(self.calls)}", "recorder")


def decision_nodes(schema: object, **options: Any) -> dict[Key, DecisionNode]:
    """Every decision node of `schema`'s graph, by the text and options of its question; `options` are
    `compile_schema`'s keywords (`union_fanout`, `criterion_template`)."""
    graph = compile_schema(schema, **options)
    return {(n.question, n.options): n for n in graph.nodes.values() if isinstance(n, DecisionNode)}


def draft_reads(schema: object, **options: Any) -> dict[Key, str | None]:
    """Each question of `schema`'s graph -> the drafting step it adjudicates, or None if it is bounded;
    `options` are `compile_schema`'s keywords, as for `decision_nodes`."""
    graph = compile_schema(schema, **options)
    drafted = {n.id for n in graph.nodes.values() if isinstance(n, StepNode) and n.drafting is not None}
    reads: dict[Key, str | None] = {}
    for k, node in decision_nodes(schema, **options).items():
        read = sorted(node.dependencies & drafted)
        reads[k] = read[0] if read else None
    return reads


def check_isolation(calls: Sequence[Call], reads: Mapping[Key, str | None]) -> None:
    """No request mixes adjudication with other questions, a state that holds `drafts` is asked
    adjudication questions only, its drafts are exactly the drafts its questions read, and an
    adjudication question is never sent without its draft."""
    for state, questions in calls:
        drafts = set(json.loads(state).get("drafts", {}))
        named = {reads[key(q)] for q in questions}
        asked = [q.instructions for q in questions]
        assert None not in named or named == {None}, f"a request mixes adjudication with other questions: {asked}"
        assert not drafts or None not in named, f"drafts {sorted(drafts)} reach non-adjudication questions: {asked}"
        assert drafts == named - {None}, f"drafts {sorted(drafts)} in a request whose questions read {named}"
