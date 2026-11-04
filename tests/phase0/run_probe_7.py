"""Probe 7: calibration reading over the probe 1-3 decisions (docs/taxonomy.md §2.7). No requests.

    uv run python -m tests.phase0.run_probe_7 [--backend decisions]

With ``--backend decisions`` it reads and writes the Phase 0r results under ``results/0r/``.
"""
from __future__ import annotations

import argparse
import json
import pathlib

from tests.phase0 import common, probes
from tests.phase0.runner import main_guard


def main(argv: list[str], results: pathlib.Path | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_probe_7")
    ap.add_argument("--backend", choices=["jev", "decisions"], default="jev")
    a = ap.parse_args(argv)
    results = results or (common.RESULTS / "0r" if a.backend == "decisions" else common.RESULTS)
    out = probes.score_7(common.read_result("probe1_2_3", results)["decisions"])
    (results / "probe7.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "reliability"} if isinstance(v, dict) else v
                      for k, v in out.items()}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    main_guard(main)
