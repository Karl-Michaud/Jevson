"""Core tests never touch the network: any socket connection raises."""

from __future__ import annotations

import socket
from collections.abc import Iterator

import pytest

from jevson.execute import ratelimit


class NetworkBlockedError(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    def refuse(*args: object, **kwargs: object) -> None:
        raise NetworkBlockedError("network access is stubbed in tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    return


@pytest.fixture(autouse=True)
def _fresh_limiters() -> Iterator[None]:
    """The per-key limiter registry is process-wide by design; each test starts with it empty."""
    ratelimit._registry.buckets.clear()  # pyright: ignore[reportPrivateUsage]
    yield
    ratelimit._registry.buckets.clear()  # pyright: ignore[reportPrivateUsage]
