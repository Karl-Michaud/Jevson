"""H39: run-time pins in a hermetic repository (plan §2 rules (a)-(d); ARCH48-R6-1 ... STATS48-R13-1).

Each case starts from the planted harness on a branch of its own and names the item `pins.check` must refuse.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import pins
from tests.j4b.fresh.attempts import Attempts
from tests.j4b.tests.planted_repo import PlantedRepo

FLAGGED = " It names the 2 dates."
ISET = "tests/j4b/fresh/iset_wordings.json"
PSET = "tests/j4b/fresh/pset_templates.json"
RSET = "tests/j4b/fresh/rset_fields.json"
METERING_TEST = "tests/j4b/tests/test_fresh_metering.py"


@pytest.fixture(scope="module")
def base(tmp_path_factory: pytest.TempPathFactory) -> PlantedRepo:
    return PlantedRepo.create(tmp_path_factory.mktemp("h39") / "repo")


@pytest.fixture
def repo(base: PlantedRepo, request: pytest.FixtureRequest) -> PlantedRepo:
    branch = re.sub(r"[^A-Za-z0-9]+", "-", request.node.name)[:80]
    base.git("checkout", "-q", "-f", "-B", branch, "base")
    base.git("clean", "-q", "-fdx")
    return base


def refuses(repo: PlantedRepo, run: Path, appendix: str, match: str, *, command: str = "confirm") -> None:
    with pytest.raises(pins.PinMismatch, match=re.escape(match)):
        pins.check(repo.root, run, appendix, command=command, attempt=1)


# --- (a)-(d): the tree must be the pinned one ---------------------------------------------------------


def test_h39a_an_unchanged_tree_passes_and_start_json_holds_the_pins(repo: PlantedRepo, tmp_path: Path) -> None:
    p = repo.record(tmp_path, 1, "dev", repo.appendix(), finish=False)
    start = (tmp_path / "attempt-1" / "dev" / "start.json").read_text()
    assert p.harness_commit == repo.git("rev-parse", "HEAD")
    assert p.harness_commit in start
    assert p.harness["tests/j4b/fresh"] in start
    assert p.library_tree == repo.git("rev-parse", "HEAD:jevson")


def test_h39b_a_committed_rules_edit_after_the_pin_makes_score_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.edit("tests/j4b/fresh/rules.py", lambda s: s.replace("NI_MULTIPLIER = 1.2", "NI_MULTIPLIER = 1.0"))
    repo.commit("edit rules")
    refuses(repo, tmp_path, appendix, "tests/j4b/fresh differs", command="score")


def test_h39c_a_committed_library_change_makes_confirm_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.edit("jevson/config.py", lambda s: s + "\n# a library change\n")
    repo.commit("edit jevson")
    refuses(repo, tmp_path, appendix, "jevson differs")


def test_h39d_an_uncommitted_edit_under_a_pinned_path_makes_dev_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.edit("tests/j4b/fresh/rules.py", lambda s: s + "\n")
    refuses(repo, tmp_path, appendix, "uncommitted change", command="dev")


def test_h39g_an_appendix_pinning_another_library_tree_is_refused_first(repo: PlantedRepo, tmp_path: Path) -> None:
    repo.edit("jevson/config.py", lambda s: s + "\n# PR-A's squash, before -44 moved jevson/\n")
    old = repo.commit("pr-a")
    appendix = repo.appendix(commit=old)
    repo.edit("jevson/config.py", lambda s: s + "\n# -44\n")
    repo.commit("minus44")
    with pytest.raises(pins.PinMismatch, match="pinned library tree"):
        pins.assert_library_pin(repo.root, appendix)
    refuses(repo, tmp_path, appendix, "jevson differs", command="dev")


@pytest.mark.parametrize(
    ("path", "label"),
    [
        ("tests/j4b/fixtures/p7_draft_injection.jsonl", "tests/j4b/fixtures"),
        ("tests/phase0/datasets/corpus/README.md", "tests/phase0/datasets/corpus"),
    ],
)
def test_h39h_the_p7_fixture_and_the_corpus_are_pinned(
    repo: PlantedRepo, tmp_path: Path, path: str, label: str
) -> None:
    appendix = repo.appendix()
    repo.edit(path, lambda s: "\n".join(s.splitlines()[:-1]) + "\n")
    repo.commit("drop a line")
    refuses(repo, tmp_path, appendix, f"{label} differs", command="score")


# --- the one allowed fix (design §2.6), and everything it may not touch --------------------------------


def plant_flagged_claim(repo: PlantedRepo) -> None:
    """A dev fixture whose c001 claim carries a guarded token, in the authored data and in its rows."""

    def claim(records: dict[str, Any]) -> None:
        records["c001"]["claim"] = records["c001"]["claim"] + FLAGGED

    def rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row["cell"] == "c001" and row["role"] == "injected":
                row["draft"] = row["draft"].replace(row["claim"], row["claim"] + FLAGGED)
                row["claim"] += FLAGGED

    repo.authored(ISET, claim)
    repo.rows("iset.jsonl", rows)


def fix_flagged_claim(repo: PlantedRepo, *, rows_too: bool = True) -> None:
    repo.authored(ISET, lambda r: r["c001"].update(claim=r["c001"]["claim"].replace(FLAGGED, "")))
    if rows_too:

        def rows(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                if row["cell"] == "c001" and row["role"] == "injected":
                    row["draft"] = row["draft"].replace(FLAGGED, "")
                    row["claim"] = row["claim"].replace(FLAGGED, "")

        repo.rows("iset.jsonl", rows)


def dev_done(repo: PlantedRepo, run: Path, *, flagged: bool = True) -> str:
    """Commit the dev harness (with a flagged claim by default), run dev under its pins; return its appendix."""
    if flagged:
        plant_flagged_claim(repo)
    repo.commit("dev harness")
    appendix = repo.appendix()
    repo.record(run, 1, "dev", appendix)
    return appendix


def amend(repo: PlantedRepo, original: str, motivating: dict[str, str] | None = None) -> str:
    repo.commit("amendment")
    return repo.appendix(parent=pins.sha256(original), motivating=motivating)


def test_h39_the_flagged_claim_fix_with_its_row_and_summary_is_accepted(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    assert pins.flags_at(repo.root, "HEAD") == {"iset#c001.claim", "iset.jsonl#c001-a-inj", "iset.jsonl#c001-b-inj"}
    fix_flagged_claim(repo)
    p = pins.check(repo.root, tmp_path, amend(repo, original), command="confirm", attempt=1)
    assert p.appendix_sha256 != pins.sha256(original)


EDITS: dict[str, tuple[Callable[[PlantedRepo], None], str]] = {
    "rules NI multiplier": (
        lambda r: r.edit("tests/j4b/fresh/rules.py", lambda s: s.replace("= 1.2", "= 1.0")),
        "frozen item tests/j4b/fresh/rules.py",
    ),
    "arms": (lambda r: r.edit("tests/j4b/fresh/arms.py", lambda s: s + "\n"), "frozen item tests/j4b/fresh/arms.py"),
    "admission": (
        lambda r: r.edit(
            "tests/j4b/fresh/admission.py",
            lambda s: s.replace(
                "admitted(result, INJECTED) or admitted(result, COMPANION)", "admitted(result, INJECTED)"
            ),
        ),
        "frozen item tests/j4b/fresh/admission.py",
    ),
    "bar inputs": (
        lambda r: r.edit("tests/j4b/fresh/bar_inputs.py", lambda s: s + "\n"),
        "frozen item tests/j4b/fresh/bar_inputs.py",
    ),
    "truth": (lambda r: r.edit("tests/j4b/fresh/truth.py", lambda s: s + "\n"), "frozen item tests/j4b/fresh/truth.py"),
    "leakage": (
        lambda r: r.edit("tests/j4b/fresh/leakage.py", lambda s: s + "\n"),
        "frozen item tests/j4b/fresh/leakage.py",
    ),
    "judging": (
        lambda r: r.edit("tests/j4b/fresh/judging.py", lambda s: s + "\n"),
        "frozen item tests/j4b/fresh/judging.py",
    ),
    "pins": (lambda r: r.edit("tests/j4b/fresh/pins.py", lambda s: s + "\n"), "frozen item tests/j4b/fresh/pins.py"),
    "sources": (
        lambda r: r.edit("tests/j4b/fresh/sources.py", lambda s: s + "\n"),
        "frozen item tests/j4b/fresh/sources.py",
    ),
    "a pinned constant": (
        lambda r: r.edit("tests/j4b/fresh/constants.py", lambda s: s.replace("15 * NANO", "16 * NANO")),
        "frozen item tests/j4b/fresh/constants.py",
    ),
    "an I-set criterion": (
        lambda r: r.authored(ISET, lambda x: x["c001"].update(criterion=x["c001"]["criterion"] + " ")),
        "frozen item iset#c001.criterion",
    ),
    "a P-set F1 criterion": (
        lambda r: r.authored(PSET, lambda x: x["p000"].update(f1=x["p000"]["f1"] + " ")),
        "frozen item pset#p000.f1",
    ),
    "an R-set criterion": (
        lambda r: r.authored(RSET, lambda x: x["receipt.total"]["f0"].append("x")),
        "frozen item rset#receipt.total.f0",
    ),
    "a benign wording": (
        lambda r: r.authored(PSET, lambda x: x["p000"].update(benign=x["p000"]["benign"] + " ")),
        "frozen item pset#p000.benign",
    ),
    "an R-set instructions": (
        lambda r: r.authored(RSET, lambda x: x["receipt.total"].update(instructions="Other.")),
        "frozen item rset#receipt.total.instructions",
    ),
    "an R-set pointer": (
        lambda r: r.authored(RSET, lambda x: x["receipt.total"].update(pointer="/sum")),
        "frozen item rset#receipt.total.pointer",
    ),
    "an R-set type": (
        lambda r: r.authored(RSET, lambda x: x["receipt.total"].update(type="text")),
        "frozen item rset#receipt.total.type",
    ),
    "the replica claim": (
        lambda r: r.authored(ISET, lambda x: x["replica"].update(claim=x["replica"]["claim"] + " ")),
        "frozen item iset#replica.claim",
    ),
    "an unflagged claim": (
        lambda r: r.authored(ISET, lambda x: x["c002"].update(claim=x["c002"]["claim"] + " ")),
        "changed item not flagged: iset#c002.claim",
    ),
    "an unflagged companion": (
        lambda r: r.authored(ISET, lambda x: x["c002"].update(companion="The draft states it.")),
        "changed item not flagged: iset#c002.companion",
    ),
    "a P-set row re-rendered": (
        lambda r: r.rows("pset.jsonl", lambda rows: rows[0].update(draft=rows[0]["draft"] + " ")),
        "changed item not flagged: pset.jsonl#p000-pass-0",
    ),
    "a new attribute": (
        lambda r: r.authored(ISET, lambda x: x["c001"].update(hook="x")),
        "keys differ: ['iset#c001.hook']",
    ),
    "a code file beside the data": (
        lambda r: r.path("tests/j4b/fresh/iset_wordings.py").write_text("import rules\nrules.NI_MULTIPLIER = 1.0\n"),
        "keys differ: ['tests/j4b/fresh/iset_wordings.py']",
    ),
    "a non-row file under fixtures": (
        lambda r: r.path(f"{pins.FIXTURES}/notes.txt").write_text("x\n"),
        "keys differ: ['tests/j4b/fixtures/fresh/notes.txt']",
    ),
    "bytes after the authored data": (lambda r: r.edit(ISET, lambda s: s + "# note\n"), f"non-canonical {ISET}"),
    "the authored data re-indented": (
        lambda r: r.edit(ISET, lambda s: s.replace('\n "', '\n  "')),
        f"non-canonical {ISET}",
    ),
    "bytes outside the rows": (
        lambda r: r.edit(f"{pins.FIXTURES}/iset.jsonl", lambda s: s + "\n"),
        "bytes outside the rows of tests/j4b/fixtures/fresh/iset.jsonl",
    ),
    "summary hand-edited": (
        lambda r: r.edit(pins.SUMMARY, lambda s: s.replace('"counts"', '"counts" ')),
        f"not the frozen summariser's output: {pins.SUMMARY}",
    ),
    "a metering fix with the claim fix": (
        lambda r: r.edit("tests/j4b/fresh/metering.py", lambda s: s + "\n"),
        "a module fix and a fixture fix together",
    ),
}


@pytest.mark.parametrize("name", sorted(EDITS))
def test_h39i_the_claim_fix_with_anything_else_is_refused_naming_it(
    repo: PlantedRepo, tmp_path: Path, name: str
) -> None:
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    change, message = EDITS[name]
    change(repo)
    refuses(repo, tmp_path, amend(repo, original), message)


def test_h39i_a_stale_summary_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    repo.edit(f"{pins.FIXTURES}/iset.jsonl", lambda s: s.replace("c000", "c000", 1))
    summary = repo.path(pins.SUMMARY).read_text()
    repo.rows("iset.jsonl", lambda rows: rows[0].update(draft=rows[0]["draft"] + " "))
    repo.path(pins.SUMMARY).write_text(summary)
    refuses(repo, tmp_path, amend(repo, original), f"not the frozen summariser's output: {pins.SUMMARY}")


def test_h39i_a_flagged_claim_fixed_with_its_row_still_flagged_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo, rows_too=False)
    repo.summarise()
    refuses(repo, tmp_path, amend(repo, original), "flagged item not fixed: iset.jsonl#c001-a-inj")


def test_h39i_with_nothing_flagged_at_dev_no_fixture_amendment_is_possible(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.authored(ISET, lambda x: x["c003"].update(claim=x["c003"]["claim"] + " "))
    refuses(repo, tmp_path, amend(repo, original), "flag nothing at dev")


FIX_TEST = """

def test_the_motivating_fix() -> None:
    from tests.j4b.fresh import metering

    assert getattr(metering, "FIXED", False)
"""


def module_fix(repo: PlantedRepo, test: bool = True) -> None:
    repo.edit("tests/j4b/fresh/metering.py", lambda s: s + "\nFIXED = True\n")
    if test:
        repo.path(METERING_TEST).parent.mkdir(parents=True, exist_ok=True)
        repo.path(METERING_TEST).write_text('"""Motivating test."""\n' + FIX_TEST)


def test_h39i_a_metering_fix_motivated_by_its_own_failing_test_is_accepted(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    appendix = amend(repo, original, {"tests/j4b/fresh/metering.py": node})
    assert pins.check(repo.root, tmp_path, appendix, command="confirm", attempt=1)


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (
            "tests/j4b/tests/test_fresh_truth.py::test_x",
            "needs a motivating test in tests/j4b/tests/test_fresh_metering.py",
        ),
        (None, "needs a motivating test"),
    ],
)
def test_h39i_a_metering_fix_without_its_own_test_is_refused(
    repo: PlantedRepo, tmp_path: Path, node: str | None, message: str
) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    module_fix(repo)
    motivating = {"tests/j4b/fresh/metering.py": node} if node else {}
    refuses(repo, tmp_path, amend(repo, original, motivating), message)


def test_h39i_a_motivating_test_that_does_not_fail_at_dev_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.edit("tests/j4b/fresh/metering.py", lambda s: s + "\n# a comment\n")
    repo.path(METERING_TEST).write_text(
        '"""Motivating test."""\n\n\ndef test_the_motivating_fix() -> None:\n    pass\n'
    )
    node = f"{METERING_TEST}::test_the_motivating_fix"
    refuses(repo, tmp_path, amend(repo, original, {"tests/j4b/fresh/metering.py": node}), "must fail at dev")


def test_h39i_old_commits_are_read_never_imported(repo: PlantedRepo, tmp_path: Path) -> None:
    repo.path("tests/j4b/fresh/boom.py").write_text("raise RuntimeError('imported')\n")
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    assert pins.check(repo.root, tmp_path, amend(repo, original), command="confirm", attempt=1)


# --- (e), (f): the pin history ------------------------------------------------------------------------


def test_h39e_after_confirm_a_repinned_rules_edit_makes_score_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.record(tmp_path, 1, "confirm", original)
    repo.edit("tests/j4b/fresh/rules.py", lambda s: s.replace("= 1.2", "= 1.0"))
    repo.commit("edit rules after confirm")
    refuses(repo, tmp_path, amend(repo, original), "score's pins differ", command="score")


def test_h39f_a_second_amendment_or_one_after_confirm_started_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    first = amend(repo, original)
    repo.record(tmp_path, 1, "confirm", first, finish=False)
    repo.edit(f"{pins.FIXTURES}/iset.jsonl", lambda s: s)
    second = repo.appendix(parent=pins.sha256(first))
    refuses(repo, tmp_path, second, "pins differ from the first confirm/start.json")
    other = tmp_path / "other"
    dev_run = Attempts(other)
    dev_run.start(
        1, "dev", {"pins": {"appendix_sha256": "o", "library_tree": "l", "harness": {}, "harness_commit": "h"}}
    )
    with pytest.raises(pins.PinMismatch, match="second amendment"):
        pins.check(repo.root, other, second, command="confirm", attempt=1)
