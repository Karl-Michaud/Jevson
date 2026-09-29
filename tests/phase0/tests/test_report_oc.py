from __future__ import annotations

import json
import pathlib

import pytest

from tests.phase0 import report
from tests.phase0 import rules as R

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_oc_data_values():
    d = report.oc_data()
    assert d["n"] == 150
    assert d["cutpoints"]["probe 1: disambiguation accuracy"]["go"] == [128, 150]
    assert d["cutpoints"]["probe 3: false abstention"]["stop"] == [31, 150]
    j = {(r["p_correct"], r["p_abstain"]): r for r in d["joint_1_3"]}
    assert j[(0.85, 0.10)]["both_go"] == pytest.approx(0.436, abs=6e-4)
    for r in d["single"]:
        assert r["go"] + r["conditional"] + r["stop"] == pytest.approx(1.0)


def test_taxonomy_md_carries_the_computed_oc():
    """The pre-registered OC in docs/taxonomy.md is exactly what the tested code computes."""
    doc = (ROOT / "docs" / "taxonomy.md").read_text()
    assert report.render_oc(report.oc_data()) in doc


def test_main_writes_oc_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(report, "RESULTS", tmp_path / "results")
    assert report.main(["oc"]) == 0
    d = json.loads((tmp_path / "results" / "oc.json").read_text())
    assert d["n"] == R.N_TARGET
    assert "Integer cut-points" in capsys.readouterr().out
    assert report.main([]) == 2


def test_render_handles_empty_band():
    d = report.oc_data(n=2)
    text = report.render_oc(d)
    assert "—" in text or "k " in text
