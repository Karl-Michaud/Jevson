"""Run-time pins of the pre-registration (plan §2 "The code that runs is the code that was pinned", rule (d);
plan §4.1 `pins.py`; ARCH48-R6-1, ARCH48-R7-1, STATS48-R7-1, STATS48-R10-1 ... STATS48-R13-1, FEAS48-R12/R13).

`check` makes `dev`, `confirm` and `score` refuse unless (a) nothing under `jevson/` or a pinned harness path is
dirty, (b) `HEAD`'s tree hashes equal the appendix in force, and (c) the run directory's own records allow these
pins: at most one amendment, parented on the original appendix, first seen after a `dev/complete.json` and before
any `confirm/start.json`, and (d) changing only what design §2.6 lets one fix change. The frozen-item map has one
item per tracked file under each pinned path, except: the `AMENDABLE` modules; the three authored JSON files, one
item per attribute of every record (only `FIXTURE_STRING_ATTRS` outside the replica cell are fixture strings); the
six row files, one item per row; and `summary.json`, which must equal its summariser's output. Inside each
amendable module, its module-level constants, parameter defaults, request-client calls and `FROZEN_FUNCTIONS` are
frozen items of their own (STATS48-B10-3). An amendment may change the appendix only in its pins block, plus an
appended amendment record, and dev's appendix must be committed at dev's `harness_commit` (STATS48-B10-7). Old
commits are read with `git show` and `ast.parse`, never imported.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tests.j4b.fresh import leakage, overlay, truth
from tests.j4b.fresh.build_fresh_sets import STRING_SETS, WORDING, summarise
from tests.j4b.fresh.canonical import canonical_file, canonical_row

__all__ = ["canonical_file", "canonical_row"]  # pins.canonical_file is the plan's name for the accepted form

LIBRARY = "jevson"
PINNED_PATHS = (
    "tests/__init__.py",
    "tests/j4b/__init__.py",
    "tests/j4b/fresh",
    "tests/j4b/fixtures",
    "tests/j4b/labelling/__init__.py",
    "tests/j4b/labelling/intervals.py",
    "tests/j4b/labelling/prepare_items.py",
    "tests/j4b/labelling/records.py",
    "tests/j4b/injection.py",
    "tests/j4b/build_injection_fixture.py",
    "tests/j4b/live.py",
    "tests/j4b/redraft.py",
    "tests/phase0/datasets/corpus",
    "tests/integration/__init__.py",
    "tests/integration/run_fresh.py",
    "tests/integration/openai_chat.py",
    "tests/integration/key.py",
)
"""The harness's whole `tests.*` import closure and every repository file it reads at run time (H40)."""
FRESH = "tests/j4b/fresh"
AMENDABLE = {
    **{f"{FRESH}/{m}.py": f"tests/j4b/tests/test_fresh_{m}.py" for m in ("inflight", "metering", "spend", "gates",
                                                                           "requeue", "phases")},
    f"{FRESH}/export_items.py": "tests/j4b/tests/test_fresh_export_items.py",
    "tests/j4b/labelling/prepare_items.py": "tests/j4b/tests/test_fresh_export_items.py",
    "tests/j4b/labelling/records.py": "tests/j4b/tests/test_fresh_export_items.py",
    "tests/integration/openai_chat.py": "tests/j4b/tests/test_fresh_openai_chat.py",
    "tests/integration/key.py": "tests/j4b/tests/test_fresh_openai_chat.py",
}  # fmt: skip
"""The request, recording, replay and item-export modules, each with the one test module that may motivate a fix
to it (design §2.6); every other pinned file is frozen."""
FROZEN_FUNCTIONS = {
    "tests/integration/openai_chat.py": ("OpenAIChatLLM.__init__", "OpenAIChatLLM.body", "OpenAIChatLLM.parse",
                                         "_encodable", "backoff_s"),
    f"{FRESH}/phases.py": ("model_strings",),
}  # fmt: skip
"""Functions of amendable modules that set outcomes, each a frozen item `<path>::<qualname>` (STATS48-B10-3): the
drafting client's settings, request body, retry ladder and D17 parse rule, and D6's model-string collection."""
REQUEST_CLIENTS = frozenset({"OpenAIChatLLM", "DecisionsBackend"})
"""Every call of these in an amendable module is a frozen item `<path>::<enclosing>/<client>()#<n>`, so a call
site cannot pass another model, effort or retry setting (STATS48-B10-3)."""
JEVSON_INTERNALS = frozenset({
    ("jevson.execute.drafting", "messages"), ("jevson.execute.drafting", "TOOL_SCHEMA"),
    ("jevson.execute.drafting", "malformed"), ("jevson.execute.drafting", "read"),
    ("jevson.compile.questions", "redraft_prompt"),
    ("jevson.types", "StepNode"), ("jevson.types", "Drafting"), ("jevson.types", "JSONValue"),
    ("jevson.adjudicate.criteria", "PASS_HUNDREDTHS"),
})  # fmt: skip
"""Plan §11 D18: the closed list of internal names the harness may import besides public Jevson,
`jevson.llm.replay` and `jevson.backends.caching`. Adding one is a pre-registration change."""
FIXTURE_STRING_ATTRS = frozenset({"claim", "companion", "self_claim"})
AUTHORED = {f"{FRESH}/iset_wordings.json": "iset", f"{FRESH}/pset_templates.json": "pset",
            f"{FRESH}/rset_fields.json": "rset"}  # fmt: skip
FIXTURES = "tests/j4b/fixtures/fresh"
ROW_FILES = ("iset.jsonl", "iset_dev.jsonl", "pset.jsonl", "pset_dev.jsonl", "rset.jsonl", "rset_dev.jsonl")
SUMMARY, PICKED = f"{FIXTURES}/summary.json", f"{FRESH}/picked.json"
APPENDIX = "docs/preregistration/ASTERION-48-58.md"
PINS_BLOCK = re.compile(r"```json pins\n(.*?)\n```", re.DOTALL)
AMENDMENT_RECORD = "## Amendment record"
"""The one section an amendment may append to the appendix, after its last byte (STATS48-B10-7)."""
LOCK_FILE = "uv.lock"


class PinMismatch(Exception):
    """The code or the records do not match the pre-registration; the command refuses, naming why."""


@dataclass(frozen=True)
class Pins:
    harness_commit: str
    library_tree: str
    harness: Mapping[str, str]
    appendix_sha256: str
    frozen_sha256: str
    environment: Mapping[str, str | None] = field(default_factory=dict[str, "str | None"])
    """The interpreter and the locked dependencies the phase ran on, recorded, not enforced (STATS48-B10-8)."""

    def record(self) -> dict[str, Any]:
        return asdict(self)


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def tree_hashes(repo: Path, commit: str) -> dict[str, str | None]:
    found = dict(overlay.ls_tree(repo, commit, LIBRARY, *PINNED_PATHS, recursive=False))
    return {path: found.get(path) for path in (LIBRARY, *PINNED_PATHS)}


def read_appendix(text: str) -> dict[str, Any]:
    """The machine-readable pins of an appendix: its fenced ```json pins block."""
    match = PINS_BLOCK.search(text)
    if match is None:
        raise PinMismatch("the appendix has no ```json pins block")
    return json.loads(match.group(1))


def _authored(set_name: str, text: str, path: str) -> dict[str, dict[str, str]]:
    try:
        records = json.loads(text)
    except ValueError:
        raise PinMismatch(f"non-canonical {path}") from None
    if text != canonical_file(records):
        raise PinMismatch(f"non-canonical {path}")
    items: dict[str, dict[str, str]] = {}
    for record_id, record in records.items():
        for attribute, value in record.items():
            fixture = attribute in FIXTURE_STRING_ATTRS and record_id != "replica"
            items[f"{set_name}#{record_id}.{attribute}"] = {"kind": "string" if fixture else "frozen",
                                                             "value": sha256(canonical_row(value))}  # fmt: skip
    return items


def _rows(name: str, data: bytes) -> dict[str, dict[str, str]]:
    try:
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    except ValueError:
        raise PinMismatch(f"bytes outside the rows of {FIXTURES}/{name}") from None
    if data.decode("utf-8") != "".join(canonical_row(r) for r in rows):
        raise PinMismatch(f"bytes outside the rows of {FIXTURES}/{name}")
    return {f"{name}#{r['draft_id']}": {"kind": "row", "value": sha256(canonical_row(r))} for r in rows}


def _frozen(node: ast.AST | list[ast.expr | None]) -> dict[str, str]:
    dumped = ast.dump(node) if isinstance(node, ast.AST) else "|".join(ast.dump(n) if n else "" for n in node)
    return {"kind": "frozen", "value": sha256(dumped)}


def _calls(items: dict[str, dict[str, str]], path: str, enclosing: str, node: ast.AST) -> None:
    for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
        callee = call.func.id if isinstance(call.func, ast.Name) else getattr(call.func, "attr", "")
        if callee in REQUEST_CLIENTS:
            key = f"{path}::{enclosing}/{callee}()#"
            items[f"{key}{sum(k.startswith(key) for k in items)}"] = _frozen(call)


def python_items(path: str, source: bytes) -> dict[str, dict[str, str]]:
    """The frozen items inside an amendable module (STATS48-B10-3): module-level constants, parameter defaults,
    request-client calls and the `FROZEN_FUNCTIONS`, each keyed `<path>::<name>`."""
    tree = ast.parse(source)
    items: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
                if isinstance(target, ast.Name):
                    items[f"{path}::{target.id}"] = _frozen(node.value)
    pending: list[tuple[str, ast.stmt]] = [("", n) for n in tree.body]
    while pending:
        prefix, node = pending.pop()
        if isinstance(node, ast.ClassDef):
            pending += [(f"{prefix}{node.name}.", n) for n in node.body]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            name = prefix + node.name
            if name in FROZEN_FUNCTIONS.get(path, ()):
                items[f"{path}::{name}"] = _frozen(node)
            elif node.args.defaults or any(node.args.kw_defaults):
                items[f"{path}::{name} defaults"] = _frozen([*node.args.defaults, *node.args.kw_defaults])
            _calls(items, path, name, node)
        else:
            _calls(items, path, f"{prefix}<body>", node)
    return items


def frozen_items(repo: Path, commit: str) -> dict[str, dict[str, str]]:
    """The frozen-item map at `commit` (plan §2 rule (d))."""
    items: dict[str, dict[str, str]] = {}
    rows = [f"{FIXTURES}/{n}" for n in ROW_FILES]
    files = overlay.show_many(repo, commit, [*AUTHORED, *rows, SUMMARY, PICKED, *AMENDABLE])
    for name, blob in overlay.ls_tree(repo, commit, *PINNED_PATHS):
        if name in AMENDABLE:
            items[name] = {"kind": "amendable", "value": blob}
            items |= python_items(name, files[name])
        elif name in AUTHORED:
            items |= _authored(AUTHORED[name], files[name].decode("utf-8"), name)
        elif name in rows:
            items |= _rows(name.removeprefix(FIXTURES + "/"), files[name])
        elif name != SUMMARY:
            items[name] = {"kind": "frozen", "value": blob}
    row_bytes = {name.removeprefix(FIXTURES + "/"): files[name] for name in rows if name in files}
    if files.get(SUMMARY, b"").decode("utf-8") != summarise(row_bytes, files.get(PICKED, b"")):
        raise PinMismatch(f"not the frozen summariser's output: {SUMMARY}")
    return items


def flags_at(repo: Path, commit: str) -> set[str]:
    """The items the frozen checker and leakage code flag over `commit`'s rows and authored strings."""
    files = overlay.show_many(repo, commit, [*AUTHORED, *(f"{FIXTURES}/{n}" for n in ROW_FILES)])
    rows = {n: [json.loads(line) for line in files[f"{FIXTURES}/{n}"].decode().splitlines()] for n in ROW_FILES}
    strings: dict[str, str] = {}
    for path, set_name in AUTHORED.items():
        records = json.loads(files[path])
        for record_id, record in records.items():
            for attribute in WORDING.get(STRING_SETS[path.rsplit("/", 1)[1]], ()):
                if attribute in record:
                    strings[f"{set_name}#{record_id}.{attribute}"] = str(record[attribute])
    return truth.flag_items(rows, strings) | leakage.flag_items(rows, strings)


def amendment_problems(  # noqa: PLR0911 - one return per refusal, in the order the rules apply
    repo: Path, original: str, amended: str, motivating: Mapping[str, str]
) -> list[str]:
    """Why an amendment from `original` to `amended` is not the one fix design §2.6 allows ([] if it is).
    `motivating` maps each changed AMENDABLE module to the node id of its motivating test."""
    before, after = frozen_items(repo, original), frozen_items(repo, amended)
    if set(before) != set(after):
        return [f"keys differ: {sorted(set(before) ^ set(after))}"]
    changed = sorted(k for k in before if before[k]["value"] != after[k]["value"])
    if frozen := [k for k in changed if before[k]["kind"] == "frozen"]:
        return [f"frozen item {frozen[0]}"]
    fixtures = {k for k in changed if before[k]["kind"] in ("string", "row")}
    modules = [k for k in changed if before[k]["kind"] == "amendable"]
    if fixtures and modules:
        return ["a module fix and a fixture fix together"]
    if fixtures:
        flagged = flags_at(repo, original)
        if not flagged:
            return ["the frozen checker and leakage code flag nothing at dev: no fixture amendment"]
        if extra := sorted(fixtures - flagged):
            return [f"changed item not flagged: {extra[0]}"]
        if missing := sorted(flagged - fixtures):
            return [f"flagged item not fixed: {missing[0]}"]
        if still := sorted(flags_at(repo, amended)):
            return [f"still flagged after the fix: {still[0]}"]
    for module in modules:
        problem = _motivated(repo, original, amended, module, motivating.get(module))
        if problem:
            return [problem]
    return [] if changed else ["nothing changed"]


def _motivated(repo: Path, original: str, amended: str, module: str, node: str | None) -> str | None:
    """A module fix needs a test in its mapped test file that fails at dev (overlaid) and passes after."""
    test_file = AMENDABLE[module]
    if node is None or node.split("::")[0] != test_file:
        return f"{module} needs a motivating test in {test_file}"
    before = overlay.run_node(repo, original, node, {test_file: overlay.show(repo, amended, test_file)})
    after = overlay.run_node(repo, amended, node, {})
    if before.exit_code != 1 or before.collected != (node,) or after.exit_code != 0:
        return f"{node} must fail at dev (exit {before.exit_code}) and pass after (exit {after.exit_code})"
    return None


def current_pins(repo: Path, appendix_text: str) -> tuple[Pins, dict[str, Any]]:
    """(a) and (b): a clean tree whose hashes equal the appendix's; the pins for every phase record."""
    if dirty := overlay.dirty(repo, [LIBRARY, *PINNED_PATHS]):
        raise PinMismatch(f"uncommitted change under a pinned path: {dirty[0]}")
    appendix = read_appendix(appendix_text)
    hashes = tree_hashes(repo, "HEAD")
    if hashes[LIBRARY] != appendix["library"]["jevson_tree"]:
        raise PinMismatch(f"{LIBRARY} differs from the pinned library tree")
    for path in PINNED_PATHS:
        if hashes[path] != appendix["harness"].get(path):
            raise PinMismatch(f"{path} differs from its pin")
    frozen = sha256(canonical_file(frozen_items(repo, "HEAD")))
    head = overlay.git(repo, "rev-parse", "HEAD").strip()
    harness = {p: h for p, h in hashes.items() if p != LIBRARY and h is not None}
    environment = {"python": sys.version, "uv_lock": overlay.rev_parse(repo, f"HEAD:{LOCK_FILE}")}
    return Pins(head, str(hashes[LIBRARY]), harness, sha256(appendix_text), frozen, environment), appendix


def records(root: Path) -> list[tuple[str, dict[str, Any]]]:
    """Every phase record under the run root that carries pins, by relative path."""
    found = [*root.glob("attempt-*/*/start.json"), *root.glob("attempt-*/*/complete.json")]
    found += [root / "analysis-started.json"] if (root / "analysis-started.json").exists() else []
    return [(str(p.relative_to(root)), json.loads(p.read_text())) for p in sorted(found)]


def _same(pins: Pins, record: Mapping[str, Any]) -> bool:
    return record.get("pins", {}).get("appendix_sha256") == pins.appendix_sha256 and record["pins"].get(
        "library_tree") == pins.library_tree and record["pins"].get("harness") == dict(pins.harness)  # fmt: skip


def history_problems(  # noqa: PLR0911 - one return per refusal, in the order the rules apply
    pins: Pins, appendix: Mapping[str, Any], found: Sequence[tuple[str, dict[str, Any]]], *, command: str, attempt: int
) -> list[str]:
    """(c): the pin history the run directory's records allow (STATS48-R7-1)."""
    pinned = [(path, r) for path, r in found if "pins" in r]
    if not pinned:
        return []
    original = pinned[0][1]["pins"]
    shas = {r["pins"]["appendix_sha256"] for _, r in pinned}
    confirm_starts = [(p, r) for p, r in pinned if p.endswith("confirm/start.json")]
    if command == "score":
        own = [r for p, r in pinned if p.startswith(f"attempt-{attempt}/confirm/")]
        return [] if own and all(_same(pins, r) for r in own) else ["score's pins differ from its confirm records"]
    if confirm_starts:
        return [] if _same(pins, confirm_starts[0][1]) else ["pins differ from the first confirm/start.json"]
    if pins.appendix_sha256 == original["appendix_sha256"]:
        return []
    if len(shas | {pins.appendix_sha256}) > 2 or appendix.get("parent") != original["appendix_sha256"]:
        return ["a second amendment, or one not parented on the original appendix"]
    if pins.library_tree != original["library_tree"]:
        return ["an amendment may not change the library pins"]
    if not any(p.endswith("dev/complete.json") for p, _ in pinned):
        return ["an amendment comes only after a dev/complete.json"]
    return []


def check(repo: Path, root: Path, appendix_text: str, *, command: str, attempt: int) -> Pins:
    """(a)-(d), or `PinMismatch` naming the first problem; `dev`, `confirm` and `score` call it first."""
    pins, appendix = current_pins(repo, appendix_text)
    found = records(root)
    if problems := history_problems(pins, appendix, found, command=command, attempt=attempt):
        raise PinMismatch(problems[0])
    pinned = [r for _, r in found if "pins" in r]
    if pinned and pins.appendix_sha256 != pinned[0]["pins"]["appendix_sha256"] and command != "score":
        original = pinned[0]["pins"]
        problems = appendix_problems(repo, original, appendix_text) or amendment_problems(
            repo, original["harness_commit"], pins.harness_commit, appendix.get("motivating", {}))  # fmt: skip
        if problems:
            raise PinMismatch(problems[0])
    return pins


def _body(text: str) -> str:
    return PINS_BLOCK.sub("```json pins\n```", text)


def appendix_problems(repo: Path, original: Mapping[str, Any], amended_text: str) -> list[str]:
    """STATS48-B10-7: the appendix dev ran under is committed at dev's `harness_commit`, and the amendment equals
    it outside the pins block, except for one `AMENDMENT_RECORD` section appended at its end."""
    committed = overlay.show_many(repo, original["harness_commit"], [APPENDIX]).get(APPENDIX)
    if committed is None or sha256(committed) != original["appendix_sha256"]:
        return [f"the appendix dev ran under is not committed at its harness_commit: {APPENDIX}"]
    before, after = _body(committed.decode("utf-8")), _body(amended_text)
    extra = after.removeprefix(before) if after.startswith(before) else None
    if extra is None or (extra and not extra.lstrip("\n").startswith(AMENDMENT_RECORD)) or AMENDMENT_RECORD in before:
        return ["the amended appendix changes text outside its pins block"]
    return []


def assert_library_pin(repo: Path, appendix_text: str) -> None:
    """Before the pre-registration commit: `HEAD:jevson` equals the appendix's library tree (ARCH48-R7-1)."""
    if overlay.rev_parse(repo, f"HEAD:{LIBRARY}") != read_appendix(appendix_text)["library"]["jevson_tree"]:
        raise PinMismatch(f"HEAD:{LIBRARY} is not the pinned library tree")
