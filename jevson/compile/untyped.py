"""Typed views of untyped JSON values: schemas and `x-jevson` declarations arrive as plain objects."""

from __future__ import annotations

from typing import cast

from jevson.types import JSONValue


def as_object(value: object) -> dict[str, object] | None:
    """A shallow, string-keyed copy of a JSON object, so callers never mutate the caller's schema."""
    if not isinstance(value, dict):
        return None
    return {str(k): v for k, v in cast("dict[object, object]", value).items()}


def as_list(value: object) -> list[object] | None:
    return list(cast("list[object]", value)) if isinstance(value, list) else None


def as_json(value: object) -> JSONValue:
    return cast("JSONValue", value)  # values come from JSON or from Pydantic's JSON Schema


def as_text(value: object) -> str | None:
    """Non-blank text, or None."""
    return value if isinstance(value, str) and value.strip() else None
