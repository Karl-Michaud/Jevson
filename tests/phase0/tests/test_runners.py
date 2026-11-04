from __future__ import annotations

import json

import pytest

from tests.phase0 import common, runner
from tests.phase0 import run_probe_1_2_3, run_probe_4, run_probe_5, run_probe_6, run_probe_7, run_probe_8
from tests.phase0.datasets import cases as CS
from tests.phase0.tests import minicorpus as MC


@pytest.fixture
def wired(tmp_path, monkeypatch):
    p = MC.make(tmp_path)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], tmp_path / "cases")
    monkeypatch.setattr(common, "CASES", tmp_path / "cases")
    monkeypatch.setattr(common, "CORPUS", p["corpus"])
    monkeypatch.setattr(runner, "OUT", tmp_path / "out")
    monkeypatch.setattr(runner, "RESULTS", tmp_path / "results")
    return tmp_path


@pytest.mark.parametrize("mod,name", [(run_probe_1_2_3, "probe1_2_3"), (run_probe_4, "probe4"), (run_probe_6, "probe6"),
                                      (run_probe_8, "probe8")])
def test_runners_estimate_and_dry_run(wired, mod, name, capsys):
    assert mod.main(["--estimate"]) == 0
    assert "requests" in capsys.readouterr().out
    assert mod.main(["--dry-run"]) == 0
    s = json.loads((wired / "out" / "dry" / f"{name}.summary.json").read_text())
    assert s["requests_sent_this_invocation"] > 0


def test_probe5_runner_estimate(wired, capsys):
    assert run_probe_5.main(["--estimate"]) == 0
    assert "probe5: 358 requests" in capsys.readouterr().out


def test_probe5_runner_dry_run_sends_positional_refs(wired):
    assert run_probe_5.main(["--dry-run"]) == 0
    s = json.loads((wired / "out" / "dry" / "probe5.summary.json").read_text())
    assert s["requests_sent_this_invocation"] == 358 and "IDX-320" in s["conditions"]


def test_probe7_runner_reads_probe123_results(wired, capsys):
    assert run_probe_1_2_3.main(["--dry-run"]) == 0
    res = wired / "results"
    res.mkdir()
    (res / "probe1_2_3.json").write_text((wired / "out" / "dry" / "probe1_2_3.summary.json").read_text())
    assert run_probe_7.main([], res) == 0
    assert json.loads((res / "probe7.json").read_text())["primary_non_tie"]["n"] >= 0
    assert "primary_non_tie" in capsys.readouterr().out
