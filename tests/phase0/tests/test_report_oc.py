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


# ---------------------------------------------------------------- generated sections

def test_doc_blocks_match_committed_data():
    """Every generated block in docs/taxonomy.md is exactly what the committed data renders to."""
    doc = (ROOT / "docs" / "taxonomy.md").read_text()
    blocks = report.generated_blocks()
    assert {"corpus", "labelling", "taxonomy", "fields"} <= set(blocks)
    for name, body in blocks.items():
        assert f"<!-- BEGIN:{name} -->\n{body}\n<!-- END:{name} -->" in doc, name


def test_replace_block_and_update_doc(tmp_path):
    doc = "a\n<!-- BEGIN:x -->\nold\n<!-- END:x -->\nb\n"
    assert report.replace_block(doc, "x", "new\n") == "a\n<!-- BEGIN:x -->\nnew\n<!-- END:x -->\nb\n"
    with pytest.raises(ValueError):
        report.replace_block(doc, "y", "z")
    p = tmp_path / "t.md"
    p.write_text("<!-- BEGIN:taxonomy -->\n<!-- END:taxonomy -->\n")
    assert report.update_doc(p) == ["taxonomy"]
    assert "Verdict on the prediction" in p.read_text()


def test_generated_blocks_skip_missing_inputs(tmp_path):
    assert report.generated_blocks(ds=tmp_path, results=tmp_path) == {}


def test_main_doc(monkeypatch, capsys):
    monkeypatch.setattr(report, "update_doc", lambda: ["corpus"])
    assert report.main(["doc"]) == 0
    assert "updated blocks: corpus" in capsys.readouterr().out
