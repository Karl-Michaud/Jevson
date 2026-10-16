"""Transport retry (DESIGN §6.1) and the redraft loop (DESIGN §6.3). v0 has no decision retries.

Transport retries are not decision retries: 429, 5xx, timeouts and dropped connections are retried
with exponential backoff (or the server's `Retry-After`) up to `retries` times, counted separately,
and exempt from the changed-input rule. Every other failure surfaces at once. A context-limit
rejection is never retried unchanged: it surfaces for the executor to split or bisect (DESIGN §8.2).

The redraft loop is per generative field, bounded by `redraft_budget`: a draft that fails a check is
rejected (`Result.rejections` names the checks and the draft) and redrafted with the failing checks
passed back; a draft identical to one already adjudicated is not adjudicated again, keeps its known
verdict, and still spends a redraft; exhaustion is `Unresolved(redraft_exhausted)`. `RedraftLoop`
keeps the books; the executor does the calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TypeVar

from jevson.assemble.assembler import Committed, Outcome
from jevson.execute.drafting import Draft, malformed
from jevson.execute.ratelimit import Sleep
from jevson.types import DecidedBy, Rejection, StepNode, Unresolved, UnresolvedReason

T = TypeVar("T")

RETRYABLE = frozenset({"rate_limited", "server_error", "timeout", "connection"})


class TransportFailure(Exception):
    """One failed attempt. `code` is the `BackendError` code it becomes if it is not retried."""

    def __init__(self, code: str, detail: str, retry_after_s: float | None = None) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail
        self.retry_after_s = retry_after_s


@dataclass(frozen=True)
class TransportPolicy:
    retries: int = 2
    base_delay_s: float = 0.5
    max_delay_s: float = 30.0

    def delay(self, failures: int, retry_after_s: float | None) -> float:
        """Seconds to wait after the `failures`-th failed attempt (1-based)."""
        if retry_after_s is not None:
            return min(max(retry_after_s, 0.0), self.max_delay_s)
        return min(self.base_delay_s * 2 ** (failures - 1), self.max_delay_s)


def parse_retry_after(header: str | None) -> float | None:
    """`Retry-After` in seconds; the HTTP-date form is not used by this API and is ignored."""
    try:
        return float(header) if header is not None else None
    except ValueError:
        return None


async def retrying(attempt: Callable[[], Awaitable[T]], policy: TransportPolicy, sleep: Sleep) -> T:
    """Run `attempt` until it succeeds, fails with a non-retryable code, or retries run out."""
    failures = 0
    while True:
        try:
            return await attempt()
        except TransportFailure as failure:
            if failure.code not in RETRYABLE or failures >= policy.retries:
                raise
            failures += 1
            await sleep(policy.delay(failures, failure.retry_after_s))


@dataclass
class _Field:
    step: StepNode
    limit: int
    redrafts_left: int
    attempt: int = 0
    """0 for the first draft, n for the n-th redraft: decisions are recorded as `node@attempt`."""
    adjudicated: set[str] = field(default_factory=set[str])
    pending: str | None = None
    rejection: Rejection | None = None
    admitted: str | None = None


class RedraftLoop:
    """The redraft bookkeeping of one call, across every generative field."""

    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.fields: dict[str, _Field] = {}
        self.rejections: list[Rejection] = []

    def offer(self, step: StepNode, limit: int, draft: Draft) -> None:
        """Take a new draft for `step`; a well-formed, unseen one waits for adjudication."""
        entry = self.fields.get(step.id)
        if entry is None:
            entry = self.fields[step.id] = _Field(step, limit, self.budget)
        if draft.text is None:
            self._reject(entry, (malformed(limit),), draft.shown)
        elif draft.text not in entry.adjudicated:
            entry.pending = draft.text

    def pending(self) -> dict[str, str]:
        """Drafts awaiting adjudication, by step id."""
        return {step_id: f.pending for step_id, f in self.fields.items() if f.pending is not None}

    def attempt(self, step_id: str) -> int:
        return self.fields[step_id].attempt

    def verdict(self, step_id: str, failing: tuple[str, ...]) -> None:
        entry = self.fields[step_id]
        draft, entry.pending = entry.pending or "", None
        entry.adjudicated.add(draft)
        if failing:
            self._reject(entry, failing, draft)
        else:
            entry.admitted = draft

    def to_redraft(self) -> list[tuple[StepNode, Rejection]]:
        """The fields to redraft now, each with the rejection passed back; spends one redraft each."""
        due: list[tuple[StepNode, Rejection]] = []
        for entry in self.fields.values():
            if entry.admitted is None and entry.rejection is not None and entry.redrafts_left > 0:
                entry.redrafts_left -= 1
                entry.attempt += 1
                due.append((entry.step, entry.rejection))
        return due

    def outcome(self, step_id: str, gated: bool) -> Outcome:
        entry = self.fields[step_id]
        target = entry.step.target
        if entry.admitted is None:
            return Unresolved(target, UnresolvedReason.REDRAFT_EXHAUSTED, detail=f"{entry.attempt} redraft(s)")
        return Committed(target, entry.admitted, DecidedBy.LLM_DECISION if gated else DecidedBy.LLM)

    def _reject(self, entry: _Field, failing: tuple[str, ...], draft: str) -> None:
        entry.rejection = Rejection(entry.step.target, failing, draft)
        self.rejections.append(entry.rejection)
