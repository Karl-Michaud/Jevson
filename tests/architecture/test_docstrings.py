"""PLAN Phase 8: every public symbol is documented (pyright --strict checks that it is typed).

A public symbol is a name in `jevson.__all__`, and every public method or property of a public
class, protocols included. A dataclass's generated `Name(field: ...)` docstring does not count.
"""

from __future__ import annotations

import enum
import inspect

import pytest

import jevson


def _has_own_docstring(obj: object, name: str) -> bool:
    doc = vars(obj).get("__doc__") if inspect.isclass(obj) else getattr(obj, "__doc__", None)
    return isinstance(doc, str) and bool(doc.strip()) and not doc.startswith(f"{name}(")


def _undocumented() -> list[str]:
    missing: list[str] = []
    for name in jevson.__all__:
        obj = getattr(jevson, name)
        if not _has_own_docstring(obj, name):
            missing.append(name)
        if not inspect.isclass(obj) or issubclass(obj, enum.Enum):
            continue
        for attr, member in vars(obj).items():
            if attr.startswith("_"):
                continue
            function = member.fget if isinstance(member, property) else getattr(member, "__func__", member)
            if inspect.isfunction(function) and not _has_own_docstring(function, attr):
                missing.append(f"{name}.{attr}")
    return missing


def test_every_public_symbol_has_a_docstring() -> None:
    assert _undocumented() == []


def test_the_check_catches_a_missing_docstring(monkeypatch: pytest.MonkeyPatch) -> None:
    class Bare:
        def method(self) -> None: ...

    monkeypatch.setattr(jevson, "__all__", [*jevson.__all__, "Bare"])
    monkeypatch.setattr(jevson, "Bare", Bare, raising=False)
    assert _undocumented() == ["Bare", "Bare.method"]
