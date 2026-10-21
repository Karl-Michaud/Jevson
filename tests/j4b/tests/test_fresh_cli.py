"""The runner's CLI wiring (`tests/integration/run_fresh.py`): every billed command checks the pins first, so with
no pre-registration appendix it refuses before reading a key or sending anything; the dry run refuses on a
negative margin with exit code 2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from tests.integration import run_fresh
from tests.j4b.fresh import dryrun, pins


def no_key() -> str:
    raise AssertionError("the key was read")


@pytest.mark.parametrize("command", ["dev", "confirm", "score"])
def test_a_billed_command_refuses_on_the_pins_before_any_key_or_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    monkeypatch.setattr(run_fresh, "openai_key", no_key)
    monkeypatch.setattr(pins, "APPENDIX", "docs/preregistration/no-such-appendix.md")
    assert run_fresh.main(["--root", str(tmp_path / "fresh"), command, "--attempt", "1"]) == 1
    assert "no pre-registration appendix" in capsys.readouterr().err
    assert not (tmp_path / "fresh" / "attempt-1").exists()
    assert not (tmp_path / "fresh" / "run.lock").exists()


def test_a_mismatched_appendix_is_refused_with_exit_code_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(run_fresh, "openai_key", no_key)
    appendix = tmp_path / "appendix.md"
    appendix.write_text('```json pins\n{"library": {"jevson_tree": "0"}, "harness": {}}\n```\n')
    monkeypatch.setattr(pins, "APPENDIX", str(appendix))
    monkeypatch.setattr(pins, "current_pins", lambda *_: (_ for _ in ()).throw(pins.PinMismatch("planted mismatch")))
    assert run_fresh.main(["--root", str(tmp_path / "fresh"), "dev", "--attempt", "1"]) == 1
    assert "refused: planted mismatch" in capsys.readouterr().err
    assert not (tmp_path / "fresh" / "attempt-1").exists()


def test_void_needs_both_test_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = ["--root", str(tmp_path / "fresh"), "void", "--attempt", "1", "--reason", "harness_defect"]
    assert run_fresh.main([*args, "--failing-test", "tests/x.py::test_y"]) == 1
    assert "go together" in capsys.readouterr().err


def test_void_through_the_cli_writes_the_interrupted_description(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    (root / "attempt-1" / "dev").mkdir(parents=True)
    (root / "attempt-1" / "dev" / "start.json").write_text("{}")
    assert run_fresh.main(["--root", str(root), "void", "--attempt", "1", "--reason", "harness_defect"]) == 0
    assert "interrupted: no completion marker" in (root / "attempt-1" / "void.json").read_text()


@pytest.mark.parametrize(("violations", "code"), [([], 0), (["planted"], 2)])
def test_the_dry_run_prints_its_figures_and_refuses_on_a_negative_margin(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], violations: list[str], code: int
) -> None:
    def figures() -> dict[str, Any]:
        return {"violations": violations}

    monkeypatch.setattr(dryrun, "figures", figures)
    monkeypatch.setattr(dryrun, "render", lambda fig: "planted figures")
    assert run_fresh.main(["dryrun"]) == code
    out = capsys.readouterr()
    assert "planted figures" in out.out
    assert ("refused before any spend" in out.err) == bool(violations)


def test_inconclusive_through_the_cli_writes_both_tickets_outcome(tmp_path: Path) -> None:
    root = tmp_path / "fresh"
    (root / "attempt-1" / "dev").mkdir(parents=True)
    (root / "attempt-1" / "dev" / "start.json").write_text("{}")
    assert run_fresh.main(["--root", str(root), "inconclusive"]) == 1  # interrupted: void it first
    assert run_fresh.main(["--root", str(root), "void", "--attempt", "1", "--reason", "harness_defect"]) == 0
    assert run_fresh.main(["--root", str(root), "inconclusive"]) == 0
    analysis = json.loads((root / "analysis.json").read_text())
    expected = "inconclusive (no complete attempt: attempt 1: harness_defect)"
    assert (analysis["asterion_48"]["outcome"], analysis["asterion_58"]["outcome"]) == (expected, expected)
