from __future__ import annotations

import pytest

from tests.phase0 import common
from tests.phase0 import probes as PR
from tests.phase0 import stats as S
from tests.phase0 import templates as T
from tests.phase0.datasets import cases as CS
from tests.phase0.tests import minicorpus as MC


@pytest.mark.parametrize("args,expected", [
    ((140, 7, 150, 7, 150, False), "proceed"),       # 0.0467 committed-when-absent, 0.0467 wrong
    ((140, 8, 150, 7, 150, False), "marginal"),      # wrong-when-present 0.0533 > 0.05
    ((140, 7, 150, 8, 150, False), "marginal"),      # 0.0533
    ((140, 7, 150, 15, 150, False), "marginal"),     # exactly 0.10 is not > 0.10
    ((140, 7, 150, 16, 150, False), "drop"),         # 0.1067
    ((105, 0, 150, 0, 150, False), "proceed"),       # correct exactly 0.70
    ((104, 0, 150, 0, 150, False), "drop"),          # correct 0.6933
    ((140, 0, 150, 0, 150, True), "drop"),           # a band in stop
])
def test_gate_verdict_edges(args, expected):
    assert S.gate_verdict(*args) == expected


def test_gate_verdict_rejects_and_oc():
    with pytest.raises(ValueError):
        S.gate_verdict(0, 0, 0, 0, 1, False)
    oc = S.gate_oc(0.03, 150)
    assert oc["p_at_most_0.05"] == pytest.approx(0.917, abs=1e-3) and oc["p_above_0.10"] < 1e-3
    assert S.gate_oc(0.10, 150)["p_above_0.10"] == pytest.approx(0.432, abs=1e-3)


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    root = tmp_path_factory.mktemp("g")
    p = MC.make(root)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], root / "cases")
    present, absent = common.selection(root / "cases", p["corpus"])
    return present, absent, common.texts(p["corpus"])


def rec(a):
    return {"response": {"status": 200, "body": {"answers": a}}}


def test_build_gate_keys_and_state(mini):
    present, absent, texts = mini
    reqs = PR.build_gate({"g1": present, "g2": absent}, texts)
    r = reqs[0]
    cid = r.meta["cases"][0]
    assert cid in r.questions and f"{cid}#v:c0" in r.questions
    case = next(c for c in present + absent if c.case_id == cid)
    assert r.questions[f"{cid}#v:c0"]["instructions"] == T.GATE_INSTRUCTIONS.format(cid="f0c0", label=case.label)
    assert "f0c0" in r.state["candidates"] and r.state["source"] == texts[r.rid.split(":", 1)[1]]


def _answers(cases, correct_gate: float, wrong_gate: float, pick="truth"):
    out = {}
    for c in cases:
        a = out.setdefault(c.doc_id, {})
        opts = [o.id for o in c.options] + ["none_of_these"]
        tgt = next((o.id for o in c.options if o.label == "correct"), None)
        if tgt is None:                                   # absent: pick a wrong option (the dangerous commit)
            tgt = c.options[0].id
        a[c.case_id] = {"probabilities": {k: (1.0 if k == tgt else 0.0) for k in opts}, "choice": tgt}
        for o in c.options:
            a[f"{c.case_id}#v:{o.id}"] = {"noul": correct_gate if o.label == "correct" else wrong_gate}
    return out


def test_score_gate_blocks_wrong_commits(mini):
    present, absent, _ = mini
    recs = {f"g1:{d}": rec(a) for d, a in _answers(present, 0.9, 0.1).items()}
    recs |= {f"g2:{d}": rec(a) for d, a in _answers(absent, 0.9, 0.1).items()}
    s = PR.score_gate(present, absent, recs, "g1", "g2")
    assert s["committed_when_absent_no_gate"]["k"] == s["n_absent"]       # without the gate: all committed
    assert s["committed_when_absent"]["k"] == 0 and s["correct_commits"]["rate"] == 1.0
    assert s["verdict"] == "proceed" and s["gate_pass_rate_by_option_label"]["correct"]["passed"] > 0


def test_score_gate_invalid_gate_fails_and_rejecting_gate_drops(mini):
    present, absent, _ = mini
    recs = {f"g1:{d}": rec(a) for d, a in _answers(present, 0.3, 0.3).items()}
    recs |= {f"g2:{d}": rec(a) for d, a in _answers(absent, 0.9, 0.9).items()}
    s = PR.score_gate(present, absent, recs, "g1", "g2")
    assert s["gated_present"].get("verification_failed") == s["n_present"] and s["verdict"] == "drop"
    for a in recs.values():
        for k in a["response"]["body"]["answers"]:
            if "#v:" in k:
                a["response"]["body"]["answers"][k] = {"noul": "x"}
    s2 = PR.score_gate(present, absent, recs, "g1", "g2")
    assert s2["committed_when_absent"]["k"] == 0          # an invalid verification answer fails the gate
    s3 = PR.score_gate(present, absent, {}, "g1", "g2")
    assert s3["gated_present"].get("invalid") == s3["n_present"]


# ---------------------------------------------------------------- gate pool pipeline

import json  # noqa: E402

import httpx  # noqa: E402

from tests.phase0 import runner as RN  # noqa: E402
from tests.phase0 import run_probe_9  # noqa: E402
from tests.phase0.datasets import agreement as AG  # noqa: E402
from tests.phase0.datasets import build as B  # noqa: E402
from tests.phase0.datasets import fetch as F  # noqa: E402
from tests.phase0.datasets import tasks as TK  # noqa: E402
from tests.phase0.datasets.models import load_manifest  # noqa: E402


def _gate_corpus(tmp_path):
    p = MC.make(tmp_path)
    gate = [F.Doc(f"g{i}", "receipt", "id", MC.RECEIPT.replace("10,000", f"9{i},000"), "u", "cc-by-4.0", "x", pool="gate")
            for i in range(6)]
    F.write_docs(gate, p["corpus"])
    for d in gate:
        (p["extraction"] / "llm" / f"{d.doc_id}.json").write_text(json.dumps(
            {"doc_id": d.doc_id, "fields": {"receipt.total_price": ["30,000", "99,000"], "receipt.cashprice": ["50,000"]}}))
    recs = B.build_options(p["corpus"], p["extraction"], "gate")
    B.write_jsonl(recs, p["extraction"] / "options_gate.jsonl")
    texts = {d.doc_id: d.text for d in gate}
    for r in recs:
        lab = {"doc_id": r["doc_id"], "multi_entity": False, "processing_note": None,
               "fields": {f["field_id"]: MC.label_for(r["doc_id"], f, texts[r["doc_id"]]) for f in r["fields"]}}
        (p["labels"] / "candidates" / f"{r['doc_id']}.json").write_text(json.dumps(lab))
    return p


def test_gate_pool_pipeline_keeps_phase0_separate(tmp_path, capsys):
    p = _gate_corpus(tmp_path)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], tmp_path / "c")
    assert not any(json.loads(x)["doc_id"].startswith("g") for x in (tmp_path / "c" / "probe1_3.jsonl").read_text().splitlines())
    s = CS.build_gate(p["corpus"], p["extraction"], p["labels"], tmp_path / "c")
    assert s["documents"] == 6 and (tmp_path / "c" / "gate_present.jsonl").exists()
    assert len(TK.extraction_tasks(load_manifest(p["corpus"]), "gate")) == 6
    assert TK.main(["extraction", str(tmp_path / "t"), "gate"], p["corpus"]) == 0
    assert B.main(["options", "gate"], p["corpus"], p["extraction"]) == 0
    assert AG.main(["sample-gate", str(tmp_path / "s")], p["labels"], p["extraction"]) == 0
    (p["labels"] / "second" / "candidates").mkdir(parents=True)
    first = sorted((p["labels"] / "candidates").glob("g*.json"))[0]
    (p["labels"] / "second" / "candidates" / first.name).write_text(first.read_text())
    assert AG.main(["report-gate"], p["labels"], p["extraction"]) == 0
    assert json.loads((p["labels"] / "agreement_gate.json").read_text())["n_documents"] == 1


def test_fetch_gate_mode_is_disjoint_and_tagged(tmp_path):
    docs = [F.Doc(f"d{i}", "resume", "en", "t", "u", "public-domain-us-gov", "x") for i in range(5)]
    out = F.fresh(docs, {"d0", "d2"}, 2)
    assert [d.doc_id for d in out] == ["d1", "d3"] and all(d.pool == "gate" for d in out)
    from tests.phase0.tests.test_fetch import _router, _cuad, _word
    client = httpx.Client(transport=httpx.MockTransport(_router))
    scratch = tmp_path / "s"
    scratch.mkdir()
    (scratch / "CUADv1.json").write_text(json.dumps(_cuad(120)))
    long_gt = {"valid_line": [{"words": [_word(f"L{i}", i, 0, i)]} for i in range(9)]}
    (scratch / "cord_test_ground_truth.jsonl").write_text("\n".join(json.dumps(long_gt) for _ in range(60)))
    root = tmp_path / "corpus"
    assert F.main(["cuad", str(scratch)], client=client, root=root) == 0
    for src in F.GATE_COUNTS:
        assert F.main(["gate", str(scratch), src], client=client, root=root) == 0
    man = [json.loads(x) for x in (root / "manifest.jsonl").read_text().splitlines()]
    main_ids = {m["doc_id"] for m in man if m["pool"] == "main"}
    gate = [m for m in man if m["pool"] == "gate"]
    assert gate and not main_ids & {m["doc_id"] for m in gate}
    assert sum(m["pool"] == "gate" and m["domain"] == "contract" for m in man) == 50


def test_run_probe_9_dry_run(tmp_path, monkeypatch):
    p = _gate_corpus(tmp_path)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], tmp_path / "cases")
    CS.build_gate(p["corpus"], p["extraction"], p["labels"], tmp_path / "cases")
    monkeypatch.setattr(common, "CASES", tmp_path / "cases")
    monkeypatch.setattr(common, "CORPUS", p["corpus"])
    monkeypatch.setattr(RN, "OUT", tmp_path / "out")
    monkeypatch.setattr(RN, "RESULTS", tmp_path / "results")
    assert run_probe_9.main(["--dry-run"]) == 0
    s = json.loads((tmp_path / "out" / "dry" / "probe9.summary.json").read_text())
    assert s["fresh"]["verdict"] in ("proceed", "marginal", "drop") and "paired_phase0" in s
