"""`ReplayLLM`: exact replay of recorded LLM responses (DESIGN §8.4).

The same scheme as `CachingBackend`: the key is the SHA-256 of the RFC 8785 canonical JSON of the
caller's LLM id, the messages and the tool schema, so recordings from two different LLMs never
collide. Responses are stored whole (arguments, raw text, token counts) and returned verbatim on a
hit, so a replayed run's `Result`, `Cost` included, is identical to the recorded one. A request that
cannot be canonicalised is passed through and not recorded. With `replay_only=True` a miss raises
`LLMError(replay_miss)`. Files are written only under the caller's directory, atomically.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import rfc8785

from jevson.errors import LLMError, UsageError
from jevson.protocols import LLM
from jevson.result import Result
from jevson.types import JSONValue, LLMResponse, Message

FORMAT_VERSION = 1


class ReplayLLM:
    def __init__(
        self, inner: LLM | None, directory: str | os.PathLike[str], *, llm_id: str, replay_only: bool = False
    ) -> None:
        if inner is None and not replay_only:
            raise UsageError("ReplayLLM needs an inner LLM unless replay_only=True")
        if not llm_id:
            raise UsageError("ReplayLLM needs the caller's LLM id, so recordings from two LLMs never collide")
        self._inner = inner
        self._directory = Path(directory)
        self._llm_id = llm_id
        self._replay_only = replay_only
        self.hits = 0
        self.misses = 0

    def __repr__(self) -> str:
        return (
            f"ReplayLLM(llm_id={self._llm_id!r}, directory={str(self._directory)!r}, replay_only={self._replay_only})"
        )

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        key = replay_key(self._llm_id, messages, tool_schema)
        path = self._directory / f"{key}.json" if key is not None else None
        if path is not None and path.exists():
            self.hits += 1
            return _load(path)
        self.misses += 1
        if self._replay_only or self._inner is None:
            reason = "no recorded response" if key is not None else "the request cannot be canonicalised"
            raise LLMError("replay_miss", reason, Result({}, False))
        response = await self._inner.complete(messages, tool_schema)
        if path is not None:
            _store(path, response)
        return response


def replay_key(llm_id: str, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> str | None:
    request = {
        "version": FORMAT_VERSION,
        "llm": llm_id,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "tool_schema": tool_schema,
    }
    try:
        canonical = rfc8785.dumps(request)
    except (rfc8785.CanonicalizationError, TypeError, ValueError):
        return None
    return hashlib.sha256(canonical).hexdigest()


def _store(path: Path, response: LLMResponse) -> None:
    try:
        text = json.dumps({
            "version": FORMAT_VERSION,
            "arguments": None if response.arguments is None else dict(response.arguments),
            "raw": response.raw,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        })  # fmt: skip
    except (TypeError, ValueError, AttributeError):
        return  # a response JSON cannot hold cannot be replayed; it passes through unrecorded
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            file.write(text)
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _load(path: Path) -> LLMResponse:
    try:
        record = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        return LLMResponse(record["arguments"], record["raw"], record["input_tokens"], record["output_tokens"])
    except (ValueError, KeyError, TypeError) as error:
        raise LLMError("replay_corrupt", f"{path.name}: {type(error).__name__}", Result({}, False)) from None
