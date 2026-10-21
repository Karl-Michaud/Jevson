"""A harness-only `LLM` over OpenAI chat completions (J4b's drafting model). Never imported by the library.

The tool schema Jevson passes (`{value: string}`) is sent as one strict function tool that the model must call, with
`reasoning_effort="none"`, which chat completions requires for function tools on this model. The call's JSON
arguments become `LLMResponse.arguments`, and anything unreadable comes back as `arguments=None` with the raw text,
which Jevson treats as a failed draft. 429, 5xx and dropped connections are retried with backoff. The key
is passed in by the harness (`tests/integration/key.py`) and never logged.

For the metered ASTERION-48/-58 run (design §6.3; plan §4.1): `max_completion_tokens` is sent only when set, so
`run_redraft.py`'s requests are unchanged; a reply cut at the cap (`finish_reason == "length"`) and arguments that
cannot be encoded as UTF-8 (a lone surrogate) are failed drafts (plan §11 D17); `transport` takes the metered
`httpx` transport; `on_attempt` is called before and after each POST; `sleep` is injectable, so a test never
waits on the wall clock. The returned model fills `LLMResponse.model` (R15). `parse` checks for that field, a
compatibility guard for a base whose `LLMResponse` has none; every base since ASTERION-44 has it.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, cast

import httpx

from jevson.types import JSONValue, LLMResponse, Message

URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.4-mini-2026-03-17"
"""Pinned snapshot; $0.75 per million input tokens, $4.50 per million output (published price, 2026-10-16)."""
TOOL = "submit"


class OpenAIChatLLM:
    def __init__(
        self,
        api_key: str,
        *,
        model: str = MODEL,
        reasoning_effort: str = "none",
        retries: int = 4,
        timeout_s: float = 120,
        max_completion_tokens: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        on_attempt: Callable[[str, int | None], None] | None = None,
        sleep: Callable[[float], Awaitable[object]] = asyncio.sleep,
    ) -> None:
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self.model = model
        self._effort = reasoning_effort
        self._retries = retries
        self._timeout = timeout_s
        self._cap = max_completion_tokens
        self._transport = transport
        self._on_attempt = on_attempt
        self._sleep = sleep
        self.returned_models: set[str] = set()

    def __repr__(self) -> str:
        return f"OpenAIChatLLM(model={self.model!r})"

    def body(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "reasoning_effort": self._effort,
        }
        if self._cap is not None:
            body["max_completion_tokens"] = self._cap
        if tool_schema is not None:
            function = {"name": TOOL, "parameters": dict(tool_schema), "strict": True}
            body["tools"] = [{"type": "function", "function": function}]
            body["tool_choice"] = {"type": "function", "function": {"name": TOOL}}
        return body

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        body = self.body(messages, tool_schema)
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            for attempt in range(self._retries + 1):
                self._notify("before", None)
                try:
                    reply = await client.post(URL, headers=self._headers, json=body)
                except httpx.TransportError:
                    self._notify("after", None)
                    if attempt == self._retries:
                        raise
                else:
                    self._notify("after", reply.status_code)
                    if reply.status_code == 200:
                        return self.parse(reply.json())
                    if (reply.status_code != 429 and reply.status_code < 500) or attempt == self._retries:
                        raise RuntimeError(f"chat completions HTTP {reply.status_code}: {reply.text[:300]}")
                await self._sleep(2**attempt)
        raise AssertionError("unreachable")  # pragma: no cover

    def _notify(self, stage: str, status: int | None) -> None:
        if self._on_attempt is not None:
            self._on_attempt(stage, status)

    def parse(self, payload: Mapping[str, Any]) -> LLMResponse:
        self.returned_models.add(str(payload.get("model")))
        usage = cast("Mapping[str, Any]", payload.get("usage") or {})
        choice = cast("Mapping[str, Any]", payload["choices"][0])
        message = cast("Mapping[str, Any]", choice["message"])
        raw = str(message.get("content") or "")
        arguments: dict[str, JSONValue] | None = None
        calls = cast("list[Mapping[str, Any]]", message.get("tool_calls") or [])
        if calls:
            raw = str(calls[0]["function"]["arguments"])
            try:
                parsed: object = json.loads(raw)
            except ValueError:
                parsed = None
            arguments = cast("dict[str, JSONValue]", parsed) if isinstance(parsed, dict) else None
        if choice.get("finish_reason") == "length" or (arguments is not None and not _encodable(arguments)):
            arguments = None
        tokens = (int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        if "model" in {f.name for f in dataclasses.fields(LLMResponse)}:
            return LLMResponse(arguments, raw, *tokens, model=payload.get("model"))  # type: ignore[call-arg]
        return LLMResponse(arguments, raw, *tokens)


def _encodable(arguments: Mapping[str, JSONValue]) -> bool:
    """Whether the arguments can be sent on as UTF-8; a lone surrogate (`\\ud83d`) cannot (plan §11 D17)."""
    try:
        json.dumps(arguments, ensure_ascii=False).encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
