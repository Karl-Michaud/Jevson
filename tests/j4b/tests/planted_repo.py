"""A hermetic git repository holding a copy of the pinned harness, for H37 and H39.

It copies files from the filesystem, never from the surrounding repository's git, so it works in an export, in a
mutation-testing copy and in a depth-1 checkout. Every git call runs with an explicit identity, no signing, and no
user or system configuration. Row files are cut to a few rows each (with `summary.json` regenerated), so the pin
check stays fast.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tests.j4b.fresh import build_fresh_sets, pins
from tests.j4b.fresh.attempts import Attempts

SOURCE = Path(__file__).resolve().parents[3]
ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"}
IDENTITY = ("-c", "user.name=h39", "-c", "user.email=h39@example.invalid", "-c", "commit.gpgsign=false")
ROWS_KEPT = 12


class PlantedRepo:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def create(cls, root: Path) -> PlantedRepo:
        repo = cls(root)
        root.mkdir(parents=True)
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc")
        for item in ("jevson", "pyproject.toml", "tests/j4b/tests/__init__.py", *pins.PINNED_PATHS):
            source, target = SOURCE / item, root / item
            target.parent.mkdir(parents=True, exist_ok=True)
            if not source.exists():
                continue  # a pinned path the harness does not have yet
            if source.is_dir():
                shutil.copytree(source, target, ignore=ignore)
            else:
                shutil.copy2(source, target)
        repo.cut_rows()
        repo.git("init", "-q", "-b", "base")
        repo.commit("planted harness")
        return repo

    def git(self, *args: str) -> str:
        run = subprocess.run(["git", *IDENTITY, "-C", str(self.root), *args], capture_output=True, env=ENV, check=True)
        return run.stdout.decode().strip()

    def commit(self, message: str) -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", message)
        return self.git("rev-parse", "HEAD")

    def path(self, relative: str) -> Path:
        return self.root / relative

    def edit(self, relative: str, change: Callable[[str], str]) -> None:
        path = self.path(relative)
        path.write_text(change(path.read_text(encoding="utf-8")), encoding="utf-8")

    def cut_rows(self) -> None:
        fixtures = self.path(pins.FIXTURES)
        for name in pins.ROW_FILES:
            lines = (fixtures / name).read_text(encoding="utf-8").splitlines(keepends=True)
            (fixtures / name).write_text("".join(lines[:ROWS_KEPT]), encoding="utf-8")
        self.summarise()

    def summarise(self) -> None:
        fixtures = self.path(pins.FIXTURES)
        data = {name: (fixtures / name).read_bytes() for name in pins.ROW_FILES}
        summary = build_fresh_sets.summarise(data, self.path(pins.PICKED).read_bytes())
        (fixtures / "summary.json").write_text(summary, encoding="utf-8")

    def authored(self, relative: str, change: Callable[[dict[str, Any]], None]) -> None:
        """Change an authored JSON file's records and write it back canonically."""
        records = json.loads(self.path(relative).read_text(encoding="utf-8"))
        change(records)
        self.path(relative).write_text(pins.canonical_file(records), encoding="utf-8")

    def rows(self, name: str, change: Callable[[list[dict[str, Any]]], None]) -> None:
        path = self.path(f"{pins.FIXTURES}/{name}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        change(rows)
        path.write_text("".join(pins.canonical_row(r) for r in rows), encoding="utf-8")
        self.summarise()

    def appendix(self, *, parent: str | None = None, motivating: Mapping[str, str] | None = None,
                 commit: str = "HEAD") -> str:  # fmt: skip
        """An appendix pinning `commit`'s trees, as the pre-registration commit would write it."""
        hashes = pins.tree_hashes(self.root, commit)
        block = {"library": {"jevson_tree": hashes[pins.LIBRARY]},
                 "harness": {p: h for p, h in hashes.items() if p != pins.LIBRARY and h is not None},
                 "parent": parent, "motivating": dict(motivating or {})}  # fmt: skip
        return f"# Pre-registration (planted)\n\n```json pins\n{json.dumps(block, indent=1, sort_keys=True)}\n```\n"

    def record(self, run: Path, attempt: int, phase: str, appendix: str, *, finish: bool = True) -> pins.Pins:
        """Start (and finish) a phase with the pins `check` returns, as the runner does."""
        p = pins.check(self.root, run, appendix, command=phase, attempt=attempt)
        attempts = Attempts(run)
        attempts.start(attempt, phase, {"pins": p.record()})
        if finish:
            attempts.finish(attempt, phase, {"pins": p.record()})
        return p
