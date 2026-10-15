"""PLAN §2 and §3: only backends/decisions.py knows the vendor wire, and no vendor SDK is a dependency."""

from __future__ import annotations

import re
from importlib.metadata import PackageNotFoundError, requires
from pathlib import Path

from packaging.requirements import Requirement

PACKAGE = Path(__file__).resolve().parents[2] / "jevson"
WIRE = re.compile(r"api\.openai\.com|/v1/decisions|Authorization|Bearer|x-request-id|OPENAI_API_KEY")
VENDOR_SDKS = {"openai", "typesafe-sdk", "anthropic"}


def test_only_backends_decisions_knows_the_url_headers_and_key_variable() -> None:
    allowed = PACKAGE / "backends" / "decisions.py"
    offenders = [
        p.relative_to(PACKAGE) for p in PACKAGE.rglob("*.py") if p != allowed and WIRE.search(p.read_text("utf-8"))
    ]
    assert offenders == []
    assert WIRE.search(allowed.read_text("utf-8"))


def closure(distribution: str) -> set[str]:
    """Every distribution `distribution` requires at run time, transitively (extras excluded)."""
    seen: set[str] = set()
    pending = [distribution]
    while pending:
        name = pending.pop()
        try:
            listed = requires(name) or []
        except PackageNotFoundError:
            continue
        for line in listed:
            requirement = Requirement(line)
            if requirement.marker is not None and not requirement.marker.evaluate({"extra": ""}):
                continue
            key = requirement.name.lower().replace("_", "-")
            if key not in seen:
                seen.add(key)
                pending.append(key)
    return seen


def test_no_vendor_sdk_in_the_dependency_closure() -> None:
    dependencies = closure("jevson")
    assert {"httpx", "rfc8785", "jsonschema"} <= dependencies
    assert not dependencies & VENDOR_SDKS
