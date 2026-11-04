from __future__ import annotations

import json

import pytest

from tests.phase0 import taxonomy as TX


def test_rules_cover_every_origin_and_classes_are_design_classes():
    assert set(TX.RULES) == {"structure", "caller", "constant", "span", "span_parse", "enum", "bool", "ordinal",
                             "generate", "classify_free", "compute", "unsupported", "array_objects", "array_spans",
                             "array_generated", "array_caller"}
    assert {r[0] for r in TX.RULES.values()} <= set("ABCDEFG")
    # every class C and D rule states primitive, option source, none_of_these, dependency, provenance, batching
    for o, r in TX.RULES.items():
        if r[0] in "CD":
            assert all(x and x != "—" for x in (r[2], r[3], r[4], r[5], r[6], r[7])), o
    assert TX.RULES["span"][4].startswith("yes") and TX.RULES["enum"][4].startswith("no")


SCHEMA = {"type": "object", "$defs": {"Tier": {"enum": ["a", "b"]}},
          "properties": {"name": {"type": "string"}, "tier": {"$ref": "#/$defs/Tier"},
                         "opt": {"anyOf": [{"type": "boolean"}, {"type": "null"}]},
                         "u": {"anyOf": [{"type": "string"}, {"type": "integer"}]},
                         "items": {"type": "array", "items": {"type": "object", "properties": {"x": {"type": "string"}}}},
                         "ext": {"$ref": "https://e/x.json"}}}
EXT = {"https://e/x.json": {"type": "object", "properties": {"y": {"type": "integer"}}}}
ANN = {"t": {"/": {"origin": "structure", "importance": "low"}, "/name": {"origin": "span", "importance": "high"},
             "/tier": {"origin": "enum", "importance": "medium"}, "/opt": {"origin": "bool", "importance": "low"},
             "/u": {"origin": "unsupported", "importance": "low"},
             "/items": {"origin": "array_objects", "importance": "low"}, "/items/[]": {"origin": "structure", "importance": "low"},
             "/items/[]/x": {"origin": "span", "importance": "low"}, "/ext": {"origin": "structure", "importance": "low"},
             "/ext/y": {"origin": "span_parse", "importance": "low", "note": "n"}}}


def test_nodes_resolve_refs_nullable_unions_and_external():
    ns = TX.nodes(SCHEMA, EXT)
    assert ("/tier", "leaf", "enum") in ns and ("/opt", "leaf", "boolean") in ns and ("/u", "leaf", "union") in ns
    assert ("/items/[]/x", "leaf", "string") in ns and ("/ext/y", "leaf", "integer") in ns


def test_classify_derives_columns_and_container_blocks_v0():
    rows = {r.pointer: r for r in TX.classify("t", "extraction", SCHEMA, ANN, EXT)}
    assert rows["/name"].cls == "D" and rows["/name"].provenance == "SOURCE_SPAN"
    assert rows["/tier"].cls == "C" and rows["/tier"].primitive == "choice"
    assert rows["/items"].cls == "G" and rows["/items/[]/x"].v0.startswith("no: inside an array of objects")
    assert rows["/ext/y"].note == "n" and rows["/u"].cls == "G"


@pytest.mark.parametrize("mut,msg", [
    (lambda a: a["t"].pop("/name"), "no annotation"),
    (lambda a: a["t"]["/name"].update(origin="nope"), "bad annotation"),
    (lambda a: a["t"]["/name"].update(importance="huge"), "bad annotation"),
    (lambda a: a["t"]["/name"].update(origin="array_spans"), "does not fit"),
    (lambda a: a["t"].update({"/ghost": {"origin": "span", "importance": "low"}}), "unknown pointers"),
])
def test_classify_rejects_bad_annotations(mut, msg):
    a = json.loads(json.dumps(ANN))
    mut(a)
    with pytest.raises(ValueError, match=msg):
        TX.classify("t", "extraction", SCHEMA, a, EXT)


def test_summary_and_prediction_logic():
    rows = TX.classify("t", "extraction", SCHEMA, ANN, EXT) + [
        TX.Row("n", "non_extraction", "/", "object", "object", "structure", "A", *["x"] * 12)]
    s = TX.summary(rows)
    p = s["prediction"]
    assert set(p) >= {"a_holds", "b_holds", "c_holds", "verdict"}
    assert p["verdict"] == ("CONFIRMED" if p["a_holds"] and p["b_holds"] and p["c_holds"] else "WRONG")
    assert s["leaves"] == sum(r.kind == "leaf" for r in rows)


def test_real_sample_meets_exit_criteria(tmp_path, capsys):
    rows = TX.load_all()
    s = TX.summary(rows)
    assert s["schemas_by_group"]["extraction"] >= 6 and s["schemas_by_group"]["non_extraction"] >= 4
    assert s["leaves"] >= 150
    assert all(r.alternatives and r.jev_implementations for r in rows)
    assert TX.main([], out=tmp_path) == 0
    d = json.loads((tmp_path / "taxonomy.json").read_text())
    assert d["summary"]["prediction"]["verdict"] in ("CONFIRMED", "WRONG")
    assert "prediction" in capsys.readouterr().out
