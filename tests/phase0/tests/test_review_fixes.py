"""Regression tests for the review-round-1 findings and the rule-bearing branches they listed."""
from __future__ import annotations

import asyncio
import itertools
import json
import math

import httpx
import pytest

from tests.phase0 import probes as PR
from tests.phase0 import runner as RN
from tests.phase0 import stats as S
from tests.phase0.client import Budget, BudgetExceeded, JevClient, RateLimiter
from tests.phase0.datasets import cases as CS
from tests.phase0.datasets import models as M
from tests.phase0.tests import minicorpus as MC
from tests.phase0.tests.test_probes import _cluster, _p4recs, rec


async def _nosleep(_):
    return None


def _client(budget=5, handler=None):
    return JevClient("k", transport=handler or RN.fake_transport(), budget=Budget(budget),
                     limiter=RateLimiter(per_min=10**9, sleep=_nosleep), sleep=_nosleep, max_retries=0)


def _reqs(n):
    return [RN.Request(f"r{i}", {"source": f"s{i}"}, {"q": {"type": "noul", "instructions": "Is it?"}}) for i in range(n)]


def test_runner_keeps_answers_paid_for_before_an_exception(tmp_path):
    raw = tmp_path / "x.jsonl"
    c = _client(budget=3)
    with pytest.raises(BudgetExceeded):
        asyncio.run(RN.execute(c, _reqs(5), raw))
    assert len(RN.load_raw(raw)) == 3


def test_runner_resends_on_changed_request_and_tolerates_truncated_line(tmp_path, capsys):
    raw = tmp_path / "x.jsonl"
    reqs = _reqs(2)
    asyncio.run(RN.execute(_client(), reqs, raw))
    with raw.open("a") as f:
        f.write('{"rid": "r0", "resp')                     # a write cut short
    changed = [RN.Request("r0", {"source": "other"}, reqs[0].questions), reqs[1]]
    c = _client()
    out = asyncio.run(RN.execute(c, changed, raw))
    assert c.budget.used == 1 and out["r0"]["request_sha256"] == RN.request_hash(changed[0])
    assert "not valid JSON" in capsys.readouterr().err


def test_runner_all_passes_fail_keeps_minus_one(tmp_path):
    def boom(req):
        raise httpx.ConnectError("down")
    c = _client(budget=10, handler=httpx.MockTransport(boom))
    out = asyncio.run(RN.execute(c, _reqs(1), tmp_path / "x.jsonl", passes=2))
    assert out["r0"]["response"]["status"] == -1 and RN.answers_of(out["r0"]) == {}


def test_score_7_ties_judged_by_argmax_label():
    d = [{"probe": "present", "outcome": "tie", "argmax_outcome": "correct", "status": "tie", "p_selected": 50},
         {"probe": "absent", "outcome": "tie", "argmax_outcome": "wrong", "status": "tie", "p_selected": 50},
         {"probe": "present", "outcome": "correct", "argmax_outcome": "correct", "status": "ok", "p_selected": 90}]
    s = PR.score_7(d)
    assert s["ties_included"]["accuracy"] == pytest.approx(2 / 3)


def test_score_5_rejects_non_numeric_and_out_of_range():
    mod = PR.probe5_module()
    reqs = PR.build_5(mod)
    recs = {r.rid: rec({k: {"noul": None} for k in r.questions}) for r in reqs[:1]}
    recs[reqs[1].rid] = rec({k: {"noul": 1.7} for k in reqs[1].questions})
    s = PR.score_5(reqs, recs, mod.TRUTH)
    c = s["conditions"][reqs[0].meta["condition"]]
    assert c["invalid"] >= len(reqs[0].questions) + len(reqs[1].questions)


def test_probe4_floor_pools_valid_pairs_of_a_run_with_an_invalid_pair():
    cl = _cluster()
    recs = _p4recs(cl, overrides={"p0_2": {"noul": "x"}})
    s = PR.score_4([cl], recs)
    assert s["invalid_pairs"] == 2 and s["floor"]["same_entity_pairs"] == 4   # 2 same pairs x 2 runs


def test_corr_undefined_is_nan():
    for pc, pa in ((1.0, 0.0), (0.0, 1.0), (0.5, 0.0), (0.0, 0.5)):
        assert math.isnan(S.corr_probes_1_3(pc, pa))


def test_options_must_be_in_source_order():
    opts = [{"id": "c0", "text": "b", "start": 2, "end": 3, "label": "correct"},
            {"id": "c1", "text": "a", "start": 0, "end": 1, "label": "wrong"},
            {"id": "c2", "text": "c", "start": 4, "end": 5, "label": "wrong"},
            {"id": "c3", "text": "d", "start": 6, "end": 7, "label": "wrong"}]
    with pytest.raises(Exception, match="source order"):
        M.SelectionCase.model_validate({"case_id": "x", "probe": "p1p3", "doc_id": "d", "field_id": "f", "label": "abc",
                                        "options": opts, "hard": False, "repeated": False, "superseded": False,
                                        "multi_entity": False})


def test_runner_final_4xx_not_resent_and_fragment_does_not_swallow_next(tmp_path):
    raw = tmp_path / "x.jsonl"
    reqs = _reqs(2)
    c = _client(handler=httpx.MockTransport(lambda req: httpx.Response(401, json={"detail": "no"})))
    asyncio.run(RN.execute(c, reqs, raw))
    c2 = _client()
    asyncio.run(RN.execute(c2, reqs, raw))
    assert c2.budget.used == 0                                   # 401 is final (§2.1)
    raw2 = tmp_path / "y.jsonl"
    raw2.write_text('{"rid": "zz", "resp')                      # cut short, no newline
    asyncio.run(RN.execute(_client(), reqs, raw2))
    c3 = _client()
    asyncio.run(RN.execute(c3, reqs, raw2))
    assert c3.budget.used == 0 and set(RN.load_raw(raw2)) == {"r0", "r1"}


def test_probe4_per_run_verdict_stop_when_no_floor():
    cl = _cluster()
    s = PR.score_4([cl], _p4recs(cl, same=0.03))
    assert all(v["verdict"] == "stop" for v in s["per_run"].values())


@pytest.fixture
def mini(tmp_path):
    p = MC.make(tmp_path)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], tmp_path / "cases")
    p["cases"] = tmp_path / "cases"
    return p


def test_status_must_agree_with_option_labels(mini):
    r = json.loads((mini["extraction"] / "options.jsonl").read_text().splitlines()[0])
    lab = json.loads((mini["labels"] / "candidates" / f"{r['doc_id']}.json").read_text())
    f = next(f for f in r["fields"] if f["options"])
    lab["fields"][f["field_id"]]["status"] = "absent"
    lab["fields"][f["field_id"]]["options"][f["options"][0]["id"]] = "correct"
    text = (mini["corpus"] / r["domain"] / f"{r['doc_id']}.txt").read_text()
    with pytest.raises(ValueError, match="correct option on a field labelled absent"):
        CS.validate_candidate_labels(lab, r, text)


def test_adjudicated_labels_are_validated(mini, tmp_path):
    r = json.loads((mini["extraction"] / "options.jsonl").read_text().splitlines()[0])
    f = next(f for f in r["fields"] if f["options"])
    (mini["labels"] / "adjudication.jsonl").write_text(json.dumps(
        {"kind": "field", "doc_id": r["doc_id"], "field_id": f["field_id"], "decision": {"options": {"c0": "correct"}}}) + "\n")
    with pytest.raises(ValueError, match="differ from those offered"):
        CS.build_all(mini["corpus"], mini["extraction"], mini["labels"], tmp_path / "c")


def test_hostile_loader_checks_style(mini, tmp_path):
    present = {c.case_id: c for c in M.load_selection(mini["cases"] / "probe1_3.jsonl", mini["corpus"])}
    h = json.loads((mini["cases"] / "probe6_attacked.jsonl").read_text().splitlines()[0])
    h["note"] = h["note"] + " "
    bad = tmp_path / "h.jsonl"
    bad.write_text(json.dumps(h) + "\n")
    with pytest.raises(ValueError, match="does not follow style"):
        M.load_hostile(bad, present, mini["corpus"])


def test_caps_stop_at_n(mini):
    present = M.load_selection(mini["cases"] / "probe1_3.jsonl", mini["corpus"])
    texts = {d: M.doc_text(r, mini["corpus"]) for d, r in M.load_manifest(mini["corpus"]).items()}
    assert len(CS.hostile_cases(present, n=1, texts=texts)) == 1
    o = lambda i, lab, t="abc def": M.Option(id=f"c{i}", text=t, start=i * 10, end=i * 10 + len(t), label=lab)  # noqa: E731
    insts = [CS.Instance(f"d{k}", "receipt.total_price", (o(0, "correct"), o(1, "wrong")), "present", False, False, 100, False)
             for k in range(3)]
    assert sum(c.set == "lone_correct" for c in CS.single_cases(insts, {f"d{k}": "abc def   abc def" for k in range(3)}, n=2)) == 2
    mrecs = [json.loads(x) for x in (mini["extraction"] / "mentions.jsonl").read_text().splitlines()]
    mlabels = {json.loads(p.read_text())["passage_id"]: json.loads(p.read_text()) for p in (mini["labels"] / "mentions").glob("*.json")}
    del mlabels[mrecs[0]["passage_id"]]                     # an unlabelled passage is skipped
    chosen, stats = CS.clusters(mrecs, mlabels, {d: "contract" for d in texts}, n=2)
    assert len(chosen) == 2 and stats["labelled"] == len(mrecs) - 1


def test_over_cap_and_degenerate_partial():
    o = M.Option(id="c0", text="a", start=0, end=1, label="correct")
    inst = CS.Instance("d", "receipt.total_price", (o,), "present", False, False, 10, True)
    assert CS.present_case(inst, "a") is None and CS.absent_case(inst) is None
    assert CS.constructed_partial(" ab", 0, 3) is None
    assert CS.constructed_partial("ab ,c", 0, 5) == (0, 2)


def test_duplicate_option_span_rejected():
    opts = [{"id": "c0", "text": "a", "start": 0, "end": 1, "label": "correct"},
            {"id": "c1", "text": "a", "start": 0, "end": 1, "label": "wrong"},
            {"id": "c2", "text": "b", "start": 2, "end": 3, "label": "wrong"},
            {"id": "c3", "text": "c", "start": 4, "end": 5, "label": "wrong"}]
    with pytest.raises(Exception, match="duplicate option span"):
        M.SelectionCase.model_validate({"case_id": "x", "probe": "p1p3", "doc_id": "d", "field_id": "f", "label": "abc",
                                        "options": opts, "hard": False, "repeated": False, "superseded": False,
                                        "multi_entity": False})


@pytest.mark.parametrize("tail", ['{"rid": "zz", "x": "é', b'{"rid": "zz", "x": "\xc3'])
def test_runner_survives_non_ascii_fragment(tmp_path, tail):
    raw = tmp_path / "x.jsonl"
    if isinstance(tail, str):
        raw.write_text(tail, encoding="utf-8")
    else:
        raw.write_bytes(tail)
    reqs = _reqs(2)
    asyncio.run(RN.execute(_client(), reqs, raw))
    c = _client()
    asyncio.run(RN.execute(c, reqs, raw))
    assert c.budget.used == 0 and {"r0", "r1"} <= set(RN.load_raw(raw))
