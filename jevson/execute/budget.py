"""The context budget (DESIGN §8.2): preflight on declared maxima, and splitting a level to fit.

Two configured limits apply to every request: `max_input_tokens` (state plus questions) and
`max_questions_per_request`. Preflight runs on every level before the first backend call:

- (a) state + the longest single question over the token limit cannot be fixed by splitting, so it
  raises `PreflightError` before anything is spent;
- (b) a level over either limit is split, greedily in level order, into requests that fit.

There is no tokenizer dependency. The estimate aims to be pessimistic: a token per 3 UTF-8 bytes
(English runs ~4), plus a fixed 160 tokens per question (the ~160 tokens per short question Phase 0r
measured [Q11]) on top of its text, and 8 per option [Q12]. Measured against billed tokens [Q15]:
with a 40-token question overhead, all 36 requests of 32 questions were under-estimated (0.62-0.72);
at 160 they sit at 1.23-1.27. It is not a guarantee: one single-question request of 164 still came in
under (0.96), from text the byte rate under-counted.

Each question is budgeted at its node's *declared* size, through a per-node hook (`DeclaredSize`), so
later phases can budget content that does not exist yet: Phase 4 adds a node's `max_draft_chars` for
the draft it will place in state. v0 options are all declared at compile time, so the v0 hook,
`declared_tokens`, is the actual question and option text. Every request's estimate is recorded next
to the `usage.input_tokens` it was billed (`CostEvent`, `Cost`), so a live run shows whether the
estimator stays conservative; a run-time context-limit rejection means it or a limit was wrong, and
the executor bisects (DESIGN §8.2).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

from jevson.config import JevsonConfig
from jevson.types import DecisionNode, Question, StepNode

DeclaredSize = Callable[[DecisionNode], int]
"""A node's declared maximum size in estimated tokens: its question, options, and any state it adds."""

ESTIMATOR_VERSION = "bytes/3+160q+8o"
BYTES_PER_TOKEN = 3
QUESTION_OVERHEAD = 160  # [Q11] ~160 tokens per short question; 40 under-counted 32-question requests [Q15]
OPTION_OVERHEAD = 8
DRAFT_BYTES_PER_CHAR = 6  # the worst case for one character of a draft in JSON state: a \\u escape


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8", "surrogatepass")) / BYTES_PER_TOKEN)


def question_tokens(question: Question) -> int:
    options = sum(OPTION_OVERHEAD + estimate_tokens(o.id) + estimate_tokens(o.description) for o in question.options)
    return QUESTION_OVERHEAD + estimate_tokens(question.instructions) + options


def declared_tokens(node: DecisionNode) -> int:
    """The v0 `DeclaredSize`: the node's question and option text, all known at compile time."""
    return question_tokens(Question("", node.kind, node.question, node.options))


def draft_tokens(step: StepNode) -> int:
    """A generated draft at its declared maximum, as it sits in the state under its key."""
    limit = step.drafting.max_draft_chars if step.drafting is not None else 0
    return math.ceil(limit * DRAFT_BYTES_PER_CHAR / BYTES_PER_TOKEN) + estimate_tokens(f'"{step.id}": "", ')


def with_drafts(declared_size: DeclaredSize, checks: Mapping[str, StepNode]) -> DeclaredSize:
    """`declared_size` plus, for each adjudication node, the draft it reads (`checks`: node id → its
    step). Preflight then refuses a field whose draft could not fit, before anything is spent."""

    def sized(node: DecisionNode) -> int:
        step = checks.get(node.id)
        return declared_size(node) + (draft_tokens(step) if step is not None else 0)

    return sized


def request_tokens(state: str, questions: Sequence[Question], sizes: Mapping[str, int]) -> int:
    """The estimate for one request: the state plus each question's declared size."""
    return estimate_tokens(state) + sum(sizes[q.name] for q in questions)


def oversized(
    state: str, questions: Sequence[Question], sizes: Mapping[str, int], config: JevsonConfig
) -> list[Question]:
    """The questions that cannot fit in any request, even alone with the state (limit (a))."""
    room = config.max_input_tokens - estimate_tokens(state)
    return [q for q in questions if sizes[q.name] > room]


def split(
    state: str, questions: Sequence[Question], sizes: Mapping[str, int], config: JevsonConfig
) -> list[list[Question]]:
    """Pack a level's questions, in order, into requests within both limits (limit (b)).

    Every question must fit alone (check `oversized` first). One chunk means no split."""
    room = config.max_input_tokens - estimate_tokens(state)
    chunks: list[list[Question]] = []
    used = 0
    for question in questions:
        cost = sizes[question.name]
        if not chunks or used + cost > room or len(chunks[-1]) >= config.max_questions_per_request:
            chunks.append([])
            used = 0
        chunks[-1].append(question)
        used += cost
    return chunks
