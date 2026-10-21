"""H19-H19f, H29 (score's half), H35 (dev's churn): the runner's attempt rules, through its own commands, over
the fake API and a trimmed workload under `tmp_path` (plan §7 single-look items 1-11)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import arms, runner, scoring
from tests.j4b.fresh.attempts import INTERRUPTED, Attempts, Refused, write_record
from tests.j4b.fresh.packing import Unit
from tests.j4b.tests import fake_api, opens


def make_env(tmp_path: Path, **kw: Any) -> tuple[runner.Env, list[str]]:
    root = tmp_path / "fresh"
    load = fake_api.loader()
    e, lines = fake_api.env(root, load=load, **kw)
    e.p7_fixture = fake_api.p7_subset(root, load("confirm"))
    return e, lines


def complete(e: runner.Env, n: int = 1) -> None:
    assert runner.run_phase(e, "dev", n) == 0
    assert runner.run_phase(e, "confirm", n) == 0


def exported_and_labelled(e: runner.Env, n: int = 1) -> None:
    complete(e, n)
    assert scoring.export(e, n) == 0
    fake_api.label_all(e.root, n)


# --- H19: attempt directories -----------------------------------------------------------------------------


def test_h19_a_non_empty_phase_directory_is_refused_and_a_voided_attempt_is_kept(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    assert runner.run_phase(e, "dev", 1) == 0
    with pytest.raises(Refused, match="not empty"):
        runner.run_phase(e, "dev", 1)
    a = Attempts(e.root)
    a.write_void(1, "cap_stop", {})
    assert (e.root / "attempt-1" / "dev" / "complete.json").exists()
    with pytest.raises(Refused):
        runner.run_phase(e, "confirm", 1)


# --- H19b, H19c: single look ---------------------------------------------------------------------------------


def test_h19b_score_records_analysis_started_before_reading_and_runs_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    e, _ = make_env(tmp_path)
    exported_and_labelled(e)

    def no_read(*_: Any) -> dict[str, Any]:
        raise RuntimeError("read")

    monkeypatch.setattr(scoring, "decide", no_read)
    with pytest.raises(RuntimeError, match="read"):
        scoring.score(e, 1)
    started = json.loads((e.root / "analysis-started.json").read_text())
    confirm = e.root / "attempt-1" / "confirm"
    assert started["attempt"] == 1
    assert started["harness_commit"] == "0" * 40
    assert started["pins"]["appendix_sha256"] == "a" * 64
    assert started["items_sha256"] == scoring._sha(confirm / "export" / "items.jsonl")  # pyright: ignore[reportPrivateUsage]
    assert started["key_sha256"] == scoring._sha(confirm / "export" / "key.jsonl")  # pyright: ignore[reportPrivateUsage]
    assert set(started["labels_sha256"]) == {p.name for p in (confirm / "labels").iterdir()}
    assert re.fullmatch(r"[0-9a-f]{64}", started["confirm_tree_sha256"])
    monkeypatch.undo()
    with pytest.raises(Refused, match="once"):
        scoring.score(e, 1)


def test_h19b_score_decides_from_the_records_and_reports(tmp_path: Path) -> None:
    e, lines = make_env(tmp_path)
    exported_and_labelled(e)
    assert scoring.score(e, 1) == 0
    analysis = json.loads((e.root / "analysis.json").read_text())
    assert set(analysis) == {"asterion_48", "asterion_58", "report"}
    assert "diagnostic_agreement" in analysis["report"]["secondaries"]
    assert json.loads(lines[-1]) == {k: analysis[k] for k in ("asterion_48", "asterion_58")}


def test_h19c_after_the_analysis_has_started_nothing_runs_again(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    assert runner.run_phase(e, "dev", 1) == 0
    write_record(e.root / "analysis-started.json", {"attempt": 1})
    for call in (
        lambda: runner.run_phase(e, "dev", 2),
        lambda: runner.run_phase(e, "confirm", 1),
        lambda: runner.void(e, 1, "harness_defect", note=None, test=None),
    ):
        with pytest.raises(Refused, match="analysis"):
            call()


# --- H19d: nothing shown before the void decision; score reads confirm only ---------------------------------

OUTCOME_WORDS = re.compile(r"admi|flip|reject|pass(?:ed)?\b|fail", re.IGNORECASE)
PER_CONFIG = re.compile(r"L[0-3]F[01]|\(L[0-3], F[01]\)")


def shows_outcomes(text: str) -> bool:
    return bool(OUTCOME_WORDS.search(text) or PER_CONFIG.search(text))


def test_h19d_confirm_and_export_print_no_outcome_and_no_per_configuration_count(tmp_path: Path) -> None:
    e, lines = make_env(tmp_path)
    assert runner.run_phase(e, "dev", 1) == 0
    lines.clear()
    assert runner.run_phase(e, "confirm", 1) == 0
    assert scoring.export(e, 1) == 0
    printed = "\n".join(lines)
    assert "decision requests" in printed
    assert "drafting calls" in printed
    assert "gpt-6-luna" in printed
    assert not shows_outcomes(printed)
    written = (e.root / "attempt-1" / "confirm" / "complete.json").read_text()
    assert not shows_outcomes(written)
    assert shows_outcomes(printed + "\nL1F0: 12 admitted")  # a planted count
    assert shows_outcomes(printed + "\n(L2, F1) 40 decision requests")  # a planted per-configuration count


def test_h19d_score_never_opens_a_dev_record(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    exported_and_labelled(e)
    dev = (e.root / "attempt-1" / "dev").resolve()
    (dev / "planted.json").write_text("{}")
    with opens.recording() as seen:
        assert scoring.score(e, 1) == 0
    assert [p for p in seen if p.is_relative_to((e.root / "attempt-1" / "confirm").resolve())]
    assert [p for p in seen if p.is_relative_to(dev)] == []


def test_h19d_void_takes_only_the_closed_list(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    assert runner.run_phase(e, "dev", 1) == 0
    for reason in ("interrupted", "the run looked odd", "cap_stop"):
        with pytest.raises(Refused):
            runner.void(e, 1, reason, note=None, test=None)


# --- H19e: attempt order and completion ------------------------------------------------------------------


def test_h19e_a_later_attempt_needs_every_earlier_one_void(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    complete(e, 1)
    for phase in ("dev", "confirm"):
        with pytest.raises(Refused, match="attempt 1 is not void"):
            runner.run_phase(e, phase, 2)
    Attempts(e.root).write_void(1, "harness_defect", {"note": "planted"})
    complete(e, 2)


def plant_complete(a: Attempts, n: int) -> None:
    for phase in ("dev", "confirm"):
        write_record(a.phase_dir(n, phase) / "start.json", {"planted": True})
        write_record(a.phase_dir(n, phase) / "complete.json", {"planted": True})


def test_h19e_no_attempt_starts_beside_or_below_a_live_later_one(tmp_path: Path) -> None:
    """STATS48B-R1-3: attempts run in order from 1, one at a time; a lower or skipped number never starts."""
    e, _ = make_env(tmp_path)
    a = Attempts(e.root)
    for n in (0, -1, 2):
        with pytest.raises(Refused, match="out of order"):
            a.check_start(n, "dev")
    plant_complete(a, 2)
    for n in (0, 1):
        for phase in ("dev", "confirm"):
            with pytest.raises(Refused):
                a.check_start(n, phase)
    with pytest.raises(Refused, match="attempt 2 is not void"):
        a.check_start(1, "dev")
    a.write_void(2, "harness_defect", {"note": "planted"})
    for n in (1, 2, 4):
        with pytest.raises(Refused):
            a.check_start(n, "dev")
    a.check_start(3, "dev")


def test_h19e_confirm_needs_a_complete_dev_phase(tmp_path: Path) -> None:
    a = Attempts(tmp_path / "fresh")
    with pytest.raises(Refused, match="attempt 1 has no complete dev phase"):
        a.check_start(1, "confirm")
    write_record(a.phase_dir(1, "dev") / "start.json", {"planted": True})
    write_record(a.phase_dir(1, "dev") / "complete.json", {"planted": True})
    a.check_start(1, "confirm")


def test_h37_a_void_takes_only_the_closed_list_and_never_follows_the_analysis(tmp_path: Path) -> None:
    a = Attempts(tmp_path / "fresh")
    write_record(a.phase_dir(1, "dev") / "start.json", {"planted": True})
    with pytest.raises(Refused, match=re.escape("is not one of design §6.4's void reasons")):
        a.write_void(1, "interrupted", {})
    with pytest.raises(Refused, match="only a harness defect is voided by hand"):
        a.hand_void(1, "interrupted", note=None, test=None)
    a.begin_analysis(None, {"planted": True})
    with pytest.raises(Refused, match="the analysis has started: no attempt is voided"):
        a.write_void(1, "cap_stop", {})
    assert a.void(1) is None


def test_h19e_score_refuses_a_void_an_incomplete_and_a_second_complete_attempt(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    exported_and_labelled(e, 1)
    a = Attempts(e.root)
    write_record(a.phase_dir(2, "confirm") / "complete.json", {"planted": True})
    with pytest.raises(Refused, match="also complete"):
        scoring.score(e, 1)
    a.write_void(2, "cap_stop", {})
    a.write_void(1, "replay_miss", {})
    with pytest.raises(Refused, match="not a complete, non-void"):
        scoring.score(e, 1)
    assert not (e.root / "analysis-started.json").exists()


def test_h19e_completion_is_only_complete_json(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    exported_and_labelled(e, 1)
    (e.root / "attempt-1" / "confirm" / "complete.json").unlink()
    with pytest.raises(Refused):
        scoring.score(e, 1)
    for phase in ("dev", "confirm"):
        with pytest.raises(Refused, match="attempt 1 is incomplete"):
            runner.run_phase(e, phase, 2)


def test_h19e_a_guard_stop_writes_its_own_void(tmp_path: Path) -> None:
    def other_model(endpoint: str, n: int, body: dict[str, Any]) -> Any:
        if endpoint == "decisions" and n == 3:
            api = fake_api.FakeAPI()
            response = api.decide(body, 10)
            payload = json.loads(response.content)
            payload["model"] = "gpt-6-luna-2"
            return fake_api.httpx.Response(200, json=payload)
        return None

    e, lines = make_env(tmp_path, api=fake_api.FakeAPI(plan=other_model))
    assert runner.run_phase(e, "dev", 1) == 2
    void = json.loads((e.root / "attempt-1" / "void.json").read_text())
    assert void["reason"] == "model_string_change"
    assert "void" in lines[-1]


def test_h29_score_refuses_a_changed_p7_fixture(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    exported_and_labelled(e, 1)
    cases = e.p7_fixture.read_text().splitlines(keepends=True)
    e.p7_fixture.write_text("".join(cases[:-1]))  # one case dropped
    with pytest.raises(Refused, match="P7"):
        scoring.score(e, 1)
    assert not (e.root / "analysis-started.json").exists()


# --- H19f: the run lock --------------------------------------------------------------------------------------


def commands(e: runner.Env) -> list[Any]:
    return [
        lambda: runner.run_phase(e, "dev", 1),
        lambda: runner.run_phase(e, "confirm", 1),
        lambda: runner.void(e, 1, "harness_defect", note=None, test=None),
        lambda: scoring.score(e, 1),
    ]


def test_h19f_a_live_lock_refuses_every_command_and_names_the_pid(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    write_record(e.root / "run.lock", {"pid": os.getpid()})
    for call in commands(e):
        with pytest.raises(Refused, match=f"live pid {os.getpid()}"):
            call()
    assert (e.root / "run.lock").exists()


def test_h19f_a_dead_pid_is_stale_replaced_and_the_lock_is_gone_after(tmp_path: Path) -> None:
    child = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, check=True)
    dead = int(child.stdout)
    e, lines = make_env(tmp_path)
    write_record(e.root / "run.lock", {"pid": dead})
    assert runner.run_phase(e, "dev", 1) == 0
    assert any(f"pid {dead}" in line and "stale" in line for line in lines)
    assert not (e.root / "run.lock").exists()
    with pytest.raises(Refused):
        runner.run_phase(e, "dev", 1)  # refused start
    assert not (e.root / "run.lock").exists()


def test_h19f_an_interrupted_attempt_is_voided_with_the_pinned_description(tmp_path: Path) -> None:
    e, _ = make_env(tmp_path)
    (e.root / "attempt-1" / "dev").mkdir(parents=True)
    (e.root / "attempt-1" / "dev" / "start.json").write_text("{}")
    with pytest.raises(Refused, match="attempt 1 is incomplete"):
        runner.run_phase(e, "dev", 2)
    assert runner.void(e, 1, "harness_defect", note="laptop closed", test=None) == 0
    void = json.loads((e.root / "attempt-1" / "void.json").read_text())
    assert (void["description"], void["note"]) == (INTERRUPTED, "laptop closed")
    assert runner.run_phase(e, "dev", 2) == 0


# --- H35: dev's churn, from dev records only -----------------------------------------------------------------


def test_h35_dev_prints_the_p_dev_churn_and_never_opens_confirm(tmp_path: Path) -> None:
    e, lines = make_env(tmp_path)
    with opens.recording() as seen:
        assert runner.run_phase(e, "dev", 1) == 0
    confirm = (e.root / "attempt-1" / "confirm").resolve()
    assert seen
    assert not [p for p in seen if p.is_relative_to(confirm)]
    assert any(p.is_relative_to((e.root / "attempt-1" / "dev").resolve()) for p in seen)
    churn = next(line for line in lines if line.startswith("P-dev template churn"))
    assert set(re.findall(r"'(L[0-3]F[01])'", churn)) == {f"L{a}F{f}" for a in range(4) for f in (0, 1)}
    assert "'L0F0': 0.0" in churn


def test_h35_the_churn_is_the_share_of_pairs_with_any_changed_answer() -> None:
    rows = [{"pair": "p1", "draft_id": "a"}, {"pair": "p1", "draft_id": "b"}, {"pair": "p2", "draft_id": "c"}]
    outcomes: dict[Unit, Any] = {}
    for arm, form in arms.CONFIGURATIONS:
        for d in "abc":
            changed = (arm, form, d) in {("L1", "F0", "b"), ("L2", "F1", "a"), ("L2", "F1", "c")}
            outcomes[Unit("pset", d, arm, form)] = {"admitted": (d == "a") != changed}
    churn = runner.churn(outcomes, rows)
    assert churn["L0F0"] == 0.0
    assert churn["L1F0"] == 0.5
    assert churn["L2F1"] == 1.0
    assert churn["L3F1"] == 0.0
