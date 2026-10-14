"""Key hygiene: count files in the repository (excluding .env and .git) that contain TYPESAFE_API_KEY.

Run before every commit: ``uv run python -m tests.phase0.keyscan``. Prints only the count and the offending
paths, never the key. Exit status 1 if the count is not 0.
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def read_key(env_path: pathlib.Path) -> str:
    for line in env_path.read_text().splitlines():
        if line.startswith("TYPESAFE_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
            if key:
                return key
    raise RuntimeError("TYPESAFE_API_KEY not set in .env")


def files_containing(root: pathlib.Path, key: str) -> list[pathlib.Path]:
    needle = key.encode()
    hits = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if rel.parts and rel.parts[0] in (".git", ".venv") or rel.name == ".env":
            continue
        if p.is_file() and not p.is_symlink():
            try:
                if needle in p.read_bytes():
                    hits.append(rel)
            except OSError:
                continue
    return hits


def main(root: pathlib.Path = ROOT) -> int:
    hits = files_containing(root, read_key(root / ".env"))
    print(f"files containing the key: {len(hits)}")
    for h in hits:
        print(f"  {h}")
    return 1 if hits else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
