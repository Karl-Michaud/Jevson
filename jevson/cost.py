"""`InMemoryCostSink`: the default `CostSink`, keeping every event in memory (DESIGN §8).

`record()` may be called from any thread, so appends and reads share one `threading.Lock`; `events`
is a snapshot, so reading it never races a later `record()`. Nothing is written anywhere.
"""

from __future__ import annotations

import threading

from jevson.types import CostEvent


class InMemoryCostSink:
    """Keeps every `CostEvent` in arrival order; thread-safe; writes nothing anywhere."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: list[CostEvent] = []

    def record(self, cost_event: CostEvent) -> None:
        """Append one event."""
        with self._lock:
            self._events.append(cost_event)

    @property
    def events(self) -> tuple[CostEvent, ...]:
        """A snapshot of every event recorded so far, oldest first."""
        with self._lock:
            return tuple(self._events)

    def clear(self) -> None:
        """Forget every event recorded so far."""
        with self._lock:
            self._events.clear()
