"""The `generate` step: messages to the caller's LLM, and reading its answer (DESIGN §6.3, §8).

The LLM is asked for the one-field tool schema `{value: string}`, passed as JSON Schema for the
adapter to render per provider. Its answer is read defensively: anything other than exactly one
`value` string of at most `max_draft_chars` characters is a **failed draft**, never an exception
(a missing or misspelled key, prose instead of a tool call, a non-string, an over-length string).
A redraft resends the conversation with the previous draft and the checks it failed.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from jevson.compile.questions import redraft_prompt
from jevson.types import Drafting, JSONValue, LLMResponse, Message, Rejection

TOOL_SCHEMA: Mapping[str, JSONValue] = {
    "type": "object",
    "properties": {"value": {"type": "string"}},
    "required": ["value"],
    "additionalProperties": False,
}
MALFORMED = "the draft is a single string value of at most {limit} characters"


@dataclass(frozen=True)
class Draft:
    text: str | None
    """The admitted-for-adjudication draft, or None for a failed (malformed) one."""
    shown: str
    """What a rejection records: the draft, or the start of whatever came back instead."""
    input_tokens: int = 0
    output_tokens: int = 0


def messages(drafting: Drafting, source: str, rejection: Rejection | None) -> tuple[Message, ...]:
    first = Message("user", f"{drafting.prompt}\n\n{source}")
    if rejection is None:
        return (first,)
    return (
        first,
        Message("assistant", rejection.draft),
        Message("user", redraft_prompt(drafting.label, rejection.criteria)),
    )


def read(response: object, limit: int) -> Draft:
    """The draft in an LLM answer, whatever came back. Never raises."""
    if not isinstance(response, LLMResponse):
        return Draft(None, "")
    tokens = (_count(response.input_tokens), _count(response.output_tokens))
    received = cast("object", response.raw)  # a caller's LLM may break its own type hints
    raw = received if isinstance(received, str) else ""
    arguments = cast("object", response.arguments)
    value: object = None
    if isinstance(arguments, Mapping):
        fields = cast("Mapping[str, object]", arguments)
        value = fields["value"] if set(fields) == {"value"} else None
    if isinstance(value, str) and len(value) <= limit:
        return Draft(value, value, *tokens)
    shown = value if isinstance(value, str) else raw
    return Draft(None, shown[:limit], *tokens)


def malformed(limit: int) -> str:
    return MALFORMED.format(limit=limit)


def _count(tokens: object) -> int:
    return tokens if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0 else 0
