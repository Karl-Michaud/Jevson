"""Probe 4: entity resolution on real prose clusters, sent twice (docs/taxonomy.md §2.4).

    uv run python -m tests.phase0.run_probe_4 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import common, probes
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    cl = common.clusters()
    tx = common.texts()
    return run_cli("probe4", argv, lambda: probes.build_4(cl, tx), lambda recs: probes.score_4(cl, recs), runs=2)


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
