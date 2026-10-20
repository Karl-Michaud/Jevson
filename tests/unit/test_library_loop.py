"""PLAN Phase 3 lifecycle and async criteria for the synchronous `resolve()` (execute/loop.py, [L20]).

Every test talks to a real `DecisionsBackend` over `httpx.MockTransport`, so the clients, the
library loop and the per-key limiter are the shipped ones. Each test uses its own API key, so its
limiter bucket is not shared with any other test.
"""

from __future__ import annotations

import asyncio
import gc
import json
import os
import signal
import threading
import time
import traceback
import uuid
import warnings
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest

from jevson import BackendError, DecisionsBackend, Jevson, Result, UsageError
from jevson.execute import loop as library

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "paid": {"type": "boolean", "description": "the invoice is paid"},
        "category": {"enum": ["software", "hardware"]},
    },
    "required": ["paid", "category"],
}
SOURCE = "Invoice 7: software licences, paid in full."
EXPECTED = {"paid": True, "category": "software"}

fork_warning = pytest.mark.filterwarnings("ignore:This process .* is multi-threaded:DeprecationWarning")


def answer(request: httpx.Request) -> httpx.Response:
    """Answers every question confidently: predicates true, choices their first option."""
    answers: list[dict[str, Any]] = []
    for q in json.loads(request.content)["questions"]:
        if q["type"] == "predicate":
            answers.append({"type": "predicate", "name": q["name"], "probability": 0.95})
        else:
            values = [c["value"] for c in q["choices"]]
            probabilities = [{"value": v, "probability": 0.95 if i == 0 else 0.05 / (len(values) - 1)}
                             for i, v in enumerate(values)]  # fmt: skip
            answers.append({"type": "choice", "name": q["name"], "choice": values[0],
                            "probabilities": probabilities, "confidence": 0.9})  # fmt: skip
    body = {"answers": answers, "model": "gpt-6-luna", "usage": {"input_tokens": 100}}
    return httpx.Response(200, json=body, headers={"x-request-id": "req"})


class Waits:
    """A frozen clock and a recording sleep: the limiter's waits show whether one bucket paced every call."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.waits: list[float] = []

    async def sleep(self, seconds: float) -> None:
        with self.lock:
            self.waits.append(seconds)


def backend(
    handler: Callable[[httpx.Request], httpx.Response] = answer, key: str | None = None, **kwargs: Any
) -> DecisionsBackend:
    key = key or f"sk-test-{uuid.uuid4()}"
    return DecisionsBackend(key, transport=httpx.MockTransport(handler), **kwargs)


def clients(b: DecisionsBackend) -> int:
    return b._live_clients  # pyright: ignore[reportPrivateUsage]


def ok(result: Result) -> bool:
    return result.complete and result.value == EXPECTED


# --- async: sequential, threads, loops ------------------------------------------------------


def test_two_sequential_resolve_calls_share_one_long_lived_client() -> None:
    b = backend()
    jevson = Jevson(b)
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    first = b._library  # pyright: ignore[reportPrivateUsage]
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    assert b._library is first  # pyright: ignore[reportPrivateUsage]
    assert clients(b) == 1
    jevson.close()
    assert clients(b) == 0


def test_resolve_from_four_threads_at_once() -> None:
    b = backend()
    jevson = Jevson(b)
    barrier = threading.Barrier(4)

    def call(_: int) -> bool:
        barrier.wait()
        return ok(jevson.resolve(SCHEMA, SOURCE))

    with ThreadPoolExecutor(4) as pool:
        assert all(pool.map(call, range(4)))
    assert clients(b) == 1
    jevson.close()
    assert clients(b) == 0


def test_aresolve_from_two_different_event_loops() -> None:
    b = backend()
    jevson = Jevson(b)
    results: list[Result] = []

    def in_thread() -> None:
        results.append(asyncio.run(jevson.aresolve(SCHEMA, SOURCE)))

    worker = threading.Thread(target=in_thread)
    worker.start()
    results.append(asyncio.run(jevson.aresolve(SCHEMA, SOURCE)))
    worker.join()
    assert len(results) == 2
    assert all(ok(r) for r in results)
    assert clients(b) == 0  # per-call clients on caller loops, each closed before its call returned


@pytest.mark.filterwarnings("error::RuntimeWarning")  # no un-awaited aresolve() coroutine is left behind
def test_resolve_inside_a_running_loop_points_at_aresolve() -> None:
    jevson = Jevson(backend())

    async def inside() -> None:
        with pytest.raises(UsageError, match=r"await aresolve\(\)"):
            jevson.resolve(SCHEMA, SOURCE)

    asyncio.run(inside())


def test_the_per_key_limiter_holds_its_rate_across_calls_threads_and_loops() -> None:
    waits = Waits()
    # One request a second, a burst of one, and a clock that never moves: the k-th request through
    # one shared bucket must wait exactly k - 1 seconds, whichever thread or loop it came from.
    key = f"sk-test-{uuid.uuid4()}"
    b = backend(key=key, requests_per_minute=60, clock=lambda: 0.0, sleep=waits.sleep)
    jevson = Jevson(b)
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    assert ok(jevson.resolve(SCHEMA, SOURCE))

    def call(_: int) -> bool:
        return ok(jevson.resolve(SCHEMA, SOURCE))

    with ThreadPoolExecutor(4) as pool:
        assert all(pool.map(call, range(4)))
    worker = threading.Thread(target=lambda: asyncio.run(jevson.aresolve(SCHEMA, SOURCE)))
    worker.start()
    worker.join()
    assert ok(asyncio.run(jevson.aresolve(SCHEMA, SOURCE)))
    with backend(key=key) as other:  # a second backend on the same key shares the bucket
        assert other._limiter is b._limiter  # pyright: ignore[reportPrivateUsage]
    assert sorted(waits.waits) == [float(k) for k in range(1, 8)]  # 8 requests; the first does not wait


# --- caller loops, through the facade (PLAN Phase 3, lifecycle on caller loops) --------------


def test_twenty_sequential_asyncio_run_aresolve_calls_leave_no_live_client() -> None:
    b = backend()
    jevson = Jevson(b)
    for _ in range(20):
        assert ok(asyncio.run(jevson.aresolve(SCHEMA, SOURCE)))  # a fresh, then dead, loop each time
        assert clients(b) == 0


def test_two_aresolve_calls_under_gather_on_one_loop_succeed_and_leave_no_client() -> None:
    b = backend()
    jevson = Jevson(b)

    async def both() -> list[Result]:
        return await asyncio.gather(jevson.aresolve(SCHEMA, SOURCE), jevson.aresolve(SCHEMA, SOURCE))

    results = asyncio.run(both())
    assert len(results) == 2
    assert all(ok(r) for r in results)
    assert clients(b) == 0


def test_inside_async_with_jevson_the_calls_share_one_client_closed_on_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    b = backend()
    made: list[httpx.AsyncClient] = []
    original = b._new_client  # pyright: ignore[reportPrivateUsage]

    def counting() -> httpx.AsyncClient:
        made.append(original())
        return made[-1]

    monkeypatch.setattr(b, "_new_client", counting)

    async def session() -> None:
        async with Jevson(b) as jevson:
            assert ok(await jevson.aresolve(SCHEMA, SOURCE))
            results = await asyncio.gather(jevson.aresolve(SCHEMA, SOURCE), jevson.aresolve(SCHEMA, SOURCE))
            assert all(ok(r) for r in results)
            assert len(made) == 1
            assert not made[0].is_closed

    asyncio.run(session())
    assert len(made) == 1
    assert made[0].is_closed
    assert clients(b) == 0


# --- interrupting a blocked resolve() ---------------------------------------------------------


def pending_on_library_loop() -> set[asyncio.Task[Any]]:
    async def others() -> set[asyncio.Task[Any]]:
        return asyncio.all_tasks() - {asyncio.current_task()}  # pyright: ignore[reportReturnType]

    future = library.submit(others)
    assert future is not None
    return future.result(timeout=5)


def test_ctrl_c_during_resolve_cancels_the_call_on_the_library_loop() -> None:
    assert threading.current_thread() is threading.main_thread()  # SIGINT is delivered to the main thread
    entered, unwound = threading.Event(), threading.Event()
    hang = True

    async def handler(request: httpx.Request) -> httpx.Response:
        if not hang:
            return answer(request)
        entered.set()
        try:
            await asyncio.Event().wait()  # never answers: the request is in flight until cancelled
        finally:
            unwound.set()
        raise AssertionError("unreachable")  # pragma: no cover - the wait above only ends by cancellation

    def ctrl_c() -> None:
        assert entered.wait(5)
        signal.pthread_kill(threading.main_thread().ident or 0, signal.SIGINT)

    b = backend(handler)  # type: ignore[arg-type]  # MockTransport awaits an async handler
    jevson = Jevson(b)
    presser = threading.Thread(target=ctrl_c)
    presser.start()
    with pytest.raises(KeyboardInterrupt):
        jevson.resolve(SCHEMA, SOURCE)
    presser.join()
    assert unwound.is_set()  # run() waited for the cancellation to reach the request before re-raising
    assert pending_on_library_loop() == set()
    hang = False
    assert ok(jevson.resolve(SCHEMA, SOURCE))  # the shared client and the limiter still work
    jevson.close()
    assert clients(b) == 0


def test_an_interrupt_that_lands_just_after_the_call_is_scheduled_still_cancels_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The interrupt lands after `run()` has scheduled `start` (and the request is in flight) but before
    the caller blocks on the result: the call must still be cancelled, not left spending."""
    entered, unwound, release = threading.Event(), threading.Event(), threading.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        entered.set()
        try:
            while not release.is_set():
                await asyncio.sleep(0.01)
        finally:
            unwound.set()
        return answer(request)  # pragma: no cover - reached only if the call was never cancelled

    loop = library._library.get()  # pyright: ignore[reportPrivateUsage]
    schedule = loop.call_soon_threadsafe

    def interrupted_after_start(callback: Any, *args: Any) -> Any:
        handle = schedule(callback, *args)
        if getattr(callback, "__name__", "") == "start":
            assert entered.wait(5)  # the request is in flight
            raise KeyboardInterrupt  # Ctrl-C lands here, before the caller waits on the result
        return handle

    monkeypatch.setattr(loop, "call_soon_threadsafe", interrupted_after_start)
    with pytest.raises(KeyboardInterrupt):
        Jevson(backend(handler)).resolve(SCHEMA, SOURCE)  # type: ignore[arg-type]
    monkeypatch.undo()
    leaked = not unwound.is_set()
    release.set()  # lets a leaked request finish, so a failure here does not leak into later tests
    deadline = time.monotonic() + 5
    while pending_on_library_loop() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not leaked, "the interrupted call was never cancelled"
    assert pending_on_library_loop() == set()


def test_an_interrupt_does_not_wait_past_the_grace_period_for_a_call_that_ignores_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(library, "CANCEL_GRACE_S", 0.05)
    started, cancelled, release = threading.Event(), threading.Event(), threading.Event()

    async def stubborn() -> None:
        started.set()
        while not release.is_set():
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                cancelled.set()
                continue  # swallows the cancellation and keeps going

    def interrupt_wait(self: Any, timeout: float | None = None) -> None:
        assert started.wait(5)  # the interrupt lands while the coroutine is running, not before it starts
        raise KeyboardInterrupt

    monkeypatch.setattr("concurrent.futures.Future.result", interrupt_wait)
    began = time.monotonic()
    with pytest.raises(KeyboardInterrupt):
        library.run(stubborn)
    waited = time.monotonic() - began
    monkeypatch.undo()
    assert cancelled.wait(5)  # the cancellation reached the running coroutine, which ignored it
    assert waited < 2
    release.set()
    deadline = time.monotonic() + 5
    while pending_on_library_loop() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert pending_on_library_loop() == set()


def test_an_interrupt_before_the_call_starts_returns_at_once_and_builds_no_coroutine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(library, "CANCEL_GRACE_S", 1.0)
    made: list[int] = []

    async def body() -> None:
        made.append(1)  # pragma: no cover - the call is interrupted before it starts

    def make() -> Any:
        made.append(0)
        return body()

    loop_busy, release = threading.Event(), threading.Event()

    def block() -> None:  # holds the library loop, so the call cannot start before the interrupt
        loop_busy.set()
        release.wait(5)

    loop = library._library.get()  # pyright: ignore[reportPrivateUsage]
    loop.call_soon_threadsafe(block)
    assert loop_busy.wait(5)

    def interrupt_wait(self: Any, timeout: float | None = None) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("concurrent.futures.Future.result", interrupt_wait)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        began = time.monotonic()
        with pytest.raises(KeyboardInterrupt):
            library.run(make)
        waited = time.monotonic() - began
        monkeypatch.undo()
        release.set()
        assert pending_on_library_loop() == set()
        gc.collect()
    assert waited < 0.5  # not the 1 s grace: a call that never started has nothing to unwind
    assert made == []  # the coroutine is built on the loop only once the call starts
    assert not [w for w in caught if "never awaited" in str(w.message)]


def run_in_thread(make: Callable[[], Any]) -> tuple[list[BaseException], float]:
    """Call `library.run(make)` on a worker thread; a call whose future is never resolved would block
    forever, so the worker is a daemon and the caller's join is bounded."""
    raised: list[BaseException] = []

    def call() -> None:
        try:
            library.run(make)
        except BaseException as error:
            raised.append(error)

    worker = threading.Thread(target=call, daemon=True)
    began = time.monotonic()
    worker.start()
    worker.join(5)
    assert not worker.is_alive(), "run() never returned: the call's future was never resolved"
    return raised, time.monotonic() - began


def test_a_factory_that_raises_on_the_loop_reraises_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(library, "CANCEL_GRACE_S", 3.0)

    def make() -> Any:
        raise ValueError("factory failed")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raised, waited = run_in_thread(make)
        assert pending_on_library_loop() == set()
    assert [type(e) for e in raised] == [ValueError]
    assert waited < 1  # not the 3 s grace: nothing of the call is running
    assert not caught


def test_a_task_that_cannot_be_created_closes_its_coroutine_and_reraises_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(library, "CANCEL_GRACE_S", 3.0)
    loop = library._library.get()  # pyright: ignore[reportPrivateUsage]

    async def body() -> None:  # pragma: no cover - its task is never created, so it never runs
        pass

    def refuse(coroutine: Any) -> Any:
        raise RuntimeError("no task")

    monkeypatch.setattr(loop, "create_task", refuse)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        raised, waited = run_in_thread(body)
        monkeypatch.undo()
        assert pending_on_library_loop() == set()
        gc.collect()
    assert [type(e) for e in raised] == [RuntimeError]
    assert waited < 1
    assert not [w for w in caught if "never awaited" in str(w.message)]


def test_an_interrupt_that_races_a_failing_start_cancels_nothing() -> None:
    """The caller's interrupt lands while `start` is building the call (its future RUNNING), and the
    factory then raises: the scheduled cancellation finds no task and must do nothing."""
    loop = asyncio.new_event_loop()
    errors: list[dict[str, Any]] = []
    loop.set_exception_handler(lambda _loop, context: errors.append(context))

    def make() -> Any:
        assert call.cancel()  # still running: a cancellation is scheduled on the loop
        raise ValueError("factory failed")

    call = library._Call(make, loop)  # pyright: ignore[reportPrivateUsage]

    async def drive() -> None:
        call.start()
        await asyncio.sleep(0)  # the scheduled cancellation runs before this resumes

    try:
        loop.run_until_complete(drive())
    finally:
        loop.close()
    assert errors == []
    assert isinstance(call.future.exception(0), ValueError)
    assert call.unwound.is_set()


# --- context managers and closing -----------------------------------------------------------


def test_jevson_and_decisions_backend_work_as_sync_context_managers() -> None:
    with backend() as b, Jevson(b) as jevson:
        assert ok(jevson.resolve(SCHEMA, SOURCE))
        assert clients(b) == 1
    assert clients(b) == 0
    with pytest.raises(UsageError, match="closed"):
        jevson.resolve(SCHEMA, SOURCE)
    with pytest.raises(UsageError, match="closed"):
        asyncio.run(b.ask("state", (), "gpt-6-luna"))


def test_a_closed_instance_raises_usage_error_and_closes_its_backend() -> None:
    b = backend()
    jevson = Jevson(b)
    jevson.close()
    with pytest.raises(UsageError, match="closed"):
        jevson.resolve(SCHEMA, SOURCE)
    with pytest.raises(BackendError, match="UsageError"):  # the closed backend refuses the next Jevson too
        Jevson(b).resolve(SCHEMA, SOURCE)


def test_aclose_closes_the_library_loop_client_from_a_caller_loop() -> None:
    b = backend()
    jevson = Jevson(b)
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    asyncio.run(jevson.aclose())
    assert clients(b) == 0


def test_closing_from_the_library_loop_itself_does_not_deadlock() -> None:
    for closer in ("close", "aclose"):
        b = backend()
        assert ok(Jevson(b).resolve(SCHEMA, SOURCE))

        async def close_here(b: DecisionsBackend = b, closer: str = closer) -> None:
            if closer == "close":
                b.close()
            else:
                await b.aclose()

        submitted = library.submit(close_here)
        assert submitted is not None
        submitted.result(timeout=5)
        drained = library.submit(lambda: asyncio.sleep(0))  # the scheduled client close runs before this
        assert drained is not None
        drained.result(timeout=5)
        assert clients(b) == 0


# --- fork -----------------------------------------------------------------------------------


def in_child(check: Callable[[], bool]) -> None:
    """Run `check` in a forked child; fail here with the child's traceback unless it returned True."""
    read, write = os.pipe()
    pid = os.fork()
    if pid == 0:  # pragma: no cover - the child exits with os._exit, so coverage never records it
        os.close(read)
        try:
            message = b"" if check() else b"check returned False"
        except BaseException:
            message = traceback.format_exc().encode()
        os.write(write, message)
        os._exit(0 if not message else 1)
    os.close(write)
    with os.fdopen(read, "rb") as pipe:
        report = pipe.read().decode()
    _, status = os.waitpid(pid, 0)
    assert os.waitstatus_to_exitcode(status) == 0, report


@fork_warning
def test_resolve_succeeds_in_a_forked_child() -> None:
    b = backend()
    jevson = Jevson(b)
    assert ok(jevson.resolve(SCHEMA, SOURCE))  # the parent's library loop and client exist
    in_child(lambda: ok(jevson.resolve(SCHEMA, SOURCE)) and clients(b) == 1)
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    jevson.close()


@fork_warning
def test_resolve_succeeds_in_a_child_forked_while_the_parent_was_blocked_mid_request() -> None:
    parent = os.getpid()
    entered, release = threading.Event(), threading.Event()

    def blocking(request: httpx.Request) -> httpx.Response:
        if os.getpid() == parent:
            entered.set()
            assert release.wait(10)
        return answer(request)

    b = backend(blocking)
    jevson = Jevson(b)
    outcome: list[Result] = []
    worker = threading.Thread(target=lambda: outcome.append(jevson.resolve(SCHEMA, SOURCE)))
    worker.start()
    try:
        assert entered.wait(10)  # the library loop thread is inside the transport, the worker blocked on it
        in_child(lambda: ok(jevson.resolve(SCHEMA, SOURCE)) and ok(jevson.resolve(SCHEMA, SOURCE)))
    finally:
        release.set()
        worker.join()
    assert ok(outcome[0])
    jevson.close()


def test_inherited_clients_are_dropped_not_closed_after_a_simulated_fork(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fork hook's effect in-process, so coverage sees the drop paths the forked children take.

    A child forked inside a running loop cannot keep using it (CPython clears the running loop in
    the child), so the stale shared client is only reachable this way.
    """
    b = backend()
    jevson = Jevson(b)
    assert ok(jevson.resolve(SCHEMA, SOURCE))
    inherited = b._library  # pyright: ignore[reportPrivateUsage]
    assert inherited is not None

    async def shared() -> None:
        async with b:
            monkeypatch.setattr(library, "generation", lambda: 99)
            async with b:  # re-entering after the "fork" drops the stale shared client
                pass

    asyncio.run(shared())
    assert b._library is None  # pyright: ignore[reportPrivateUsage]
    assert not inherited[1].is_closed  # dropped, never closed
    assert clients(b) == 0
    jevson.close()  # nothing left to close on the library loop


def test_the_fork_hook_forgets_the_loop_and_bumps_the_generation() -> None:
    state = library._LibraryLoop()  # pyright: ignore[reportPrivateUsage]
    loop = state.get()
    assert state.get() is loop
    state.after_fork_in_child()
    assert (state.loop, state.generation) == (None, 1)
    loop.call_soon_threadsafe(loop.stop)  # this process still runs the thread; stop it


def test_submit_never_creates_a_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(library._library, "loop", None)  # pyright: ignore[reportPrivateUsage]
    assert library.submit(lambda: asyncio.sleep(0)) is None
