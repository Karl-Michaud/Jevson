"""The result type, exactly as DESIGN §8.1 pins it. Every field is always present."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from jevson.types import (
    Absent,
    Cost,
    DecidedBy,
    Decision,
    JSONValue,
    Overflow,
    Provenance,
    Rejection,
    Unresolved,
    Violation,
)


@dataclass(frozen=True)
class Result:
    """The outcome of one call: the assembled value and, for every field, how it was decided or why not."""

    value: Mapping[str, JSONValue]
    satisfies_schema: bool
    provenance: Mapping[str, Provenance] = field(default_factory=dict[str, Provenance])
    decided_by: Mapping[str, DecidedBy] = field(default_factory=dict[str, DecidedBy])
    decisions: Mapping[str, Decision] = field(default_factory=dict[str, Decision])
    unresolved: tuple[Unresolved, ...] = ()
    violations: tuple[Violation, ...] = ()
    absent: tuple[Absent, ...] = ()
    ungated: tuple[str, ...] = ()
    overflow: tuple[Overflow, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    cost: Cost = field(default_factory=Cost)
    model: tuple[str, ...] = ()
    versions: Mapping[str, str] = field(default_factory=dict[str, str])

    @property
    def complete(self) -> bool:
        """True exactly when nothing is unresolved; `absent` fields do not count (DESIGN §6.1)."""
        return not self.unresolved
