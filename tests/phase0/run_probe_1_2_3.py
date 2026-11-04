"""Probes 1-3: disambiguation accuracy, abstention sensitivity, false abstention (docs/taxonomy.md §2.2-2.3).

    uv run python -m tests.phase0.run_probe_1_2_3 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import common, probes
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    present, absent = common.selection()
    tx = common.texts()
    dom = common.domains()
    return run_cli("probe1_2_3", argv, lambda: probes.build_123(present, absent, tx),
                   lambda recs: probes.score_123(present, absent, recs, dom))


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
