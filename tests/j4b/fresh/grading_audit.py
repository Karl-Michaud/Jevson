"""The allowlist audit of one grader session's transcript (design §3 step 6; plan §4.1 `grading_audit.py`).

A chunk fails, and its labels are void, if its session's transcript shows: a tool outside {Read, Write, Edit, Glob,
Grep}; an assistant content block other than text, thinking or `tool_use` (a `server_tool_use` call of the deferred
`advisor` server tool the B9 request carried, RC1-3); a sidechain or subagent (`"isSidechain": true`, or a
`<session>/subagents/agent-*.jsonl` file); a path outside the grading directory, or any `file://` URL; a compaction
(`compact_boundary` or `"isCompactSummary": true`); Read results on the chunk file that, together, did not return
every line 1..N (a PARTIAL page whose rest was never read counts as unread; Grep and Glob do not count); fewer Write
or Edit calls on the label file than the chunk has items; more than one model id, or one other than the pinned id. A
path naming `key.jsonl` or the harness run directory is reported as `key exposure`, which voids all grading of the
attempt.

Usage: python -m tests.j4b.fresh.grading_audit TRANSCRIPT GRADING_DIR NNN ITEMS MODEL
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

ALLOWED = frozenset({"Read", "Write", "Edit", "Glob", "Grep"})
BLOCKS = frozenset({"text", "thinking", "redacted_thinking", "tool_use"})
"""The only assistant content blocks a grader session may show; any other (`server_tool_use`, ...) fails (RC1-3)."""
PATH_KEYS = ("file_path", "path", "notebook_path")
LINE = re.compile(r"^\s*(\d+)\t", re.MULTILINE)
KEY_EXPOSURE = ("key.jsonl", "recordings/fresh")


def records(transcript: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in transcript.read_text(encoding="utf-8").splitlines() if line.strip()]


def _content(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    message = record.get("message")
    content = cast("Mapping[str, Any]", message).get("content") if isinstance(message, dict) else None
    items = cast("list[Any]", content) if isinstance(content, list) else []
    return [cast("dict[str, Any]", c) for c in items if isinstance(c, dict)]


def tool_uses(recs: Sequence[Mapping[str, Any]]) -> Iterator[dict[str, Any]]:
    for record in recs:
        if record.get("type") == "assistant":
            yield from (c for c in _content(record) if c.get("type") == "tool_use")


def block_failures(recs: Sequence[Mapping[str, Any]]) -> list[str]:
    blocks = (c for r in recs if r.get("type") == "assistant" for c in _content(r))
    return [f"an assistant block of type {c.get('type')} ({c.get('name')}) is not allowed"
            for c in blocks if c.get("type") not in BLOCKS]  # fmt: skip


def tool_results(recs: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """tool_use id -> the result's text."""
    out: dict[str, str] = {}
    for record in recs:
        for c in _content(record):
            if c.get("type") == "tool_result":
                body = c.get("content")
                parts = cast("list[Any]", body) if isinstance(body, list) else [body]
                out[str(c.get("tool_use_id"))] = "".join(_text(p) for p in parts)
    return out


def _text(part: Any) -> str:
    return str(cast("dict[str, Any]", part).get("text", "")) if isinstance(part, dict) else str(part)


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in cast("dict[str, Any]", value).values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in cast("list[Any]", value):
            yield from _strings(v)


def path_failures(use: Mapping[str, Any], grading_dir: Path) -> list[str]:
    out: list[str] = []
    data = cast("Mapping[str, Any]", use.get("input") or {})
    for text in _strings(data):
        if any(k in text for k in KEY_EXPOSURE):
            out.append(f"key exposure: {use.get('name')} names {text!r}")
        if "file://" in text:
            out.append(f"a file:// URL in {use.get('name')}")
    for key in PATH_KEYS:
        value = data.get(key)
        if isinstance(value, str):
            path = (grading_dir / value).resolve() if not value.startswith("/") else Path(value).resolve()
            if not path.is_relative_to(grading_dir.resolve()):
                out.append(f"{use.get('name')} touched {value}, outside the grading directory")
    return out


def _file(use: Mapping[str, Any]) -> str:
    return str(cast("Mapping[str, Any]", use.get("input") or {}).get("file_path", ""))


def coverage_failure(recs: Sequence[Mapping[str, Any]], chunk: str, lines: int) -> str | None:
    results = tool_results(recs)
    seen: set[int] = set()
    for use in tool_uses(recs):
        if use.get("name") == "Read" and _file(use).endswith(chunk):
            seen |= {int(n) for n in LINE.findall(results.get(str(use.get("id")), ""))}
    missing = sorted(set(range(1, lines + 1)) - seen)
    return f"Read never returned lines {missing[:5]}... of {chunk}" if missing else None


def audit(transcript: Path, grading_dir: Path, nnn: str, items: int, model: str) -> list[str]:
    """Every reason the chunk fails ([] if it passes)."""
    recs = records(transcript)
    failures: list[str] = []
    uses = list(tool_uses(recs))
    failures += [f"tool {u.get('name')} is not allowed" for u in uses if u.get("name") not in ALLOWED]
    failures += block_failures(recs)
    failures += [f for u in uses for f in path_failures(u, grading_dir)]
    if any(r.get("isSidechain") is True for r in recs):
        failures.append("a sidechain record")
    if list((transcript.parent / transcript.stem / "subagents").glob("agent-*.jsonl")):
        failures.append("a subagent transcript")
    if any(r.get("subtype") == "compact_boundary" or r.get("isCompactSummary") is True for r in recs):
        failures.append("a compaction")
    if (missing := coverage_failure(recs, f"items-{nnn}.jsonl", items)) is not None:
        failures.append(missing)
    writes = [u for u in uses if u.get("name") in ("Write", "Edit") and _file(u).endswith(f"labels-{nnn}.jsonl")]
    if len(writes) < items:
        failures.append(f"the label file was written in {len(writes)} calls for {items} items")
    models = {str(cast("Mapping[str, Any]", r["message"]).get("model")) for r in recs
              if r.get("type") == "assistant" and isinstance(r.get("message"), dict)}  # fmt: skip
    if models != {model}:
        failures.append(f"model ids {sorted(models)}, not exactly the pinned {model}")
    return failures


def main(argv: Sequence[str] | None = None) -> int:
    transcript, grading_dir, nnn, items, model = (argv or sys.argv[1:])[:5]
    failures = audit(Path(transcript), Path(grading_dir), nnn, int(items), model)
    print("\n".join(failures) if failures else f"items-{nnn}.jsonl: audit passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
