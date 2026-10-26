"""The grader hand-off files (plan §6; design §3 steps 3-5): the pinned instruction, the deny list, the empty MCP
configuration, `launch.sh` and the canary chunks. No Claude session is launched: `claude` is a stub on PATH."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from tests.j4b.fresh import pins
from tests.j4b.fresh.constants import CHUNK_CHARS
from tests.j4b.fresh.grader.canary import make_canary

ROOT = Path(__file__).resolve().parents[3]
GRADER = ROOT / pins.FRESH / "grader"
FILES = ("instruction.md", "settings.json", "empty-mcp.json", "launch.sh")


def test_the_instruction_carries_the_paging_rule_the_label_format_and_the_append_rule() -> None:
    text = (GRADER / "instruction.md").read_text()
    for sentence in (
        "Read the chunk file with the Read tool.",
        "If any Read result says it is a PARTIAL view, keep calling Read with the offset and limit that the result "
        "names until every line of the file has been returned.",
        "Never label an item whose line you have not been shown.",
        "A Grep or Glob result does not count as reading an item.",
        '`{"id": "<item id>", "criteria": {"<criterion id>": true or false, ...}, "note": "<optional note>"}`',
        "Append each label as soon as the item is judged; never write the file once at the end.",
        "Write nothing else",
    ):
        assert sentence in text, sentence


def test_the_settings_deny_every_tool_outside_the_allowlist_and_mcp_is_empty() -> None:
    deny = json.loads((GRADER / "settings.json").read_text())["permissions"]["deny"]
    assert deny == ["Bash", "WebFetch", "WebSearch", "Agent", "Task", "Skill", "NotebookEdit", "mcp__*"]
    assert json.loads((GRADER / "empty-mcp.json").read_text()) == {"mcpServers": {}}


def grading_dir(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    directory = tmp_path / "grading"
    directory.mkdir()
    for name in FILES:
        shutil.copy2(GRADER / name, directory / name)
    (directory / "items-007.jsonl").write_text("{}\n")
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "claude").write_text('#!/bin/sh\nprintf "stub ran with %s args\\n" "$#"\n')
    (stub / "claude").chmod(0o755)
    return directory, {**os.environ, "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}", "GIT_CONFIG_NOSYSTEM": "1"}


def test_launch_prints_and_runs_exactly_the_pinned_command(tmp_path: Path) -> None:
    directory, env = grading_dir(tmp_path)
    run = subprocess.run(["./launch.sh", "007"], cwd=directory, env=env, capture_output=True, text=True, check=True)
    command, ran = run.stdout.splitlines()[0], run.stdout.splitlines()[-1]
    assert command.startswith(
        "claude -p --model claude-opus-5-5 --restricted --tools Read,Write,Edit,Glob,Grep --strict-mcp-config "
        "--mcp-config empty-mcp.json --no-chrome --disable-slash-commands --settings settings.json "
        "--permission-mode acceptEdits --permission-prompts none You are grading drafts. The file `items-007.jsonl`"
    )
    assert ran == "stub ran with 18 args"  # the flags of the pinned command and the instruction


def test_launch_refuses_inside_a_worktree_inside_project_asterion_and_without_its_chunk(tmp_path: Path) -> None:
    directory, env = grading_dir(tmp_path)
    assert (
        subprocess.run(["./launch.sh", "008"], cwd=directory, env=env, capture_output=True, check=False).returncode == 2
    )
    nested = tmp_path / "x" / "project-asterion" / "grading"
    shutil.copytree(directory, nested)
    assert subprocess.run(["./launch.sh", "007"], cwd=nested, env=env, capture_output=True, check=False).returncode == 2
    subprocess.run(["git", "init", "-q"], cwd=directory, env=env, check=True)
    refused = subprocess.run(
        ["./launch.sh", "007"], cwd=directory, env=env, capture_output=True, text=True, check=False
    )
    assert refused.returncode == 2
    assert "worktree" in refused.stderr


def test_launch_refuses_under_a_dot_claude_directory(tmp_path: Path) -> None:
    """STATS48-B10-1 / RC1-1: the B9 canary's only label write was denied as a sensitive file because its grading
    directory sat under ~/.claude/, so a grading directory there could never produce a label."""
    directory, env = grading_dir(tmp_path)
    nested = tmp_path / "home" / ".claude" / "projects" / "grading"
    shutil.copytree(directory, nested)
    refused = subprocess.run(["./launch.sh", "007"], cwd=nested, env=env, capture_output=True, text=True, check=False)
    assert refused.returncode == 2
    assert refused.stderr == f"refused: {nested.resolve()} is inside a .claude/ directory\n"
    assert "stub ran" not in refused.stdout


def test_the_canary_chunks_are_reproducible_and_the_full_one_is_packed_to_the_bound(tmp_path: Path) -> None:
    assert make_canary.main([str(tmp_path)]) == 0
    for name in ("items-001.jsonl", "items-002.jsonl"):
        assert (tmp_path / name).read_bytes() == (GRADER / "canary" / name).read_bytes()
    full = (GRADER / "canary" / "items-002.jsonl").read_text()
    assert CHUNK_CHARS - 200 < len(full) <= CHUNK_CHARS
