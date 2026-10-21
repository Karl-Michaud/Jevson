"""The dry run's figures and the batch reservations (design §6.3; plan §7 "dryrun", §11 D10; FEAS48-7, FEAS48-8,
FEAS48-R10-3).

- **The cost model** is the design's (`S/exp/design-update/cost3.py`, `S/exp/feas-r3-4858cap/worst.py`): preflight
  tokens (chars + drafts x 536 + 60) / 3 + 160 per question + 8 per option (2 per predicate), 3.5 criteria per
  R-set field, run 1's $0.00193 per drafting call, and cost3.py's first-draft rejection shares per configuration;
  only the inputs (case counts and source sizes) come from the built fixtures.
- **Bounds** are `bounds.py`'s: each request's wire bytes + 64 tokens, + 160 per question and 8 per option for a
  decision request (D21), and for drafting the 2,048-token output cap; a draft not yet seen is reserved at
  `max_draft_chars` x `BYTES_PER_CHAR`: 7 on the decision side and 6 on the chat side for the run (D10); the
  design's R_max uses 4.
- **The margin check** compares each decision request's metered bound, bytes + 64 + 160 q + 8 o (plan §11 D21), with
  the harness formula ceil(bytes / 3) + 160 q + 8 o over the questions and options it was built with, never with the
  library's `+dw` estimate.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from tests.j4b.fresh.constants import CAP, DECISION_OPTION_TOKENS, DECISION_QUESTION_TOKENS, NANO, PRICE

Q_TOKENS, O_TOKENS = DECISION_QUESTION_TOKENS, DECISION_OPTION_TOKENS
CRITERIA_PER_FIELD, DRAFT_CHARS = 3.5, 536
DCALL_USD = 0.00193
P7_TOKENS_PER_ARM = 39_563
SHARES = {
    "L0F0": 0.55,
    "L1F0": 0.60,
    "L2F0": 0.55,
    "L3F0": 0.60,
    "L0F1": 0.40,
    "L1F1": 0.40,
    "L2F1": 0.40,
    "L3F1": 0.40,
}
"""cost3.py's assumed first-draft rejection shares (UNVERIFIED): 0.55 baseline, 0.60 with the screen, 0.40 under F1."""
SCREENS = {"L0": 0, "L1": 1, "L2": 0, "L3": 1}
BYTES_PER_CHAR = {"design": 4, "decision": 7, "chat": 6}


def tok(source_chars: float, drafts: float, questions: float) -> float:
    return (source_chars + drafts * DRAFT_CHARS + 60) / 3 + Q_TOKENS * questions + O_TOKENS * 2 * questions


@dataclass(frozen=True)
class Split:
    """One phase's sizes from the built fixtures: I-set case source lengths, P-set draft source lengths, R-set
    document lengths, fields per document, and whether [P7] runs (confirm only)."""

    iset: Sequence[int]
    pset: Sequence[int]
    rset: Sequence[int]
    fields: int = 3
    p7: bool = False


def decisions_usd(split: Split, share: Callable[[str], float]) -> float:
    i_tok = sum(2 * (tok(c, 2, 2) + tok(c, 2, 4)) for c in split.iset)
    p7_tok = (2 * P7_TOKENS_PER_ARM + 2 * (P7_TOKENS_PER_ARM + 80 * 2 * (Q_TOKENS + 2 * O_TOKENS))) if split.p7 else 0
    p_tok = sum(4 * tok(c, 1, 1) + 4 * tok(c, 1, 2) for c in split.pset)
    r_tok = 0.0
    for config, s in ((c, share(c)) for c in SHARES):
        checks = CRITERIA_PER_FIELD + SCREENS[config[:2]]
        p_any = 1 - (1 - s) ** split.fields
        r_tok += sum(tok(c, split.fields, split.fields * checks) for c in split.rset)
        if p_any > 0:
            redrafted = split.fields * s / p_any
            r_tok += sum(p_any * tok(c, redrafted, redrafted * checks) for c in split.rset)
    return (i_tok + p7_tok + p_tok + r_tok) * PRICE["decision_in"] / NANO


def drafting_usd(split: Split, share: Callable[[str], float]) -> float:
    first = len(split.rset) * split.fields
    return (first + sum(len(split.rset) * split.fields * share(c) for c in SHARES)) * DCALL_USD


def expected_usd(splits: Sequence[Split]) -> float:
    return sum(decisions_usd(s, SHARES.__getitem__) + drafting_usd(s, SHARES.__getitem__) for s in splits)


def start_gate_usd(splits: Sequence[Split]) -> float:
    """The start gate's figure: decisions at the assumed shares, every configuration redrafting 60% (cost3.py)."""
    return sum(decisions_usd(s, SHARES.__getitem__) + drafting_usd(s, lambda _: 0.60) for s in splits)


def attempt_usd(splits: Sequence[Split], s: float) -> float:
    """One attempt at one rejection share for every configuration (gate.py's `attempt`); s = 1 is the
    all-rejected figure at run 1's mean call (worst.py), not a bound."""
    return sum(decisions_usd(x, lambda _: s) + drafting_usd(x, lambda _: s) for x in splits)


def two_attempt_share(splits: Sequence[Split], r_max_nano: int) -> float:
    """The share up to which two complete attempts fit under $15 - R_max: attempt(s) <= (15 - R_max) / 2."""
    target = (CAP - r_max_nano) / NANO / 2
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if attempt_usd(splits, mid) <= target else (lo, mid)
    return lo


# --- the decision-bound margin ------------------------------------------------------------------------


def harness_formula(body: int, questions: int, options: int) -> int:
    """The harness's estimate of a decision request's billed tokens: ceil(bytes / 3) + 160 q + 8 o."""
    return math.ceil(body / 3) + Q_TOKENS * questions + O_TOKENS * options


def margin(bound: int, body: int, questions: int, options: int) -> int:
    """A request's metered input bound (`metering.input_bound`) - the harness formula over the questions and options
    the request was built with; the dry run raises before any spend if it is negative."""
    return bound - harness_formula(body, questions, options)
