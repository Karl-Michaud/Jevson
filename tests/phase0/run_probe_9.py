"""Probe 9: the second gate (docs/gate-probe.md) on the fresh cases (deciding) and on the Phase 0 cases (paired,
in-sample, not deciding).

    uv run python -m tests.phase0.run_probe_9 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import common, probes
from tests.phase0.datasets import models as M
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    root = common.CORPUS
    gp = M.load_selection(common.CASES / "gate_present.jsonl", root)
    ga = M.load_selection(common.CASES / "gate_absent.jsonl", root)
    p0p, p0a = common.selection()
    groups = {"g1": gp, "g2": ga, "r1": p0p, "r2": p0a}
    reqs = probes.build_gate(groups, common.texts())
    return run_cli("probe9", argv, lambda: reqs,
                   lambda recs: {"fresh": probes.score_gate(gp, ga, recs, "g1", "g2"),
                                 "paired_phase0": probes.score_gate(p0p, p0a, recs, "r1", "r2")})


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
