"""`report`: every bar's numbers and every secondary the design requires (design §3-§4; STATS48-R4-3).

It decides nothing: `adopt_48` and `decide_58` decide, from `rules.Readings`. A void attempt's report runs on
`bar_inputs.PartialBarInputs` over its code-truth bars only (single-look item 12(b)), with each bar's n stated.
Kept apart from `rules.py` for size (plan §5); it imports no decision function.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

from tests.j4b.fresh import admission, rules
from tests.j4b.fresh.bar_inputs import STRATA, Config, PartialBarInputs, _Inputs  # pyright: ignore[reportPrivateUsage]
from tests.j4b.fresh.clustering import Matrix

FACTORS = ("verb", "echo", "topic", "value", "position", "domain_pair")
ARMS = ("L0", "L1", "L2", "L3")


def _ni(x: Matrix, b: Matrix, z: float, *, multiplier: bool, cell: bool) -> dict[str, Any]:
    reading = rules.ni_paired(x, b, z, ni_z=(rules.NI_MULTIPLIER if multiplier else 1.0) * z, cell=cell)
    n = sum(len(c) for c in x)
    return {
        "n": n,
        "clusters": len(x),
        "cluster_sizes": dict(Counter(len(c) for c in x)),
        **{k: (str(v) if k == "point" else v) for k, v in asdict(reading).items()},
    }


def iset_report(inputs: _Inputs) -> dict[str, Any]:
    out: dict[str, Any] = {}
    levels = {r["cell"]: r for r in inputs.rows["iset.jsonl"] if r["role"] == "injected"}
    for arm in ARMS:
        flips = inputs.flips_by_cell(arm)
        interval, passed = rules.bar_i(admission.flipped_cells(flips), len(flips) if inputs.partial else rules.G_CELLS)
        per_level = {
            f: dict(Counter(str(levels[c].get(f)) for c, v in flips.items() if any(v) and c != "replica"))
            for f in FACTORS
        }
        pairs = [v for c, v in flips.items() if c != "replica" and len(v) == 2]
        out[arm] = {
            "flipped_cells": admission.flipped_cells(flips),
            "cells": len(flips),
            "bar_i": asdict(interval),
            "bar_i_passed": passed,
            "flipped_cells_by_level": per_level,
            "within_cell_agreement": [sum(a == b for a, b in pairs), len(pairs)],
            "replica_flipped_cases": admission.replica_flipped_cases(flips),
        }
    pc_interval, pc_passed = rules.bar_pc(out["L0"]["replica_flipped_cases"])
    out["pc"] = {"lower_z_1_96": pc_interval.low, "passed": pc_passed}
    return out


def pset_report(inputs: _Inputs) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm in ARMS:
        f0, f1 = (arm, "F0"), (arm, "F1")
        out[f"{arm}F0"] = {
            "FRR-NI": _ni(*inputs.paired("FRR-NI", f0, rules.L0F0), rules.Z_48, multiplier=True, cell=True),
            "FRR-NI_benign": _ni(*inputs.benign_frr(f0, rules.L0F0), rules.Z_48, multiplier=True, cell=True),
            "FA-NI_48": _ni(*inputs.paired("FA-NI", f0, rules.L0F0), rules.Z_48, multiplier=True, cell=True),
        }
        frr_t, deff, passed = rules.bar_frr_t(inputs.single(f1))
        out[f"{arm}F1"] = {
            "FA-NI_58": _ni(*inputs.paired("FA-NI", f1, f0), rules.Z_ONE, multiplier=True, cell=True),
            "SC-FA": _ni(*inputs.paired("SC-FA", f1, f0), rules.Z_ONE, multiplier=True, cell=True),
            "SC-FA_by_stratum": {
                s: _ni(*inputs.stratum_self_claims(s, f1, f0), rules.Z_ONE, multiplier=True, cell=True)
                for s in STRATA.values()
            },
            "FA-S": _ni(*inputs.paired("FA-S", f1, rules.L0F0), rules.Z_ONE, multiplier=True, cell=True),
            "SC-S": _ni(*inputs.paired("SC-S", f1, rules.L0F0), rules.Z_ONE, multiplier=True, cell=True),
            "FRR-T": {"interval": asdict(frr_t), "deff": deff, "passed": passed},
            "FRR-Fi": {s: rules.bar_frr_fi(*inputs.stratum(s, f1, f0)) for s in STRATA.values()},
        }
    return out


def rset_report(inputs: _Inputs, fields: Mapping[str, str]) -> dict[str, Any]:
    """RB points, C-NI and B-NI against (L0, F0), per-field C and B differences, and R-FRR."""
    out: dict[str, Any] = {}
    for arm in ARMS:
        for form in ("F0", "F1"):
            config: Config = (arm, form)
            points = rules.rb_points(inputs.rb_rows(config))
            per_field = _per_field(inputs, config, fields)
            out[f"{arm}{form}"] = {
                "RB": {**asdict(points), "a": str(points.a), "b_minus_c": str(points.b_minus_c)},
                "C-NI": _ni(*inputs.paired("C-NI", config, rules.L0F0), rules.Z_48, multiplier=False, cell=False),
                "B-NI": _ni(*inputs.paired("B-NI", config, rules.L0F0), rules.Z_48, multiplier=False, cell=False),
                "C_and_B_by_field": per_field,
                "R-FRR": _r_frr(inputs, config),
            }
    return out


def _per_field(inputs: _Inputs, config: Config, fields: Mapping[str, str]) -> dict[str, list[int]]:
    """Per R-set field: (C, B) counts under `config` minus under (L0, F0), over drafts recorded for both."""
    out: dict[str, list[int]] = {}
    for bar, slot in (("C-NI", 0), ("B-NI", 1)):
        error = inputs.rset_error(bar)
        for ids in inputs.documents.values():
            for draft_id in ids:
                xv, bv = error(config, draft_id), error(rules.L0F0, draft_id)
                if xv is not None and bv is not None:
                    out.setdefault(fields[draft_id], [0, 0])[slot] += xv - bv
    return out


def _r_frr(inputs: _Inputs, config: Config) -> dict[str, Any]:
    firsts = inputs.outcomes.rset.get(config, {})
    clusters = [
        [int(not firsts[i].first_admitted) for i in ids if i in firsts and firsts[i].first_true]
        for ids in inputs.documents.values()
    ]
    clusters = [c for c in clusters if c]
    if not clusters:
        return {"n": 0}
    interval, deff = rules.r_frr(clusters)
    return {"n": sum(map(len, clusters)), "interval": asdict(interval), "deff": deff}


def report(
    inputs: _Inputs,
    *,
    p7_cases: Sequence[dict[str, Any]],
    rset_fields: Mapping[str, str] | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Every bar's estimate, iid and adjusted intervals and DEFF, and every secondary. A partial (void) attempt is
    reported over its code-truth bars only, with its (L0, F0) rejected count."""
    out: dict[str, Any] = {"partial": isinstance(inputs, PartialBarInputs), "iset": iset_report(inputs)}
    out["fx"] = {
        arm: rules.bar_fx(list(p7_cases), inputs.outcomes.p7[arm]) for arm in ARMS if arm in inputs.outcomes.p7
    }
    out["pset"] = pset_report(inputs)
    out["l0f0_rejected"] = rules.rb_points(inputs.rb_rows(rules.L0F0)).rejected
    if not out["partial"] and rset_fields is not None:
        out["rset"] = rset_report(inputs, rset_fields)
    out["secondaries"] = dict(extras or {})
    return out
