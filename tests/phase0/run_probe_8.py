"""Probe 8: single candidates and partials (docs/taxonomy.md §2.8).

    uv run python -m tests.phase0.run_probe_8 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import common, probes
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    cases = common.single()
    tx = common.texts()
    return run_cli("probe8", argv, lambda: probes.build_8(cases, tx), lambda recs: probes.score_8(cases, recs))


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
