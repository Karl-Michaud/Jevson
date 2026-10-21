"""The attempt state machine: single look, attempt order, completion, voids and the run lock (design §6.2-§6.4;
plan §7 single-look items 1-12, §11 D5, D13, D15).

Everything is under a run root passed in (`run_fresh --root`; tests pass `tmp_path`):
`attempt-N/{dev,confirm}/` with `start.json` and `complete.json`, `attempt-N/void.json`, and at the root
`analysis-started.json`, `run.lock` and `spend.jsonl`. An attempt is complete exactly when
`attempt-N/confirm/complete.json` exists; nothing infers completion from directory contents.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from tests.j4b.fresh import overlay

REASONS = ("harness_defect", "model_string_change", "replay_miss", "cap_stop", "usage_over_bound")
"""Design §6.4's closed list of void reasons."""
INTERRUPTED = "interrupted: no completion marker"
"""The pinned description of an interrupted attempt's void (plan §11 D13)."""
PHASES = ("dev", "confirm")


class Refused(Exception):
    """A command the attempt rules do not allow; nothing was written."""


def now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")


def tree_hash(directory: Path) -> str:
    """SHA-256 over every file under `directory`: sorted relative paths with each file's SHA-256 (no git)."""
    digest = hashlib.sha256()
    if directory.exists():
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            digest.update(
                f"{path.relative_to(directory).as_posix()}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode()
            )
    return digest.hexdigest()


def write_record(path: Path, record: Mapping[str, Any], *, exclusive: bool = False) -> None:
    """Write and fsync a JSON record; with `exclusive`, refuse if it exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    try:
        fd = os.open(path, flags, 0o644)
    except FileExistsError:
        raise Refused(f"{path.name} already exists") from None
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, indent=1, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_record(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


class RunLock:
    """`run.lock`, created with O_CREAT|O_EXCL and holding the pid; a lock whose pid is dead is stale."""

    def __init__(self, root: Path) -> None:
        self.path = root / "run.lock"
        self.stale: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            write_record(self.path, {"pid": os.getpid(), "started": now()}, exclusive=True)
            return
        except Refused:
            held = read_record(self.path) or {}
        pid = int(held.get("pid", 0))
        if pid and alive(pid):
            raise Refused(f"run.lock is held by live pid {pid}")
        self.stale = pid
        self.path.unlink()
        write_record(self.path, {"pid": os.getpid(), "started": now(), "replaced_stale": pid}, exclusive=True)

    def release(self) -> None:
        self.path.unlink(missing_ok=True)

    def __enter__(self) -> RunLock:
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Attempts:
    """The rules of single look over a run root; every check reads only the records written there."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def attempt_dir(self, n: int) -> Path:
        return self.root / f"attempt-{n}"

    def phase_dir(self, n: int, phase: str) -> Path:
        return self.attempt_dir(n) / phase

    def numbers(self) -> list[int]:
        return sorted(int(p.name.split("-")[1]) for p in self.root.glob("attempt-*") if p.is_dir())

    def void(self, n: int) -> dict[str, Any] | None:
        return read_record(self.attempt_dir(n) / "void.json")

    def complete(self, n: int, phase: str = "confirm") -> bool:
        return (self.phase_dir(n, phase) / "complete.json").exists()

    def interrupted(self) -> list[int]:
        """Attempts with a non-empty phase directory lacking that phase's `complete.json`, and no `void.json`."""
        out: list[int] = []
        for n in self.numbers():
            for phase in PHASES:
                directory = self.phase_dir(n, phase)
                started = directory.exists() and any(directory.iterdir())
                if started and not self.complete(n, phase) and self.void(n) is None and n not in out:
                    out.append(n)
        return out

    def analysis_started(self) -> dict[str, Any] | None:
        return read_record(self.root / "analysis-started.json")

    def check_start(self, n: int, phase: str) -> None:
        """Items 2, 6, 11 and D5: no analysis yet, no interrupted attempt, every other attempt void, attempts in
        order (the latest one, or the next after it; the first is 1), the dev phase complete before confirm, and
        the phase's own directory empty. So no attempt starts while another is live, and a repeat (design §6.4,
        only after a void) is always the next number: no outcome is seen before the choice of which to score."""
        if self.analysis_started() is not None:
            raise Refused("the analysis has started: no attempt runs again")
        if blocked := self.interrupted():
            raise Refused(f"attempt {blocked[0]} is incomplete with no void.json; void it first")
        numbers = self.numbers()
        for m in numbers:
            void = self.void(m)
            if m != n and (void is None or void.get("reason") not in REASONS):
                raise Refused(f"attempt {m} is not void; attempt {n} cannot start")
        latest = max(numbers, default=0)
        if n < 1 or n not in (latest, latest + 1):
            raise Refused(f"attempt {n} is out of order: attempts run from 1, and the next is {latest + 1}")
        if phase == "confirm" and not self.complete(n, "dev"):
            raise Refused(f"attempt {n} has no complete dev phase")
        directory = self.phase_dir(n, phase)
        if self.void(n) is not None or (directory.exists() and any(directory.iterdir())):
            raise Refused(f"attempt-{n}/{phase} is not empty or the attempt is void")

    def start(self, n: int, phase: str, record: Mapping[str, Any]) -> Path:
        self.check_start(n, phase)
        directory = self.phase_dir(n, phase)
        write_record(directory / "start.json", {"started": now(), "attempt": n, "phase": phase, **record})
        return directory

    def finish(self, n: int, phase: str, record: Mapping[str, Any]) -> None:
        """Item 9: the completion marker, written last, with the phase directory's tree hash."""
        directory = self.phase_dir(n, phase)
        write_record(directory / "complete.json",
                     {"completed": now(), "tree_sha256": tree_hash(directory), **record}, exclusive=True)  # fmt: skip

    def write_void(self, n: int, reason: str, record: Mapping[str, Any]) -> None:
        if reason not in REASONS:
            raise Refused(f"{reason!r} is not one of design §6.4's void reasons {REASONS}")
        if self.analysis_started() is not None:
            raise Refused("the analysis has started: no attempt is voided")
        write_record(self.attempt_dir(n) / "void.json",
                     {"voided": now(), "reason": reason, "tree_sha256": tree_hash(self.attempt_dir(n)), **record},
                     exclusive=True)  # fmt: skip

    def hand_void(self, n: int, reason: str, *, note: str | None, test: Callable[[], Mapping[str, Any]] | None) -> None:
        """Item 5 and 12(a): `void` by hand; only a harness defect, and for a complete attempt only with a
        failing-test record (`test`, the overlay check); an incomplete one gets the pinned description."""
        if reason != "harness_defect":
            raise Refused("only a harness defect is voided by hand; the runner writes every guard void")
        if self.complete(n):
            if test is None:
                raise Refused("a complete attempt's harness defect needs --failing-test and --test-commit")
            self.write_void(n, reason, {"note": note, "failing_test": dict(test())})
            return
        self.write_void(n, reason, {"description": INTERRUPTED, "note": note})

    def score_target(self, n: int) -> None:
        """Item 7: attempt `n` is complete, not void, and the only complete attempt without a void."""
        if not self.complete(n) or self.void(n) is not None:
            raise Refused(f"attempt {n} is not a complete, non-void attempt")
        others = [m for m in self.numbers() if m != n and self.complete(m) and self.void(m) is None]
        if others:
            raise Refused(f"attempt {others[0]} is also complete and not void")

    def begin_analysis(self, n: int, record: Mapping[str, Any]) -> None:
        """Item 1: written and fsynced before anything is read; a second analysis refuses."""
        write_record(self.root / "analysis-started.json", {"started": now(), "attempt": n, **record}, exclusive=True)


def failing_test_record(
    repo: Path, harness_commit: str, test_commit: str, node: str, pinned: tuple[str, ...]
) -> dict[str, Any]:
    """Item 12(a): the failing test of a complete attempt's harness defect. `test_commit` descends from the
    attempt's `harness_commit` and touches no pinned path and nothing under `jevson/`; the node, run on the archived
    `harness_commit` with the commit's changed files overlaid, collects exactly itself and exits 1."""
    if not overlay.is_ancestor(repo, harness_commit, test_commit):
        raise Refused(f"{test_commit} does not descend from the attempt's harness commit {harness_commit}")
    changed = overlay.changed_paths(repo, harness_commit, test_commit)
    touched = [p for p in changed if p.startswith("jevson/") or any(p == q or p.startswith(q + "/") for q in pinned)]
    if touched:
        raise Refused(f"{test_commit} touches pinned or library paths: {touched}")
    files = {path: overlay.show(repo, test_commit, path) for path in changed}
    run = overlay.run_node(repo, harness_commit, node, files)
    if run.exit_code != 1 or run.collected != (node,):
        raise Refused(f"{node} must collect exactly itself and fail (exit {run.exit_code}, collected {run.collected})")
    blobs = {path: overlay.rev_parse(repo, f"{test_commit}:{path}") for path in changed}
    return {"test_commit": test_commit, "node": node, "overlaid_blobs": blobs, "output_sha256": run.output_sha256}
