"""The criteria dry run: see exactly what adjudication asks about a draft, without a key or an LLM.

`dry_run(schema, pointer, draft, source)` compiles the schema under `config`'s options, places
`draft` in the state the way a real run would (`drafts.<step id>`), and asks the field's criteria and
rubric, and the draft screen when `draft_screen` is on, in one request. With no `backend` it uses a
`FakeBackend` that gives each check its rule's passing answer (`PASS_RULES`), so it runs offline and
spends nothing; pass a scripted `FakeBackend` to try verdicts, or a real backend to test criteria on
live answers. See `docs/criteria-guide.md`.
"""

from __future__ import annotations

from dataclasses import dataclass

from jevson.adjudicate.criteria import PASS_RULES, judge
from jevson.backends.fake import FakeBackend
from jevson.compile.compiler import compile_schema
from jevson.config import JevsonConfig
from jevson.errors import UsageError
from jevson.execute.state import LevelState
from jevson.protocols import Backend
from jevson.types import DecisionNode, Question, StepNode


@dataclass(frozen=True)
class DryRun:
    """What a dry run asked about a draft and which checks it failed."""

    state: str
    """The state sent: the source and the draft under its key."""
    questions: tuple[str, ...]
    """Each check's question, in declared order."""
    failing: tuple[str, ...]
    """The checks the draft failed, as `Result.rejections` would name them."""


async def dry_run(
    schema: object,
    pointer: str,
    draft: str,
    source: str = "",
    *,
    backend: Backend | None = None,
    config: JevsonConfig | None = None,
) -> DryRun:
    """Ask a generative field's criteria and rubric, and the draft screen when `draft_screen` is on,
    about `draft`; offline and free with no `backend`, whose stand-in passes every check."""
    config = config or JevsonConfig()
    graph = compile_schema(
        schema,
        union_fanout=config.union_fanout,
        criterion_template=config.criterion_template,
        draft_screen=config.draft_screen,
    )
    steps = [n for n in graph.nodes.values() if isinstance(n, StepNode) and n.target == pointer]
    if not steps or steps[0].drafting is None:
        raise UsageError(f"{pointer!r} is not a generative field of this schema")
    step, drafting = steps[0], steps[0].drafting
    nodes = {n.id: n for n in graph.nodes.values() if isinstance(n, DecisionNode) and step.id in n.dependencies}
    questions = [Question(f"q{i}", n.kind, n.question, n.options) for i, n in enumerate(nodes.values())]
    state = LevelState(source, {step.id: draft}).serialise()
    if not questions:
        return DryRun(state, (), ())
    rules = {check.node_id: check.rule for check in drafting.checks}
    passing = {q.name: PASS_RULES[rules[node_id]].passing for node_id, q in zip(nodes, questions, strict=True)}
    asked = backend if backend is not None else FakeBackend(passing)
    response = await asked.ask(state, questions, config.model)
    by_name = {getattr(answer, "name", ""): answer for answer in response.answers}
    answers = {node_id: by_name.get(q.name) for node_id, q in zip(nodes, questions, strict=True)}
    _, failing = judge(drafting, nodes, answers, config.tie_margin_hundredths)
    return DryRun(state, tuple(q.instructions for q in questions), failing)
