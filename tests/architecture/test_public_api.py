"""PLAN Phase 1: the public API is exported from `__init__.py`, and nothing else is."""

from __future__ import annotations

import types

import jevson

EXPECTED = {
    # PLAN §2's surface, as far as Phase 1 builds it
    "Result",
    "FakeBackend",
    "DecisionsBackend",
    "CachingBackend",
    "Jevson",
    "JevsonConfig",
    "compile_schema",
    "ReplayLLM",
    "dry_run",
    "DryRun",
    # the exception hierarchy
    "JevsonError",
    "CompileError",
    "RefusalCode",
    "RefusalReason",
    "PreflightError",
    "UsageError",
    "MissingCredentials",
    "SchemaViolation",
    "BackendError",
    "LLMError",
    "ExtractorError",
    # the five protocols
    "Backend",
    "Extractor",
    "LLM",
    "Normalizer",
    "CostSink",
    # reading a Result
    "Absent",
    "Cost",
    "DecidedBy",
    "Decision",
    "DecisionKind",
    "DeclaredOption",
    "Overflow",
    "Provenance",
    "Rejection",
    "Span",
    "Unresolved",
    "UnresolvedReason",
    "Violation",
    # implementing a protocol
    "Answer",
    "BackendResponse",
    "Candidate",
    "ChoiceAnswer",
    "CostEvent",
    "FieldSpec",
    "InvalidAnswer",
    "LLMResponse",
    "Message",
    "Option",
    "PredicateAnswer",
    "Question",
    "Refusal",
    "ScoreAnswer",
}


def test_all_is_exactly_the_public_surface() -> None:
    assert set(jevson.__all__) == EXPECTED
    assert len(jevson.__all__) == len(EXPECTED)


def test_every_exported_name_resolves() -> None:
    for name in jevson.__all__:
        assert getattr(jevson, name) is not None


def test_nothing_else_public_is_exported() -> None:
    public = {
        name
        for name, value in vars(jevson).items()
        if not name.startswith("_") and not isinstance(value, types.ModuleType)
    }
    assert public == EXPECTED
