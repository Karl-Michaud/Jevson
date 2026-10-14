"""The type model: graph nodes, provenance, decisions, result entries, and protocol payloads.

Every type is a frozen dataclass or a string enum. Probabilities that Jevson stores are integer
hundredths (DESIGN §2.1); the protocol payloads in the last section carry the raw floats a backend
returned, because the sum check runs on raw values before rounding.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal, TypeAlias

JSONValue: TypeAlias = "bool | int | float | str | list[JSONValue] | dict[str, JSONValue] | None"

NONE_OF_THESE = "none_of_these"
"""The option id of the abstention option every candidate-backed choice carries (R1)."""

MAX_OPTIONS = 255
"""The API's upper bound on `choice` options (DESIGN §2.2)."""


class DecisionKind(StrEnum):
    CHOICE = "choice"
    SCORE = "score"
    PREDICATE = "predicate"


class StepKind(StrEnum):
    EXTRACT = "extract"
    GENERATE = "generate"


class OptionSource(StrEnum):
    SCHEMA_ENUM = "schema_enum"
    SCHEMA_RUBRIC = "schema_rubric"
    CANDIDATE_SPANS = "candidate_spans"
    PREDICATE = "predicate"


class ProvenanceKind(StrEnum):
    SOURCE_SPAN = "source_span"
    DECLARED_OPTION = "declared_option"


class DecidedBy(StrEnum):
    CODE = "code"
    DECISION = "decision"
    LLM_DECISION = "llm+decision"
    LLM = "llm"
    DIRECT = "direct"
    CALLER = "caller"


class UnresolvedReason(StrEnum):
    """The closed set of DESIGN §6.1. `not_yet_supported` is a CompileError reason, not this."""

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

    Only the shape is checked here. Substring and grapheme-boundary verification is
    `extract/spans.py`, which is not built yet.
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

    def __post_init__(self) -> None:
        is_predicate = self.kind is DecisionKind.PREDICATE
        if is_predicate != (self.option_source is OptionSource.PREDICATE):
            raise ValueError(f"{self.id}: a predicate, and only a predicate, has option_source predicate")
        if is_predicate and self.options:
            raise ValueError(f"{self.id}: a predicate has no options")
        if not is_predicate and not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError(f"{self.id}: a {self.kind} needs 2-{MAX_OPTIONS} options, got {len(self.options)}")
        ids = [option.id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.id}: option ids must be unique")
        if self.option_source is OptionSource.CANDIDATE_SPANS and NONE_OF_THESE not in ids:
            raise ValueError(f"{self.id}: a candidate-backed choice must offer {NONE_OF_THESE} (R1)")


@dataclass(frozen=True)
class StepNode:
    """An external step: extraction through an Extractor, or drafting through an LLM."""

    id: str
    kind: StepKind
    target: str
    dependencies: frozenset[str] = frozenset()

    @property
    def protocol(self) -> Literal["Extractor", "LLM"]:
        return "Extractor" if self.kind is StepKind.EXTRACT else "LLM"

    @property
    def produces(self) -> Literal["candidates", "draft"]:
        return "candidates" if self.kind is StepKind.EXTRACT else "draft"


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
    pointer: str
    reason: UnresolvedReason
    candidates_seen: tuple[Span, ...] = ()
    abstain_probability: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Absent:
    pointer: str
    candidates_seen: tuple[Span, ...] = ()
    abstain_probability: int | None = None


@dataclass(frozen=True)
class Violation:
    pointer: str
    keyword: str
    message: str


@dataclass(frozen=True)
class Overflow:
    pointer: str
    spans: tuple[Span, ...]
    membership_probability: tuple[int, ...]


@dataclass(frozen=True)
class Rejection:
    pointer: str
    criteria: tuple[str, ...]
    draft: str


@dataclass(frozen=True)
class Cost:
    decision_requests: int = 0
    decision_input_tokens: int = 0
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
    name: str
    probability: float


@dataclass(frozen=True)
class ChoiceAnswer:
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


Answer: TypeAlias = PredicateAnswer | ChoiceAnswer | ScoreAnswer | Refusal


@dataclass(frozen=True)
class BackendResponse:
    answers: tuple[Answer, ...]
    input_tokens: int
    request_id: str
    model: str


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
    id: str
    text: str
    span: Span
    context: str | None = None


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMResponse:
    arguments: Mapping[str, JSONValue] | None
    raw: str
    input_tokens: int
    output_tokens: int


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
