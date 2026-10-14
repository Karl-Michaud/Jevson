from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.phase0 import scoring as SC

OPTS = ["c0", "c1", "c2", SC.NONE]


def ans(**p):
    probs = {k: v for k, v in p.items()}
    top = max(probs, key=probs.get)
    return {"type": "choice", "choice": top, "probabilities": probs, "confidence": 0.5}


# ---------------------------------------------------------------- decoding

def test_hundredths():
    assert SC.hundredths(0.29) == 29 and SC.hundredths(1) == 100 and SC.hundredths(0.0) == 0
    for bad in (True, "0.5", None, -0.01, 1.01, float("nan")):
        with pytest.raises(ValueError):
            SC.hundredths(bad)


@pytest.mark.parametrize("k,tol", [(2, 1), (3, 2), (4, 2), (9, 5), (11, 5), (255, 5)])
def test_sum_tolerance(k, tol):
    assert SC.sum_tolerance(k) == tol


def test_decode_clear_commit():
    d = SC.decode_choice(ans(c0=0.8, c1=0.1, c2=0.05, none_of_these=0.05), OPTS)
    assert d.status == "ok" and d.selected == "c0" and d.margin == 70


@pytest.mark.parametrize("top,second,status", [
    (0.52, 0.42, "tie"), (0.53, 0.42, "ok"), (0.55, 0.45, "tie"), (0.50, 0.50, "tie"), (0.61, 0.39, "ok"),
])
def test_decode_tie_margin(top, second, status):
    d = SC.decode_choice({"probabilities": {"c0": top, "c1": second, "c2": round(1 - top - second, 2),
                                            SC.NONE: 0.0}}, OPTS)
    assert d.status == status


def test_decode_tie_margin_exact_design_example():
    # DESIGN / PLAN Phase 1: a choice at 0.52/0.42/0.06 is a tie
    d = SC.decode_choice({"probabilities": {"a": 0.52, "b": 0.42, "c": 0.06}}, ["a", "b", "c"])
    assert d.status == "tie" and d.selected == "a"


def test_decode_sum_tolerance():
    ok = SC.decode_choice({"probabilities": {"a": 0.5, "b": 0.3, "c": 0.19}}, ["a", "b", "c"])
    assert ok.status == "ok"                                              # 0.99 with K = 3
    bad = SC.decode_choice({"probabilities": {"a": 0.5, "b": 0.3, "c": 0.15}}, ["a", "b", "c"])
    assert bad.status == "invalid" and bad.reason == "sum outside tolerance"   # 0.95


@pytest.mark.parametrize("answer,reason", [
    ("nope", "answer is not an object"),
    ({"choice": "c0"}, "no probabilities"),
    ({"probabilities": {"c0": 1.0}}, "options differ from those offered"),
    ({"probabilities": {"c0": 0.9, "c1": 0.1, "c2": 0.0, SC.NONE: 0.0, "c9": 0.0}}, "options differ from those offered"),
    ({"probabilities": {"c0": 1.2, "c1": 0.1, "c2": 0.0, SC.NONE: 0.0}}, "probability outside [0, 1] or not a number"),
    ({"probabilities": {"c0": "0.9", "c1": 0.1, "c2": 0.0, SC.NONE: 0.0}}, "probability outside [0, 1] or not a number"),
])
def test_decode_invalid(answer, reason):
    d = SC.decode_choice(answer, OPTS)
    assert d.status == "invalid" and d.reason == reason and d.selected is None


def test_vendor_choice_disagreeing_outside_margin_is_invalid_inside_is_tie():
    d = SC.decode_choice({"choice": "c1", "probabilities": {"c0": 0.8, "c1": 0.2, "c2": 0.0, SC.NONE: 0.0}}, OPTS)
    assert d.status == "invalid" and d.reason == "vendor choice is not the argmax"
    d2 = SC.decode_choice({"choice": "c1", "probabilities": {"c0": 0.5, "c1": 0.45, "c2": 0.05, SC.NONE: 0.0}}, OPTS)
    assert d2.status == "tie"


def test_decode_requires_two_distinct_options():
    with pytest.raises(ValueError):
        SC.decode_choice({}, ["c0"])
    with pytest.raises(ValueError):
        SC.decode_choice({}, ["c0", "c0"])


@pytest.mark.parametrize("p,expected", [
    (0.56, ("ok", True)), (0.55, ("tie", None)), (0.50, ("tie", None)), (0.45, ("tie", None)),
    (0.44, ("ok", False)), (1.0, ("ok", True)), (0.0, ("ok", False)),
])
def test_decode_noul_bool_rule(p, expected):
    st_, v, h = SC.decode_noul({"noul": p})
    assert (st_, v) == expected and h == round(p * 100)


@pytest.mark.parametrize("a", [None, {}, {"noul": 2}, {"noul": "x"}])
def test_decode_noul_invalid(a):
    assert SC.decode_noul(a) == ("invalid", None, None)


def test_pair_probability_and_screen():
    assert SC.pair_probability({"noul": 0.51}) == 51
    assert SC.pair_probability({"noul": 7}) is None and SC.pair_probability(None) is None
    assert SC.screen_flagged({"noul": 0.56}) and not SC.screen_flagged({"noul": 0.55})
    assert SC.screen_flagged(None) and SC.screen_flagged({"noul": -1})


# ---------------------------------------------------------------- classification and tie scoring

LABELS = {"c0": "correct", "c1": "partial", "c2": "wrong"}


def test_classify_outcomes():
    mk = lambda sel, st_="ok": SC.ChoiceAnswer(st_, sel, {}, 50)  # noqa: E731
    assert SC.classify(mk("c0"), LABELS) == "correct"
    assert SC.classify(mk("c1"), LABELS) == "partial"
    assert SC.classify(mk("c2"), LABELS) == "wrong"
    assert SC.classify(mk(SC.NONE), LABELS) == "abstain"
    assert SC.classify(mk("c0", "tie"), LABELS) == "tie"
    assert SC.classify(SC.ChoiceAnswer("invalid", None, {}, None, "x"), LABELS) == "invalid"
    with pytest.raises(ValueError):
        SC.classify(mk("c0"), {"c0": "maybe"})


def test_ties_are_not_correct_not_abstaining_not_false_abstention():
    # a tie whose argmax is the correct option (probe 1/3) and a tie whose argmax is none_of_these (probe 2)
    tie_correct = SC.decode_choice({"probabilities": {"c0": 0.46, "c1": 0.0, "c2": 0.0, SC.NONE: 0.54}}, OPTS)
    tie_none = SC.decode_choice({"probabilities": {"c0": 0.0, "c1": 0.0, "c2": 0.46, SC.NONE: 0.54}}, OPTS)
    assert tie_correct.status == tie_none.status == "tie"
    present = SC.Counts.of([SC.classify(tie_correct, LABELS)])
    absent = SC.Counts.of([SC.classify(tie_none, LABELS)])
    assert SC.probe1_k(present) == 0            # not correct
    assert SC.probe3_k(present) == 0            # not a false abstention
    assert SC.probe2_k(absent) == 0             # not abstaining
    assert present.tie == absent.tie == 1


def test_counts():
    c = SC.Counts.of(["correct", "correct", "abstain", "tie", "invalid", "partial", "wrong"])
    assert (c.n, c.correct, c.abstain, c.tie, c.invalid, c.partial, c.wrong) == (7, 2, 1, 1, 1, 1, 1)


# ---------------------------------------------------------------- entity components

def pairs_from(n, same=(), p_same=90, p_diff=10, overrides=None):
    P = {}
    for i, j in itertools.combinations(range(n), 2):
        P[(i, j)] = p_same if (i, j) in same else p_diff
    P.update(overrides or {})
    return P


def test_components_basic():
    P = pairs_from(4, same={(0, 1), (2, 3)})
    assert SC.components(4, P) == [(0, 1), (2, 3)]


def test_chain_case_merges_under_floor_30():
    # PLAN Phase 7 chain case: Dana = Dana Whitfield 0.9, Dana Whitfield = Ms. Whitfield 0.9, Dana vs Ms. 0.4
    P = {(0, 1): 90, (1, 2): 90, (0, 2): 40}
    for v in ("internal", "cross"):
        assert SC.score_cluster(["e", "e", "e"], P, 30, v) == [("correct", (0, 1, 2))]


def test_internal_conflict_case():
    P = {(0, 1): 90, (1, 2): 90, (0, 2): 20, (0, 3): 5, (1, 3): 5, (2, 3): 5}
    out = SC.score_cluster(["a", "a", "a", "b"], P, 30, "internal")
    assert out == [("unresolved", (0, 1, 2)), ("correct", (3,))]


def test_split_case_differs_by_variant():
    # two components linked by a pair at 0.40, above a 0.30 floor
    P = {(0, 1): 90, (2, 3): 90, (0, 2): 40, (0, 3): 10, (1, 2): 10, (1, 3): 10}
    gold = ["x", "x", "x", "x"]
    assert SC.score_cluster(gold, P, 30, "internal") == [("split", (0, 1)), ("split", (2, 3))]
    assert SC.score_cluster(gold, P, 30, "cross") == [("unresolved", (0, 1)), ("unresolved", (2, 3))]


def test_merge_is_silently_wrong():
    P = pairs_from(3, same={(0, 1), (1, 2), (0, 2)})
    assert SC.score_cluster(["a", "a", "b"], P, 30, "internal") == [("merge", (0, 1, 2))]


def test_pair_at_floor_is_conflict_and_at_half_is_not_an_edge():
    P = {(0, 1): 90, (1, 2): 90, (0, 2): 30}
    assert SC.score_cluster(["e"] * 3, P, 30, "internal")[0][0] == "unresolved"
    P2 = {(0, 1): 50}
    assert SC.components(2, P2) == [(0,), (1,)]
    assert SC.score_cluster(["e", "e"], P2, 30, "cross") == [("unresolved", (0,)), ("unresolved", (1,))]
    assert SC.score_cluster(["e", "e"], {(0, 1): 30}, 30, "cross") == [("split", (0,)), ("split", (1,))]


def test_score_cluster_requires_complete_pairs():
    with pytest.raises(ValueError):
        SC.score_cluster(["a", "b", "c"], {(0, 1): 10}, 30, "internal")


def test_pair_stats():
    gold = ["a", "a", "b"]
    P = {(0, 1): 90, (0, 2): 60, (1, 2): 10}
    assert SC.pair_accuracy(gold, P) == (2, 3)
    assert SC.non_transitive_triples(3, P) == (1, 1)
    assert SC.clique_complete(gold, P) == (1, 1)
    assert SC.clique_complete(gold, {(0, 1): 40, (0, 2): 60, (1, 2): 10}) == (0, 1)
    assert SC.pair_flips(P, {(0, 1): 40, (0, 2): 60, (1, 2): 10}) == (1, 3)
    with pytest.raises(ValueError):
        SC.pair_flips(P, {(0, 1): 1})


@given(st.integers(2, 7).flatmap(lambda n: st.tuples(
    st.just(n), st.lists(st.integers(0, 100), min_size=n * (n - 1) // 2, max_size=n * (n - 1) // 2),
    st.lists(st.sampled_from("abc"), min_size=n, max_size=n))))
def test_components_partition_and_cross_only_blanks(args):
    n, ps, gold = args
    P = dict(zip(itertools.combinations(range(n), 2), ps))
    comps = SC.components(n, P)
    assert sorted(i for c in comps for i in c) == list(range(n))
    a = SC.score_cluster(gold, P, 30, "internal")
    b = SC.score_cluster(gold, P, 30, "cross")
    assert [c for _, c in a] == [c for _, c in b]
    for (ka, _), (kb, _) in zip(a, b):
        assert kb == ka or kb == "unresolved"
