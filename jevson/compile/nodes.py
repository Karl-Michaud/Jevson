"""Node ids: the target **instance** pointer plus a role suffix (DESIGN §3.1).

`/billing/address/country#choice`. The pointer is an instance pointer (RFC 6901, from the
normaliser), so two fields of one `$defs` type get distinct ids, and the same schema gives the same
ids on every run. The role is the decision kind: `choice`, `score`, or `predicate`; a generative
field's nodes use `generate`, `criterion:<i>` and `rubric` (`compile/generative.py`).

An array's items sit at `<array>/-` in the normalised tree, but that pointer never reaches an id.
Phase 7 keys its per-value membership predicates on the array's own pointer plus the declared
option id, `/tags#member:c3`, so each member gets a distinct, stable id without a positional
reference (R13).
"""

from __future__ import annotations

from jevson.types import DecisionKind


def node_id(pointer: str, kind: DecisionKind) -> str:
    return f"{pointer}#{kind}"


def option_id(index: int) -> str:
    """Opaque option and level ids `c0…cN` in declared order (R13, [P5])."""
    return f"c{index}"


def member_id(pointer: str, option: str) -> str:
    """A multi-label enum array's membership predicate: `/tags#member:c3` (R13: no position)."""
    return f"{pointer}#member:{option}"


def role_id(pointer: str, role: str) -> str:
    """A node id with a named role: a generative field's `generate`, `criterion:<i>` and `rubric`."""
    return f"{pointer}#{role}"
