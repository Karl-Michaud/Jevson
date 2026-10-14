"""The five protocols, with the signatures pinned in DESIGN §8.

The three I/O protocols are async; `Normalizer` and `CostSink` are synchronous. A later phase that
needs a new protocol amends DESIGN §8 first.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from jevson.types import (
    BackendResponse,
    Candidate,
    CostEvent,
    FieldSpec,
    JSONValue,
    LLMResponse,
    Message,
    Question,
    Span,
)


@runtime_checkable
class Backend(Protocol):
    """Asks one level's questions over one shared state; answers come back in question order."""

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse: ...


@runtime_checkable
class Extractor(Protocol):
    """Returns candidate spans into the original source, skipping the spans in `exclude`."""

    async def extract(self, source: str, field: FieldSpec, exclude: Sequence[Span]) -> list[Candidate]: ...


@runtime_checkable
class LLM(Protocol):
    """Completes a conversation, optionally constrained to one tool schema (JSON Schema)."""

    async def complete(
        self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None
    ) -> LLMResponse: ...


@runtime_checkable
class Normalizer(Protocol):
    """Per entity type; used by entity resolution, post-v0."""

    def normalise(self, text: str) -> str: ...

    def representative(self, spans: Sequence[Span]) -> Span: ...


@runtime_checkable
class CostSink(Protocol):
    """Receives every cost event as it happens; may be called from any thread."""

    def record(self, cost_event: CostEvent) -> None: ...
