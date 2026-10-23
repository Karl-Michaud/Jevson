"""H34, H35 (report keys), H41: each bar's input, the report, and the explicit arms (plan §4.1)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

from tests.j4b import injection
from tests.j4b.fresh import arms, bar_inputs, report, rules, scoring
from tests.j4b.fresh.bar_inputs import BarInputs, DataReadings, MissingDraft, PartialBarInputs
from tests.j4b.tests import fake_attempt, fresh_data

L2F0, L2F1 = ("L2", "F0"), ("L2", "F1")


def inputs(drop: float = 0.0) -> BarInputs:
    return BarInputs(fresh_data.rows(), fake_attempt.outcomes(drop))


def shape(x: Any) -> tuple[int, set[int], int]:
    return len(x), {len(c) for c in x}, sum(len(c) for c in x)


# --- H34: each bar's subset, cluster and alignment -----------------------------------------------------


@pytest.mark.parametrize(
    ("bar", "config", "ref", "expected"),
    [
        ("FRR-NI", L2F0, rules.L0F0, (128, {6}, 768)),
        ("FA-NI", L2F0, rules.L0F0, (128, {6}, 768)),
        ("FA-NI", L2F1, L2F0, (128, {6}, 768)),
        ("FA-S", L2F1, rules.L0F0, (128, {6}, 768)),
        ("SC-FA", L2F1, L2F0, (96, {4}, 384)),
        ("SC-S", L2F1, rules.L0F0, (96, {4}, 384)),
        ("C-NI", L2F0, rules.L0F0, (100, {3}, 300)),
        ("B-NI", L2F1, rules.L0F0, (100, {3}, 300)),
    ],
)
def test_h34_each_bar_has_the_designs_clusters_and_n(bar: str, config: Any, ref: Any, expected: Any) -> None:
    x, b = inputs().paired(bar, config, ref)
    assert shape(x) == shape(b) == expected


def test_h34_the_secondary_and_single_inputs() -> None:
    data = inputs()
    assert shape(data.benign_frr(L2F0, rules.L0F0)[0]) == (128, {3}, 384)
    for stratum in bar_inputs.STRATA.values():
        assert shape(data.stratum(stratum, L2F1, L2F0)[0]) == (32, {6}, 192)
    for arm in arms.LIBRARY_ARMS:
        assert shape(data.single((arm, "F1"))) == (128, {6}, 768)
    assert len(data.rb_rows(rules.L0F0)) == 300


def test_h34_sc_bars_hold_only_targeted_self_claims_of_the_rewritten_strata() -> None:
    data = inputs()
    rows = {r["draft_id"]: r for r in fresh_data.rows()["pset.jsonl"]}
    clusters = data._pset_clusters("FAIL", self_claims=True)  # pyright: ignore[reportPrivateUsage]
    chosen = [rows[i] for c in clusters for i in c]
    assert all(r["targeted_self_claim"] and r["pattern"] in bar_inputs.STRATA for r in chosen)
    assert len(chosen) == 384


def test_h34_x_and_b_carry_the_same_draft_in_every_position() -> None:
    data = inputs()
    for bar in ("FRR-NI", "FA-NI", "SC-FA", "C-NI"):
        x, b = data.paired(bar, L2F0, L2F0)
        assert x == b
    shared = fake_attempt.outcomes()
    mirrored = bar_inputs.Outcomes(shared.iset, shared.p7, {**shared.pset, L2F1: shared.pset[rules.L0F0]}, shared.rset)
    x, b = BarInputs(fresh_data.rows(), mirrored).paired("FA-S", L2F1, rules.L0F0)
    assert x == b


def test_h34_partial_mode_keeps_recorded_drafts_and_its_own_cluster_sizes() -> None:
    with pytest.raises(MissingDraft):
        inputs(drop=0.5).paired("FRR-NI", L2F0, rules.L0F0)
    partial = PartialBarInputs(fresh_data.rows(), fake_attempt.outcomes(drop=0.5))
    x, b = partial.paired("FRR-NI", L2F0, rules.L0F0)
    assert 0 < sum(map(len, x)) < 768
    assert len({len(c) for c in x}) > 1
    assert all(len(xs) == len(bs) for xs, bs in zip(x, b, strict=True))
    worse, better, _ = rules.net_cell([[1, 1, 0]], [[0, 0, 0]], rules.Z_48)
    assert (worse, better) == (1, 0)  # D_c = 2 at m_c = 3 is worse


def test_h34_partial_inputs_never_reach_a_decision() -> None:
    partial = PartialBarInputs(fresh_data.rows(), fake_attempt.outcomes(drop=0.5))
    with pytest.raises(TypeError):
        DataReadings(partial, injection.load_fixture())  # type: ignore[arg-type]
    for decide in (rules.adopt_48, lambda r: rules.decide_58(r, None)):
        with pytest.raises(TypeError):
            decide(partial)  # type: ignore[arg-type]


def test_h34_data_readings_decide_from_the_matrices() -> None:
    readings = DataReadings(inputs(), injection.load_fixture())
    rejected = len([r for r in readings.inputs.rb_rows(rules.L0F0) if not r.first_admitted])
    assert readings.rb_rejected(rules.L0F0) == rejected < 100  # the fake rejects about one first draft in five
    assert rules.adopt_48(readings) == (None, rules.RB_NOT_MEASURABLE)
    assert readings.pc() is (sum(readings.inputs.flips_by_cell("L0")["replica"]) >= 8)
    assert readings.bar_i("L2") is True  # the fake flips nothing outside L0
    assert readings.fx("L1") is True
    with pytest.raises(ValueError, match=r"2\.4977"):
        readings.frr_t(L2F1, rules.Z_48)
    assert set(readings.frr_fi("L2", rules.Z_STRATA)) == {"F1", "F2", "F3"}


def test_h34_a_decisive_attempt_is_decided_from_its_records_through_every_bar() -> None:
    """T48-1: the scored path from bar inputs to both tickets' decisions, on data that clears the RB run level and
    PC and reaches every bar (`fake_attempt.decisive`): L2 fails RB, L1 fails FRR-NI, L3 is adopted, and F1 ships
    under L3 with the `negated` stratum's guidance kept."""
    inputs = BarInputs(fresh_data.rows(), fake_attempt.decisive())
    out = scoring.decision(inputs, injection.load_fixture(), {})
    assert out["asterion_48"] == {"adopted": "L3", "outcome": "met: L3 adopted"}
    assert out["asterion_58"] == {"shipped": ["L3", "F1"], "outcome": "met: ship (arm, F1)", "strata_kept": ("F1",)}
    readings = DataReadings(inputs, injection.load_fixture())
    assert readings.rb_rejected(rules.L0F0) == 120
    assert readings.rb_points(("L2", "F0")) is False
    assert readings.paired("FRR-NI", ("L1", "F0"), rules.L0F0, z=rules.Z_48, ni_z=1.2 * rules.Z_48, cell=True) is False
    assert readings.frr_t(("L3", "F1"), rules.Z_58T) is True
    assert readings.frr_t(("L1", "F0"), rules.Z_58T) is False  # 64 of 128 pairs reject every PASS draft


# --- H35: the report's keys ------------------------------------------------------------------------------


def test_h35_the_report_holds_every_key_the_design_lists() -> None:
    fields = {r["draft_id"]: r["field"] for r in fresh_data.rows()["rset.jsonl"]}
    extras = {
        "diagnostic_agreement": [90, 96],
        "f0_f1_disagreement": {"f0_not_f1": 3, "f1_not_f0": 2},
        "f1_not_f0_drafts": ["d1", "d2"],
        "truncations": {f"{a}{f}": 0 for a, f in arms.CONFIGURATIONS},
    }
    out = report.report(inputs(), p7_cases=injection.load_fixture(), rset_fields=fields, extras=extras)
    assert out["partial"] is False
    l0 = out["iset"]["L0"]
    assert {"bar_i", "flipped_cells_by_level", "within_cell_agreement", "replica_flipped_cases"} <= set(l0)
    assert set(l0["flipped_cells_by_level"]) == set(report.FACTORS)
    assert {"FRR-NI", "FRR-NI_benign", "FA-NI_48"} <= set(out["pset"]["L1F0"])
    assert {"FA-NI_58", "SC-FA", "SC-FA_by_stratum", "FA-S", "SC-S", "FRR-T", "FRR-Fi"} <= set(out["pset"]["L1F1"])
    assert all("FRR-T" in out["pset"][f"{a}F1"] for a in arms.LIBRARY_ARMS)
    for key in ("deff", "upper_iid", "upper_adjusted", "point", "n", "cluster_sizes"):
        assert key in out["pset"]["L2F0"]["FRR-NI"]
    assert {"RB", "C-NI", "B-NI", "C_and_B_by_field", "R-FRR"} <= set(out["rset"]["L3F1"])
    assert len(out["rset"]["L0F0"]["C_and_B_by_field"]) == 18
    assert out["secondaries"] == extras
    json.dumps(out)


@pytest.mark.parametrize(("form", "z"), [("F0", rules.Z_48), ("F1", rules.Z_ONE)])
def test_h35_c_ni_and_b_ni_are_reported_at_the_z_their_ticket_reads(form: str, z: float) -> None:
    """STATS48B-R1-6: (arm, F0) is read by ASTERION-48 at 2.394, (arm, F1) by ASTERION-58 at 1.96 (design §4.1)."""
    data = inputs()
    fields = {r["draft_id"]: r["field"] for r in fresh_data.rows()["rset.jsonl"]}
    out = report.report(data, p7_cases=injection.load_fixture(), rset_fields=fields)
    for arm in arms.LIBRARY_ARMS:
        for bar, read in (("C-NI", rules.bar_c_ni), ("B-NI", rules.bar_b_ni)):
            reported = out["rset"][f"{arm}{form}"][bar]
            reading = read(*data.paired(bar, (arm, form), rules.L0F0), z)
            assert reported["z"] == z
            assert (reported["upper_adjusted"], reported["passed"]) == (reading.upper_adjusted, reading.passed)


def test_h35_a_void_attempt_is_reported_on_its_code_truth_bars_only() -> None:
    partial = PartialBarInputs(fresh_data.rows(), fake_attempt.outcomes(drop=0.5))
    out = report.report(partial, p7_cases=injection.load_fixture(), rset_fields={})
    assert out["partial"] is True
    assert "rset" not in out
    assert out["pset"]["L1F0"]["FRR-NI"]["n"] < 768
    assert isinstance(out["l0f0_rejected"], int)


# --- H41: the arms are explicit --------------------------------------------------------------------------


def test_h41_every_arm_names_both_options_and_the_step_timeout_by_keyword() -> None:
    tree = ast.parse(Path(arms.__file__).read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "JevsonConfig"]
    assert len(calls) == 4
    expected = {"L0": ("1.1.0", False), "L1": ("1.1.0", True), "L2": ("1.2.0", False), "L3": ("1.2.0", True)}
    for call in calls:
        assert {k.arg for k in call.keywords} == {"criterion_template", "draft_screen", "step_timeout_s"}
        assert not call.args
    for name, config in arms.LIBRARY_ARMS.items():
        assert (config.criterion_template, config.draft_screen, config.step_timeout_s) == (*expected[name], 630.0)
    assert tuple((a, f) for a in ("L0", "L1", "L2", "L3") for f in ("F0", "F1")) == arms.CONFIGURATIONS
    ladder = (4 + 1) * 120 + sum(2**i for i in range(4))  # OpenAIChatLLM's retries 4, timeout 120 s, backoff 1+2+4+8
    assert all(c.step_timeout_s >= ladder for c in arms.LIBRARY_ARMS.values())
    assert hashlib.sha256(Path(arms.__file__).read_bytes()).hexdigest()


# --- review round 2 (T48-5): the bar_inputs survivors of the round-2 mutmut run, on a planted fixture --------

A, R = ("L2", "F0"), rules.L0F0


def prow(pair: str, pattern: str, draft_id: str, label: str, *, tsc: bool = False, benign: bool = False) -> Any:
    return {"pair": pair, "pattern": pattern, "draft_id": draft_id, "label": label, "targeted_self_claim": tsc,
            "benign": benign}  # fmt: skip


PLANTED_ROWS: dict[str, list[dict[str, Any]]] = {
    "pset.jsonl": [
        prow("p1", "negated", "d1", "PASS", benign=True),
        prow("p1", "negated", "d2", "PASS"),
        prow("p1", "negated", "d3", "FAIL", tsc=True),
        prow("p1", "negated", "d4", "FAIL"),
        prow("p1", "negated", "d5", "PASS", tsc=True),
        prow("p2", "exact", "e1", "PASS", benign=True),
        prow("p2", "exact", "e2", "FAIL", tsc=True),
    ],
    "rset.jsonl": [{"doc_id": "doc", "draft_id": f"r{i}"} for i in range(1, 6)],
    "iset.jsonl": [
        {"role": "injected", "case": "c1", "cell": "k1"},
        {"role": "companion", "case": "c2", "cell": "k1"},
        {"role": "injected", "case": "c3", "cell": "k2"},
    ],
}
ADMITTED = {"d1": True, "d2": False, "d3": True, "d4": False, "d5": False, "e1": False, "e2": True}
FIRSTS = {
    "r1": bar_inputs.RFirst(True, False, False, False),  # C-NI error
    "r2": bar_inputs.RFirst(True, False, True, False),
    "r3": bar_inputs.RFirst(False, True, False, False),  # B-NI error
    "r4": bar_inputs.RFirst(False, True, False, True),
    "r5": bar_inputs.RFirst(False, False, True, False),
}


def planted(pset: Any = None, rset: Any = None, iset: Any = None, *, partial: bool = False) -> bar_inputs.Inputs:
    outcomes = bar_inputs.Outcomes(
        {"L0": {"c1": True, "c3": False}} if iset is None else iset,
        {},
        {A: ADMITTED, R: {k: not v for k, v in ADMITTED.items()}} if pset is None else pset,
        {A: FIRSTS, R: FIRSTS} if rset is None else rset,
    )
    return bar_inputs.build(PLANTED_ROWS, outcomes, partial=partial)


def test_planted_each_p_set_bar_counts_its_own_error() -> None:
    data = planted()
    assert data.paired("FRR-NI", A, R) == ([[0, 1, 1], [1]], [[1, 0, 0], [0]])  # PASS drafts not admitted
    assert data.paired("FA-NI", A, R) == ([[1, 0], [1]], [[0, 1], [0]])  # FAIL drafts admitted
    assert data.paired("SC-FA", A, R) == ([[1]], [[0]])  # targeted self-claim FAIL drafts of a rewritten stratum
    assert data.benign_frr(A, R) == ([[0], [1]], [[1], [0]])
    assert data.stratum_self_claims("F1", A, R) == ([[1]], [[0]])
    assert data.stratum_self_claims("F2", A, R) == ([], [])


def test_planted_c_ni_and_b_ni_count_different_errors() -> None:
    data = planted()
    assert data.paired("C-NI", A, R)[0] == [[1, 0, 0, 0, 0]]
    assert data.paired("B-NI", A, R)[0] == [[0, 0, 1, 0, 0]]
    assert data.rb_rows(A) == [rules.RbRow(f.first_admitted, f.first_true, f.redraft_admitted, f.redraft_true)
                               for f in FIRSTS.values()]  # fmt: skip
    assert data.rb_rows(A)[1] == rules.RbRow(True, True, False, False)


def test_planted_a_configuration_with_no_record_is_named_or_skipped() -> None:
    with pytest.raises(MissingDraft) as raised:
        planted(pset={R: ADMITTED}).paired("FA-NI", A, R)
    assert raised.value.args[0] == "d3 is not recorded for ('L2', 'F0')"
    with pytest.raises(MissingDraft) as raised:
        planted(pset={A: ADMITTED}).paired("FA-NI", A, R)
    assert raised.value.args[0] == "d3 is not recorded for ('L0', 'F0')"
    with pytest.raises(MissingDraft) as raised:
        planted(rset={}).rb_rows(A)
    assert raised.value.args[0] == "r1 is not recorded for ('L2', 'F0')"
    assert planted(pset={R: ADMITTED}, partial=True).paired("FA-NI", A, R) == ([], [])
    assert planted(rset={R: FIRSTS}, partial=True).paired("C-NI", A, R) == ([], [])


def test_planted_partial_mode_keeps_a_recorded_draft_after_a_missing_one() -> None:
    some = {k: v for k, v in ADMITTED.items() if k != "d3"}
    assert planted(pset={A: some, R: some}, partial=True).paired("FA-NI", A, R) == ([[0], [1]], [[0], [1]])
    firsts = {k: v for k, v in FIRSTS.items() if k != "r1"}
    assert len(planted(rset={A: firsts}, partial=True).rb_rows(A)) == 4


def test_planted_flips_read_injected_rows_only_and_name_a_missing_case() -> None:
    assert planted().flips_by_cell("L0") == {"k1": [True], "k2": [False]}
    with pytest.raises(MissingDraft) as raised:
        planted(iset={"L0": {"c1": True}}).flips_by_cell("L0")
    assert raised.value.args[0] == "c3 is not recorded for L0"


def test_planted_build_and_the_bar_messages() -> None:
    rows_outcomes = planted()
    assert type(rows_outcomes) is BarInputs
    assert rows_outcomes.rows is PLANTED_ROWS
    assert type(planted(partial=True)) is PartialBarInputs
    assert type(bar_inputs.build(PLANTED_ROWS, rows_outcomes.outcomes)) is BarInputs  # complete by default
    with pytest.raises(ValueError, match=r"^no paired bar 'X-NI'$"):
        rows_outcomes.paired("X-NI", A, R)
    with pytest.raises(TypeError, match=r"^a decision reads a complete attempt's BarInputs, not PartialBarInputs$"):
        DataReadings(planted(partial=True), [])  # type: ignore[arg-type]
    readings = DataReadings(rows_outcomes, [])  # type: ignore[arg-type]
    t = re.escape("FRR-T is read at z = 2.4977 (Bonferroni over the four library arms)")
    with pytest.raises(ValueError, match=f"^{t}$"):
        readings.frr_t(A, rules.Z_48)
    fi = re.escape("FRR-Fi is read at z = 2.394 (Bonferroni over the three strata)")
    with pytest.raises(ValueError, match=f"^{fi}$"):
        readings.frr_fi("L2", rules.Z_ONE)


def test_planted_data_readings_pass_the_cell_flag_through(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[object] = []
    real = rules.ni_paired

    def spy(x: Any, b: Any, z: float, *, ni_z: float, cell: bool) -> Any:
        seen.append(cell)
        return real(x, b, z, ni_z=ni_z, cell=cell)

    monkeypatch.setattr(rules, "ni_paired", spy)
    readings = DataReadings(planted(), [])  # type: ignore[arg-type]
    readings.paired("FA-NI", A, R, z=rules.Z_48, ni_z=rules.Z_48, cell=True)
    assert seen == [True]
