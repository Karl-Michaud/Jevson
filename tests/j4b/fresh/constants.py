"""The run's pinned constants (plan §9.1 appendix; §2 rule (d)): one frozen module, so a fix to a request,
recording or replay module can never move them.
"""

from __future__ import annotations

NANO = 1_000_000_000
CAP = 15 * NANO
"""$15 over every attempt, in nano-dollars (OWNER-DECISIONS item 9)."""
PRICE = {"decision_in": 100, "chat_in": 750, "chat_out": 4500}
"""Nano-dollars per token: decisions $0.10/M input; drafting $0.75/M input and $4.50/M output (design §6.3)."""
CHAT_FORMAT_TOKENS = 64
"""Tokens a request may bill beyond its body's bytes (design §6.3)."""
DECISION_QUESTION_TOKENS, DECISION_OPTION_TOKENS = 160, 8
"""Tokens a decision request may bill per question and per option beyond its bytes + 64 (plan §11 D21,
FEAS48-C1-1): the API bills about 110-160 tokens per question that are not in the body (DESIGN §8.2), so the
decision bound is bytes + 64 + 160 q + 8 o, at least the harness formula ceil(bytes / 3) + 160 q + 8 o."""
MAX_COMPLETION_TOKENS = 2048
"""The drafting LLM's output cap (design §6.3)."""
BATCH_UNITS = 10
"""At most 10 units per batch, one batch in flight (design §6.3)."""
MAX_HTTP_IN_FLIGHT = 30
"""At most 30 HTTP attempts in flight inside a batch (design §6.3)."""
UNIT_REQUEUES = 2
UNIT_REQUEUE_WAIT_S = 30.0
"""Plan §11 D11."""
CHUNK_CHARS = 72_000
"""The grader chunk bound, in characters of item JSON (design §3 step 3)."""
START_GATE_SHARE = 0.60
"""The start gate's rejection share (design §6.3)."""
PACKING_SEEDS = (20261019, 4858)
"""Each set's (case, configuration) list is shuffled by the first, the concatenation by the second (STATS48-R6-4);
the drafting phase's documents by the second alone (FEAS48-R8-1)."""
DIAGNOSTIC_SEED = 4858
"""The 96 diagnostic P-set items' draw (design §3)."""
