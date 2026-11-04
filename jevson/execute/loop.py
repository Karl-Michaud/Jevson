"""The library-owned event loop behind the synchronous `resolve()` (DESIGN §8, [L20]).

One loop runs in a daemon thread for the whole process, created on first use, so every synchronous
call shares it and an `httpx.AsyncClient` bound to it stays usable across calls. A fresh loop per
call is not used: a client and asyncio locks are bound to the loop that first used them [L20].

- `run()` refuses inside a running loop (the caller's or this one), pointing at `aresolve()`. The
  coroutine is built on the library loop, only once the call starts, so neither a refusal nor an
  interrupt that lands before the call starts leaves a coroutine un-awaited.
- If building the coroutine or its task raises on the library loop, the call finishes with that error
  (a loop callback's exception would otherwise reach only the loop's handler and `run()` would block).
- If the caller's wait is interrupted (Ctrl-C, or any exception raised while blocked), a call that has
  not started never will, and `run()` re-raises at once; a running call's task is cancelled on the
  library loop and `run()` waits up to `CANCEL_GRACE_S` for it to unwind before re-raising, so the
  interrupted call stops spending. A coroutine that ignores cancellation, or a wedged loop, is not
  waited on past the grace period.
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
from typing import Any, Generic, TypeVar

from jevson.errors import UsageError

T = TypeVar("T")

CANCEL_GRACE_S = 2.0


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
    call = _Call(make, _library.get())
    try:  # scheduling is inside: an interrupt that lands right after it still cancels the call
        call.loop.call_soon_threadsafe(call.start)
        return call.future.result()
    except BaseException:
        if call.cancel():  # it was running: let its task unwind
            call.unwound.wait(CANCEL_GRACE_S)
        raise


class _Call(Generic[T]):
    """One synchronous call on the library loop. `unwound` is set once nothing of it runs any more:
    its task finished, or it was cancelled before it started and so never built its coroutine."""

    def __init__(self, make: Callable[[], Coroutine[Any, Any, T]], loop: asyncio.AbstractEventLoop) -> None:
        self.make = make
        self.loop = loop
        self.future: concurrent.futures.Future[T] = concurrent.futures.Future()
        self.unwound = threading.Event()
        self.task: asyncio.Task[T] | None = None

    def start(self) -> None:
        """On the loop: build the coroutine and its task, unless the caller already gave up."""
        if not self.future.set_running_or_notify_cancel():
            self.unwound.set()
            return
        try:
            coroutine = self.make()
            try:
                self.task = self.loop.create_task(coroutine)
            except BaseException:
                coroutine.close()  # never awaited: close it so it is not reported as such
                raise
        except BaseException as error:  # in a loop callback it would reach only the loop's handler
            self.future.set_exception(error)
            self.unwound.set()
            return
        self.task.add_done_callback(self._finish)

    def cancel(self) -> bool:
        """From the caller's thread: a call not yet started never starts, and a finished one has nothing
        left to cancel (False: nothing to wait for); a running one has its task cancelled on the loop (True)."""
        if self.future.cancel() or self.future.done():
            return False
        self.loop.call_soon_threadsafe(self._cancel_task)
        return True

    def _cancel_task(self) -> None:
        # Runs after `start` (both are loop callbacks, scheduled in that order). No task means `start`
        # failed and already finished the future: an interrupt that raced it has nothing to cancel.
        if self.task is not None:
            self.task.cancel()

    def _finish(self, task: asyncio.Task[T]) -> None:
        if task.cancelled():
            self.future.set_exception(concurrent.futures.CancelledError())
        elif (error := task.exception()) is not None:
            self.future.set_exception(error)
        else:
            self.future.set_result(task.result())
        self.unwound.set()


def submit(make: Callable[[], Coroutine[Any, Any, None]]) -> concurrent.futures.Future[None] | None:
    """Schedule `make()` on the library loop if it exists in this process; never creates one."""
    loop = _library.loop
    if loop is None:
        return None
    return asyncio.run_coroutine_threadsafe(make(), loop)
