"""H38: the guard detects a change, and an absent directory is a state of its own."""

from __future__ import annotations

from pathlib import Path

from tests.j4b.tests.conftest import recordings_state


def test_h38_the_recordings_state_changes_with_any_file(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    assert recordings_state(root) == "absent"
    root.mkdir()
    empty = recordings_state(root)
    (root / "spend.jsonl").write_text("{}\n")
    once = recordings_state(root)
    (root / "spend.jsonl").write_text("{}\n{}\n")
    assert len({"absent", empty, once, recordings_state(root)}) == 4
