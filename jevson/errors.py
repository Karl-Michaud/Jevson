"""Jevson's exception hierarchy (DESIGN §6.1).

`CompileError`, `PreflightError`, `UsageError` and `MissingCredentials` are raised before anything
is spent. `SchemaViolation`, `BackendError`, `LLMError` and `ExtractorError` carry the partial
`Result` and its `Cost`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from jevson.result import Result
from jevson.types import Cost


class JevsonError(Exception):
    """Base of every exception Jevson raises on purpose."""


class RefusalCode(StrEnum):
    """The named reasons a `RefusalReason` carries (DESIGN §3.5, §10; PLAN Phase 2).

    `not_yet_supported` promises a later phase; `source_selection_dropped` does not (Phase 0r).
    """

    # graph construction
    DUPLICATE_NODE_ID = "duplicate_node_id"
    UNKNOWN_DEPENDENCY = "unknown_dependency"
    DEPENDENCY_CYCLE = "dependency_cycle"
    # normalisation
    MALFORMED_SCHEMA = "malformed_schema"
    PYDANTIC_TOO_OLD = "pydantic_too_old"
    SCHEMA_TOO_LARGE = "schema_too_large"
    RECURSIVE_REF = "recursive_ref"
    DYNAMIC_REF = "dynamic_ref"
    EXTERNAL_REF = "external_ref"
    REF_SIBLING_CONFLICT = "ref_sibling_conflict"
    NON_FLAT_ALL_OF = "non_flat_all_of"
    DICT_FIELD = "dict_field"
    TUPLE_FIELD = "tuple_field"
    ANY_FIELD = "any_field"
    BYTES_FIELD = "bytes_field"
    ARRAY_OF_OBJECTS = "array_of_objects"
    UNION_IN_ARRAY = "union_in_array"
    ROOT_UNION = "root_union"
    UNSUPPORTED_KEYWORD = "unsupported_keyword"
    ENUM_SIZE = "enum_size"
    # declarations
    UNKNOWN_DECLARATION_KEY = "unknown_declaration_key"
    MALFORMED_DECLARATION = "malformed_declaration"
    MISPLACED_DECLARATION = "misplaced_declaration"
    SEMANTIC_ORDER = "semantic_order"
    SOURCE_AND_GENERATE = "source_and_generate"
    SOURCE_SELECTION_DROPPED = "source_selection_dropped"
    RUBRIC_DESCRIPTION_MISSING = "rubric_description_missing"
    # mapping (checked by compile/mapping.py)
    ORDINAL_LEVELS = "ordinal_levels"
    ENUM_VALUE_TYPE = "enum_value_type"
    INDISTINGUISHABLE_OPTIONS = "indistinguishable_options"
    UNBOUNDED_FIELD = "unbounded_field"
    BOOL_PREDICATE_MISSING = "bool_predicate_missing"
    GENERATE_FIELD_TYPE = "generate_field_type"
    UNDISCRIMINABLE_UNION = "undiscriminable_union"
    # compilation (checked by compile/compiler.py)
    DUPLICATE_QUESTION = "duplicate_question"
    # later phases
    NOT_YET_SUPPORTED = "not_yet_supported"


@dataclass(frozen=True)
class RefusalReason:
    """Why one schema location (or graph node) cannot be compiled. `pointer` names it."""

    pointer: str
    reason: str
    """A `RefusalCode` value; graph construction and later phases share the one set."""
    message: str


class CompileError(JevsonError):
    """The schema cannot be mapped; every offending pointer is named at once (R14)."""

    def __init__(self, reasons: list[RefusalReason]) -> None:
        self.reasons: tuple[RefusalReason, ...] = tuple(reasons)
        listed = "; ".join(f"{r.pointer}: {r.reason} ({r.message})" for r in self.reasons)
        super().__init__(f"cannot compile: {listed}")


class PreflightError(JevsonError):
    """Refused before any backend call: a limit cannot fit, or the call is malformed."""


class UsageError(JevsonError):
    """The library was used wrongly, e.g. `resolve()` inside a running event loop."""


class MissingCredentials(JevsonError):
    """No API key was passed and none is in the environment."""


class _SpentError(JevsonError):
    """An error raised after spending: carries the partial result and what it cost."""

    def __init__(self, message: str, result: Result) -> None:
        super().__init__(message)
        self.result = result
        self.cost: Cost = result.cost


class SchemaViolation(_SpentError):
    """A required field is unresolved and the caller set `raise_on_unresolved_required`."""


class _ProtocolError(_SpentError):
    """A transport or protocol failure. `code` names it, e.g. `timeout` or `replay_miss`."""

    def __init__(self, code: str, message: str, result: Result) -> None:
        super().__init__(f"{code}: {message}", result)
        self.code = code


class BackendError(_ProtocolError):
    """A decision backend failed in transport or protocol; carries the partial `Result` and its `Cost`."""


class LLMError(_ProtocolError):
    """The caller's LLM failed in transport, timed out, or a replay missed; carries the partial `Result`."""


class ExtractorError(_ProtocolError):
    """An extractor failed or timed out. Never raised in v0, which has no extractor step."""
