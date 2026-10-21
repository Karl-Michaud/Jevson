"""H9, H9b: the adoption rules of design §4.4, read through `rules.Readings` against `rules.REFERENCE`."""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pytest

from tests.j4b.fresh import rules as R

Call = tuple[str, R.Config, R.Config, float, float, bool]


class FakeReadings(R.Readings):
    """Every bar passes unless a test says otherwise; every `paired` read is recorded."""

    def __init__(
        self,
        *,
        paired: Callable[[Call], bool] = lambda call: True,
        failing_arms: frozenset[str] = frozenset(),
        frr_t: bool = True,
        pc: bool = True,
        l0f0_rejected: int = 150,
        strata: Mapping[str, bool] | None = None,
    ) -> None:
        self.decide, self.failing_arms, self._frr_t, self._pc = paired, failing_arms, frr_t, pc
        self.l0f0_rejected = l0f0_rejected
        self.strata = dict(strata or {"F1": True, "F2": True, "F3": True})
        self.calls: list[Call] = []
        self.frr_t_reads: list[tuple[R.Config, float]] = []

    def paired(self, bar: str, config: R.Config, ref: R.Config, *, z: float, ni_z: float, cell: bool) -> bool:
        call = (bar, config, ref, z, ni_z, cell)
        self.calls.append(call)
        return self.decide(call)

    def frr_t(self, config: R.Config, z: float) -> bool:
        self.frr_t_reads.append((config, z))
        return self._frr_t

    def frr_fi(self, arm: str, z: float) -> Mapping[str, bool]:
        assert z == R.Z_STRATA
        return self.strata

    def rb_points(self, config: R.Config) -> bool:
        return True

    def rb_rejected(self, config: R.Config) -> int:
        assert config == R.L0F0
        return self.l0f0_rejected

    def bar_i(self, arm: str) -> bool:
        return arm not in self.failing_arms

    def pc(self) -> bool:
        return self._pc

    def fx(self, arm: str) -> bool:
        return True


# --- H9: adoption order and the outcomes ------------------------------------------------------------


def test_h9_adoption_order_is_m2_then_m1_then_both() -> None:
    assert R.adopt_48(FakeReadings())[0] == "L2"
    assert R.adopt_48(FakeReadings(failing_arms=frozenset({"L2"})))[0] == "L1"
    assert R.adopt_48(FakeReadings(failing_arms=frozenset({"L2", "L1"})))[0] == "L3"
    none = R.adopt_48(FakeReadings(failing_arms=frozenset({"L2", "L1", "L3"})))
    assert none == (None, "not met: no arm passes every bar")


def test_h9_a_failed_positive_control_adopts_nothing_but_asterion_58_still_decides_on_l0() -> None:
    readings = FakeReadings(pc=False)
    assert R.adopt_48(readings) == (None, "I inconclusive (positive control failed)")
    cell, outcome, _ = R.decide_58(readings, None)
    assert readings.frr_t_reads == [(("L0", "F1"), R.Z_58T)]
    assert cell == ("L0", "F1")
    assert outcome == "FRR target met; injection clause not met, because of the library arm, not F1"


def test_h9_outcome_1_ships_the_arm_with_f1_when_the_shipped_cell_gates_pass() -> None:
    assert R.decide_58(FakeReadings(), "L2")[:2] == (("L2", "F1"), "met: ship (arm, F1)")


@pytest.mark.parametrize("gate", ["FA-S", "SC-S"])
def test_h9_outcome_1_falls_back_to_f0_when_a_shipped_cell_gate_fails(gate: str) -> None:
    readings = FakeReadings(paired=lambda call: call[0] != gate)
    assert R.decide_58(readings, "L1")[:2] == (("L1", "F0"), "ship (arm, F0); ASTERION-58 not met: combined FA rise")


def test_h9_outcome_3_frr_t_fails() -> None:
    cell, outcome, _ = R.decide_58(FakeReadings(frr_t=False), "L2")
    assert cell is None
    assert outcome.startswith("not met: FRR-T")


@pytest.mark.parametrize("guard", ["FA-NI", "SC-FA", "C-NI", "B-NI"])
def test_h9_outcome_4_a_guard_fails(guard: str) -> None:
    readings = FakeReadings(paired=lambda call: not (call[0] == guard and call[1][1] == "F1"))
    assert R.decide_58(readings, "L2")[:2] == (None, f"not met: guard {guard} failed; F1 not adopted")


def test_h9_outcome_5_rb_not_measurable_adopts_nothing_for_either_ticket() -> None:
    readings = FakeReadings(l0f0_rejected=99)
    assert R.adopt_48(readings) == (None, R.RB_NOT_MEASURABLE)
    assert R.decide_58(readings, None) == (None, R.RB_NOT_MEASURABLE, ())
    assert readings.calls == []


STRATA = {"F1": True, "F2": False, "F3": True}


def test_h9_rewrite_guidance_is_kept_exactly_for_the_passing_strata_when_f1_ships() -> None:
    """Design §4.4: guidance for rewrite Fi is kept only where FRR-Fi passes, as part of an adopted F1 candidate:
    outcome 1 with FA-S and SC-S passing, and outcome 2."""
    assert R.decide_58(FakeReadings(strata=STRATA), "L2")[::2] == (("L2", "F1"), ("F1", "F3"))
    assert R.decide_58(FakeReadings(strata=STRATA), None)[::2] == (("L0", "F1"), ("F1", "F3"))


@pytest.mark.parametrize(
    ("readings", "adopted"),
    [
        (FakeReadings(strata=STRATA, frr_t=False), "L2"),  # outcome 3
        (FakeReadings(strata=STRATA, frr_t=False), None),  # outcome 3, no arm adopted
        (FakeReadings(strata=STRATA, paired=lambda call: not (call[0] == "SC-FA" and call[1][1] == "F1")), "L2"),
        (FakeReadings(strata=STRATA, paired=lambda call: call[0] != "FA-S"), "L1"),  # outcome-1 fallback to F0
        (FakeReadings(strata=STRATA, l0f0_rejected=99), "L2"),  # outcome 5
    ],
)
def test_h9_no_rewrite_guidance_is_kept_when_f1_is_not_shipped(readings: FakeReadings, adopted: str | None) -> None:
    cell, _, kept = R.decide_58(readings, adopted)
    assert cell is None or cell[1] == "F0"
    assert kept == ()


# --- H9b: every bar is read against the design's reference, at its z ---------------------------------


def expected(arm: str) -> set[Call]:
    """Design §4.4: FRR-NI, -48's FA-NI, C-NI, B-NI, FA-S and SC-S against (L0, F0); -58's FA-NI and SC-FA
    against (arm, F0); the NI upper at 1.2 z on the five net-rule bars only."""
    z48, z1, m = R.Z_48, R.Z_ONE, R.NI_MULTIPLIER
    f0, f1 = (arm, "F0"), (arm, "F1")
    return {
        ("FRR-NI", f0, R.L0F0, z48, m * z48, True),
        ("FA-NI", f0, R.L0F0, z48, m * z48, True),
        ("C-NI", f0, R.L0F0, z48, z48, False),
        ("B-NI", f0, R.L0F0, z48, z48, False),
        ("FA-NI", f1, f0, z1, m * z1, True),
        ("SC-FA", f1, f0, z1, m * z1, True),
        ("C-NI", f1, R.L0F0, z1, z1, False),
        ("B-NI", f1, R.L0F0, z1, z1, False),
        ("FA-S", f1, R.L0F0, z1, m * z1, True),
        ("SC-S", f1, R.L0F0, z1, m * z1, True),
    }


def test_h9b_each_bar_passes_only_against_the_designs_reference_and_z() -> None:
    table = expected("L2")
    readings = FakeReadings(paired=lambda call: call in table)
    assert R.adopt_48(readings)[0] == "L2"
    assert R.decide_58(readings, "L2")[:2] == (("L2", "F1"), "met: ship (arm, F1)")
    assert set(readings.calls) == table
    assert len(readings.calls) == len(table)  # each bar read once


def test_h9b_outcome_2_reads_fa_and_sc_once_against_l0_f0() -> None:
    table = expected("L0") - {c for c in expected("L0") if c[0] in ("FA-S", "SC-S")}
    readings = FakeReadings(paired=lambda call: call in table, failing_arms=frozenset({"L1", "L2", "L3"}))
    cell, _, _ = R.decide_58(readings, None)
    assert cell == ("L0", "F1")
    reads = [c for c in readings.calls if c[1] == ("L0", "F1")]
    assert sorted(c[0] for c in reads) == ["B-NI", "C-NI", "FA-NI", "SC-FA"]
    assert {c[2] for c in reads if c[0] in ("FA-NI", "SC-FA")} == {R.L0F0}


def test_a_void_attempts_partial_inputs_cannot_reach_a_decision() -> None:
    with pytest.raises(TypeError, match="Readings"):
        R.adopt_48(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Readings"):
        R.decide_58(object(), None)  # type: ignore[arg-type]


# --- T48-1: every read, with every argument, in order ------------------------------------------------------


class RecordingReadings(R.Readings):
    """Every bar passes; every read and its arguments are recorded in order."""

    def __init__(self) -> None:
        self.reads: list[tuple[object, ...]] = []

    def paired(self, bar: str, config: R.Config, ref: R.Config, *, z: float, ni_z: float, cell: bool) -> bool:
        self.reads.append(("paired", bar, config, ref, z, ni_z, cell))
        return True

    def frr_t(self, config: R.Config, z: float) -> bool:
        self.reads.append(("frr_t", config, z))
        return True

    def frr_fi(self, arm: str, z: float) -> Mapping[str, bool]:
        self.reads.append(("frr_fi", arm, z))
        return {"F1": True, "F2": False, "F3": True}

    def rb_points(self, config: R.Config) -> bool:
        self.reads.append(("rb_points", config))
        return True

    def rb_rejected(self, config: R.Config) -> int:
        self.reads.append(("rb_rejected", config))
        return 150

    def bar_i(self, arm: str) -> bool:
        self.reads.append(("bar_i", arm))
        return True

    def pc(self) -> bool:
        self.reads.append(("pc",))
        return True

    def fx(self, arm: str) -> bool:
        self.reads.append(("fx", arm))
        return True


def test_adopt_and_decide_read_each_bar_with_its_exact_arguments() -> None:
    z48, z1, m = R.Z_48, R.Z_ONE, R.NI_MULTIPLIER
    f0, f1 = ("L2", "F0"), ("L2", "F1")
    r = RecordingReadings()
    assert R.adopt_48(r) == ("L2", "met: L2 adopted")
    assert r.reads == [
        ("rb_rejected", R.L0F0), ("pc",), ("bar_i", "L2"), ("fx", "L2"),
        ("paired", "FRR-NI", f0, R.L0F0, z48, m * z48, True), ("paired", "FA-NI", f0, R.L0F0, z48, m * z48, True),
        ("rb_points", f0),
        ("paired", "C-NI", f0, R.L0F0, z48, z48, False), ("paired", "B-NI", f0, R.L0F0, z48, z48, False),
    ]  # fmt: skip
    r = RecordingReadings()
    assert R.decide_58(r, "L2") == (f1, "met: ship (arm, F1)", ("F1", "F3"))
    assert r.reads == [
        ("rb_rejected", R.L0F0), ("frr_t", f1, R.Z_58T),
        ("paired", "FA-NI", f1, f0, z1, m * z1, True), ("paired", "SC-FA", f1, f0, z1, m * z1, True),
        ("rb_points", f1),
        ("paired", "C-NI", f1, R.L0F0, z1, z1, False), ("paired", "B-NI", f1, R.L0F0, z1, z1, False),
        ("paired", "FA-S", f1, R.L0F0, z1, m * z1, True), ("paired", "SC-S", f1, R.L0F0, z1, m * z1, True),
        ("frr_fi", "L2", R.Z_STRATA),
    ]  # fmt: skip


# --- review round 2 (T48-9): guard names, the library-arm branch's strata, the refusal's message -----------


class FailingGuards(RecordingReadings):
    """The named guards fail for the F1 candidate ("RB" is `rb_points`); everything else passes."""

    def __init__(self, failing: frozenset[str]) -> None:
        super().__init__()
        self.failing = failing

    def paired(self, bar: str, config: R.Config, ref: R.Config, *, z: float, ni_z: float, cell: bool) -> bool:
        super().paired(bar, config, ref, z=z, ni_z=ni_z, cell=cell)
        return not (bar in self.failing and config[1] == "F1")

    def rb_points(self, config: R.Config) -> bool:
        super().rb_points(config)
        return not ("RB" in self.failing and config[1] == "F1")


def test_decide_58_names_every_failed_guard_rb_included_in_order() -> None:
    both = FailingGuards(frozenset({"FA-NI", "RB"}))
    assert R.decide_58(both, "L2") == (None, "not met: guard FA-NI, RB failed; F1 not adopted", ())
    assert R.decide_58(FailingGuards(frozenset({"RB"})), "L1")[1] == "not met: guard RB failed; F1 not adopted"


def test_the_library_arm_branch_keeps_the_strata_frr_fi_reads_for_l0() -> None:
    r = RecordingReadings()
    assert R.decide_58(r, None) == (
        ("L0", "F1"),
        "FRR target met; injection clause not met, because of the library arm, not F1",
        ("F1", "F3"),
    )
    assert r.reads[-1] == ("frr_fi", "L0", R.Z_STRATA)


def test_the_refusal_names_the_type_it_was_given() -> None:
    with pytest.raises(TypeError, match=r"^a decision reads a complete attempt's Readings, not object$"):
        R.adopt_48(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"not dict$"):
        R.decide_58({}, None)  # type: ignore[arg-type]
