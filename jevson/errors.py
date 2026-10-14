"""Jevson's exception hierarchy (DESIGN §6.1).

`CompileError`, `PreflightError`, `UsageError` and `MissingCredentials` are raised before anything
is spent. `SchemaViolation`, `BackendError`, `LLMError` and `ExtractorError` carry the partial
`Result` and its `Cost`.
"""

from __future__ import annotations

from dataclasses import dataclass

from jevson.result import Result
from jevson.types import Cost


class JevsonError(Exception):
    """Base of every exception Jevson raises on purpose."""


@dataclass(frozen=True)
class RefusalReason:
    """Why one schema location (or graph node) cannot be compiled. `pointer` names it."""

    pointer: str
    reason: str
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
    pass


class LLMError(_ProtocolError):
    pass


class ExtractorError(_ProtocolError):
    pass
