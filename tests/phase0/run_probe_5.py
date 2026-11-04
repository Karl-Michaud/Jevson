"""Probe 5: state referencing, probe_state_references.py re-run on the pinned model (docs/taxonomy.md §2.5).
The only runner that sends positional references, on purpose.

    uv run python -m tests.phase0.run_probe_5 --estimate | --dry-run | --live
"""
from __future__ import annotations

from tests.phase0 import probes
from tests.phase0.runner import main_guard, run_cli


def main(argv: list[str]) -> int:
    mod = probes.probe5_module()
    reqs = probes.build_5(mod)
    return run_cli("probe5", argv, lambda: reqs, lambda recs: probes.score_5(reqs, recs, mod.TRUTH),
                   allow_positional=True)


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
