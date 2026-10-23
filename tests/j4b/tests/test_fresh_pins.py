"""H39: run-time pins in a hermetic repository (plan §2 rules (a)-(d); ARCH48-R6-1 ... STATS48-R13-1).

Each case starts from the planted harness on a branch of its own and names the item `pins.check` must refuse.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.j4b.fresh import build_fresh_sets, overlay, pins
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
    repo.edit("tests/j4b/fresh/phases.py", lambda s: s + "\nFIXED = True\n")
    repo.path(PHASES_TEST).write_text(
        '"""Motivating test."""\n\n\ndef test_fix() -> None:\n    from tests.j4b.fresh import phases\n\n'
        '    assert getattr(phases, "FIXED", False)\n'
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
    repo.edit("tests/j4b/fresh/metering.py", lambda s: s + "\nFIXED = True\n")
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
