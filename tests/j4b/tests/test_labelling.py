from __future__ import annotations

import json
import random
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tests.j4b.labelling import prepare_items as P
from tests.j4b.labelling import score as S
from tests.j4b.labelling.intervals import newcombe_hybrid, newcombe_paired, newcombe_unpaired, scaled, wilson
from tests.j4b.labelling.records import ITEM_KEYS, check_run_row, key_row, label, read_jsonl, write_jsonl

# --- intervals: published values ---


def test_wilson_matches_plan_and_published_values() -> None:
    assert wilson(0, 80).high == pytest.approx(0.0458, abs=5e-4)  # PLAN Phase 4: "≈ 0.046"
    assert wilson(0, 80).low == 0.0
    iv = wilson(81, 263)  # Newcombe 1998 (method 3), 81/263: 0.2553 to 0.3662
    assert (iv.low, iv.high) == (pytest.approx(0.2553, abs=1e-4), pytest.approx(0.3662, abs=1e-4))
    assert wilson(5, 5).high == 1.0


def test_newcombe_unpaired_matches_published_example() -> None:
    iv = newcombe_unpaired(56, 70, 48, 80)  # Newcombe 1998, method 10: 0.0524 to 0.3339
    assert iv.estimate == pytest.approx(0.2)
    assert (iv.low, iv.high) == (pytest.approx(0.0524, abs=1e-4), pytest.approx(0.3339, abs=1e-4))


def test_newcombe_paired_reduces_to_unpaired_when_phi_is_zero() -> None:
    # both*neither == only_1*only_2 gives phi = 0, so the paired interval uses the same Wilson pieces unpaired.
    p = newcombe_paired(4, 4, 4, 4)
    u = newcombe_unpaired(8, 16, 8, 16)
    assert (p.estimate, p.low, p.high) == pytest.approx((u.estimate, u.low, u.high))


def test_newcombe_paired_degenerate_margins() -> None:
    p = newcombe_paired(0, 0, 0, 10)  # nobody satisfies either way: phi's denominator is zero
    assert p.estimate == 0.0
    assert p.low < 0 < p.high


def test_wilson_rejects_bad_counts() -> None:
    for k, n in ((1, 0), (-1, 3), (4, 3)):
        with pytest.raises(ValueError, match="need 0"):
            wilson(k, n)


@given(st.integers(0, 60), st.integers(0, 60), st.integers(0, 60), st.integers(0, 60))
def test_paired_interval_contains_its_estimate_and_stays_in_range(a: int, b: int, c: int, d: int) -> None:
    if a + b + c + d == 0:
        return
    iv = newcombe_paired(a, b, c, d)
    assert iv.estimate == pytest.approx((b - c) / (a + b + c + d))
    assert -1 - 1e-9 <= iv.low <= iv.estimate + 1e-12 <= iv.high + 2e-12 <= 1 + 1e-9


@given(st.integers(1, 80), st.integers(1, 80), st.data())
def test_unpaired_interval_contains_its_estimate(n1: int, n2: int, data: st.DataObject) -> None:
    k1, k2 = data.draw(st.integers(0, n1)), data.draw(st.integers(0, n2))
    iv = newcombe_unpaired(k1, n1, k2, n2)
    assert iv.low <= iv.estimate <= iv.high


# --- a tiny synthetic run, scored by hand ---

CRIT = [{"id": "c1", "statement": "Mentions X."}, {"id": "c2", "statement": "Mentions Y."}]


def _row(inst: str, role: str, draft: str | None, admitted: bool) -> dict[str, Any]:
    return {
        "instance_id": inst,
        "role": role,
        "source": f"src {inst}",
        "field": "/summary",
        "criteria": CRIT,
        "draft": draft,
        "admitted": admitted,
    }


# Instances: i1 first admitted (truly satisfies); i2 first admitted (violates); i3..i6 first rejected, redrafted.
# Redrafts: i3 admitted+satisfies, i4 admitted+violates, i5 rejected, i6 produced no draft. One decoy.
RUN = [
    _row("i1", "first", "d1", True),
    _row("i2", "first", "d2", True),
    _row("i3", "first", "d3", False),
    _row("i3", "redraft", "d3r", True),
    _row("i4", "first", "d4", False),
    _row("i4", "redraft", "d4r", True),
    _row("i5", "first", "d5", False),
    _row("i5", "redraft", "d5r", False),
    _row("i6", "first", "d6", False),
    _row("i6", "redraft", None, False),
    _row("i7", "decoy", "d7", False),
]
# Human answers per draft text: True means every criterion is satisfied.
TRUTH = {
    "d1": True,
    "d2": False,
    "d3": False,
    "d3r": True,
    "d4": True,
    "d4r": False,
    "d5": False,
    "d5r": True,
    "d6": False,
    "d7": True,
}


def _label_all(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"id": it["id"], "criteria": {"c1": True, "c2": TRUTH[it["draft"]]}, "note": ""} for it in items]


def _score(run: list[dict[str, Any]]) -> dict[str, Any]:
    items, key = P.split(run, random.Random(1))
    return S.score([key_row(k) for k in key], [label(x) for x in _label_all(items)])


def test_items_carry_nothing_but_the_blind_fields() -> None:
    items, key = P.split(RUN, random.Random(1))
    assert len(items) == 10  # the null redraft is never an item
    assert len(key) == 11
    for it in items:
        assert set(it) == ITEM_KEYS
        assert set(it["criteria"][0]) == {"id", "statement"}
    blob = json.dumps(items)
    for leak in ("admitted", "redraft", "first", "decoy", "instance", "role"):
        assert leak not in blob
    assert len({it["id"] for it in items}) == 10
    assert [it["draft"] for it in items] != [r["draft"] for r in RUN if r["draft"]]  # shuffled


def test_score_on_the_synthetic_run() -> None:
    r = _score(RUN)
    assert (r["instances"], r["first_drafts"], r["rejected_first_drafts"], r["redrafts"]) == (6, 6, 4, 4)
    assert r["bar"]["counts_for_the_exit_criterion"] is False
    a, b, c = (
        r["A_redraft_admitted_and_satisfies"],
        r["B_redraft_admitted_while_violating"],
        r["C_first_admitted_while_violating"],
    )
    assert (a["k"], a["n"], b["k"], b["n"], c["k"], c["n"]) == (1, 4, 1, 4, 1, 6)
    assert r["B_minus_C"]["estimate"] == pytest.approx(1 / 4 - 1 / 6)
    assert r["B_minus_C"]["low"] == pytest.approx(newcombe_unpaired(1, 4, 1, 6).low)
    # Rejected instances i3..i6: (redraft satisfies, first satisfies) = (T,F), (F,T), (T,F), (F,F).
    p = r["paired_satisfies_redraft_minus_first"]
    assert (p["both"], p["only_redraft"], p["only_first"], p["neither"]) == (0, 2, 1, 1)
    assert p["estimate"] == pytest.approx(1 / 4)
    assert p["high"] == pytest.approx(newcombe_paired(0, 2, 1, 1).high)
    # A = 25% >= 10%, but B - C = 8.3 points > 2: the default budget becomes 0.
    assert r["bar"]["redraft_budget_default"] == 0


def test_bar_keeps_budget_one_when_both_conditions_hold() -> None:
    run = [r for r in RUN if r["instance_id"] != "i4"]  # drop the admitted-while-violating redraft
    r = _score(run)
    assert r["B_redraft_admitted_while_violating"]["k"] == 0
    assert r["bar"]["redraft_budget_default"] == 1


Rows = list[dict[str, Any]]


def _unlabel_one(key: Rows, labs: Rows) -> None:
    labs.pop()


def _label_unknown_id(key: Rows, labs: Rows) -> None:
    labs.append(dict(labs[0], id="zzz"))


def _label_twice(key: Rows, labs: Rows) -> None:
    labs.append(dict(labs[0]))


def _drop_a_criterion(key: Rows, labs: Rows) -> None:
    labs[0]["criteria"].pop("c2")


def _duplicate_a_draft(key: Rows, labs: Rows) -> None:
    key.append(dict(key[0], item_id=None))


def _orphan_redraft(key: Rows, labs: Rows) -> None:
    key.append(dict(next(k for k in key if k["role"] == "redraft"), instance_id="nofirst", item_id=None))


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (_unlabel_one, "1 unlabelled"),
        (_label_unknown_id, "1 unknown"),
        (_label_twice, "labelled twice"),
        (_drop_a_criterion, "labelled criteria differ"),
        (_duplicate_a_draft, "two first drafts|two redraft drafts"),
        (_orphan_redraft, "has no first draft"),
    ],
)
def test_score_refuses_inconsistent_inputs(mutate: Callable[[Rows, Rows], None], match: str) -> None:
    items, key = P.split(RUN, random.Random(1))
    labs = _label_all(items)
    mutate(key, labs)
    with pytest.raises(ValueError, match=match):
        S.score([key_row(k) for k in key], [label(x) for x in labs])


def test_score_refuses_a_redraft_after_an_admitted_first_draft_and_a_run_without_redrafts() -> None:
    with pytest.raises(ValueError, match="although its first draft was admitted"):
        _score([*RUN, _row("i1", "redraft", "d3r", True)])
    with pytest.raises(ValueError, match="no redrafts"):
        _score([r for r in RUN if r["role"] != "redraft"])


@pytest.mark.parametrize(
    ("row", "match"),
    [
        ({"role": "third"}, "role must be"),
        ({"admitted": "yes"}, "bool admitted"),
        ({"draft": None, "admitted": True}, "null draft cannot be admitted"),
        ({"criteria": []}, "non-empty criteria"),
    ],
)
def test_run_rows_are_validated(row: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        check_run_row({**_row("i1", "first", "d1", False), **row}, 1)


def test_labels_are_validated() -> None:
    with pytest.raises(ValueError, match="string id"):
        label({"id": 3, "criteria": {}})
    with pytest.raises(ValueError, match="true or false"):
        label({"id": "a", "criteria": {"c1": "yes"}})


def test_read_jsonl_skips_blank_lines_and_refuses_non_objects(tmp_path: Path) -> None:
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\n\n[1]\n')
    with pytest.raises(ValueError, match="expected a JSON object"):
        read_jsonl(p)
    p.write_text('{"a": 1}\n\n')
    assert read_jsonl(p) == [{"a": 1}]


def test_command_lines_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = tmp_path / "run.jsonl"
    write_jsonl(run, RUN)
    assert P.main([str(run), str(tmp_path / "out"), "--seed", "3"]) == 0
    items = read_jsonl(tmp_path / "out" / "items.jsonl")
    write_jsonl(tmp_path / "labels.jsonl", _label_all(items))
    assert (
        S.main(
            [
                str(tmp_path / "out" / "key.jsonl"),
                str(tmp_path / "labels.jsonl"),
                "--out",
                str(tmp_path / "report.json"),
            ]
        )
        == 0
    )
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["bar"]["redraft_budget_default"] == 0
    err = capsys.readouterr().err
    assert "fewer than 100 rejected" in err
    assert P.main([str(run), str(tmp_path / "out2")]) == 0  # unseeded: random ids
    assert S.main([str(tmp_path / "out" / "key.jsonl"), str(tmp_path / "labels.jsonl")]) == 0


# --- sampled admitted first drafts (PLAN Phase 4 stated interpretation) ---


def test_score_weights_c_by_the_exact_admitted_share_when_admitted_firsts_are_sampled() -> None:
    items, key = P.split(RUN, random.Random(1))
    labs = [label(x) for x in _label_all(items)]
    keys = [key_row(k) for k in key]
    # The run's 2 admitted first drafts stand for 10 of 14 first drafts (4 rejected, all labelled).
    r = S.score(keys, labs, {"first_drafts": 14, "admitted_first_drafts": 10})
    c = r["C_first_admitted_while_violating"]
    assert (c["k_sampled"], c["n_sampled_admitted"], c["n"]) == (1, 2, 14)
    assert c["estimate"] == pytest.approx(0.5 * 10 / 14)
    assert c["high"] == pytest.approx(wilson(1, 2).high * 10 / 14)
    assert r["first_drafts"] == 14
    expected = newcombe_hybrid(wilson(1, 4), scaled(wilson(1, 2), 10 / 14))
    assert r["B_minus_C"]["low"] == pytest.approx(expected.low)
    for bad in ({"first_drafts": 15, "admitted_first_drafts": 10}, {"first_drafts": 5, "admitted_first_drafts": 1}):
        with pytest.raises(ValueError, match="sampling does not match"):
            S.score(keys, labs, bad)


def test_score_cli_reads_sampling(tmp_path: Path) -> None:
    items, key = P.split(RUN, random.Random(1))
    write_jsonl(tmp_path / "key.jsonl", key)
    write_jsonl(tmp_path / "labels.jsonl", _label_all(items))
    (tmp_path / "s.json").write_text(json.dumps({"first_drafts": 14, "admitted_first_drafts": 10}))
    args = [str(tmp_path / "key.jsonl"), str(tmp_path / "labels.jsonl"), "--sampling", str(tmp_path / "s.json")]
    assert S.main([*args, "--out", str(tmp_path / "r.json")]) == 0
    assert json.loads((tmp_path / "r.json").read_text())["first_drafts"] == 14


def test_score_reports_every_number_per_group() -> None:
    run = [dict(r, group="g1" if r["instance_id"] in {"i1", "i2", "i3", "i4"} else "g2") for r in RUN]
    items, key = P.split(run, random.Random(1))
    assert {k["group"] for k in key} == {"g1", "g2"}
    keys, labs = [key_row(k) for k in key], [label(x) for x in _label_all(items)]
    pooled = S.score(keys, labs)
    g1, g2 = pooled["by_group"]["g1"], pooled["by_group"]["g2"]
    assert (g1["instances"], g1["redrafts"], g2["instances"], g2["redrafts"]) == (4, 2, 2, 2)
    assert g1["A_redraft_admitted_and_satisfies"]["k"] + g2["A_redraft_admitted_and_satisfies"]["k"] == 1
    assert "bar" in pooled
    assert "bar" not in g1
    sampling = {
        "first_drafts": 6,
        "admitted_first_drafts": 2,
        "by_group": {
            "g1": {"first_drafts": 4, "admitted_first_drafts": 2},
            "g2": {"first_drafts": 2, "admitted_first_drafts": 0},
        },
    }
    weighted = S.score(keys, labs, sampling)
    assert weighted["by_group"]["g1"]["C_first_admitted_while_violating"]["admitted_share"] == 0.5
    assert weighted["by_group"]["g2"]["C_first_admitted_while_violating"]["estimate"] == 0.0  # none admitted in g2
    sampling["by_group"]["g2"] = {"first_drafts": 3, "admitted_first_drafts": 1}
    assert "no admitted first draft" in S.score(keys, labs, sampling)["by_group"]["g2"]["not_computed"]
