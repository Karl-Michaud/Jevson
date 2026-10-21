"""The I-set's rows (design §2.1): every case of every cell, an injected draft beside its clean companion.

The injected draft states none of the source's values of the cell's kind (by topic only, or not at all, per the
cell's topic factor) and ends with the cell's claim. The companion states its own kind's values only as values the
source does not have, so it fails its own criterion. Both are known FAILs.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from typing import Any

from tests.j4b.fresh.drafts import Plan, slots_json, source_json, summary
from tests.j4b.fresh.sources import DOMAINS, SEED, Source, different, kind, make_source

Row = dict[str, Any]
FACTORS = ("cell_index", "verb", "echo", "topic", "value", "position", "domain_pair")


class Sources:
    """Distinct sources across every set: a drawn source whose text was already used is drawn again."""

    def __init__(self) -> None:
        self.used: set[str] = set()

    def draw(self, rng: random.Random, domain: str, *, dev: bool, absent: Sequence[str] = ()) -> Source:
        spec = DOMAINS[domain]
        while True:
            source = make_source(rng, domain, spec.dev_items if dev else spec.items, absent)
            if source.text not in self.used:
                self.used.add(source.text)
                return source


def _injected(source: Source, value_kind: str, topic: str, claim: str) -> Plan:
    slots = frozenset(s for s, v in source.facts.items() if kind(v) == value_kind)
    return Plan(omit=frozenset() if topic == "yes" else slots, topic_only=slots if topic == "yes" else frozenset(),
                tail=(claim,))  # fmt: skip


def _companion(rng: random.Random, source: Source, value_kind: str) -> Plan:
    same = [v for v in source.facts.values() if kind(v) == value_kind]
    override = {
        slot: (different(rng, value, same, source.domain), source.forms[slot])
        for slot, value in source.facts.items()
        if kind(value) == value_kind
    }
    return Plan(override=override)


def _row(set_name: str, draft_id: str, source: Source, plan: Plan, extra: Mapping[str, Any]) -> Row:
    draft = summary(source, plan)
    return {"set": set_name, "draft_id": draft_id, **source_json(source), "draft": draft.text,
            "slots": slots_json(draft), "label": "FAIL", **extra}  # fmt: skip


def case_rows(set_name: str, case_id: str, record: Mapping[str, Any], source: Source, rng: random.Random) -> list[Row]:
    """The injected and companion rows of one case."""
    shared = {"cell": case_id.rsplit("-", 1)[0], "case": case_id, **{f: record[f] for f in FACTORS if f in record}}
    injected = _row(
        set_name, f"{case_id}-inj", source, _injected(source, record["value"], record["topic"], record["claim"]),
        {**shared, "role": "injected", "criterion": record["criterion"], "checked_kind": record["value"],
         "rule": "absent", "claim": record["claim"]},
    )  # fmt: skip
    companion = _row(
        set_name, f"{case_id}-com", source, _companion(rng, source, record["companion_kind"]),
        {**shared, "role": "companion", "criterion": record["companion"], "checked_kind": record["companion_kind"],
         "rule": "differs"},
    )  # fmt: skip
    return [injected, companion]


def iset_rows(records: Mapping[str, Mapping[str, Any]], sources: Sources) -> dict[str, list[Row]]:
    """`iset.jsonl` (120 cells x 2 cases, then the replica's 16) and `iset_dev.jsonl` (32 cells x 2 cases)."""
    out: dict[str, list[Row]] = {"iset.jsonl": [], "iset_dev.jsonl": []}
    for name, prefix, dev in (("iset.jsonl", "c", False), ("iset_dev.jsonl", "d", True)):
        rng = random.Random(f"{SEED}:{name}")
        for cell_id in sorted(k for k in records if k.startswith(prefix)):
            record = records[cell_id]
            for letter, domain in zip("ab", record["domain_pair"], strict=True):
                source = sources.draw(rng, domain, dev=dev)
                out[name] += case_rows(name.removesuffix(".jsonl"), f"{cell_id}-{letter}", record, source, rng)
    replica = records["replica"]
    rng = random.Random(f"{SEED}:replica")
    for i in range(int(replica["cases"])):
        source = sources.draw(rng, str(replica["domain"]), dev=False)
        out["iset.jsonl"] += case_rows("iset", f"replica-{i:02d}", replica, source, rng)
    return out
