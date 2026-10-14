"""Fail unless line coverage and branch coverage each reach the threshold.

Ported from Asterion's scripts/ci/coverage_gate.py. pytest's --cov-fail-under checks one combined
figure, (lines + branches covered) / (lines + branches), so 100% of lines can carry 50% of branches
past a 90% gate. Agents/CLAUDE.md §7.1 asks for 90% line *and* branch coverage, so CI checks the
two separately.

Usage: uv run --frozen python -I scripts/ci/coverage_gate.py coverage.json 90
"""

import json
import sys
from pathlib import Path


def main() -> int:
    totals: dict[str, float] = json.loads(Path(sys.argv[1]).read_text())["totals"]
    threshold = float(sys.argv[2])
    lines, branches = totals["percent_statements_covered"], totals["percent_branches_covered"]
    print(f"coverage gate: lines {lines:.2f}%, branches {branches:.2f}%, threshold {threshold}%")
    return 0 if lines >= threshold and branches >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
