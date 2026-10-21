"""Run-time pins of the pre-registration (plan §2, §4.1 `pins.py`).

This first part holds only the canonical serialisation every authored data file and derived summary must equal,
so no byte of them lies outside a record (ARCH48-R13-1).
"""

from __future__ import annotations

import json
from typing import Any


def canonical_file(obj: Any) -> str:
    """`json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\\n"`: the one accepted form."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, indent=1) + "\n"


def canonical_row(obj: Any) -> str:
    """One fixture row: canonical JSON on one line."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False) + "\n"
