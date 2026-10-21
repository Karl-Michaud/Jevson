"""The ASTERION-48/-58 fresh-set run (design §6; plan §7): opt-in and billed, never in CI or `testpaths`.

    uv run --frozen python -m tests.integration.run_fresh dryrun                # no network, no key
    uv run --frozen python -m tests.integration.run_fresh dev     --attempt N   # billed; needs Karl's go-ahead
    uv run --frozen python -m tests.integration.run_fresh confirm --attempt N   # billed; once
    uv run --frozen python -m tests.integration.run_fresh export  --attempt N   # no network
    uv run --frozen python -m tests.integration.run_fresh score   --attempt N   # replay only, no network; once, ever
    uv run --frozen python -m tests.integration.run_fresh inconclusive          # no complete attempt; once, ever
    uv run --frozen python -m tests.integration.run_fresh void    --attempt N --reason harness_defect [--note TEXT]
                                                         [--failing-test NODE --test-commit C]

A thin CLI: it parses arguments and wires the modules under `tests/j4b/fresh/`, where every rule lives (pins,
attempt order, gates, re-queue, spend, metering, phases, scoring). `--root` (default `tests/j4b/recordings/fresh`)
holds `attempt-N/`, `spend.jsonl`, `run.lock` and `analysis-started.json`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from tests.integration.key import openai_key
from tests.j4b.fresh import attempts, dryrun, pins, runner, scoring
from tests.j4b.fresh.attempts import Refused

REPO = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO / "tests" / "j4b" / "recordings" / "fresh"


def pin_check(root: Path) -> runner.PinCheck:
    """`pins.check` against the appendix in force; it refuses on a dirty or mismatched tree (plan §2)."""

    def check(command: str, attempt: int) -> Mapping[str, Any]:
        path = REPO / pins.APPENDIX
        if not path.exists():
            raise pins.PinMismatch(f"no pre-registration appendix at {pins.APPENDIX}")
        return pins.check(REPO, root, path.read_text(encoding="utf-8"), command=command, attempt=attempt).record()

    return check


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("dryrun")
    sub.add_parser("inconclusive")
    for name in ("dev", "confirm", "export", "score", "void"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--attempt", type=int, required=True)
        if name == "void":
            cmd.add_argument("--reason", required=True)
            cmd.add_argument("--note")
            cmd.add_argument("--failing-test")
            cmd.add_argument("--test-commit")
    return ap


def void(env: runner.Env, a: argparse.Namespace) -> int:
    test: Callable[[], Mapping[str, Any]] | None = None
    if a.failing_test or a.test_commit:
        if not (a.failing_test and a.test_commit):
            raise Refused("--failing-test and --test-commit go together")
        start = attempts.read_record(attempts.Attempts(env.root).phase_dir(a.attempt, "confirm") / "start.json") or {}

        def failing() -> Mapping[str, Any]:
            return attempts.failing_test_record(
                REPO, str(start.get("harness_commit")), a.test_commit, a.failing_test, pins.PINNED_PATHS
            )

        test = failing
    return runner.void(env, a.attempt, a.reason, note=a.note, test=test)


def dry() -> int:
    figures = dryrun.figures()
    print(dryrun.render(figures))
    try:
        dryrun.check(figures)
    except dryrun.MarginViolation as violation:
        print(f"refused before any spend: {violation}", file=sys.stderr)
        return 2
    return 0


COMMANDS: dict[str, Callable[[runner.Env, argparse.Namespace], int]] = {
    "dev": lambda env, a: runner.run_phase(env, "dev", a.attempt),
    "confirm": lambda env, a: runner.run_phase(env, "confirm", a.attempt),
    "export": lambda env, a: scoring.export(env, a.attempt),
    "score": lambda env, a: scoring.score(env, a.attempt),
    "void": void,
    "inconclusive": lambda env, a: scoring.inconclusive(env),
}


def main(argv: Sequence[str] | None = None) -> int:
    a = parser().parse_args(argv)
    if a.command == "dryrun":
        return dry()
    root = a.root.resolve()
    try:
        return COMMANDS[a.command](runner.Env(root, pin_check(root), key=openai_key), a)
    except (Refused, pins.PinMismatch) as refused:
        print(f"refused: {refused}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
