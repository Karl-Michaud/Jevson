"""The type model: graph nodes, provenance, decisions, result entries, and protocol payloads.

Every type is a frozen dataclass or a string enum. Probabilities that Jevson stores are integer
hundredths (DESIGN §2.1); the protocol payloads in the last section carry the raw floats a backend
returned, because the sum check runs on raw values before rounding.

Length (~430 lines, over the ~400 convention): this is the public type model that `__init__.py`
re-exports, one small frozen dataclass or enum each with its docstring; splitting it would only move
re-exports around. Split by payload family (protocol payloads, result entries) if it grows again.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, TypeAlias

from jevson.checks import Check

JSONValue: TypeAlias = "bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None"

MAX_OPTIONS = 255
"""The API's upper bound on `choice` options (DESIGN §2.2)."""


class DecisionKind(StrEnum):
    """The decision primitive a question uses: `choice`, `score` (ordinal levels) or `predicate`."""

    CHOICE = "choice"
    SCORE = "score"
    PREDICATE = "predicate"


class StepKind(StrEnum):
    EXTRACT = "extract"
    GENERATE = "generate"


class OptionSource(StrEnum):
    """`candidate_spans` (class D) is deferred with source selection (PLAN §9.2); v0 has none."""

    SCHEMA_ENUM = "schema_enum"
    SCHEMA_RUBRIC = "schema_rubric"
    SCHEMA_UNION = "schema_union"
    """A union discriminator's options: one per branch (DESIGN §3.2)."""
    PREDICATE = "predicate"


class ProvenanceKind(StrEnum):
    SOURCE_SPAN = "source_span"
    DECLARED_OPTION = "declared_option"


class DecidedBy(StrEnum):
    """How a field's value was decided; `Result.decided_by` maps each pointer to one of these."""

    CODE = "code"
    DECISION = "decision"
    LLM_DECISION = "llm+decision"
    LLM = "llm"
    DIRECT = "direct"
    CALLER = "caller"


class UnresolvedReason(StrEnum):
    """The closed set of DESIGN §6.1. Reachable in v0: tie, invalid_backend_answer, budget_exceeded,
    redraft_exhausted, dependency_unresolved, refused; the rest are reserved for deferred work."""

    ABSTAINED = "abstained"
    NO_CANDIDATES = "no_candidates"
    TIE = "tie"
    INVALID_BACKEND_ANSWER = "invalid_backend_answer"
    TOO_MANY_CANDIDATES = "too_many_candidates"
    BUDGET_EXCEEDED = "budget_exceeded"
    UNPARSEABLE = "unparseable"
    ENTITY_CONFLICT = "entity_conflict"
    REDRAFT_EXHAUSTED = "redraft_exhausted"
    SOURCE_FLAGGED = "source_flagged"
    VERIFICATION_FAILED = "verification_failed"
    DEPENDENCY_UNRESOLVED = "dependency_unresolved"
    REFUSED = "refused"


# --- provenance (DESIGN §5.9) ---------------------------------------------------------------


@dataclass(frozen=True)
class Span:
    """A half-open [start, end) range of Python `str` code-point offsets into one original source.

    Kept so reviving class D is not a breaking change; no v0 code constructs one (DESIGN §5.9).
    """

    source_id: str
    start: int
    end: int

    def __post_init__(self) -> None:
        if not 0 <= self.start < self.end:
            raise ValueError(f"span offsets must satisfy 0 <= start < end, got [{self.start}, {self.end})")


@dataclass(frozen=True)
class DeclaredOption:
    """A value chosen from a declared option set: a schema enum value or a rubric level."""

    option_id: str


Provenance: TypeAlias = Span | DeclaredOption

Gates: TypeAlias = tuple[tuple[str, str], ...]
"""The (discriminator node id, option id) pairs, outermost first, that must all be selected for a
node inside union branches to run (DESIGN §3.2). Empty outside every union."""


# --- the decision graph (DESIGN §3.1) -------------------------------------------------------


@dataclass(frozen=True)
class Option:
    """One option of a choice, or one level of a score (lowest first). `id` is opaque (R13)."""

    id: str
    description: str


@dataclass(frozen=True)
class DecisionNode:
    id: str
    kind: DecisionKind
    question: str
    option_source: OptionSource
    target: str
    options: tuple[Option, ...] = ()
    dependencies: frozenset[str] = frozenset()
    provenance: ProvenanceKind | None = None
    values: tuple[JSONValue, ...] = ()
    """The schema value each option stands for, aligned with `options`; empty for a predicate or a
    hand-built node. Descriptions are quoted text, so `1` and `"1"` cannot be recovered from them."""
    branch: Gates = ()
    member: JSONValue = None
    """A multi-label enum array's membership predicate: the declared value it asks about (DESIGN §4.2)."""
    max_items: int | None = None
    """The array's `maxItems`, on each of its membership predicates."""

    @property
    def key(self) -> str:
        """Where the executor keeps this node's outcome: its target, or its id for a membership
        predicate, whose array pointer it shares with the array's other values."""
        return self.target if self.member is None else self.id

    def __post_init__(self) -> None:
        if self.member is not None and self.kind is not DecisionKind.PREDICATE:
            raise ValueError(f"{self.id}: a membership node is a predicate")
        if self.values and len(self.values) != len(self.options):
            raise ValueError(f"{self.id}: values must align with options")
        is_predicate = self.kind is DecisionKind.PREDICATE
        if is_predicate != (self.option_source is OptionSource.PREDICATE):
            raise ValueError(f"{self.id}: a predicate, and only a predicate, has option_source predicate")
        if is_predicate and self.options:
            raise ValueError(f"{self.id}: a predicate has no options")
        if not is_predicate and not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError(f"{self.id}: a {self.kind} needs 2-{MAX_OPTIONS} options, got {len(self.options)}")
        if len({option.id for option in self.options}) != len(self.options):
            raise ValueError(f"{self.id}: option ids must be unique")


@dataclass(frozen=True)
class Drafting:
    """What a `generate` step needs (DESIGN §6.3): its rendered prompt, its label for a redraft, the
    draft limit, and each of its adjudication nodes' checks (`jevson/checks.py`: node id, text and pass
    rule), in declared order. `rubric_minimum` is the id of the lowest passing rubric level, when the
    field declares a rubric."""

    prompt: str
    label: str
    max_draft_chars: int = 4000
    checks: tuple[Check, ...] = ()
    rubric_minimum: str | None = None


@dataclass(frozen=True)
class StepNode:
    """An external step: drafting through an LLM (v0), or extraction (class D, deferred)."""

    id: str
    kind: StepKind
    target: str
    dependencies: frozenset[str] = frozenset()
    drafting: Drafting | None = None
    """Set on every compiled `generate` step; an extraction step has none."""
    branch: Gates = ()

    @property
    def key(self) -> str:
        return self.target

    @property
    def protocol(self) -> Literal["Extractor", "LLM"]:
        return "Extractor" if self.kind is StepKind.EXTRACT else "LLM"


@dataclass(frozen=True)
class Constant:
    """A class A value committed by code (DESIGN §3.5): a required constant with no default, or any
    constant of a union branch, which is committed when its branch is selected."""

    pointer: str
    value: JSONValue
    branch: Gates = ()


# --- result entries (DESIGN §8.1) -----------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    """One asked decision. `selected` is None when nothing was selected (refusal, invalid answer)."""

    kind: DecisionKind
    selected: str | bool | None
    distribution_hundredths: Mapping[str, int]
    vendor_confidence: float | None
    target_pointer: str


@dataclass(frozen=True)
class Unresolved:
    """A hole in the result: the pointer and a reason from the closed set (DESIGN §6.1)."""

    pointer: str
    reason: UnresolvedReason
    candidates_seen: tuple[Span, ...] = ()
    abstain_probability: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Absent:
    """Reserved: in v0 nothing abstains, so `Result.absent` is always empty (DESIGN §5.6)."""

    pointer: str
    candidates_seen: tuple[Span, ...] = ()
    abstain_probability: int | None = None


@dataclass(frozen=True)
class Violation:
    """A failed schema constraint on `.value`: the pointer, the JSON Schema keyword, and the message."""

    pointer: str
    keyword: str
    message: str


@dataclass(frozen=True)
class Overflow:
    """Accepted members a `maxItems` dropped (R8): spans for a source-grounded array (deferred), or the
    declared `values` of a multi-label enum array, aligned with their membership probabilities."""

    pointer: str
    spans: tuple[Span, ...]
    membership_probability: tuple[int, ...]
    values: tuple[JSONValue, ...] = ()


@dataclass(frozen=True)
class Rejection:
    """A draft adjudication rejected, with the checks it failed (criteria or rubric); the field keeps
    its name, `criteria`."""

    pointer: str
    criteria: tuple[str, ...]
    draft: str


@dataclass(frozen=True)
class Cost:
    """What one call spent: decision requests and tokens, LLM tokens, cache hits, retries and redrafts."""

    decision_requests: int = 0
    decision_input_tokens: int = 0
    decision_input_tokens_estimated: int = 0
    """Preflight's estimate for the same requests `decision_input_tokens` counts (DESIGN §8.2)."""
    decision_request_ids: tuple[str, ...] = ()
    cache_hits: int = 0
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    decision_retries: int = 0
    transport_retries: int = 0
    redrafts: int = 0
    level_splits: int = 0
    wall_clock_by_component: Mapping[str, float] = field(default_factory=dict[str, float])


# --- protocol payloads (DESIGN §2.1, §8) ----------------------------------------------------


@dataclass(frozen=True)
class Question:
    """One named question in a request. `name` is opaque (q0…qN); `options` are levels for a score."""

    name: str
    kind: DecisionKind
    instructions: str
    options: tuple[Option, ...] = ()


@dataclass(frozen=True)
class PredicateAnswer:
    """A `predicate` answer: the probability of yes. Predicates carry no confidence."""

    name: str
    probability: float


@dataclass(frozen=True)
class ChoiceAnswer:
    """A `choice` answer: the chosen option id, the distribution over option ids, and the API's confidence."""

    name: str
    choice: str
    probabilities: Mapping[str, float]
    confidence: float | None = None


@dataclass(frozen=True)
class ScoreAnswer:
    """`score` is the vendor's probability-weighted mean of level indices; `probabilities` is keyed
    by level id. The value Jevson commits is the most probable level, never `score`."""

    name: str
    score: float
    probabilities: Mapping[str, float]
    confidence: float | None = None


@dataclass(frozen=True)
class Refusal:
    """The API declined this question (DESIGN §2.1). Never an option, a default, or an absence."""

    name: str


@dataclass(frozen=True)
class InvalidAnswer:
    """A well-formed response carried no usable answer for this question (DESIGN §6.1): a missing,
    duplicated, misplaced or mis-typed entry. It resolves to `Unresolved(invalid_backend_answer)`."""

    name: str
    detail: str


Answer: TypeAlias = PredicateAnswer | ChoiceAnswer | ScoreAnswer | Refusal | InvalidAnswer


@dataclass(frozen=True)
class BackendResponse:
    """A backend's answers to one request, with the billed input tokens, request id and returned model."""

    answers: tuple[Answer, ...]
    input_tokens: int
    request_id: str
    model: str
    cache_hit: bool = False
    """True when a `CachingBackend` served the response from its directory; nothing was spent."""
    transport_retries: int = 0
    """Failed attempts retried before this response (DESIGN §6.1), counted apart from decision retries."""
    retried_request_ids: tuple[str, ...] = ()
    """Request ids of those failed attempts, where the server sent one (PLAN §3)."""


@dataclass(frozen=True)
class FieldSpec:
    """What an Extractor needs to know about the field it extracts for (DESIGN §3.5 `source`)."""

    pointer: str
    extractor: str
    entity_type: str | None = None
    scope: str | None = None
    max_candidates: int = 50
    max_candidate_chars: int = 120
    locale: str = "en-US"


@dataclass(frozen=True)
class Candidate:
    """A candidate span offered for source selection. Reserved: v0 selects nothing from the source."""

    id: str
    text: str
    span: Span
    context: str | None = None


@dataclass(frozen=True)
class Message:
    """One chat message sent to the caller's LLM."""

    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResponse:
    """An LLM completion: the tool-call arguments (None if there were none), the raw text, and token counts."""

    arguments: Mapping[str, JSONValue] | None
    raw: str
    input_tokens: int
    output_tokens: int
    model: str | None = None
    """The model id the LLM reported, recorded per R15 (`CostEvent.model`, `Result.versions["llm_model"]`)."""


@dataclass(frozen=True)
class CostEvent:
    """One spend event, emitted to the CostSink as it happens; failures are counted too."""

    component: Literal["decision", "llm", "extractor"]
    request_id: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_hit: bool = False
    transport_retry: bool = False
    succeeded: bool = True
    estimated_input_tokens: int | None = None
    """For a decision request, preflight's estimate of its input, beside the billed `input_tokens`."""
    model: str | None = None
    """The model string the response named (R15): the API's for a decision, the LLM's for `llm`;
    None for a failed attempt or an LLM that reports none."""
