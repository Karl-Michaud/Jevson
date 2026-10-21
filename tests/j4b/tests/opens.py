"""A recorder of the files a block of code opens, through one process-wide audit hook (an audit hook cannot be
removed, so it records only while `recording()` is active; H35, H40 (ii))."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_ACTIVE: ContextVar[list[Path] | None] = ContextVar("opens", default=None)
_INSTALLED: list[bool] = []


def _hook(event: str, args: tuple[object, ...]) -> None:
    if event != "open":
        return
    seen = _ACTIVE.get()
    if seen is not None and isinstance(args[0], (str, bytes, os.PathLike)):
        seen.append(Path(os.fsdecode(args[0])).resolve())  # pyright: ignore[reportArgumentType]


@contextmanager
def recording() -> Iterator[list[Path]]:
    """Every path opened inside the block (by this thread's context), resolved."""
    if not _INSTALLED:
        sys.addaudithook(_hook)
        _INSTALLED.append(True)
    seen: list[Path] = []
    token = _ACTIVE.set(seen)
    try:
        yield seen
    finally:
        _ACTIVE.reset(token)
