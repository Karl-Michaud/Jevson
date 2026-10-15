"""Loud refusal with every offending pointer (R14).

Compilation never stops at the first problem: each stage adds what it finds to one `Refusals`, and
the compiler raises a single `CompileError` naming all of them, before any network call.
"""

from __future__ import annotations

from jevson.errors import CompileError, RefusalCode, RefusalReason


def child_pointer(parent: str, token: str) -> str:
    """The RFC 6901 pointer to `token` under `parent` (root is ``""``)."""
    return f"{parent}/{token.replace('~', '~0').replace('/', '~1')}"


class Refusals:
    """Collects refusals in the order they are found; duplicates are kept once."""

    def __init__(self) -> None:
        self._reasons: list[RefusalReason] = []

    def add(self, pointer: str, code: RefusalCode, message: str) -> None:
        reason = RefusalReason(pointer, code, message)
        if reason not in self._reasons:
            self._reasons.append(reason)

    @property
    def reasons(self) -> tuple[RefusalReason, ...]:
        return tuple(self._reasons)

    def __bool__(self) -> bool:
        return bool(self._reasons)

    def raise_if_any(self) -> None:
        if self._reasons:
            raise CompileError(self._reasons)
