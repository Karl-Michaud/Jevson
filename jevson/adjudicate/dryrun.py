"""The criteria dry run: see exactly what adjudication asks about a draft, without a key or an LLM.

`dry_run(schema, pointer, draft, source)` compiles the schema, places `draft` in the state the way
a real run would (`drafts.<step id>`), and asks the field's criteria and rubric in one request. With
no `backend` it uses a `FakeBackend` that passes every check, so it runs offline and spends nothing;
pass a scripted `FakeBackend` to try verdicts, or a real backend to test criteria on live answers.
See `docs/criteria-guide.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from jevson.adjudicate.criteria import judge
from jevson.backends.fake import FakeBackend
from jevson.compile.compiler import compile_schema
from jevson.config import JevsonConfig
from jevson.errors import UsageError
from jevson.execute.state import LevelState
from jevson.protocols import Backend
from jevson.types import Answer, DecisionKind, DecisionNode, PredicateAnswer, Question, ScoreAnswer, StepNode


@dataclass(frozen=True)
class DryRun:
    """What a dry run asked about a draft and which checks it failed."""

    state: str
    """The state sent: the source and the draft under its key."""
    questions: tuple[str, ...]
    """Each check's question, in declared order."""
    failing: tuple[str, ...]
    """The checks the draft failed, as `Result.rejections` would name them."""


def _passing(question: Question) -> Answer:
    if question.kind is DecisionKind.PREDICATE:
        return PredicateAnswer(question.name, 1.0)
    top = question.options[-1].id
    probabilities = {option.id: float(option.id == top) for option in question.options}
    return ScoreAnswer(question.name, float(len(question.options) - 1), probabilities)


async def dry_run(
    schema: object,
    pointer: str,
    draft: str,
    source: str = "",
    *,
    backend: Backend | None = None,
    config: JevsonConfig | None = None,
) -> DryRun:
    """Ask a generative field's criteria and rubric about `draft`; offline and free with no `backend`."""
    graph = compile_schema(schema)
    steps = [n for n in graph.nodes.values() if isinstance(n, StepNode) and n.target == pointer]
    if not steps or steps[0].drafting is None:
        raise UsageError(f"{pointer!r} is not a generative field of this schema")
    step, drafting = steps[0], steps[0].drafting
    nodes = {n.id: n for n in graph.nodes.values() if isinstance(n, DecisionNode) and step.id in n.dependencies}
    questions = [Question(f"q{i}", n.kind, n.question, n.options) for i, n in enumerate(nodes.values())]
    state = LevelState(source, {step.id: draft}).serialise()
    if not questions:
        return DryRun(state, (), ())
    asked = backend if backend is not None else FakeBackend(default=_passing)
    response = await asked.ask(state, questions, (config or JevsonConfig()).model)
    by_name = {getattr(answer, "name", ""): answer for answer in response.answers}
    answers = {node_id: by_name.get(q.name) for node_id, q in zip(nodes, questions, strict=True)}
    margin = (config or JevsonConfig()).tie_margin_hundredths
    _, failing = judge(drafting, nodes, answers, margin)
    return DryRun(state, tuple(q.instructions for q in questions), failing)
