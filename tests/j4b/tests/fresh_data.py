"""The committed fresh fixtures and authored data, loaded once for the H-tests (no network, no key)."""

from __future__ import annotations

import functools
import json
from typing import Any

from tests.j4b.fresh import build_fresh_sets as builder


@functools.cache
def authored() -> dict[str, dict[str, dict[str, Any]]]:
    return {n: builder.load_authored(n, (builder.FRESH / n).read_text(encoding="utf-8")) for n in builder.AUTHORED}


@functools.cache
def rows() -> dict[str, list[dict[str, Any]]]:
    """The committed row files, parsed."""
    return {
        name: [json.loads(line) for line in (builder.FIXTURES / name).read_text(encoding="utf-8").splitlines()]
        for name in builder.ROW_FILES
    }


@functools.cache
def picked() -> dict[str, list[str]]:
    return json.loads(builder.PICKED.read_text(encoding="utf-8"))


def strings() -> dict[str, str]:
    return builder.strings(authored())


def copy_rows() -> dict[str, list[dict[str, Any]]]:
    """A deep copy of the rows, for planting a defect."""
    return json.loads(json.dumps(rows()))
