"""The context budget (DESIGN §8.2): preflight on declared maxima, and splitting a level to fit.

Two configured limits apply to every request: `max_input_tokens` (state plus questions) and
`max_questions_per_request`. Preflight runs on every level before the first backend call:

- (a) state + the longest single question over the token limit cannot be fixed by splitting, so it
  raises `PreflightError` before anything is spent;
- (b) a level over either limit is split, greedily in level order, into requests that fit.

There is no tokenizer dependency. The estimate is deliberately pessimistic: a token per 3 UTF-8 bytes
(English runs ~4) plus fixed per-question and per-option overheads above the ~160 tokens per short
question Phase 0r measured [Q11, Q12]. v0 options are all declared at compile time, so the
declared maxima are the actual question and option texts. Each response's `usage.input_tokens` is
recorded in `Cost`; a run-time context-limit rejection means this estimate or a limit was wrong, and
the executor bisects (DESIGN §8.2).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from jevson.config import JevsonConfig
from jevson.types import Question

ESTIMATOR_VERSION = "bytes/3+40q+8o"
BYTES_PER_TOKEN = 3
QUESTION_OVERHEAD = 40
OPTION_OVERHEAD = 8


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8", "surrogatepass")) / BYTES_PER_TOKEN)


def question_tokens(question: Question) -> int:
    options = sum(OPTION_OVERHEAD + estimate_tokens(o.id) + estimate_tokens(o.description) for o in question.options)
    return QUESTION_OVERHEAD + estimate_tokens(question.instructions) + options


def oversized(state: str, questions: Sequence[Question], config: JevsonConfig) -> list[Question]:
    """The questions that cannot fit in any request, even alone with the state (limit (a))."""
    room = config.max_input_tokens - estimate_tokens(state)
    return [q for q in questions if question_tokens(q) > room]


def split(state: str, questions: Sequence[Question], config: JevsonConfig) -> list[list[Question]]:
    """Pack a level's questions, in order, into requests within both limits (limit (b)).

    Every question must fit alone (check `oversized` first). One chunk means no split."""
    room = config.max_input_tokens - estimate_tokens(state)
    chunks: list[list[Question]] = []
    used = 0
    for question in questions:
        cost = question_tokens(question)
        if not chunks or used + cost > room or len(chunks[-1]) >= config.max_questions_per_request:
            chunks.append([])
            used = 0
        chunks[-1].append(question)
        used += cost
    return chunks
