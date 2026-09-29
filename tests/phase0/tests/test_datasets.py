from __future__ import annotations

import json
import pathlib

import pytest
from pydantic import ValidationError

from tests.phase0.datasets import agreement as AG
from tests.phase0.datasets import build as B
from tests.phase0.datasets import cases as CS
from tests.phase0.datasets import models as M
from tests.phase0.datasets import sample as SA
from tests.phase0.datasets import tasks as TK
from tests.phase0.tests import minicorpus as MC


@pytest.fixture
def mini(tmp_path):
    p = MC.make(tmp_path)
    CS.build_all(p["corpus"], p["extraction"], p["labels"], tmp_path / "cases")
    p["cases"] = tmp_path / "cases"
    return p


# ---------------------------------------------------------------- validators reject malformed cases

def _opt(i, text, start, label):
    return {"id": f"c{i}", "text": text, "start": start, "end": start + len(text), "label": label}


def _case(**kw):
    base = {"case_id": "x", "probe": "p1p3", "doc_id": "r0", "field_id": "receipt.total_price", "label": "total price",
            "options": [_opt(0, "a", 0, "correct"), _opt(1, "b", 2, "wrong"), _opt(2, "c", 4, "wrong"),
                        _opt(3, "d", 6, "partial")],
            "hard": False, "repeated": False, "superseded": False, "multi_entity": False}
    base.update(kw)
    return base


def test_selection_case_accepts_valid():
    M.SelectionCase.model_validate(_case())


@pytest.mark.parametrize("mutate,msg", [
    (lambda c: c["options"][0].pop("label"), "Field required"),                                  # missing label
    (lambda c: c["options"][0].update(label="maybe"), "Input should be"),
    (lambda c: c["options"][0].update(id="opt0"), "opaque"),
    (lambda c: c["options"].reverse(), "c0..cN"),
    (lambda c: c.update(options=[_opt(0, "a", 0, "wrong")] + c["options"][1:]), "without a correct option"),
    (lambda c: c.update(options=c["options"][:3]), "fewer than 3 competitors"),
    (lambda c: c.update(removed=[_opt(0, "z", 9, "correct")]), "present-answer case with removed"),
    (lambda c: c["options"][1].update(end=9), "span length"),
    (lambda c: c["options"][1].update(start=5, end=4), "after start"),
    (lambda c: c.update(options=[_opt(0, "a", 0, "correct"), _opt(1, "a", 0, "wrong"), _opt(2, "c", 4, "wrong"),
                                 _opt(3, "d", 6, "wrong")]), "duplicate option span"),
    (lambda c: c.update(extra=1), "Extra inputs"),
])
def test_selection_case_rejects(mutate, msg):
    c = _case()
    mutate(c)
    with pytest.raises(ValidationError, match=msg):
        M.SelectionCase.model_validate(c)


def _absent(**kw):
    c = _case(probe="p2", options=[_opt(0, "b", 2, "wrong"), _opt(1, "c", 4, "wrong"), _opt(2, "d", 6, "partial")],
              removed=[_opt(0, "a", 0, "correct"), _opt(9, "a", 8, "wrong")])
    c.update(kw)
    return c


def test_absent_case_accepts_valid():
    M.SelectionCase.model_validate(_absent())


@pytest.mark.parametrize("mutate,msg", [
    (lambda c: c["options"].__setitem__(0, _opt(0, "b", 2, "correct")), "still offers a correct option"),
    (lambda c: c.update(removed=[]), "removed no correct option"),
    (lambda c: c.update(removed=[_opt(0, "a", 0, "correct"), _opt(9, "q", 8, "wrong")]), "neither correct nor same-text"),
    (lambda c: c.update(options=[_opt(0, "a", 1, "wrong"), _opt(1, "c", 4, "wrong"), _opt(2, "d", 6, "wrong")]),
     "correct text is still offered"),
    (lambda c: c.update(options=c["options"][:2]), "fewer than 3 remaining"),
    (lambda c: c.update(options=[_opt(i, f"t{i}", 10 * i, "wrong") for i in range(51)]), "more than 50"),
])
def test_absent_case_rejects(mutate, msg):
    c = _absent()
    mutate(c)
    with pytest.raises(ValidationError, match=msg):
        M.SelectionCase.model_validate(c)


def test_loader_checks_offsets_documents_duplicates(mini, tmp_path):
    cases = M.load_selection(mini["cases"] / "probe1_3.jsonl", mini["corpus"])
    assert cases and all(c.probe == "p1p3" for c in cases)
    line = (mini["cases"] / "probe1_3.jsonl").read_text().splitlines()[0]
    bad = tmp_path / "bad.jsonl"
    bad.write_text(line + "\n" + line + "\n")
    with pytest.raises(ValueError, match="duplicate case"):
        M.load_selection(bad, mini["corpus"])
    c = json.loads(line)
    c["options"][0]["text"] = "X" * len(c["options"][0]["text"])
    bad.write_text(json.dumps(c) + "\n")
    with pytest.raises(ValueError, match="do not reproduce"):
        M.load_selection(bad, mini["corpus"])
    c = json.loads(line)
    c["doc_id"] = "nope"
    bad.write_text(json.dumps(c) + "\n")
    with pytest.raises(ValueError, match="unknown document"):
        M.load_selection(bad, mini["corpus"])


def test_combining_boundary_rejected(tmp_path):
    with pytest.raises(ValueError, match="combining"):
        M._check_spans_against("aéb", [M.Span(text="ae", start=0, end=2)], "x")


def test_manifest_duplicate_rejected(mini, tmp_path):
    line = (mini["corpus"] / "manifest.jsonl").read_text().splitlines()[0]
    root = tmp_path / "dup"
    root.mkdir()
    (root / "manifest.jsonl").write_text(line + "\n" + line + "\n")
    with pytest.raises(ValueError, match="duplicate document"):
        M.load_manifest(root)


def test_other_case_files_load_and_validate(mini, tmp_path):
    present = {c.case_id: c for c in M.load_selection(mini["cases"] / "probe1_3.jsonl", mini["corpus"])}
    assert M.load_clusters(mini["cases"] / "probe4.jsonl", mini["corpus"])
    assert M.load_hostile(mini["cases"] / "probe6_attacked.jsonl", present, mini["corpus"])
    assert M.load_screen(mini["cases"] / "probe6_benign.jsonl", mini["corpus"])
    assert M.load_single(mini["cases"] / "probe8.jsonl", mini["corpus"])
    bad = tmp_path / "b.jsonl"
    # clusters
    cl = json.loads((mini["cases"] / "probe4.jsonl").read_text().splitlines()[0])
    for mut, msg in ((lambda c: c.update(doc_id="nope"), "unknown document"),
                     (lambda c: c.update(passage_end=10**6), "beyond the document"),
                     (lambda c: c["mentions"][0].update(spans=[[0, 3]]), "does not reproduce")):
        c = json.loads(json.dumps(cl))
        mut(c)
        bad.write_text(json.dumps(c) + "\n")
        with pytest.raises(ValueError, match=msg):
            M.load_clusters(bad, mini["corpus"])
    # hostile
    h = json.loads((mini["cases"] / "probe6_attacked.jsonl").read_text().splitlines()[0])
    for mut, msg in ((lambda x: x.update(base_case_id="p2:zz"), "base case"),
                     (lambda x: x.update(advocated_text="NOPE"), "wrong option"),
                     (lambda x: x.update(insert_at=10**6), "beyond the document")):
        x = dict(h)
        mut(x)
        bad.write_text(json.dumps(x) + "\n")
        with pytest.raises(ValueError, match=msg):
            M.load_hostile(bad, present, mini["corpus"])
    # screen and single
    bad.write_text(json.dumps({"doc_id": "s0", "note_quote": "not in the text"}) + "\n")
    with pytest.raises(ValueError, match="quoted processing note"):
        M.load_screen(bad, mini["corpus"])
    bad.write_text(json.dumps({"doc_id": "zz", "note_quote": "abc"}) + "\n")
    with pytest.raises(ValueError, match="unknown document"):
        M.load_screen(bad, mini["corpus"])
    sc = json.loads((mini["cases"] / "probe8.jsonl").read_text().splitlines()[0])
    sc["doc_id"] = "zz"
    bad.write_text(json.dumps(sc) + "\n")
    with pytest.raises(ValueError, match="unknown document"):
        M.load_single(bad, mini["corpus"])


@pytest.mark.parametrize("mut,msg", [
    (lambda c: c.update(mentions=c["mentions"][:3]), "outside"),
    (lambda c: c["mentions"][0].update(id="m0"), "c0..cN"),
    (lambda c: c["mentions"][1].update(text=c["mentions"][0]["text"] + " "), "pre-merged"),
    (lambda c: [m.update(gold="E1") for m in c["mentions"]], "two gold entities"),
    (lambda c: [m.update(role_noun=False) for m in c["mentions"]], "role-noun"),
    (lambda c: c.update(passage_end=0), "empty passage"),
])
def test_cluster_rejects(mut, msg):
    c = {"cluster_id": "k", "doc_id": "d", "entity_type": "person", "passage_start": 0, "passage_end": 50,
         "mentions": [{"id": f"c{i}", "text": t, "spans": [[i, i + 1]], "gold": g, "role_noun": i == 1}
                      for i, (t, g) in enumerate([("A", "E1"), ("the B", "E1"), ("C", "E2"), ("D", "E2")])]}
    M.Cluster.model_validate(c)
    mut(c)
    with pytest.raises(ValidationError, match=msg):
        M.Cluster.model_validate(c)


def test_single_case_constructed_only_partial():
    base = {"case_id": "s", "set": "lone_wrong", "doc_id": "d", "field_id": "f", "field_type": "text", "label": "abc",
            "span": {"text": "a", "start": 0, "end": 1}, "constructed": True, "group": "g"}
    with pytest.raises(ValidationError, match="constructed"):
        M.SingleCase.model_validate(base)


def test_premerge_key_and_dump(tmp_path):
    assert M.premerge_key("Acme  Corp\n") == "Acme Corp" and M.premerge_key("US") != M.premerge_key("us")
    M.dump([M.ScreenDoc(doc_id="a", note_quote="abc")], tmp_path / "x" / "s.jsonl")
    assert M.raw_json(tmp_path / "x" / "s.jsonl") == {"doc_id": "a", "note_quote": "abc"}


# ---------------------------------------------------------------- sampling

class C:
    def __init__(self, cid, doc, hard=False, repeated=False):
        self.case_id, self.doc_id, self.hard, self.repeated = cid, doc, hard, repeated

    def __repr__(self):
        return self.case_id


def test_sample_deterministic_cap_and_shortfall():
    pool = [C(f"p{i:03d}", f"d{i % 5}") for i in range(60)]
    a1, b1, n1 = SA.sample(pool, pool, n=20, cap=3, min_hard=0.0, min_repeated=0)
    a2, _, _ = SA.sample(pool, pool, n=20, cap=3, min_hard=0.0, min_repeated=0)
    assert [c.case_id for c in a1] == [c.case_id for c in a2]
    assert len(a1) == 15 and max(sum(c.doc_id == d for c in a1) for d in {c.doc_id for c in a1}) == 3
    assert n1["n_present"] == 15


def test_sample_hard_and_repeated_swaps():
    present = [C(f"p{i:03d}", f"d{i}", hard=i % 5 == 0, repeated=i % 7 == 0) for i in range(100)]
    absent = [C(f"a{i:03d}", f"e{i}", hard=i % 5 == 0) for i in range(100)]
    p, a, notes = SA.sample(present, absent, n=40, cap=8, min_hard=0.3, min_repeated=8)
    hard = sum(c.hard for c in p + a)
    assert hard / 80 >= 0.3 and notes["hard_swaps"] > 0 and "hard_shortfall" not in notes
    assert sum(c.repeated for c in p) >= 8 and notes["repeated_swaps"] > 0


def test_sample_shortfalls_recorded():
    present = [C(f"p{i}", f"d{i}") for i in range(10)]
    p, a, notes = SA.sample(present, present, n=5, cap=8, min_hard=0.5, min_repeated=2)
    assert notes["hard_shortfall"] and notes["repeated_shortfall"]


def test_draw_swap_fails_cleanly_when_no_replacement():
    d = SA.Draw([C("a", "x"), C("b", "x"), C("c", "y")], [], cap=1)
    d.add(d.order[0])
    d.add(d.order[2])
    assert not d.swap(lambda c: c.case_id == "c", lambda c: c.case_id == "b")   # cap on doc x blocks b; c restored
    assert sorted(c.case_id for c in d.taken) == ["a", "c"]
    assert d.swap(lambda c: c.case_id == "a", lambda c: c.case_id == "b")       # removing a frees the cap
    assert sorted(c.case_id for c in d.taken) == ["b", "c"]
    assert not SA.Draw([], [], 1).swap(lambda c: True, lambda c: True)
    assert SA._hard_share(SA.Draw([], [], 1)) == 0.0


# ---------------------------------------------------------------- case construction

def test_split_alternates_per_domain():
    s = CS.split({"a": ["x1", "x2", "x3", "x4"], "b": ["y1", "y2"]})
    assert sorted(s.values()).count("P") == 3 and set(s) == {"x1", "x2", "x3", "x4", "y1", "y2"}


def test_constructed_partial():
    t = "Harvard Law School, Cambridge, MA"
    assert CS.constructed_partial(t, 0, len(t)) == (0, len("Harvard Law School"))
    t2 = "Harvard Law School"
    assert CS.constructed_partial(t2, 0, len(t2)) == (0, len("Harvard Law"))
    assert CS.constructed_partial("1,204", 0, 5) is None
    assert CS.constructed_partial("1 204", 0, 5) is None          # never inside a number
    assert CS.constructed_partial(" x", 0, 2) is None


def test_absent_options_removes_same_text():
    opts = [M.Option(id="c0", text="5", start=0, end=1, label="correct"),
            M.Option(id="c1", text="5", start=4, end=5, label="wrong"),
            M.Option(id="c2", text="6", start=8, end=9, label="wrong")]
    keep, removed = CS.absent_options(opts)
    assert [o.text for o in keep] == ["6"] and len(removed) == 2


def test_validate_candidate_labels(mini):
    recs = [json.loads(x) for x in (mini["extraction"] / "options.jsonl").read_text().splitlines()]
    r = recs[0]
    lab = json.loads((mini["labels"] / "candidates" / f"{r['doc_id']}.json").read_text())
    text = (mini["corpus"] / r["domain"] / f"{r['doc_id']}.txt").read_text()
    CS.validate_candidate_labels(lab, r, text)
    fid = r["fields"][0]["field_id"]
    for mut, msg in ((lambda x: x.update(doc_id="z"), "names"), (lambda x: x.update(multi_entity=None), "multi_entity"),
                     (lambda x: x.update(processing_note="zzz not here"), "processing_note"),
                     (lambda x: x["fields"].pop(fid), "not labelled"),
                     (lambda x: x["fields"][fid].update(status="maybe"), "bad status"),
                     (lambda x: x["fields"][fid].update(superseded=None), "superseded"),
                     (lambda x: x["fields"][fid].update(options={}), "differ"),
                     (lambda x: x["fields"][fid]["options"].update({k: "meh" for k in x["fields"][fid]["options"]}), "bad option")):
        x = json.loads(json.dumps(lab))
        mut(x)
        with pytest.raises(ValueError, match=msg):
            CS.validate_candidate_labels(x, r, text)
    over = json.loads(json.dumps(r))
    over["fields"][0]["over_cap"] = True
    x = json.loads(json.dumps(lab))
    x["fields"][fid]["options"] = {}
    CS.validate_candidate_labels(x, over, text)


def test_apply_adjudication():
    labels = {"d": {"multi_entity": False, "fields": {"f": {"status": "absent", "options": {"c0": "wrong"}}}}}
    out = CS.apply_adjudication(labels, [{"kind": "field", "doc_id": "d", "field_id": "f",
                                          "decision": {"status": "present", "options": {"c0": "correct"}}},
                                         {"kind": "doc", "doc_id": "d", "decision": {"multi_entity": True}}])
    assert out["d"]["multi_entity"] and out["d"]["fields"]["f"]["options"]["c0"] == "correct"
    assert labels["d"]["multi_entity"] is False
    with pytest.raises(ValueError):
        CS.apply_adjudication(labels, [{"kind": "zzz"}])


def test_build_all_outputs_valid_files(mini):
    s = json.loads((mini["cases"] / "build_summary.json").read_text())
    assert s["pools"]["present"] > 0 and s["clusters"]["eligible"] > 0
    present = M.load_selection(mini["cases"] / "probe1_3.jsonl", mini["corpus"])
    absent = M.load_selection(mini["cases"] / "probe2.jsonl", mini["corpus"])
    assert {c.doc_id for c in present}.isdisjoint({c.doc_id for c in absent})
    single = M.load_single(mini["cases"] / "probe8.jsonl", mini["corpus"])
    assert {c.set for c in single} >= {"lone_correct", "lone_wrong", "lone_partial"}


def test_build_all_applies_adjudication_including_mentions(mini, tmp_path):
    pid = json.loads((mini["extraction"] / "mentions.jsonl").read_text().splitlines()[0])["passage_id"]
    lab = next(json.loads(p.read_text()) for p in (mini["labels"] / "mentions").glob("*.json")
               if json.loads(p.read_text())["passage_id"] == pid)
    for m in lab["mentions"].values():
        m["ambiguous"] = True
    doc = next(iter(json.loads(x)["doc_id"] for x in (mini["extraction"] / "options.jsonl").read_text().splitlines()))
    (mini["labels"] / "adjudication.jsonl").write_text(
        json.dumps({"kind": "doc", "doc_id": doc, "decision": {"multi_entity": True}}) + "\n"
        + json.dumps({"kind": "mentions", "passage_id": pid, "decision": lab}) + "\n")
    s = CS.build_all(mini["corpus"], mini["extraction"], mini["labels"], tmp_path / "c2")
    assert s["clusters"]["eligible"] == 3


def test_single_cases_partial_only_and_cap():
    o = lambda i, lab, t="abc def": M.Option(id=f"c{i}", text=t, start=i * 10, end=i * 10 + len(t), label=lab)  # noqa: E731
    insts = [CS.Instance("d", "receipt.total_price", (o(0, "correct"), o(1, "wrong"), o(2, "partial", "abc")),
                         "present", False, False, 100, False),
             CS.Instance("d", "receipt.cashprice", (o(0, "partial", "abc"),), "partial_only", False, False, 100, False),
             CS.Instance("d", "receipt.tax_price", (o(0, "correct", "12"), o(1, "wrong")), "present", False, False, 100, False)]
    out = CS.single_cases(insts, {"d": "x" * 100})
    sets = [c.set for c in out]
    assert sets.count("partial_only") == 1 and "lone_partial" in sets
    assert not any(c.field_id == "receipt.tax_price" for c in out)   # no partial, none constructible


# ---------------------------------------------------------------- build and tasks

def test_premerge_merges_whitespace_and_rejects():
    ms, rej = B.premerge("Acme Corp met Acme  Corp and Bob", 100, ["Acme Corp", "Acme  Corp", "Zed", " ", "Bob"])
    assert rej == ["Zed"] and [m["text"] for m in ms] == ["Acme Corp", "Bob"]
    assert ms[0]["spans"] == [(100, 109), (114, 124)] and ms[0]["merged_texts"] == ["Acme Corp", "Acme  Corp"]


def test_build_options_rejects_mismatched_file(mini):
    p = mini["extraction"] / "llm" / "r0.json"
    d = json.loads(p.read_text())
    d["doc_id"] = "other"
    p.write_text(json.dumps(d))
    with pytest.raises(ValueError, match="names other"):
        B.build_options(mini["corpus"], mini["extraction"])


def test_build_main(mini, capsys):
    assert B.main(["options"], mini["corpus"], mini["extraction"]) == 0
    assert B.main(["mentions"], mini["corpus"], mini["extraction"]) == 0
    assert B.main([], mini["corpus"], mini["extraction"]) == 2
    assert "documents" in capsys.readouterr().out


def test_windows_and_passages(mini, tmp_path):
    text = ("para one.\n\n" * 400)
    s, e = TK.window(text, False, 100)
    assert s == 0 and text[e:e + 2] == "\n\n" and e <= 100
    s, e = TK.window(text, True, 100)
    assert e == len(text) and s > len(text) - 100
    assert TK.window("abc", False) == (0, 3)
    assert TK.window("x" * 200, False, 50) == (0, 50) and TK.window("x" * 200, True, 50) == (150, 200)
    s, e = TK.middle_window(text, 100)
    assert 0 < s < e <= s + 100
    assert TK.middle_window("y" * 300, 100) == (100, 200)
    docs = M.load_manifest(mini["corpus"])
    assert len(TK.extraction_tasks(docs)) == 10
    ps = TK.passages(docs, mini["corpus"])
    assert {p["entity_type"] for p in ps} == {"organization", "person"}
    assert TK.main(["extraction", str(tmp_path / "o")], mini["corpus"]) == 0
    assert TK.main(["passages", str(tmp_path / "o")], mini["corpus"]) == 0
    assert TK.main(["nope"], mini["corpus"]) == 2


def test_middle_passage_for_long_contracts(tmp_path):
    from tests.phase0.datasets.fetch import Doc, write_docs
    write_docs([Doc("k", "contract", "en", "a\n\n" * 7000, "u", "cc-by-4.0", "x")], tmp_path)
    ps = TK.passages(M.load_manifest(tmp_path), tmp_path)
    assert [p["passage_id"].split("#")[1] for p in ps] == ["organization", "person", "organization-middle"]


# ---------------------------------------------------------------- agreement

def test_agreement_sample_and_kappas(mini, tmp_path, capsys):
    keys = [("d", f"f{i}") for i in range(10)]
    assert len(AG.sample_keys(keys)) == 2 and AG.sample_keys(keys) == AG.sample_keys(list(reversed(keys)))
    labels = mini["labels"]
    (labels / "second" / "candidates").mkdir(parents=True)
    (labels / "second" / "mentions").mkdir(parents=True)
    cand = sorted((labels / "candidates").glob("*.json"))[:2]
    for i, p in enumerate(cand):
        lab = json.loads(p.read_text())
        f0 = next(iter(lab["fields"]))
        sec = {"doc_id": lab["doc_id"], "multi_entity": lab["multi_entity"] if i else not lab["multi_entity"],
               "fields": {f0: json.loads(json.dumps(lab["fields"][f0]))}}
        if i == 0 and sec["fields"][f0]["options"]:
            k = next(iter(sec["fields"][f0]["options"]))
            sec["fields"][f0]["options"][k] = "partial"
        (labels / "second" / "candidates" / p.name).write_text(json.dumps(sec))
    m = sorted((labels / "mentions").glob("*.json"))[0]
    lab = json.loads(m.read_text())
    lab["mentions"]["c0"]["entity"] = "E9"
    (labels / "second" / "mentions" / m.name).write_text(json.dumps(lab))
    assert AG.main(["report"], labels, mini["extraction"]) == 0
    rep = json.loads((labels / "agreement.json").read_text())
    assert rep["candidates"]["n_documents"] == 2 and rep["candidates"]["disagreements"]
    assert rep["mentions"]["disagreements"] and rep["mentions"]["kappa_pairs"] is not None
    assert AG.main(["sample", str(tmp_path / "s")], labels, mini["extraction"]) == 0
    assert json.loads((tmp_path / "s" / "second_sample.json").read_text())["fields"]
    assert AG.main([], labels, mini["extraction"]) == 2


def test_agreement_empty():
    assert AG.candidate_agreement({}, {})["kappa_options"] is None
    assert AG.mention_agreement({}, {})["kappa_pairs"] is None
