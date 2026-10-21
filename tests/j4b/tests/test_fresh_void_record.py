"""H37: a hand-entered harness-defect void leaves a reviewable record (plan §7 single-look item 12, §11 D15;
STATS48-R4-6, FEAS48-R10-2, FEAS48-R10-5).

Hermetic: the repository is made in `tmp_path` with an explicit identity, no signing and no user or system git
configuration, and nothing is archived from the surrounding repository.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.integration import run_fresh
from tests.j4b.fresh import runner, scoring
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
