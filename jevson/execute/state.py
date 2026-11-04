"""The level state: the one shared `input` every question in a request reads (DESIGN §5.2).

`{"source": <text>}` plus, once a step has produced one, `"drafts": {<step node id>: <draft>}`. Every
collection is an object keyed by opaque ids, never a list, so a question can only name an entry by
its key (R13). It is serialised the way the Phase 0r probes sent it: JSON text, `ensure_ascii=False`,
`source` first and drafts in id order, so identical inputs give byte-identical states.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from jevson.types import JSONValue


@dataclass(frozen=True)
class LevelState:
    source: str
    drafts: Mapping[str, JSONValue] = field(default_factory=dict[str, JSONValue])

    def __post_init__(self) -> None:
        for key, draft in self.drafts.items():
            if _has_list(draft):
                raise ValueError(f"draft {key!r} holds a list; state collections are keyed objects (R13)")

    def serialise(self) -> str:
        state: dict[str, JSONValue] = {"source": self.source}
        if self.drafts:
            state["drafts"] = {key: self.drafts[key] for key in sorted(self.drafts)}
        return json.dumps(state, ensure_ascii=False)


def _has_list(value: JSONValue) -> bool:
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return any(_has_list(child) for child in value.values())
    return False
