"""H40: the pinned paths cover everything the harness imports, and every `jevson` import is public, from the
two replay modules, or on plan §11 D18's closed allowlist (STATS48-R7-1, STATS48-R8-1, ARCH48-R9-1)."""

from __future__ import annotations

import ast
from pathlib import Path

import jevson
from tests.j4b.fresh import pins

ROOT = Path(__file__).resolve().parents[3]
ENTRY = sorted((ROOT / pins.FRESH).glob("*.py")) + [p for p in [ROOT / "tests/integration/run_fresh.py"] if p.exists()]


def resolve(module: str, name: str | None) -> list[Path]:
    """The files `from module import name` (or `import module`) loads, with every package `__init__.py` on the
    way: `from pkg import name` resolves to `pkg/name.py` when that file exists."""
    parts = module.split(".")
    files = [ROOT.joinpath(*parts[:i], "__init__.py") for i in range(1, len(parts) + 1)]
    target = ROOT.joinpath(*parts)
    if name and (target / f"{name}.py").exists():
        files.append(target / f"{name}.py")
    elif target.with_suffix(".py").exists():
        files.append(target.with_suffix(".py"))
    return [f for f in files if f.exists()]


def imported_files(path: Path) -> list[Path]:
    found: list[Path] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "tests":
            for alias in node.names:
                found += resolve(node.module, alias.name)
        elif isinstance(node, ast.Import):
            found += [f for a in node.names if a.name.startswith("tests.") for f in resolve(a.name, None)]
    return found


def closure() -> set[Path]:
    seen: set[Path] = set()
    todo = list(ENTRY)
    while todo:
        path = todo.pop()
        if path in seen:
            continue
        seen.add(path)
        todo += imported_files(path)
    return seen


def pinned(path: Path) -> bool:
    relative = path.relative_to(ROOT).as_posix()
    return any(relative == p or relative.startswith(p + "/") for p in pins.PINNED_PATHS)


def test_h40i_the_import_closure_is_under_the_pinned_paths() -> None:
    files = closure()
    assert ROOT / "tests/j4b/redraft.py" in files
    assert ROOT / "tests/j4b/labelling/intervals.py" in files
    assert ROOT / "tests/__init__.py" in files
    assert [f.relative_to(ROOT).as_posix() for f in sorted(files) if not pinned(f)] == []


def test_h40i_the_walk_resolves_a_module_imported_by_name() -> None:
    assert ROOT / "tests/j4b/redraft.py" in resolve("tests.j4b", "redraft")
    assert ROOT / "tests/j4b/__init__.py" in resolve("tests.j4b", "redraft")


def violations(path: Path, name: str | None = None) -> list[str]:
    shown = name or path.relative_to(ROOT).as_posix()
    out: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out += [f"{shown}:{node.lineno} {a.name}" for a in node.names if a.name.startswith("jevson.")]
        if not (isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "jevson"):
            continue
        for alias in node.names:
            module = node.module
            if (
                module in ("jevson.llm.replay", "jevson.backends.caching")
                or (module, alias.name) in pins.JEVSON_INTERNALS
            ):
                continue
            if alias.name in jevson.__all__:
                defining = __import__(module, fromlist=[alias.name])
                if getattr(defining, alias.name) is getattr(jevson, alias.name):
                    continue
            out.append(f"{shown}:{node.lineno} {module}.{alias.name}")
    return out


def test_h40iii_every_jevson_import_is_public_replay_or_allowlisted() -> None:
    assert [v for f in sorted(closure()) for v in violations(f)] == []


def test_h40iii_a_planted_internal_import_is_named(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""Planted."""\n\nfrom jevson.execute.executor import _Run\nimport jevson.types\n', encoding="utf-8"
    )
    name = f"{pins.FRESH}/planted.py"
    assert violations(planted, name) == [f"{name}:3 jevson.execute.executor._Run", f"{name}:4 jevson.types"]
