"""The library-owned event loop behind the synchronous `resolve()` (DESIGN §8, [L20]).

One loop runs in a daemon thread for the whole process, created on first use, so every synchronous
call shares it and an `httpx.AsyncClient` bound to it stays usable across calls. A fresh loop per
call is not used: a client and asyncio locks are bound to the loop that first used them [L20].

- `run()` refuses inside a running loop (the caller's or this one), pointing at `aresolve()`. The
  coroutine is built only after that check, so a refusal leaves nothing un-awaited.
- After `os.fork()` the child has no loop thread. The fork hook forgets the loop, the thread and the
  lock without touching them, and bumps `generation()`; the next call builds a fresh loop. Objects
  bound to the old loop (clients) compare their generation and are dropped, never closed.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

from jevson.errors import UsageError

T = TypeVar("T")


class _LibraryLoop:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None
        self.generation = 0

    def get(self) -> asyncio.AbstractEventLoop:
        with self.lock:
            if self.loop is None:
                loop = asyncio.new_event_loop()
                thread = threading.Thread(target=loop.run_forever, name="jevson-loop", daemon=True)
                thread.start()
                self.loop = loop
            return self.loop

    def after_fork_in_child(self) -> None:
        self.lock = threading.Lock()
        self.loop = None
        self.generation += 1


_library = _LibraryLoop()
os.register_at_fork(after_in_child=_library.after_fork_in_child)


def generation() -> int:
    """Bumped in every forked child; an object made under an older generation belongs to a dead loop."""
    return _library.generation


def is_library_loop(loop: asyncio.AbstractEventLoop) -> bool:
    return loop is _library.loop


def _running() -> asyncio.AbstractEventLoop | None:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return None


def run(make: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """Run `make()` on the library loop and block for its result."""
    if _running() is not None:
        raise UsageError("resolve() cannot run inside a running event loop; await aresolve() instead")
    return asyncio.run_coroutine_threadsafe(make(), _library.get()).result()


def submit(make: Callable[[], Coroutine[Any, Any, None]]) -> concurrent.futures.Future[None] | None:
    """Schedule `make()` on the library loop if it exists in this process; never creates one."""
    loop = _library.loop
    if loop is None:
        return None
    return asyncio.run_coroutine_threadsafe(make(), loop)
