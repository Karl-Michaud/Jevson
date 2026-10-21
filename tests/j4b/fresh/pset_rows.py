"""The P-set's rows (design §2.2): each template pair's 6 PASS and 6 FAIL drafts, each on its own source.

A PASS draft states every fact in the source's exact form; 3 of the 6 carry the pair's benign self-description at
its position. A FAIL draft carries exactly one violation of its pattern; 4 of the 6 carry the pair's targeted
self-claim. The violation of each pattern (`truth.ALLOWED`) keeps truth the same under F0 and F1.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import Any

from tests.j4b.fresh.drafts import Plan, slots_json, source_json, summary
from tests.j4b.fresh.iset_rows import Sources
from tests.j4b.fresh.sources import DOMAINS, RENDERINGS, SEED, Source, Value, different, draw_value, kind

Row = dict[str, Any]
PASS_DRAFTS = FAIL_DRAFTS = 6
BENIGN_DRAFTS, SELF_CLAIM_DRAFTS = 3, 4


def benign_text(record: Mapping[str, Any], source: Source) -> str:
    return str(record["benign"]).replace("{object}", str(record["benign_object"]).replace("{item}", source.item))


def _other_form(source: Source, slot: str) -> int:
    return (source.forms[slot] + 1) % len(RENDERINGS(source.facts[slot]))


def _wrong(rng: random.Random, source: Source, slot: str) -> tuple[Value, int]:
    same = [v for v in source.facts.values() if kind(v) == kind(source.facts[slot])]
    return different(rng, source.facts[slot], same, source.domain), source.forms[slot]


def violation(record: Mapping[str, Any], source: Source, i: int, rng: random.Random) -> tuple[Plan, str]:
    """The `i`-th FAIL draft's one violation of the pair's pattern."""
    pattern, target = record["pattern"], list(record["target"])
    if pattern == "plain":
        return Plan(topic_only=frozenset(target)), f"missing:{target[0]}"
    if pattern == "negated":
        same = [v for v in source.facts.values() if kind(v) == record["kind"]]
        extra = different(rng, draw_value(rng, record["kind"], source.domain), same, source.domain)
        return Plan(extra=(extra,)), "extra"
    slot = target[(i // 2) % len(target)] if pattern == "universal" else target[0]
    if pattern == "as_given" and i % 2 == 0:
        return Plan(override={slot: (source.facts[slot], _other_form(source, slot))}), f"form:{slot}"
    if pattern != "as_given" and i % 2 == 0:
        return Plan(topic_only=frozenset({slot})), f"missing:{slot}"
    return Plan(override={slot: _wrong(rng, source, slot)}), f"wrong:{slot}"


def _row(
    record: Mapping[str, Any], pair: str, draft_id: str, source: Source, *, plan: Plan, extra: Mapping[str, Any]
) -> Row:
    draft = summary(source, plan)
    target = list(record["target"])
    present = [t for t in target if t in source.facts]
    return {
        "set": extra["set"], "draft_id": draft_id, "pair": pair, "pattern": record["pattern"],
        "stratum": record["pattern"], "target": target, "kind": record.get("kind"),
        "required": present if record["pattern"] != "negated" else [],
        "criterion_f0": record["f0"], "criterion_f1": record["f1"], **source_json(source),
        "draft": draft.text, "slots": slots_json(draft),
        "none_sentence": DOMAINS[source.domain].none_sentence.get(target[0]) if target else None,
        **{k: v for k, v in extra.items() if k != "set"},
    }  # fmt: skip


def pair_rows(set_name: str, pair: str, record: Mapping[str, Any], sources: Sources, rng: random.Random) -> list[Row]:
    domain, dev = str(record["domain"]), set_name == "pset_dev"
    rows: list[Row] = []
    for i in range(PASS_DRAFTS):
        absent = list(record["target"]) if record["pattern"] == "disjunction" and i >= PASS_DRAFTS // 2 else []
        source = sources.draw(rng, domain, dev=dev, absent=absent)
        benign = i < BENIGN_DRAFTS
        text = benign_text(record, source) if benign else ""
        opening = record["benign_position"] == "opening"
        plan = Plan(say_none=frozenset(absent), lead=text if benign and opening else "",
                    tail=(text,) if benign and not opening else ())  # fmt: skip
        rows.append(_row(record, pair, f"{pair}-pass-{i}", source, plan=plan, extra={
            "set": set_name, "label": "PASS", "benign": benign, "benign_text": text or None,
            "targeted_self_claim": False, "self_claim_text": None, "violation": None}))  # fmt: skip
    for i in range(FAIL_DRAFTS):
        source = sources.draw(rng, domain, dev=dev)
        plan, broken = violation(record, source, i, rng)
        claimed = i < SELF_CLAIM_DRAFTS
        plan = Plan(plan.omit, plan.topic_only, plan.override, plan.extra, plan.say_none,
                    tail=(str(record["self_claim"]),) if claimed else ())  # fmt: skip
        rows.append(_row(record, pair, f"{pair}-fail-{i}", source, plan=plan, extra={
            "set": set_name, "label": "FAIL", "benign": False, "benign_text": None, "targeted_self_claim": claimed,
            "self_claim_text": record["self_claim"] if claimed else None, "violation": broken}))  # fmt: skip
    return rows


def pset_rows(records: Mapping[str, Mapping[str, Any]], sources: Sources) -> dict[str, list[Row]]:
    """`pset.jsonl` (128 pairs) and `pset_dev.jsonl` (8 pairs), 12 drafts each."""
    out: dict[str, list[Row]] = {}
    for name, prefix in (("pset.jsonl", "p"), ("pset_dev.jsonl", "q")):
        rng = random.Random(f"{SEED}:{name}")
        out[name] = [
            row
            for pair in sorted(k for k in records if k.startswith(prefix))
            for row in pair_rows(name.removesuffix(".jsonl"), pair, records[pair], sources, rng)
        ]
    return out
