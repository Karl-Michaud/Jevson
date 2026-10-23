"""H37: a hand-entered harness-defect void leaves a reviewable record (plan §7 single-look item 12, §11 D15;
STATS48-R4-6, FEAS48-R10-2, FEAS48-R10-5).

Hermetic: the repository is made in `tmp_path` with an explicit identity, no signing and no user or system git
configuration, and nothing is archived from the surrounding repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.integration import run_fresh
from tests.j4b.fresh import attempts, runner, scoring
from tests.j4b.fresh.attempts import INTERRUPTED, Attempts, Refused, write_record
from tests.j4b.tests import fake_api

IDENTITY = ("-c", "user.name=h37", "-c", "user.email=h37@example.invalid", "-c", "commit.gpgsign=false")
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "PYTHONDONTWRITEBYTECODE": "1"}
FAILING, PASSING = "tests/h37/test_defect.py::test_defect_shows", "tests/h37/test_defect.py::test_fine"


def git(repo: Path, *args: str) -> str:
    run = subprocess.run(["git", *IDENTITY, "-C", str(repo), *args], capture_output=True, env=GIT_ENV, check=True)
    return run.stdout.decode().strip()


def commit(repo: Path, files: dict[str, str], message: str) -> str:
    for path, text in files.items():
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


HARNESS = {
    "jevson/__init__.py": "",
    "tests/__init__.py": "",
    "tests/j4b/__init__.py": "",
    "tests/j4b/fresh/__init__.py": "",
    "tests/j4b/fresh/rules.py": "def total(xs):\n    return sum(xs)\n",
    "pyproject.toml": "[tool.pytest.ini_options]\naddopts = ''\n",
}
DEFECT_TEST = (
    "from tests.j4b.fresh.rules import total\n\n\n"
    "def test_defect_shows():\n    assert total([1.5, 1.5]) == 4\n\n\n"
    "def test_fine():\n    assert total([1, 2]) == 3\n"
)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    return root, commit(root, HARNESS, "planted harness")


def attempt_complete(root: Path, harness_commit: str) -> runner.Env:
    e, _ = fake_api.env(root / "fresh")
    for phase in ("dev", "confirm"):
        write_record(e.root / "attempt-1" / phase / "start.json", {"harness_commit": harness_commit})
        write_record(e.root / "attempt-1" / phase / "complete.json", {"harness_commit": harness_commit})
    return e


def void_args(test: str | None, commit_: str | None) -> argparse.Namespace:
    return argparse.Namespace(attempt=1, reason="harness_defect", note="defect", failing_test=test, test_commit=commit_)


def test_h37_a_complete_attempt_needs_a_failing_test(tmp_path: Path, repo: tuple[Path, str]) -> None:
    e = attempt_complete(tmp_path, repo[1])
    with pytest.raises(Refused, match="failing-test"):
        runner.void(e, 1, "harness_defect", note="free text", test=None)
    assert not (e.root / "attempt-1" / "void.json").exists()


def test_h37_the_void_runs_the_later_test_on_the_archived_harness_with_its_overlay(
    tmp_path: Path, repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, harness_commit = repo
    e = attempt_complete(tmp_path, harness_commit)  # complete.json is written before the test exists
    later = commit(root, {"tests/h37/__init__.py": "", "tests/h37/test_defect.py": DEFECT_TEST}, "the defect's test")
    monkeypatch.setattr(run_fresh, "REPO", root)
    for node in (PASSING, "tests/h37/test_defect.py::test_no_such_node"):
        with pytest.raises(Refused, match="exit"):
            run_fresh.void(e, void_args(node, later))
    with pytest.raises(Refused, match="go together"):
        run_fresh.void(e, void_args(FAILING, None))
    assert run_fresh.void(e, void_args(FAILING, later)) == 0
    record = json.loads((e.root / "attempt-1" / "void.json").read_text())["failing_test"]
    assert record["test_commit"] == later
    assert record["node"] == FAILING
    assert set(record["overlaid_blobs"]) == {"tests/h37/__init__.py", "tests/h37/test_defect.py"}
    assert record["overlaid_blobs"] == {p: git(root, "rev-parse", f"{later}:{p}") for p in record["overlaid_blobs"]}
    assert len(record["output_sha256"]) == 64


@pytest.mark.parametrize("touched", ["tests/j4b/fresh/rules.py", "jevson/__init__.py"])
def test_h37_a_commit_touching_a_pinned_or_library_path_is_refused(
    tmp_path: Path, repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch, touched: str
) -> None:
    root, harness_commit = repo
    e = attempt_complete(tmp_path, harness_commit)
    files = {"tests/h37/__init__.py": "", "tests/h37/test_defect.py": DEFECT_TEST, touched: "# changed\n"}
    later = commit(root, files, "the test and a pinned edit")
    monkeypatch.setattr(run_fresh, "REPO", root)
    with pytest.raises(Refused, match="pinned or library"):
        run_fresh.void(e, void_args(FAILING, later))


def test_h37_a_commit_not_descending_from_the_harness_commit_is_refused(
    tmp_path: Path, repo: tuple[Path, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root, harness_commit = repo
    e = attempt_complete(tmp_path, harness_commit)
    git(root, "checkout", "-q", "--orphan", "elsewhere")
    git(root, "rm", "-rq", "--cached", ".")
    other = commit(root, {**HARNESS, "tests/h37/__init__.py": "", "tests/h37/test_defect.py": DEFECT_TEST}, "other")
    monkeypatch.setattr(run_fresh, "REPO", root)
    with pytest.raises(Refused, match="does not descend"):
        run_fresh.void(e, void_args(FAILING, other))


# --- 12(b): void attempts are reported, never decided on --------------------------------------------------------


def test_h37_every_void_attempt_is_reported_partially_and_the_decision_does_not_change(tmp_path: Path) -> None:
    load = fake_api.loader()
    e, _ = fake_api.env(tmp_path / "fresh", load=load)
    e.p7_fixture = fake_api.p7_subset(e.root, load("confirm"))
    assert runner.run_phase(e, "dev", 1) == 0
    assert runner.run_phase(e, "confirm", 1) == 0
    confirm = e.root / "attempt-1" / "confirm"
    (confirm / "complete.json").unlink()
    cached = sorted((confirm / "decisions").iterdir())
    for path in cached[: len(cached) // 2]:
        path.unlink()  # an interrupted attempt: about half its units recorded
    assert runner.void(e, 1, "harness_defect", note=None, test=None) == 0
    assert runner.run_phase(e, "dev", 2) == 0
    assert runner.run_phase(e, "confirm", 2) == 0
    assert scoring.export(e, 2) == 0
    fake_api.label_all(e.root, 2)
    assert scoring.score(e, 2) == 0
    reports = json.loads((e.root / "void-reports.json").read_text())["attempts"]
    assert [(r["attempt"], r["reason"], r["label"]) for r in reports] == [(1, "harness_defect", "voided, non-deciding")]
    partial = reports[0]["report"]
    assert partial["partial"] is True
    assert "rset" not in partial
    assert 0 < partial["iset"]["L0"]["cells"] <= len(load("confirm").cases["iset"])
    assert json.loads((e.root / "attempt-1" / "void.json").read_text())["description"] == INTERRUPTED
    decided = scoring.decide(load("confirm"), Attempts(e.root).phase_dir(2, "confirm"), scoring.p7_fixture(
        e, Attempts(e.root).phase_dir(2, "confirm")))  # fmt: skip
    analysis = json.loads((e.root / "analysis.json").read_text())
    assert json.dumps(decided, sort_keys=True, default=str) == json.dumps(analysis, sort_keys=True, default=str)


def test_h37_a_void_report_counts_the_attempts_rejected_l0_f0_first_drafts(tmp_path: Path) -> None:
    """STATS48B-R1-4: single-look item 12(b) and plan D15 report the void attempt's (L0, F0) rejected count, which
    needs no grader truth (the admissions are in its replayed records)."""
    load = fake_api.loader()
    e, _ = fake_api.env(tmp_path / "fresh", load=load)
    e.p7_fixture = fake_api.p7_subset(e.root, load("confirm"))
    assert runner.run_phase(e, "dev", 1) == 0
    assert runner.run_phase(e, "confirm", 1) == 0
    confirm = e.root / "attempt-1" / "confirm"
    (confirm / "complete.json").unlink()
    assert runner.void(e, 1, "harness_defect", note=None, test=None) == 0
    replayed = runner.outcomes_of(load("confirm"), confirm, partial=True)
    rejected = sum(not f["first_admitted"] for u, r in replayed.items() if u.set_name == "rset"
                   and u.config == ("L0", "F0") for f in r["fields"].values())  # fmt: skip
    assert rejected > 0
    (report,) = scoring.void_reports(e, Attempts(e.root))
    assert report["report"]["l0f0_rejected"] == rejected


# --- review round 2 (T48-5): the attempts survivors of the round-2 mutmut run ------------------------------


def test_now_is_utc() -> None:
    assert attempts.now().endswith("+00:00")


def test_tree_hash_reads_every_file(tmp_path: Path) -> None:
    empty = attempts.tree_hash(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_bytes(b"x")
    line = f"a/f.txt\0{hashlib.sha256(b'x').hexdigest()}\n".encode()
    assert attempts.tree_hash(tmp_path) == hashlib.sha256(line).hexdigest() != empty


def test_write_record_layout_mode_and_exclusive_refusal(tmp_path: Path) -> None:
    path = tmp_path / "r.json"
    old = os.umask(0o022)
    try:
        write_record(path, {"b": 1, "a": [2]})
    finally:
        os.umask(old)
    assert path.read_text(encoding="utf-8") == '{\n "a": [\n  2\n ],\n "b": 1\n}\n'
    assert path.stat().st_mode & 0o777 == 0o644
    write_record(path, {"c": 3})  # not exclusive by default: replaced
    assert json.loads(path.read_text()) == {"c": 3}
    with pytest.raises(Refused, match=r"^r\.json already exists$"):
        write_record(path, {}, exclusive=True)


def test_run_lock_file_content_stale_and_release(tmp_path: Path) -> None:
    lock = attempts.RunLock(tmp_path / "a" / "b")
    assert lock.stale is None
    lock.acquire()
    assert [p.name for p in (tmp_path / "a" / "b").iterdir()] == ["run.lock"]
    held = attempts.read_record(lock.path)
    assert held is not None
    assert (set(held), held["pid"]) == ({"pid", "started"}, os.getpid())
    lock.release()
    lock.release()  # a missing lock releases quietly
    write_record(lock.path, {})  # a lock with no pid is stale
    lock.acquire()
    replaced = attempts.read_record(lock.path)
    assert replaced is not None
    assert (lock.stale, set(replaced), replaced["pid"], replaced["replaced_stale"]) == (
        0, {"pid", "started", "replaced_stale"}, os.getpid(), 0)  # fmt: skip
    with pytest.raises(Refused, match=f"^run.lock is held by live pid {os.getpid()}$"):
        attempts.RunLock(tmp_path / "a" / "b").acquire()
    assert attempts.alive(os.getpid())


def test_a_stale_lock_replaced_while_another_run_takes_it_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock = attempts.RunLock(tmp_path)
    write_record(lock.path, {"pid": 0})
    real = Path.unlink

    def raced(self: Path, missing_ok: bool = False) -> None:
        real(self, missing_ok=missing_ok)
        if self == lock.path:
            write_record(self, {"pid": 1})  # another run took the lock between unlink and write

    monkeypatch.setattr(Path, "unlink", raced)
    with pytest.raises(Refused, match=r"^run\.lock already exists$"):
        lock.acquire()


def test_attempt_records_hold_their_keys_and_are_written_once(tmp_path: Path) -> None:
    a = Attempts(tmp_path)
    a.start(1, "dev", {"x": 1})
    start = attempts.read_record(tmp_path / "attempt-1" / "dev" / "start.json")
    assert start is not None
    assert (set(start), start["attempt"], start["phase"]) == ({"started", "attempt", "phase", "x"}, 1, "dev")
    tree = attempts.tree_hash(tmp_path / "attempt-1" / "dev")
    a.finish(1, "dev", {"y": 2})
    done = attempts.read_record(tmp_path / "attempt-1" / "dev" / "complete.json")
    assert done is not None
    assert (set(done), done["tree_sha256"]) == ({"completed", "tree_sha256", "y"}, tree)
    with pytest.raises(Refused, match=r"^complete\.json already exists$"):
        a.finish(1, "dev", {})
    tree = attempts.tree_hash(tmp_path / "attempt-1")
    a.write_void(1, "cap_stop", {"z": 3})
    assert sorted(p.name for p in (tmp_path / "attempt-1").iterdir()) == ["dev", "void.json"]
    void = a.void(1)
    assert void is not None
    assert (set(void), void["tree_sha256"]) == ({"voided", "reason", "tree_sha256", "z"}, tree)
    with pytest.raises(Refused, match=r"^void\.json already exists$"):
        a.write_void(1, "cap_stop", {})
    a.begin_analysis(None, {"w": 4})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["analysis-started.json", "attempt-1"]
    started = a.analysis_started()
    assert started is not None
    assert set(started) == {"started", "attempt", "w"}
    with pytest.raises(Refused, match=r"^analysis-started\.json already exists$"):
        a.begin_analysis(None, {})
    with pytest.raises(Refused, match=r"^the analysis has started: no attempt is voided$"):
        a.write_void(2, "cap_stop", {})
    with pytest.raises(Refused, match=r"^the analysis has started: no attempt runs again$"):
        a.check_start(2, "dev")


def test_attempt_reads_name_their_own_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The names `void`, `complete` (confirm by default, dev before confirm) and `analysis_started` read, checked
    on the name itself so a case-insensitive file system cannot hide a misspelling."""
    seen: list[str] = []
    real_exists = Path.exists

    def exists(self: Path) -> bool:
        seen.append(self.relative_to(tmp_path).as_posix() if self.is_relative_to(tmp_path) else self.name)
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists)
    a = Attempts(tmp_path)
    a.void(1), a.complete(1), a.analysis_started()
    assert seen == ["attempt-1/void.json", "attempt-1/confirm/complete.json", "analysis-started.json"]
    seen.clear()
    with pytest.raises(Refused, match=r"^attempt 1 has no complete dev phase$"):
        a.check_start(1, "confirm")
    assert "attempt-1/dev/complete.json" in seen


def test_out_of_order_and_hand_void_messages(tmp_path: Path) -> None:
    a = Attempts(tmp_path)
    with pytest.raises(Refused, match=r"^attempt 3 is out of order: attempts run from 1, and the next is 1$"):
        a.check_start(3, "dev")
    with pytest.raises(Refused, match=r"^only a harness defect is voided by hand; the runner writes every guard void$"):
        a.hand_void(1, "cap_stop", note=None, test=None)
    a.start(1, "dev", {})
    a.finish(1, "dev", {})
    a.start(1, "confirm", {})
    a.finish(1, "confirm", {})
    with pytest.raises(Refused, match=r"^a complete attempt's harness defect needs --failing-test and --test-commit$"):
        a.hand_void(1, "harness_defect", note="n", test=None)
    a.hand_void(1, "harness_defect", note="n", test=lambda: {"node": "x"})
    void = a.void(1)
    assert void is not None
    assert (void["note"], void["failing_test"]) == ("n", {"node": "x"})


def complete_attempt(a: Attempts, n: int) -> None:
    for phase in ("dev", "confirm"):
        write_record(a.phase_dir(n, phase) / "start.json", {})
        write_record(a.phase_dir(n, phase) / "complete.json", {})


def test_no_complete_attempt_and_score_target_read_each_attempts_own_void(tmp_path: Path) -> None:
    a = Attempts(tmp_path)
    complete_attempt(a, 1)
    a.write_void(1, "cap_stop", {})
    a.attempt_dir(2).mkdir()
    assert a.no_complete_attempt() == ["attempt 1: cap_stop", "attempt 2: not complete"]
    complete_attempt(a, 3)
    a.score_target(3)
    with pytest.raises(Refused, match=r"^attempt 3 is complete and not void: score it$"):
        a.no_complete_attempt()


def test_a_pid_owned_by_another_user_is_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    def kill(pid: int, signal: int) -> None:
        raise PermissionError

    monkeypatch.setattr(attempts.os, "kill", kill)
    assert attempts.alive(4242)
