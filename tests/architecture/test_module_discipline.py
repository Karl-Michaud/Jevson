"""PLAN §2 module discipline, checked by path so it covers packages that do not exist yet.

import-linter enforces the same rules in CI for the modules that exist; this test also covers
`compile/` and `execute/` from the moment their first file lands.
"""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2] / "jevson"


def imported_modules(path: Path) -> set[str]:
    package = ".".join(path.relative_to(PACKAGE.parent).with_suffix("").parts[:-1])
    return imports(path.read_text(encoding="utf-8"), package)


def imports(source: str, package: str) -> set[str]:
    """Absolute module names a module in `package` imports; `from m import x` also counts `m.x`."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            parts = package.split(".")
            base = parts[: len(parts) - node.level + 1] if node.level else []
            module = ".".join([*base, *([node.module] if node.module else [])])
            names.add(module)
            names.update(f"{module}.{alias.name}" for alias in node.names)
    return names


def files(*relative: str) -> list[Path]:
    found: list[Path] = []
    for item in relative:
        path = PACKAGE / item
        found += sorted(path.rglob("*.py")) if path.is_dir() else [path] if path.exists() else []
    return found


def test_compile_assemble_and_graph_never_import_execute_or_backends() -> None:
    checked = files("compile", "assemble", "graph.py")
    assert checked, "graph.py and assemble/ exist from Phase 1"
    for path in checked:
        bad = {m for m in imported_modules(path) if m.startswith(("jevson.execute", "jevson.backends"))}
        assert not bad, f"{path.relative_to(PACKAGE)} imports {sorted(bad)}"


def test_only_backends_decisions_knows_the_vendor_wire() -> None:
    allowed = PACKAGE / "backends" / "decisions.py"
    for path in files("."):
        if path == allowed:
            continue
        bad = {m for m in imported_modules(path) if m.split(".")[0] in {"httpx", "openai", "typesafe_sdk", "requests"}}
        assert not bad, f"{path.relative_to(PACKAGE)} imports {sorted(bad)}"


def test_protocols_are_defined_only_in_protocols_py() -> None:
    for path in files("."):
        if path.name == "protocols.py" and path.parent == PACKAGE:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ClassDef):
                bases = {b.id if isinstance(b, ast.Name) else getattr(b, "attr", "") for b in node.bases}
                assert "Protocol" not in bases, f"{path.relative_to(PACKAGE)} defines protocol {node.name}"


def test_the_five_protocols_live_in_protocols_py() -> None:
    tree = ast.parse((PACKAGE / "protocols.py").read_text(encoding="utf-8"))
    defined = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    assert defined == {"Backend", "Extractor", "LLM", "Normalizer", "CostSink"}


def test_hostile_doubles_are_not_shipped() -> None:
    assert not [p for p in PACKAGE.rglob("*") if p.name.startswith("hostile")]


def test_relative_imports_resolve() -> None:
    source = "from ..backends import fake\nfrom . import sibling\nfrom .. import execute\nimport httpx\n"
    assert imports(source, "jevson.assemble") == {
        "jevson.backends",
        "jevson.backends.fake",
        "jevson.assemble",
        "jevson.assemble.sibling",
        "jevson",
        "jevson.execute",
        "httpx",
    }
