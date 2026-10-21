"""The one owner of each bar's input (design §4.1; STATS48-R4-1): which drafts, which cluster, which pair of
configurations, which truth form, aligned draft by draft.

From the built fixture rows and an attempt's recorded outcomes it returns, for each bar, the aligned per-cluster
0/1 matrices of the configuration (`x`) and its reference (`b`), 1 being the error the bar counts. The default mode
raises if a draft is missing on either side. `partial=True` (single-look item 12(b), void reports only) keeps the
drafts recorded on both sides and returns a `PartialBarInputs`, which is not `rules.Readings` and so can never reach
`adopt_48` or `decide_58`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tests.j4b.fresh import admission, rules
from tests.j4b.fresh.clustering import Matrix

Config = rules.Config
STRATA = {"negated": "F1", "disjunction": "F2", "universal": "F3"}
"""The three rewritten P-set strata, named by the rewrite that applies to them (design §1)."""


@dataclass(frozen=True)
class RFirst:
    """One R-set first draft under one configuration, with grader truth against F0 (design §3)."""

    first_admitted: bool
    redraft_admitted: bool
    first_true: bool
    redraft_true: bool


@dataclass(frozen=True)
class Outcomes:
    """An attempt's recorded outcomes: I-set flips by arm and case, [P7] verdicts by arm, P-set admissions and
    R-set first drafts by configuration, each keyed by draft (or case) id."""

    iset: Mapping[str, Mapping[str, bool]]
    p7: Mapping[str, Mapping[str, Mapping[str, Mapping[str, bool]]]]
    pset: Mapping[Config, Mapping[str, bool]]
    rset: Mapping[Config, Mapping[str, RFirst]]


class MissingDraft(KeyError):
    """A draft a bar compares is not recorded for one of its configurations."""


class Inputs:
    """Every bar's input over built rows and recorded outcomes; `BarInputs` (complete) and `PartialBarInputs`
    (void reports) fix `partial`, and `report.py` reads either through this type."""

    def __init__(self, rows: Mapping[str, Sequence[Mapping[str, Any]]], outcomes: Outcomes, *, partial: bool) -> None:
        self.rows, self.outcomes, self.partial = rows, outcomes, partial
        self.pairs: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows["pset.jsonl"]:
            self.pairs.setdefault(row["pair"], []).append(row)
        self.documents: dict[str, list[str]] = {}
        for row in rows["rset.jsonl"]:
            self.documents.setdefault(row["doc_id"], []).append(row["draft_id"])

    def _aligned(self, clusters: Sequence[Sequence[str]], error: Callable[[Config, str], int | None],
                 config: Config, ref: Config) -> tuple[Matrix, Matrix]:  # fmt: skip
        x: list[list[int]] = []
        b: list[list[int]] = []
        for ids in clusters:
            xs: list[int] = []
            bs: list[int] = []
            for draft_id in ids:
                xv, bv = error(config, draft_id), error(ref, draft_id)
                if xv is None or bv is None:
                    if not self.partial:
                        raise MissingDraft(f"{draft_id} is not recorded for {config if xv is None else ref}")
                    continue
                xs.append(xv)
                bs.append(bv)
            if xs:
                x.append(xs)
                b.append(bs)
        return x, b

    def _pset_error(self, failing: bool) -> Callable[[Config, str], int | None]:
        def error(config: Config, draft_id: str) -> int | None:
            admitted = self.outcomes.pset.get(config, {}).get(draft_id)
            return None if admitted is None else int(admitted is failing)

        return error

    def _pset_clusters(self, label: str, *, self_claims: bool = False, stratum: str | None = None) -> list[list[str]]:
        clusters: list[list[str]] = []
        for rows in self.pairs.values():
            if (self_claims and rows[0]["pattern"] not in STRATA) or (
                stratum and STRATA.get(rows[0]["pattern"]) != stratum
            ):
                continue
            chosen = [
                r["draft_id"] for r in rows if r["label"] == label and (r["targeted_self_claim"] or not self_claims)
            ]
            clusters.append(chosen)
        return clusters

    def rset_error(self, bar: str) -> Callable[[Config, str], int | None]:
        def error(config: Config, draft_id: str) -> int | None:
            first = self.outcomes.rset.get(config, {}).get(draft_id)
            if first is None:
                return None
            if bar == "C-NI":
                return int(first.first_admitted and not first.first_true)
            return int(not first.first_admitted and first.redraft_admitted and not first.redraft_true)

        return error

    def paired(self, bar: str, config: Config, ref: Config) -> tuple[Matrix, Matrix]:
        """The aligned (x, b) of `bar` for `config` against `ref`."""
        if bar == "FRR-NI":
            return self._aligned(self._pset_clusters("PASS"), self._pset_error(False), config, ref)
        if bar in ("FA-NI", "FA-S"):
            return self._aligned(self._pset_clusters("FAIL"), self._pset_error(True), config, ref)
        if bar in ("SC-FA", "SC-S"):
            return self._aligned(self._pset_clusters("FAIL", self_claims=True), self._pset_error(True), config, ref)
        if bar in ("C-NI", "B-NI"):
            return self._aligned(list(self.documents.values()), self.rset_error(bar), config, ref)
        raise ValueError(f"no paired bar {bar!r}")

    def benign_frr(self, config: Config, ref: Config) -> tuple[Matrix, Matrix]:
        """FRR-NI's secondary: the 384 benign PASS drafts alone."""
        clusters = [[r["draft_id"] for r in rows if r["benign"]] for rows in self.pairs.values()]
        return self._aligned(clusters, self._pset_error(False), config, ref)

    def stratum(self, name: str, config: Config, ref: Config) -> tuple[Matrix, Matrix]:
        """FRR-Fi: PASS drafts of stratum `name` (32 pairs x 6), (arm, F1) against (arm, F0)."""
        return self._aligned(self._pset_clusters("PASS", stratum=name), self._pset_error(False), config, ref)

    def stratum_self_claims(self, name: str, config: Config, ref: Config) -> tuple[Matrix, Matrix]:
        """SC-FA's per-stratum secondary."""
        clusters = [c for p, c in zip(self.pairs.values(), self._all_self_claims(), strict=True)
                    if STRATA.get(p[0]["pattern"]) == name]  # fmt: skip
        return self._aligned(clusters, self._pset_error(True), config, ref)

    def _all_self_claims(self) -> list[list[str]]:
        return [[r["draft_id"] for r in rows if r["label"] == "FAIL" and r["targeted_self_claim"]]
                for rows in self.pairs.values()]  # fmt: skip

    def single(self, config: Config) -> Matrix:
        """FRR-T: PASS drafts rejected under `config`, 128 pairs x 6."""
        return self._aligned(self._pset_clusters("PASS"), self._pset_error(False), config, config)[0]

    def rb_rows(self, config: Config) -> list[rules.RbRow]:
        firsts = self.outcomes.rset.get(config, {})
        out: list[rules.RbRow] = []
        for ids in self.documents.values():
            for draft_id in ids:
                if draft_id not in firsts:
                    if not self.partial:
                        raise MissingDraft(f"{draft_id} is not recorded for {config}")
                    continue
                f = firsts[draft_id]
                out.append(rules.RbRow(f.first_admitted, f.first_true, f.redraft_admitted, f.redraft_true))
        return out

    def flips_by_cell(self, arm: str) -> dict[str, list[bool]]:
        flips: dict[str, list[bool]] = {}
        recorded = self.outcomes.iset.get(arm, {})
        for row in self.rows["iset.jsonl"]:
            if row["role"] == "injected" and (row["case"] in recorded or not self.partial):
                if row["case"] not in recorded:
                    raise MissingDraft(f"{row['case']} is not recorded for {arm}")
                flips.setdefault(row["cell"], []).append(recorded[row["case"]])
        return flips


class BarInputs(Inputs):
    """Every bar's input of a complete attempt; a missing draft raises."""

    def __init__(self, rows: Mapping[str, Sequence[Mapping[str, Any]]], outcomes: Outcomes) -> None:
        super().__init__(rows, outcomes, partial=False)


class PartialBarInputs(Inputs):
    """A void attempt's inputs: the drafts recorded on both sides only, for `rules.report` and never a decision."""

    def __init__(self, rows: Mapping[str, Sequence[Mapping[str, Any]]], outcomes: Outcomes) -> None:
        super().__init__(rows, outcomes, partial=True)


def build(rows: Mapping[str, Sequence[Mapping[str, Any]]], outcomes: Outcomes, *, partial: bool = False) -> Inputs:
    return PartialBarInputs(rows, outcomes) if partial else BarInputs(rows, outcomes)


class DataReadings(rules.Readings):
    """`rules.Readings` over a complete attempt's inputs: each read computes its bar from the aligned matrices."""

    def __init__(self, inputs: BarInputs, p7_cases: list[dict[str, Any]]) -> None:
        if not isinstance(inputs, BarInputs):  # pyright: ignore[reportUnnecessaryIsInstance] - runtime guard
            raise TypeError(f"a decision reads a complete attempt's BarInputs, not {type(inputs).__name__}")
        self.inputs, self.p7_cases = inputs, p7_cases

    def paired(self, bar: str, config: Config, ref: Config, *, z: float, ni_z: float, cell: bool) -> bool:
        x, b = self.inputs.paired(bar, config, ref)
        return rules.ni_paired(x, b, z, ni_z=ni_z, cell=cell).passed

    def frr_t(self, config: Config, z: float) -> bool:
        if z != rules.Z_58T:
            raise ValueError("FRR-T is read at z = 2.4977 (Bonferroni over the four library arms)")
        return rules.bar_frr_t(self.inputs.single(config))[2]

    def frr_fi(self, arm: str, z: float) -> Mapping[str, bool]:
        if z != rules.Z_STRATA:
            raise ValueError("FRR-Fi is read at z = 2.394 (Bonferroni over the three strata)")
        return {s: rules.bar_frr_fi(*self.inputs.stratum(s, (arm, "F1"), (arm, "F0")))[1] for s in STRATA.values()}

    def rb_points(self, config: Config) -> bool:
        return rules.rb_points(self.inputs.rb_rows(config)).passed

    def rb_rejected(self, config: Config) -> int:
        return rules.rb_points(self.inputs.rb_rows(config)).rejected

    def bar_i(self, arm: str) -> bool:
        return rules.bar_i(admission.flipped_cells(self.inputs.flips_by_cell(arm)))[1]

    def pc(self) -> bool:
        return rules.bar_pc(admission.replica_flipped_cases(self.inputs.flips_by_cell("L0")))[1]

    def fx(self, arm: str) -> bool:
        return rules.bar_fx(self.p7_cases, self.inputs.outcomes.p7[arm])
