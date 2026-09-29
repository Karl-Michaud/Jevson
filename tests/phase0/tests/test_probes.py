from __future__ import annotations

import itertools
import json
import sys

import pytest

from tests.phase0 import common
from tests.phase0 import probes as PR
from tests.phase0.datasets import cases as CS
from tests.phase0.datasets.models import Cluster, Mention
from tests.phase0.tests import minicorpus as MC


@pytest.fixture(scope="module")
def mini(tmp_path_factory):
    root = tmp_path_factory.mktemp("mini")
    p = MC.make(root)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], root / "cases")
    present, absent = common.selection(root / "cases", p["corpus"])
    return {"p": p, "present": present, "absent": absent, "texts": common.texts(p["corpus"]),
            "domains": common.domains(p["corpus"]), "cases": root / "cases"}


def rec(answers: dict) -> dict:
    return {"response": {"status": 200, "body": {"answers": answers}}}


def choice(**p):
    return {"probabilities": p, "choice": max(p, key=p.get)}


# ---------------------------------------------------------------- probes 1-3

def test_build_123_one_request_per_document(mini):
    reqs = PR.build_123(mini["present"], mini["absent"], mini["texts"])
    assert len({r.rid for r in reqs}) == len(reqs)
    q = next(iter(reqs[0].questions.values()))
    assert q["criteria"]["none_of_these"].startswith("None of the other options")
    assert reqs[0].state["source"] == mini["texts"][reqs[0].rid.split(":", 1)[1]]


def _perfect_recs(mini):
    recs = {}
    for tag, cases in (("p13", mini["present"]), ("p2", mini["absent"])):
        for c in cases:
            opts = [o.id for o in c.options] + ["none_of_these"]
            target = next((o.id for o in c.options if o.label == "correct"), "none_of_these")
            recs.setdefault(f"{tag}:{c.doc_id}", rec({}))["response"]["body"]["answers"][c.case_id] = choice(
                **{k: (0.9 if k == target else round(0.1 / (len(opts) - 1), 2)) for k in opts})
    return recs


def test_score_123_perfect_answers_go(mini):
    s = PR.score_123(mini["present"], mini["absent"], _perfect_recs(mini), mini["domains"])
    assert s["probe1"]["rate"] == 1.0 and s["probe1"]["verdict"] == "go"
    assert s["probe2"]["rate"] == 1.0 and s["probe3"]["rate"] == 0.0 and s["probe3"]["verdict"] == "go"
    assert s["candidate_selection"] == "go" and not s["abandon"]
    assert len(s["decisions"]) == len(mini["present"]) + len(mini["absent"])


def test_score_123_missing_answers_stop(mini):
    s = PR.score_123(mini["present"], mini["absent"], {}, mini["domains"])
    assert s["probe1"]["counts"]["invalid"] == s["probe1"]["n"] and s["probe1"]["verdict"] == "stop"
    assert s["abandon"] and s["candidate_selection"].startswith("stop")


def test_score_123_conditional_branch(mini):
    recs = _perfect_recs(mini)
    # turn ~20% of present answers into false abstentions: probe 3 conditional or stop, probe 1 below go
    for i, c in enumerate(mini["present"]):
        if i % 6 == 0:
            a = recs[f"p13:{c.doc_id}"]["response"]["body"]["answers"][c.case_id]["probabilities"]
            a.update({k: 0.0 for k in a})
            a["none_of_these"] = 1.0
            recs[f"p13:{c.doc_id}"]["response"]["body"]["answers"][c.case_id]["choice"] = "none_of_these"
    s = PR.score_123(mini["present"], mini["absent"], recs, mini["domains"])
    assert s["probe1"]["verdict"] in ("conditional", "stop")


# ---------------------------------------------------------------- probe 4

def _cluster():
    ms = [Mention(id=f"c{i}", text=t, spans=[(i, i + 1)], gold=g, role_noun=r)
          for i, (t, g, r) in enumerate([("Acme", "E1", False), ("the Company", "E1", True), ("Beta", "E2", False), ("the Buyer", "E2", True)])]
    return Cluster(cluster_id="k#organization", doc_id="d", entity_type="organization", passage_start=0,
                   passage_end=10, mentions=ms)


def _p4recs(cl, same=0.95, diff=0.02, overrides=None, runs=("A", "B")):
    out = {}
    for run in runs:
        ans = {}
        for i, j in itertools.combinations(range(len(cl.mentions)), 2):
            ans[f"p{i}_{j}"] = {"noul": same if cl.mentions[i].gold == cl.mentions[j].gold else diff}
        ans.update(overrides or {})
        out[f"{run}:p4:{cl.cluster_id}"] = rec(ans)
    return out


def test_build_4_keyed_pairs():
    cl = _cluster()
    r = PR.build_4([cl], {"d": "Acme Beta the Company the Buyer"})[0]
    assert len(r.questions) == 6 and r.state["candidates"]["c1"] == "the Company"
    assert "candidates.c0" in r.questions["p0_1"]["instructions"]


def test_score_4_perfect_and_grid_top():
    cl = _cluster()
    s = PR.score_4([cl], _p4recs(cl))
    assert s["floor"]["value"] == 0.45 and s["floor"]["grid_top_binds"]
    assert s["verdict"] == "go" and s["pooled"]["correct_rate"] == 1.0 and s["chosen_variant"] == "internal"
    assert s["pair_flips"] == {"k": 0, "n": 6}


def test_score_4_no_floor_is_stop_and_invalid_runs_unresolved():
    cl = _cluster()
    s = PR.score_4([cl], _p4recs(cl, same=0.03))
    assert s["floor"]["no_value_qualified"] and s["verdict"] == "stop"
    recs = _p4recs(cl, overrides={"p0_1": {"noul": "x"}})
    s2 = PR.score_4([cl], recs)
    assert s2["invalid_cluster_runs"] == 2 and s2["pooled"]["correct"] == 0
    assert PR.score_4([cl], {})["verdict"] == "stop"


def test_score_4_merge_counts_silently_wrong():
    cl = _cluster()
    s = PR.score_4([cl], _p4recs(cl, overrides={"p0_2": {"noul": 0.9}, "p1_2": {"noul": 0.9}, "p0_3": {"noul": 0.9},
                                                  "p1_3": {"noul": 0.9}}))
    assert s["pooled"]["silently_wrong"] > 0 and s["verdict"] == "stop"


# ---------------------------------------------------------------- probe 5

def test_probe5_rebuilds_the_original_conditions_without_touching_jevclient():
    before = sys.modules.get("jevclient")
    mod = PR.probe5_module()
    assert sys.modules.get("jevclient") is before
    assert len(mod.WORDS) == 320 and sum(mod.TRUTH) == 100
    reqs = PR.build_5(mod)
    assert len(reqs) == 358
    idx = next(r for r in reqs if r.meta["condition"] == "IDX-320")
    assert idx.questions["q137"]["instructions"] == "Is `items[137]` the name of a fruit?"
    key = next(r for r in reqs if r.meta["condition"] == "KEY-320")
    assert key.questions["q5"]["instructions"] == "Is `items.k5` the name of a fruit?"


def test_probe5_module_restores_existing_jevclient(monkeypatch):
    import types
    sentinel = types.ModuleType("jevclient")
    monkeypatch.setitem(sys.modules, "jevclient", sentinel)
    sys.modules.pop("jev_api.probe_state_references", None)
    PR.probe5_module()
    assert sys.modules["jevclient"] is sentinel


@pytest.mark.parametrize("idx_wrong,key_wrong,verdict", [
    (0.6, 0.0, "reproduces [P4]"), (0.0, 0.0, "indexed references are fine: revisit R13"), (0.1, 0.0, "not reproduced"),
    (0.6, 0.1, "not reproduced")])
def test_score_5_rules(idx_wrong, key_wrong, verdict):
    mod = PR.probe5_module()
    reqs = PR.build_5(mod)
    recs = {}
    for r in reqs:
        ans = {}
        for k, gi in r.meta["items"].items():
            truth = mod.TRUTH[gi]
            rate = idx_wrong if r.meta["condition"] == "IDX-320" else key_wrong if r.meta["condition"] == "KEY-320" else 0.0
            wrong = (gi % 100) < rate * 100
            ans[k] = {"noul": 0.9 if truth != wrong else 0.1}
        recs[r.rid] = rec(ans)
    s = PR.score_5(reqs, recs, mod.TRUTH)
    assert s["verdict"] == verdict
    del recs[reqs[0].rid]
    assert PR.score_5(reqs, recs, mod.TRUTH)["conditions"][reqs[0].meta["condition"]]["invalid"] > 0


# ---------------------------------------------------------------- probe 6

def test_probe6_build_and_score(mini):
    hostile, benign, base = common.hostile(mini["cases"], mini["p"]["corpus"])
    reqs = PR.build_6(hostile, benign, base, mini["texts"])
    att = [r for r in reqs if r.meta["kind"] == "attacked"]
    assert att and all(h.note in r.state["source"] for r, h in zip(att, hostile))
    # a style-B note repeats the advocated text: that occurrence is offered and labelled "note"
    b = next(r for r in att if r.meta["style"] == "B")
    assert any(o["label"] == "note" for o in b.meta["options"]["present"].values())
    # steer every attacked present question to the advocated text; abstain on baseline
    recs = {}
    for r in reqs:
        ans = {"screen": {"noul": 0.9 if r.meta["kind"] == "attacked" else 0.1}}
        for q, opts in r.meta.get("options", {}).items():
            ids = list(opts) + ["none_of_these"]
            if r.meta["kind"] == "attacked":
                tgt = next(i for i, o in opts.items() if o["text"] == r.meta["advocated"]) if any(
                    o["text"] == r.meta["advocated"] for o in opts.values()) else "none_of_these"
            else:
                tgt = "none_of_these"
            ans[q] = choice(**{i: (1.0 if i == tgt else 0.0) for i in ids})
        recs[r.rid] = rec(ans)
    s = PR.score_6(reqs, recs)
    assert s["attacked_present"]["steered_rate"] == 1.0 and s["baseline_present"]["abstain_rate"] == 1.0
    assert s["attacked_screen"]["flagged_rate"] == 1.0 and s["benign_screen"]["flagged_rate"] == 0.0
    assert "steered_rate" not in s["attacked_screen"] and "flagged_rate" not in s["attacked_present"]
    s2 = PR.score_6(reqs, {})
    assert s2["attacked_present"].get("invalid", 0) == s2["attacked_present"]["n"]
    assert s2["benign_screen"]["flagged_rate"] == 1.0          # an invalid screen answer counts as flagged


def test_probe6_skips_absent_question_without_options(mini):
    hostile, _, base = common.hostile(mini["cases"], mini["p"]["corpus"])
    h = hostile[0]
    b = base[h.base_case_id]
    only_correct = b.model_copy(update={"options": [o for o in b.options if o.label == "correct"]})
    qs, meta = PR._probe6_questions(only_correct, mini["texts"][b.doc_id], None)
    assert "absent" not in qs and "present" in qs
    r = PR.Request("x", {}, qs, {"kind": "baseline", "options": meta, "advocated": "zz", "style": "A"})
    s = PR.score_6([r], {"x": rec({})})
    assert s["baseline_absent"]["skipped_no_options"] == 1


# ---------------------------------------------------------------- probe 7

def test_score_7_calibration_reading():
    dec = [{"probe": "present", "outcome": "correct", "status": "ok", "p_selected": 90}] * 9 + \
          [{"probe": "present", "outcome": "wrong", "status": "ok", "p_selected": 90}] + \
          [{"probe": "absent", "outcome": "abstain", "status": "ok", "p_selected": 100}] * 5 + \
          [{"probe": "absent", "outcome": "tie", "status": "tie", "p_selected": 50},
           {"probe": "absent", "outcome": "invalid", "status": "invalid", "p_selected": None}]
    s = PR.score_7(dec)
    assert s["primary_non_tie"]["n"] == 15 and s["ties_included"]["n"] == 16
    assert s["excluded_ties"] == 1 and s["excluded_invalid"] == 1
    assert s["primary_non_tie"]["ece"] == pytest.approx(0.0)
    assert PR.score_7([])["primary_non_tie"] == {"n": 0}


# ---------------------------------------------------------------- probe 8

def test_probe8_build_and_score(mini):
    cases = common.single(mini["cases"], mini["p"]["corpus"])
    reqs = PR.build_8(cases, mini["texts"])
    assert sum(len(r.questions) for r in reqs) == len(cases)
    q = next(iter(reqs[0].questions.values()))
    assert list(q["criteria"]) == ["c0", "none_of_these"]
    recs = {}
    for r in reqs:
        ans = {}
        for cid in r.questions:
            s = next(c for c in cases if c.case_id == cid).set
            ans[cid] = choice(c0=1.0, none_of_these=0.0) if s == "lone_correct" else (
                choice(c0=0.5, none_of_these=0.5) if s == "lone_partial" else choice(c0=0.0, none_of_these=1.0))
        recs[r.rid] = rec(ans)
    s = PR.score_8(cases, recs)
    assert s["lone_correct"]["rate"] == 1.0 and s["lone_wrong"]["rate"] == 1.0
    assert s["lone_partial"].get("tie") == s["lone_partial"]["n"] and "constructed" in s["lone_partial"]
    s2 = PR.score_8(cases, {})
    assert s2["lone_correct"].get("invalid") == s2["lone_correct"]["n"]


def test_dry_answers_shape(mini):
    reqs = PR.build_123(mini["present"], mini["absent"], mini["texts"])
    recs = PR.dry_answers(reqs)
    assert set(recs) == {r.rid for r in reqs}
    s = PR.score_123(mini["present"], mini["absent"], recs, mini["domains"])
    assert s["probe1"]["n"] == len(mini["present"])
