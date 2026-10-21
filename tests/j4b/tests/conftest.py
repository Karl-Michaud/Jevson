"""H38: the committed fresh recordings are never touched by the suite (FEAS48-R5-4).

Hashed without git (sorted relative paths and file SHA-256s), so it works in an export; an absent directory is its
own state. Every test that runs a runner command passes its own root under `tmp_path`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path

import pytest

RECORDINGS = Path(__file__).resolve().parents[1] / "recordings" / "fresh"


def recordings_state(directory: Path = RECORDINGS) -> str:
    if not directory.exists():
        return "absent"
    digest = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        digest.update(
            f"{path.relative_to(directory).as_posix()}\0{hashlib.sha256(path.read_bytes()).hexdigest()}\n".encode()
        )
    return digest.hexdigest()


@pytest.fixture(scope="session", autouse=True)
def committed_recordings_are_untouched() -> Iterator[None]:
    before = recordings_state()
    yield
    assert recordings_state() == before, "a test wrote under tests/j4b/recordings/fresh/"
