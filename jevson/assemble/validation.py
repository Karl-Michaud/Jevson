"""The one JSON Schema validator Jevson uses, so preflight and final validation agree (DESIGN §6.1).

`format` is checked: always for the formats `jsonschema` checks itself (e.g. `email`), and for the
rest only when the caller installs jsonschema's format extras [L10]. Both the final validation of
`.value` (`assembler.py`) and the preflight check of `known=` values (`known.py`) build their
validator here, so they can never disagree on keywords or formats.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator


def validator(schema: Mapping[str, Any]) -> Any:
    """A draft 2020-12 validator for `schema`, with the format checker on."""
    return Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
