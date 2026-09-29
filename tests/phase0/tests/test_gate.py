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
