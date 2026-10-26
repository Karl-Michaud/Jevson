"""H27: the grader-session audit fails on each planted transcript and passes on a clean one (design §3 step 6)."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import grading_audit

MODEL = "claude-opus-5-5"
ITEMS = 24
CHUNK = "items-001.jsonl"


class Transcript:
    def __init__(self, grading: Path) -> None:
        self.grading, self.n = grading, 0
        self.records: list[dict[str, Any]] = []

    def use(self, name: str, result: str = "ok", model: str = MODEL, **data: Any) -> Transcript:
        self.n += 1
        tool_id = f"t{self.n}"
        self.records.append({"type": "assistant", "message": {"model": model, "content": [
            {"type": "tool_use", "id": tool_id, "name": name, "input": data}]}})  # fmt: skip
        returned = {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": result}]}
        self.records.append({"type": "user", "message": {"content": [returned]}})
        return self

    def read(self, first: int, last: int, partial: bool = False) -> Transcript:
        body = "".join(f'{n:6d}\t{{"id": "{n:012x}"}}\n' for n in range(first, last + 1))
        if partial:
            body += f"[Truncated: PARTIAL view ... showing lines {first}-{last} of {ITEMS} total]"
        return self.use("Read", body, file_path=str(self.grading / CHUNK))

    def labels(self, calls: int = ITEMS) -> Transcript:
        for _ in range(calls):
            self.use("Edit", file_path=str(self.grading / "labels-001.jsonl"), old_string="", new_string="{}")
        return self

    def write(self, path: Path) -> Path:
        path.write_text("".join(json.dumps(r) + "\n" for r in self.records))
        return path


def clean(grading: Path) -> Transcript:
    return Transcript(grading).read(1, ITEMS).labels()


def failures(tmp_path: Path, plant: Callable[[Transcript], Any] = lambda t: None) -> list[str]:
    grading = tmp_path / "grading"
    grading.mkdir(exist_ok=True)
    t = clean(grading)
    plant(t)
    return grading_audit.audit(t.write(tmp_path / "session.jsonl"), grading, "001", ITEMS, MODEL)


def test_h27_a_clean_transcript_passes(tmp_path: Path) -> None:
    assert failures(tmp_path) == []


def test_h27_a_partial_read_followed_by_the_rest_passes(tmp_path: Path) -> None:
    grading = tmp_path / "grading"
    grading.mkdir()
    t = Transcript(grading).read(1, 13, partial=True).read(14, 24).labels()
    assert grading_audit.audit(t.write(tmp_path / "s.jsonl"), grading, "001", ITEMS, MODEL) == []


PLANTS: dict[str, Callable[[Transcript], Any]] = {
    "Bash": lambda t: t.use("Bash", command="ls"),
    "connector": lambda t: t.use("mcp__claude_ai_Google_Drive__search", query="x"),
    "chrome file://": lambda t: t.use("mcp__claude-in-chrome__navigate", url="file:///etc/hosts"),
    "subagent tool": lambda t: t.use("Agent", prompt="label these"),
    "sidechain": lambda t: t.records.append({"type": "assistant", "isSidechain": True, "message": {"model": MODEL}}),
    "compact_boundary": lambda t: t.records.append({"type": "system", "subtype": "compact_boundary"}),
    "isCompactSummary": lambda t: t.records.append({"type": "user", "isCompactSummary": True}),
    "outside path": lambda t: t.use("Read", file_path="/etc/hosts"),
    "relative escape": lambda t: t.use("Glob", pattern="*", path="../.."),
    "second model": lambda t: t.use("Glob", model="claude-sonnet-5", pattern="*.jsonl"),
    "key": lambda t: t.use("Grep", pattern="x", path="key.jsonl"),
}


@pytest.mark.parametrize("name", sorted(PLANTS))
def test_h27_each_planted_transcript_fails(tmp_path: Path, name: str) -> None:
    assert failures(tmp_path, PLANTS[name]), name


def test_h27_a_subagent_transcript_file_fails(tmp_path: Path) -> None:
    sub = tmp_path / "session" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-1.jsonl").write_text("{}\n")
    assert "a subagent transcript" in failures(tmp_path)


def test_h27_one_write_for_a_multi_item_chunk_fails(tmp_path: Path) -> None:
    grading = tmp_path / "grading"
    grading.mkdir()
    t = Transcript(grading).read(1, ITEMS).labels(calls=1)
    assert grading_audit.audit(t.write(tmp_path / "s.jsonl"), grading, "001", ITEMS, MODEL)


def test_h27_a_partial_read_with_no_follow_up_fails(tmp_path: Path) -> None:
    grading = tmp_path / "grading"
    grading.mkdir()
    t = Transcript(grading).read(1, 13, partial=True).labels()
    assert any(
        "never returned" in f for f in grading_audit.audit(t.write(tmp_path / "s.jsonl"), grading, "001", ITEMS, MODEL)
    )


def test_h27_reading_only_through_grep_fails(tmp_path: Path) -> None:
    grading = tmp_path / "grading"
    grading.mkdir()
    lines = "".join(f"{n:6d}\t{{}}\n" for n in range(1, ITEMS + 1))
    t = Transcript(grading).use("Grep", lines, pattern=".", path=CHUNK).labels()
    assert any(
        "never returned" in f for f in grading_audit.audit(t.write(tmp_path / "s.jsonl"), grading, "001", ITEMS, MODEL)
    )


def test_h27_the_cli_exits_1_on_a_failure(tmp_path: Path) -> None:
    failures(tmp_path, PLANTS["Bash"])
    assert (
        grading_audit.main([str(tmp_path / "session.jsonl"), str(tmp_path / "grading"), "001", str(ITEMS), MODEL]) == 1
    )


def _block(t: Transcript, block: dict[str, Any]) -> None:
    t.records.append({"type": "assistant", "message": {"model": MODEL, "content": [block]}})


def test_rc1_3_a_server_tool_call_or_an_unknown_block_fails(tmp_path: Path) -> None:
    """The B9 request carried a deferred `advisor` server tool; a call to it is a `server_tool_use` block, which the
    `tool_use` filter never saw (RC1-3). Any assistant block other than text, thinking or tool_use fails."""
    advisor: dict[str, Any] = {"type": "server_tool_use", "id": "s1", "name": "advisor", "input": {}}
    assert failures(tmp_path, lambda t: _block(t, advisor)) == [
        "an assistant block of type server_tool_use (advisor) is not allowed"
    ]
    assert failures(tmp_path, lambda t: _block(t, {"type": "mcp_tool_use", "name": "x"})) == [
        "an assistant block of type mcp_tool_use (x) is not allowed"
    ]


def test_rc1_3_text_and_thinking_blocks_pass(tmp_path: Path) -> None:
    def plant(t: Transcript) -> None:
        for block in ({"type": "text", "text": "done"}, {"type": "thinking", "thinking": "..."},
                      {"type": "redacted_thinking", "data": "..."}):  # fmt: skip
            _block(t, block)

    assert failures(tmp_path, plant) == []
