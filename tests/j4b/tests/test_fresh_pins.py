"""H39: run-time pins in a hermetic repository (plan §2 rules (a)-(d); ARCH48-R6-1 ... STATS48-R13-1).

Each case starts from the planted harness on a branch of its own and names the item `pins.check` must refuse.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import build_fresh_sets, overlay, pins
from tests.j4b.fresh.attempts import Attempts
from tests.j4b.tests.planted_repo import PlantedRepo

ROOT = Path(__file__).resolve().parents[3]

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
    """`check` refuses with exactly the message `match` (review round 2, T48-5: no substring match)."""
    with pytest.raises(pins.PinMismatch, match=f"^{re.escape(match)}$"):
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
    refuses(repo, tmp_path, appendix, "tests/j4b/fresh differs from its pin", command="score")


def test_h39c_a_committed_library_change_makes_confirm_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.edit("jevson/config.py", lambda s: s + "\n# a library change\n")
    repo.commit("edit jevson")
    refuses(repo, tmp_path, appendix, "jevson differs from the pinned library tree")


def test_h39d_an_uncommitted_edit_under_a_pinned_path_makes_dev_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.edit("tests/j4b/fresh/rules.py", lambda s: s + "\n")
    refuses(
        repo, tmp_path, appendix, "uncommitted change under a pinned path:  M tests/j4b/fresh/rules.py", command="dev"
    )


def test_h39g_an_appendix_pinning_another_library_tree_is_refused_first(repo: PlantedRepo, tmp_path: Path) -> None:
    repo.edit("jevson/config.py", lambda s: s + "\n# PR-A's squash, before -44 moved jevson/\n")
    old = repo.commit("pr-a")
    appendix = repo.appendix(commit=old)
    repo.edit("jevson/config.py", lambda s: s + "\n# -44\n")
    repo.commit("minus44")
    with pytest.raises(pins.PinMismatch, match="pinned library tree"):
        pins.assert_library_pin(repo.root, appendix)
    refuses(repo, tmp_path, appendix, "jevson differs from the pinned library tree", command="dev")


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
    refuses(repo, tmp_path, appendix, f"{label} differs from its pin", command="score")


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
    repo.path(pins.APPENDIX).parent.mkdir(parents=True, exist_ok=True)
    repo.path(pins.APPENDIX).write_text(appendix, encoding="utf-8")
    repo.commit("pre-registration")
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
    refuses(repo, tmp_path, amend(repo, original),
            "the frozen checker and leakage code flag nothing at dev: no fixture amendment")  # fmt: skip


FIX_TEST = """

def test_the_motivating_fix() -> None:
    from tests.j4b.fresh import metering

    assert getattr(metering, "fixed", lambda: False)()
"""
FIXED = "\n\ndef fixed() -> bool:\n    return True\n"
"""A planted fix inside a function: a module-level constant of an amendable module is a frozen item (STATS48-B10-3)."""


def module_fix(repo: PlantedRepo, test: bool = True) -> None:
    repo.edit("tests/j4b/fresh/metering.py", lambda s: s + FIXED)
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
            "tests/j4b/fresh/metering.py needs a motivating test in tests/j4b/tests/test_fresh_metering.py",
        ),
        (None, "tests/j4b/fresh/metering.py needs a motivating test in tests/j4b/tests/test_fresh_metering.py"),
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
    refuses(repo, tmp_path, amend(repo, original, {"tests/j4b/fresh/metering.py": node}),
            f"{node} must fail at dev (exit 0) and pass after (exit 0)")  # fmt: skip


FLIP_AND_TRUTH = {
    "the I-set flip, injected draft only": (
        "tests/j4b/fresh/admission.py",
        'return {"flipped": case_flipped(judged.result)}',
        'return {"flipped": admitted(judged.result, INJECTED)}',
    ),
    "truth read from F1": ("tests/j4b/fresh/grading.py", 'TRUTH_FORM, SANITY_FORM = "F0", "F1"',
                           'TRUTH_FORM, SANITY_FORM = "F1", "F0"'),
}  # fmt: skip
PHASES_TEST = "tests/j4b/tests/test_fresh_phases.py"


@pytest.mark.parametrize("name", sorted(FLIP_AND_TRUTH))
def test_h39i_a_motivated_amendment_cannot_redefine_a_flip_or_the_truth_form(
    repo: PlantedRepo, tmp_path: Path, name: str
) -> None:
    """STATS48B-R1-2: each bar's outcome is defined in frozen code (`admission.record`, `grading.TRUTH_FORM`), so
    even an amendment carried by a phases test that fails at dev and passes after is refused, naming the item."""
    path, old, new = FLIP_AND_TRUTH[name]
    original = dev_done(repo, tmp_path, flagged=False)
    assert old in repo.path(path).read_text(encoding="utf-8")
    repo.edit(path, lambda s: s.replace(old, new))
    repo.edit("tests/j4b/fresh/phases.py", lambda s: s + FIXED)
    repo.path(PHASES_TEST).write_text(
        '"""Motivating test."""\n\n\ndef test_fix() -> None:\n    from tests.j4b.fresh import phases\n\n'
        '    assert getattr(phases, "fixed", lambda: False)()\n'
    )
    motivating = {"tests/j4b/fresh/phases.py": f"{PHASES_TEST}::test_fix"}
    refuses(repo, tmp_path, amend(repo, original, motivating), f"frozen item {path}")


def test_h39i_old_commits_are_read_never_imported(repo: PlantedRepo, tmp_path: Path) -> None:
    repo.path("tests/j4b/fresh/boom.py").write_text("raise RuntimeError('imported')\n")
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    assert pins.check(repo.root, tmp_path, amend(repo, original), command="confirm", attempt=1)


# --- (e), (f): the pin history ------------------------------------------------------------------------


def test_h39f_an_amendment_may_not_change_the_library_pins(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.edit("jevson/__init__.py", lambda s: s + "\n# planted\n")
    refuses(repo, tmp_path, amend(repo, original), "an amendment may not change the library pins")


def test_h39f_an_amendment_comes_only_after_a_dev_complete_json(repo: PlantedRepo, tmp_path: Path) -> None:
    repo.commit("dev harness")
    original = repo.appendix()
    repo.record(tmp_path, 1, "dev", original, finish=False)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    refuses(repo, tmp_path, amend(repo, original, {"tests/j4b/fresh/metering.py": node}),
            "an amendment comes only after a dev/complete.json", command="dev")  # fmt: skip


def test_h39e_after_confirm_a_repinned_rules_edit_makes_score_refuse(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.record(tmp_path, 1, "confirm", original)
    repo.edit("tests/j4b/fresh/rules.py", lambda s: s.replace("= 1.2", "= 1.0"))
    repo.commit("edit rules after confirm")
    refuses(repo, tmp_path, amend(repo, original), "score's pins differ from its confirm records", command="score")


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


# --- review round 2 (T48-5): the pins survivors of the round-2 mutmut run ----------------------------------


def test_sha256_of_bytes_and_text() -> None:
    assert pins.sha256(b"\xff") == hashlib.sha256(b"\xff").hexdigest()
    assert pins.sha256("é") == hashlib.sha256("é".encode()).hexdigest()


def test_an_appendix_without_a_pins_block_and_a_non_canonical_row_are_named() -> None:
    with pytest.raises(pins.PinMismatch, match=r"^the appendix has no ```json pins block$"):
        pins.read_appendix("# no block\n")
    with pytest.raises(pins.PinMismatch, match=r"^bytes outside the rows of tests/j4b/fixtures/fresh/x\.jsonl$"):
        pins._rows("x.jsonl", b'{"z": 1, "draft_id": "a"}\n')  # pyright: ignore[reportPrivateUsage]


def test_frozen_items_read_a_missing_picked_file_as_empty_and_refuse_a_missing_summary(repo: PlantedRepo) -> None:
    repo.path(pins.PICKED).unlink()
    data = {name: repo.path(f"{pins.FIXTURES}/{name}").read_bytes() for name in pins.ROW_FILES}
    repo.path(pins.SUMMARY).write_text(build_fresh_sets.summarise(data, b""), encoding="utf-8")
    commit = repo.commit("no picked.json")
    assert pins.frozen_items(repo.root, commit)
    repo.path(pins.SUMMARY).unlink()
    commit = repo.commit("no summary.json")
    with pytest.raises(pins.PinMismatch, match=f"^not the frozen summariser's output: {re.escape(pins.SUMMARY)}$"):
        pins.frozen_items(repo.root, commit)


def test_current_pins_read_head_and_record_the_frozen_hash_and_the_present_harness_paths(
    repo: PlantedRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    commits: list[str] = []
    real_ls, real_show, real_git = overlay.ls_tree, overlay.show_many, overlay.git

    def ls_tree(r: Path, commit: str, *paths: str, recursive: bool = True) -> Any:
        commits.append(commit)
        return real_ls(r, commit, *paths, recursive=recursive)

    def show_many(r: Path, commit: str, paths: Any) -> Any:
        commits.append(commit)
        return real_show(r, commit, paths)

    def git(r: Path, *args: str) -> str:
        if args[0] == "rev-parse":
            commits.append(args[1])
        return real_git(r, *args)

    monkeypatch.setattr(overlay, "ls_tree", ls_tree)
    monkeypatch.setattr(overlay, "show_many", show_many)
    monkeypatch.setattr(overlay, "git", git)
    p, _ = pins.current_pins(repo.root, repo.appendix())
    assert set(commits) == {"HEAD"}
    assert p.frozen_sha256 == pins.sha256(pins.canonical_file(pins.frozen_items(repo.root, "HEAD")))
    hashes = pins.tree_hashes(repo.root, "HEAD")
    assert p.harness == {k: v for k, v in hashes.items() if k != pins.LIBRARY and v is not None}
    assert pins.LIBRARY not in p.harness
    assert None in hashes.values() or len(p.harness) == len(pins.PINNED_PATHS)


def test_records_include_analysis_started(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "analysis-started.json").write_text('{"pins": {"appendix_sha256": "a"}}')
    seen: list[str] = []
    real_exists = Path.exists

    def exists(self: Path) -> bool:  # the name itself, so a case-insensitive file system cannot hide a misspelling
        seen.append(self.name)
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", exists)
    assert pins.records(tmp_path) == [("analysis-started.json", {"pins": {"appendix_sha256": "a"}})]
    assert seen == ["analysis-started.json"]


PINS = pins.Pins("c", "lib", {"tests/j4b/fresh": "h"}, "app", "frozen")
SAME = {"appendix_sha256": "app", "library_tree": "lib", "harness": {"tests/j4b/fresh": "h"}, "harness_commit": "c"}


def test_same_compares_appendix_library_and_harness() -> None:
    same = pins._same  # pyright: ignore[reportPrivateUsage]
    assert same(PINS, {"pins": SAME})
    assert not same(PINS, {})
    for key, value in (("appendix_sha256", "x"), ("library_tree", "x"), ("harness", {"tests/j4b/fresh": "x"})):
        assert not same(PINS, {"pins": {**SAME, key: value}})


def history(found: list[tuple[str, dict[str, Any]]], command: str = "confirm", parent: str | None = "o") -> list[str]:
    return pins.history_problems(PINS, {"parent": parent}, found, command=command, attempt=1)


def rec(sha: str, library: str = "lib") -> dict[str, Any]:
    return {"pins": {**SAME, "appendix_sha256": sha, "library_tree": library}}


def test_history_problems_each_rule_and_its_exact_refusal() -> None:
    own = [("attempt-1/confirm/start.json", rec("app")), ("attempt-1/dev/start.json", rec("o"))]
    assert history(own, "score") == []
    assert history([("attempt-1/dev/start.json", rec("app"))], "score") == [
        "score's pins differ from its confirm records"
    ]
    assert history([("attempt-1/confirm/start.json", rec("app"))]) == []
    assert history([("attempt-1/confirm/start.json", rec("x"))]) == ["pins differ from the first confirm/start.json"]
    two = [("attempt-1/dev/complete.json", rec("o")), ("attempt-2/dev/complete.json", rec("a1"))]
    assert history(two) == ["a second amendment, or one not parented on the original appendix"]
    assert history([("attempt-1/dev/complete.json", rec("o", "other"))]) == [
        "an amendment may not change the library pins"
    ]
    assert history([("attempt-1/dev/start.json", rec("o"))]) == ["an amendment comes only after a dev/complete.json"]
    assert history([("attempt-1/dev/complete.json", rec("o"))]) == []


def test_score_after_confirm_passes_under_the_same_pins(repo: PlantedRepo, tmp_path: Path) -> None:
    appendix = repo.appendix()
    repo.record(tmp_path, 1, "dev", appendix)
    repo.record(tmp_path, 1, "confirm", appendix)
    assert pins.check(repo.root, tmp_path, appendix, command="score", attempt=1)


def test_confirm_rechecked_under_its_amended_pins_passes(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    fix_flagged_claim(repo)
    first = amend(repo, original)
    repo.record(tmp_path, 1, "confirm", first, finish=False)
    assert pins.check(repo.root, tmp_path, first, command="confirm", attempt=1)


def test_an_amendment_that_changes_nothing_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    refuses(repo, tmp_path, amend(repo, original), "nothing changed")


def test_a_fix_that_leaves_the_items_flagged_is_refused_naming_the_first(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path)
    other = " It names the 3 dates."

    def rows(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if row["cell"] == "c001" and row["role"] == "injected":
                row["draft"] = row["draft"].replace(FLAGGED, other)
                row["claim"] = row["claim"].replace(FLAGGED, other)

    repo.authored(ISET, lambda r: r["c001"].update(claim=r["c001"]["claim"].replace(FLAGGED, other)))
    repo.rows("iset.jsonl", rows)
    refuses(repo, tmp_path, amend(repo, original), "still flagged after the fix: iset#c001.claim")


def test_a_module_fix_whose_test_still_fails_after_is_refused(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    repo.edit("tests/j4b/fresh/metering.py", lambda s: s + FIXED)
    repo.path(METERING_TEST).write_text(
        '"""Motivating test."""\n\n\ndef test_the_motivating_fix() -> None:\n    raise AssertionError\n'
    )
    node = f"{METERING_TEST}::test_the_motivating_fix"
    refuses(repo, tmp_path, amend(repo, original, {"tests/j4b/fresh/metering.py": node}),
            f"{node} must fail at dev (exit 1) and pass after (exit 1)")  # fmt: skip


def test_an_appendix_without_motivating_refuses_a_module_fix(repo: PlantedRepo, tmp_path: Path) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    module_fix(repo)
    repo.commit("amendment")
    appendix = repo.appendix(parent=pins.sha256(original)).replace(',\n "motivating": {}', "")
    assert '"motivating"' not in appendix
    refuses(repo, tmp_path, appendix, f"tests/j4b/fresh/metering.py needs a motivating test in {METERING_TEST}")


def test_assert_library_pin_passes_on_the_pinned_tree(repo: PlantedRepo) -> None:
    pins.assert_library_pin(repo.root, repo.appendix())


# --- STATS48-B10-3: the request-shaping knobs inside amendable modules are frozen items -----------------------

OPENAI_CHAT, CHAT_TEST, PHASES = (
    "tests/integration/openai_chat.py",
    "tests/j4b/tests/test_fresh_openai_chat.py",
    ("tests/j4b/fresh/phases.py"),
)
REQUEST_KNOBS = {
    "the drafting model id": (OPENAI_CHAT, 'MODEL = "gpt-5.4-mini-2026-03-17"', 'MODEL = "gpt-5.5-other-model"',
                              "MODEL"),
    "the drafting reasoning effort": (OPENAI_CHAT, 'reasoning_effort: str = "none"', 'reasoning_effort: str = "high"',
                                      "OpenAIChatLLM.__init__"),
    "the drafting retries": (OPENAI_CHAT, "retries: int = 4", "retries: int = 6", "OpenAIChatLLM.__init__"),
    "the drafting timeout": (OPENAI_CHAT, "timeout_s: float = 120", "timeout_s: float = 300", "OpenAIChatLLM.__init__"),
    "the backoff ladder": (OPENAI_CHAT, "2**attempt", "3**attempt", "backoff_s"),
    "the D17 cut-at-the-cap rule": (OPENAI_CHAT, 'choice.get("finish_reason") == "length"',
                                    'choice.get("finish_reason") == "truncated"', "OpenAIChatLLM.parse"),
    "the request body": (OPENAI_CHAT, '"reasoning_effort": self._effort,', '"reasoning_effort": "high",',
                         "OpenAIChatLLM.body"),
    "a call-site override of the drafting client": (
        PHASES, "OpenAIChatLLM(key, max_completion_tokens", 'OpenAIChatLLM(key, reasoning_effort="high", '
        "max_completion_tokens", "clients/OpenAIChatLLM()#0"),
    "a call-site override of the decision client": (
        PHASES, "DecisionsBackend(api_key=key,", 'DecisionsBackend(api_key=key, model="gpt-other",',
        "clients/DecisionsBackend()#0"),
    "the per-endpoint model strings (D6)": (PHASES, "s.status == 200 and s.model is not None",
                                            "s.status in (200, 203) and s.model is not None",
                                            "model_strings"),
    # STATS48-B10-3 round 2 (exp/b48b/rev-stats/r2/probe.out, probe2.out): both were accepted before.
    "a request rewrite after body() (round-2 probe 1)": (
        OPENAI_CHAT, "body = self.body(messages, tool_schema)",
        'body = self.body(messages, tool_schema)\n        body["reasoning_effort"] = "high"', "OpenAIChatLLM.complete"),
    "every unit judged under L0 (round-2 probe 2)": (PHASES, "config = arms.LIBRARY_ARMS[unit.arm]",
                                                    'config = arms.LIBRARY_ARMS["L0"]', "run_unit"),
    "every field drafted under L0's screen and template": (PHASES, "options = arms.LIBRARY_ARMS[config[0]]",
                                                           'options = arms.LIBRARY_ARMS["L0"]', "draftings"),
    "first drafts built under another configuration": (PHASES, "for d in draftings(fields)]",
                                                       'for d in draftings(fields, ("L1", "F0"))]',
                                                       "first_draft_requests"),
    "the recorded first-draft keys": (PHASES, "replay_key(MODEL, m, TOOL_SCHEMA)", "replay_key(MODEL, m, None)",
                                      "first_keys"),
    "the first-draft gate": (PHASES, "if len(messages) == 3 and", "if len(messages) >= 3 and", "FirstDraftGate"),
    "the redraft prompts the gate passes": (PHASES, "malformed(drafting.max_draft_chars)", "malformed(0)",
                                            "redraft_prompts"),
    "the failing-check subsets": (PHASES, "for mask in range(1, 2 ** len(items))",
                                  "for mask in range(0, 2 ** len(items))", "_subsets"),
    "which drafting units run": (PHASES, "requests = {d: first_draft_requests(",
                                 "requests = {d: [] if d.endswith('7') else first_draft_requests(", "drafting_phase"),
    "which configuration units are kept": (PHASES, "outcomes.update(zip(batch, done, strict=True))",
                                           "outcomes.update(zip(batch[1:], done[1:], strict=True))",
                                           "configuration_phase"),
}  # fmt: skip


@pytest.mark.parametrize("name", sorted(REQUEST_KNOBS))
def test_stats48_b10_3_a_motivated_amendment_cannot_move_a_request_knob(
    repo: PlantedRepo, tmp_path: Path, name: str
) -> None:
    """Even with a planted motivating test that fails at dev and passes after, the amendment is refused, naming the
    frozen item: the model id, the effort, the retry ladder, the D17 parse rule, the request body, a call-site
    override and D6's model-string collection are frozen, though their modules are amendable."""
    path, old, new, item = REQUEST_KNOBS[name]
    original = dev_done(repo, tmp_path, flagged=False)
    assert repo.path(path).read_text(encoding="utf-8").count(old) == 1
    repo.edit(path, lambda s: s.replace(old, new))
    test_file = pins.AMENDABLE[path]
    module = path.removesuffix(".py").replace("/", ".")
    repo.path(test_file).write_text(
        f'"""Motivating test."""\n\nimport inspect\n\nimport {module} as m\n\n\n'
        f"def test_fix() -> None:\n    assert {new!r} in inspect.getsource(m)\n"
    )
    refuses(repo, tmp_path, amend(repo, original, {path: f"{test_file}::test_fix"}), f"frozen item {path}::{item}")


def test_stats48_b10_3_every_named_frozen_function_and_call_exists_at_head() -> None:
    items = pins.frozen_items(ROOT, "HEAD")
    for path, names in pins.FROZEN_FUNCTIONS.items():
        for name in names:
            assert items[f"{path}::{name}"]["kind"] == "frozen", (path, name)
    for _, _, _, item in REQUEST_KNOBS.values():
        assert any(key.endswith(f"::{item}") for key in items), item


# --- STATS48-B10-7: an amendment changes only the appendix's pins block (and may add an amendment record) -------


def test_stats48_b10_7_an_amendment_that_rewrites_the_appendix_body_is_refused(
    repo: PlantedRepo, tmp_path: Path
) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    amended = amend(repo, original, {"tests/j4b/fresh/metering.py": node})
    rewritten = amended.replace("# Pre-registration (planted)", "# Pre-registration (planted): NI multiplier 1.0")
    refuses(repo, tmp_path, rewritten, "the amended appendix changes text outside its pins block")
    recorded = amended + "\n## Amendment record\n\nThe metering fix of design §2.6.\n"
    assert pins.check(repo.root, tmp_path, recorded, command="confirm", attempt=1)


QUOTED_RULE = "\nIt may add one `## Amendment record` section appended at its end.\n"
"""Appendix C of the committed pre-registration quotes the marker inline, as this sentence does (RC2-1)."""


def test_rc2_1_an_original_appendix_that_quotes_the_marker_inline_still_allows_the_amendment(
    repo: PlantedRepo, tmp_path: Path
) -> None:
    """The marker is a heading line, not a substring: the committed appendix quotes it inside a sentence, which made
    every amendment, a correct one included, fail (exp/b48b/rev-correct/r2/planted.out case 7)."""
    repo.commit("dev harness")
    original = repo.appendix() + QUOTED_RULE
    repo.path(pins.APPENDIX).parent.mkdir(parents=True, exist_ok=True)
    repo.path(pins.APPENDIX).write_text(original, encoding="utf-8")
    repo.commit("pre-registration")
    repo.record(tmp_path, 1, "dev", original)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    amended = amend(repo, original, {"tests/j4b/fresh/metering.py": node}) + QUOTED_RULE
    recorded = amended + "\n## Amendment record\n\nThe metering fix of design §2.6.\n"
    assert pins.check(repo.root, tmp_path, recorded, command="confirm", attempt=1)
    refuses(repo, tmp_path, amended + "\nIt adds a `## Amendment record` inline.\n",
            "the amended appendix changes text outside its pins block")  # fmt: skip


def test_rc2_1_the_committed_appendix_accepts_one_appended_amendment_record() -> None:
    """On the real committed pre-registration: an amendment that changes only its pins block and appends one record
    passes `appendix_problems`; a second record heading inside the original would not."""
    commit = overlay.git(ROOT, "log", "-1", "--format=%H", "--", pins.APPENDIX).strip()
    committed = overlay.show(ROOT, commit, pins.APPENDIX).decode("utf-8")
    original = {"harness_commit": commit, "appendix_sha256": pins.sha256(committed)}
    block = pins.read_appendix(committed)
    repinned = pins.PINS_BLOCK.sub(
        lambda _: "```json pins\n" + json.dumps({**block, "parent": pins.sha256(committed)}, indent=1) + "\n```",
        committed,
    )
    assert repinned != committed
    assert pins.appendix_problems(ROOT, original, repinned + "\n## Amendment record\n\nA fix.\n") == []
    assert pins.appendix_problems(ROOT, original, repinned + "\nA sentence.\n") == [
        "the amended appendix changes text outside its pins block"
    ]


def test_stats48_b10_7_the_original_appendix_must_be_committed_at_the_dev_commit(
    repo: PlantedRepo, tmp_path: Path
) -> None:
    repo.commit("dev harness")
    original = repo.appendix()
    repo.record(tmp_path, 1, "dev", original)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    refuses(repo, tmp_path, amend(repo, original, {"tests/j4b/fresh/metering.py": node}),
            f"the appendix dev ran under is not committed at its harness_commit: {pins.APPENDIX}")  # fmt: skip


# --- STATS48-B10-8: each phase record names the interpreter and the locked dependencies it ran on -----------------


def test_stats48_b10_8_every_phase_record_carries_the_interpreter_and_the_lock_file(
    repo: PlantedRepo, tmp_path: Path
) -> None:
    p = repo.record(tmp_path, 1, "dev", repo.appendix(), finish=False)
    environment = {"python": sys.version, "uv_lock": repo.git("rev-parse", "HEAD:uv.lock")}
    assert p.record()["environment"] == environment
    assert '"uv_lock": "' + environment["uv_lock"] in (tmp_path / "attempt-1" / "dev" / "start.json").read_text()


def test_python_items_key_each_kind_of_frozen_item() -> None:
    source = (
        b"A = 1\nB: int = 2\nC: int\nD, E = 3, 4\nOpenAIChatLLM()\n"
        b"def f(x=1, *, y=None, z): OpenAIChatLLM(model='m'); OpenAIChatLLM()\n"
        b"def g(*, z, w=3): pass\ndef h(a, *, b): pass\n"
        b"class K:\n    c = DecisionsBackend()\n    def m(self, a=0): DecisionsBackend(); other()\n"
        b"def model_strings(): pass\n"
    )
    items = pins.python_items("tests/j4b/fresh/phases.py", source)
    assert sorted(k.removeprefix("tests/j4b/fresh/phases.py::") for k in items) == [
        "<body>/OpenAIChatLLM()#0", "A", "B", "K.<body>/DecisionsBackend()#0", "K.m defaults",
        "K.m/DecisionsBackend()#0", "f defaults", "f/OpenAIChatLLM()#0", "f/OpenAIChatLLM()#1", "g defaults",
        "model_strings",
    ]  # fmt: skip
    assert {i["kind"] for i in items.values()} == {"frozen"}
    changed = pins.python_items("tests/j4b/fresh/phases.py", source.replace(b"model='m'", b"model='n'"))
    assert [k for k in items if items[k] != changed[k]] == ["tests/j4b/fresh/phases.py::f/OpenAIChatLLM()#0"]
    assert pins.python_items("x.py", b"def model_strings(): pass\n") == {}


def test_python_items_freeze_a_named_class_whole() -> None:
    """A class named in `FROZEN_FUNCTIONS` (the first-draft gate) is one item over its whole source, so a change to
    any of its methods moves that item (STATS48-B10-3 round 2)."""
    source = b"class FirstDraftGate:\n    def m(self, a=0):\n        return a == 3\n\nclass Other:\n    pass\n"
    items = pins.python_items(PHASES, source)
    assert sorted(items) == [f"{PHASES}::FirstDraftGate"]
    assert items[f"{PHASES}::FirstDraftGate"]["value"] == pins.sha256(
        "class FirstDraftGate:\n    def m(self, a=0):\n        return a == 3"
    )
    changed = pins.python_items(PHASES, source.replace(b"a == 3", b"a >= 3"))
    assert changed[f"{PHASES}::FirstDraftGate"] != items[f"{PHASES}::FirstDraftGate"]


def test_python_items_hash_the_source_text_so_every_interpreter_agrees() -> None:
    """`ast.dump` changed in Python 3.13 (empty fields omitted), so a map built on 3.14 differed from one built on
    3.11 or 3.12 (exp/b48b/r1fix/frozen-by-version-before.out); the items hash each node's exact source text."""
    source = b"A = (1,  2)\ndef f(x=1, *, y=None):\n    OpenAIChatLLM(model='m')  # pinned\n"
    items = pins.python_items("p.py", source)
    assert items["p.py::A"]["value"] == pins.sha256("(1,  2)")
    assert items["p.py::f defaults"]["value"] == pins.sha256("1\x00None")
    assert items["p.py::f/OpenAIChatLLM()#0"]["value"] == pins.sha256("OpenAIChatLLM(model='m')")
    named = pins.python_items("tests/j4b/fresh/phases.py", b"def model_strings():\n    return 1\n")
    assert named["tests/j4b/fresh/phases.py::model_strings"]["value"] == pins.sha256(
        "def model_strings():\n    return 1"
    )


def test_stats48_b10_7_dev_under_an_uncommitted_appendix_or_a_second_record_is_refused(
    repo: PlantedRepo, tmp_path: Path
) -> None:
    original = dev_done(repo, tmp_path, flagged=False)
    module_fix(repo)
    node = f"{METERING_TEST}::test_the_motivating_fix"
    amended = amend(repo, original, {"tests/j4b/fresh/metering.py": node})
    trailing = amended + "\nA sentence that is not an amendment record.\n"
    refuses(repo, tmp_path, trailing, "the amended appendix changes text outside its pins block")
    original_commit = pins.records(tmp_path)[0][1]["pins"]["harness_commit"]
    recorded = {"harness_commit": original_commit, "appendix_sha256": pins.sha256(original)}
    assert pins.appendix_problems(repo.root, recorded, amended) == []
    assert pins.appendix_problems(repo.root, {**recorded, "appendix_sha256": "x"}, amended) == [
        f"the appendix dev ran under is not committed at its harness_commit: {pins.APPENDIX}"
    ]
    repo.path(pins.APPENDIX).write_text(original + "\n## Amendment record\n", encoding="utf-8")
    with_record = repo.commit("an original carrying a record")
    again = {"harness_commit": with_record, "appendix_sha256": pins.sha256(original + "\n## Amendment record\n")}
    assert pins.appendix_problems(repo.root, again, amended + "\n## Amendment record\n") == [
        "the amended appendix changes text outside its pins block"
    ]
