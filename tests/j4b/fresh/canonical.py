"""The one accepted serialisation of every authored data file, fixture row and derived summary (ARCH48-R13-1)."""

from __future__ import annotations

import json
from typing import Any


def canonical_file(obj: Any) -> str:
    """`json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\\n"`: no byte lies outside a record."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def canonical_row(obj: Any) -> str:
    """One fixture row: canonical JSON on one line."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False) + "\n"
