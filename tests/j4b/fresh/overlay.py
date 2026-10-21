"""Git reads and the overlay test run that the pin check and the void record share (plan §2 rule (d);
single-look item 12(a), FEAS48-R10-2).

Every git call runs with no user or system configuration. A test is run against the harness that ran: `git
archive <commit>` unpacked in a new temporary directory, the named files written over it at another commit's
content, then `pytest -p no:cacheprovider <node>` there, offline. Old commits are read with `git show`, never
imported.
"""

from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0"}


def git(repo: Path, *args: str) -> str:
    run = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True, env={**os.environ, **GIT_ENV}
    )
    return run.stdout.decode("utf-8")


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, check=True, env={**os.environ, **GIT_ENV}
    ).stdout


def rev_parse(repo: Path, spec: str) -> str | None:
    """The object `spec` names, or None when it does not exist (a path absent at that commit)."""
    run = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", spec],
        capture_output=True,
        check=False,
        env={**os.environ, **GIT_ENV},
    )
    return run.stdout.decode().strip() or None


def is_ancestor(repo: Path, older: str, newer: str) -> bool:
    run = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", older, newer],
        capture_output=True,
        check=False,
        env={**os.environ, **GIT_ENV},
    )
    return run.returncode == 0


def changed_paths(repo: Path, older: str, newer: str) -> list[str]:
    return [p for p in git(repo, "diff", "--name-only", older, newer).splitlines() if p]


def ls_tree(repo: Path, commit: str, *paths: str, recursive: bool = True) -> list[tuple[str, str]]:
    """(path, object) of every tracked file under `paths` at `commit`; with `recursive=False`, of each path
    itself (a directory's tree, a file's blob), absent paths omitted."""
    out: list[tuple[str, str]] = []
    for line in git(repo, "ls-tree", *(["-r"] if recursive else []), commit, "--", *paths).splitlines():
        meta, name = line.split("\t", 1)
        out.append((name, meta.split()[2]))
    return out


def show(repo: Path, commit: str, path: str) -> bytes:
    return git_bytes(repo, "show", f"{commit}:{path}")


def show_many(repo: Path, commit: str, paths: Sequence[str]) -> dict[str, bytes]:
    """Several files at `commit` through one `git cat-file --batch`."""
    request = "".join(f"{commit}:{p}\n" for p in paths).encode()
    out = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "--batch"],
        input=request,
        capture_output=True,
        check=True,
        env={**os.environ, **GIT_ENV},
    ).stdout
    found: dict[str, bytes] = {}
    position = 0
    for path in paths:
        header_end = out.index(b"\n", position)
        header = out[position:header_end].split()
        if header[-1] == b"missing":
            position = header_end + 1
            continue
        size = int(header[2])
        found[path] = out[header_end + 1 : header_end + 1 + size]
        position = header_end + 1 + size + 1
    return found


def dirty(repo: Path, paths: Sequence[str]) -> list[str]:
    return [line for line in git(repo, "status", "--porcelain", "--", *paths).splitlines() if line]


@dataclass(frozen=True)
class NodeRun:
    exit_code: int
    collected: tuple[str, ...]
    output_sha256: str


def run_node(repo: Path, commit: str, node: str, overlay: Mapping[str, bytes]) -> NodeRun:
    """Run one pytest node on `git archive <commit>` with `overlay` (path -> content) written over it."""
    archive = git_bytes(repo, "archive", "--format=tar", commit)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(root, filter="data")
        for path, content in overlay.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_bytes(content)
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        base = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", "--no-header", "-o", "addopts="]
        collect = subprocess.run([*base, "--collect-only", node], cwd=root, capture_output=True, env=env, check=False)
        collected = tuple(line for line in collect.stdout.decode().splitlines() if "::" in line)
        run = subprocess.run([*base, node], cwd=root, capture_output=True, env=env, check=False)
    return NodeRun(run.returncode, collected, hashlib.sha256(run.stdout + run.stderr).hexdigest())
