"""Probe 6: hostile source, and the source screen on attacked and benign documents (docs/taxonomy.md §2.6).

    uv run python -m tests.phase0.run_probe_6 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import common, probes
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    hostile, benign, base = common.hostile()
    reqs = probes.build_6(hostile, benign, base, common.texts())
    return run_cli("probe6", argv, lambda: reqs, lambda recs: probes.score_6(reqs, recs))


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
