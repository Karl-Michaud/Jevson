"""Jevson: source-grounded structured extraction.

The public surface is exactly `__all__`. Phase 1 ships the result type, the fake backend, the
configuration, the exception hierarchy, the five protocols, and the types needed to read a
`Result` or implement a protocol; Phase 2 adds `compile_schema`; Phase 3 adds `DecisionsBackend`,
`CachingBackend` and `Jevson`; Phase 4 adds `ReplayLLM` and `dry_run` (PLAN §2).
"""

from jevson.adjudicate.dryrun import DryRun, dry_run
from jevson.backends.caching import CachingBackend
from jevson.backends.decisions import DecisionsBackend
from jevson.backends.fake import FakeBackend
from jevson.compile.compiler import compile_schema
from jevson.config import JevsonConfig
from jevson.errors import (
    BackendError,
    CompileError,
    ExtractorError,
    JevsonError,
    LLMError,
    MissingCredentials,
    PreflightError,
    RefusalCode,
    RefusalReason,
    SchemaViolation,
    UsageError,
)
from jevson.facade import Jevson
from jevson.llm.replay import ReplayLLM
from jevson.protocols import LLM, Backend, CostSink, Extractor, Normalizer
from jevson.result import Result
from jevson.types import (
    Absent,
    Answer,
    BackendResponse,
    Candidate,
    ChoiceAnswer,
    Cost,
    CostEvent,
    DecidedBy,
    Decision,
    DecisionKind,
    DeclaredOption,
    FieldSpec,
    InvalidAnswer,
    LLMResponse,
    Message,
    Option,
    Overflow,
    PredicateAnswer,
    Provenance,
    Question,
    Refusal,
    Rejection,
    ScoreAnswer,
    Span,
    Unresolved,
    UnresolvedReason,
    Violation,
)

__all__ = [
    "LLM",
    "Absent",
    "Answer",
    "Backend",
    "BackendError",
    "BackendResponse",
    "CachingBackend",
    "Candidate",
    "ChoiceAnswer",
    "CompileError",
    "Cost",
    "CostEvent",
    "CostSink",
    "DecidedBy",
    "Decision",
    "DecisionKind",
    "DecisionsBackend",
    "DeclaredOption",
    "DryRun",
    "Extractor",
    "ExtractorError",
    "FakeBackend",
    "FieldSpec",
    "InvalidAnswer",
    "Jevson",
    "JevsonConfig",
    "JevsonError",
    "LLMError",
    "LLMResponse",
    "Message",
    "MissingCredentials",
    "Normalizer",
    "Option",
    "Overflow",
    "PredicateAnswer",
    "PreflightError",
    "Provenance",
    "Question",
    "Refusal",
    "RefusalCode",
    "RefusalReason",
    "Rejection",
    "ReplayLLM",
    "Result",
    "SchemaViolation",
    "ScoreAnswer",
    "Span",
    "Unresolved",
    "UnresolvedReason",
    "UsageError",
    "Violation",
    "compile_schema",
    "dry_run",
]
