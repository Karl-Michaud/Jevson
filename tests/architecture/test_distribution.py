"""PLAN Phase 8: the built wheel and sdist hold only the intended package, with the agreed metadata.

Builds both with hatchling into a temporary directory (offline: hatchling is a dev dependency), then
reads the archives. No tests, hostile doubles, Phase 0 harness, fixtures, recordings or `.env` may
ship, and the wheel's dependencies are exactly PLAN Phase 8's list as amended (rfc8785, PLAN §6).
"""

from __future__ import annotations

import subprocess
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
REQUIRES = {"httpx>=0.28.1", "jsonschema>=4.23", "pydantic>=2.12", "rfc8785>=0.1.4"}
FORBIDDEN = ("tests/", "phase0", "hostile", "fixtures", "recordings", ".env", "conftest", "__pycache__")


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    out = tmp_path_factory.mktemp("dist")
    subprocess.run(
        [sys.executable, "-m", "hatchling", "build", "-d", str(out)], cwd=ROOT, check=True, capture_output=True
    )
    (wheel,) = out.glob("*.whl")
    (sdist,) = out.glob("*.tar.gz")
    return wheel, sdist


def test_the_wheel_holds_only_the_package_and_its_metadata(built: tuple[Path, Path]) -> None:
    names = zipfile.ZipFile(built[0]).namelist()
    dist_info = {n for n in names if n.split("/")[0].endswith(".dist-info")}
    assert {n for n in names if n not in dist_info} == {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "jevson").rglob("*")
        if p.is_file() and p.suffix in {".py", ".typed"}
    }
    assert "jevson/py.typed" in names
    assert any(n.endswith("licenses/LICENSE") for n in dist_info)
    assert not [n for n in names if any(bad in n for bad in FORBIDDEN)]


def test_the_wheel_declares_the_agreed_dependencies_and_python(built: tuple[Path, Path]) -> None:
    archive = zipfile.ZipFile(built[0])
    (metadata,) = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
    message = Parser().parsestr(archive.read(metadata).decode())
    assert set(message.get_all("Requires-Dist") or []) == REQUIRES
    assert message["Requires-Python"] == ">=3.11"
    assert message["License-Expression"] == "MIT"
    assert message.get_all("Provides-Extra") is None


def test_the_sdist_is_an_allow_list(built: tuple[Path, Path]) -> None:
    with tarfile.open(built[1]) as archive:
        names = {name.split("/", 1)[1] for name in archive.getnames() if "/" in name}
    top = {name.split("/")[0] for name in names}
    # hatchling always adds .gitignore to an sdist, beside the allow-list
    assert top == {
        "jevson",
        "examples",
        "README.md",
        "CHANGELOG.md",
        "LICENSE",
        "pyproject.toml",
        "PKG-INFO",
        ".gitignore",
    }
    assert not [n for n in names if any(bad in n for bad in FORBIDDEN)]
