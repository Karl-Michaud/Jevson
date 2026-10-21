"""Drafts assembled by code from a synthetic source's facts, with every typed value in a declared slot (design §2.2).

A draft is a list of the domain's fact sentences (`sources.DOMAINS`), each stating its value, or only its topic, or
left out, plus any whole sentences a set adds (a self-claim, a benign self-description, an added value). Each value
is rendered by `sources.RENDERINGS` and recorded as a slot with its span, so `truth.py` can check the draft against
the text the judge reads, never against a description of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from tests.j4b.fresh.sources import DOMAINS, RENDERINGS, Day, Ident, Money, Person, Source, Value, kind


@dataclass(frozen=True)
class Slot:
    slot: str
    kind: str
    value: Value
    form: int
    start: int
    end: int


@dataclass
class Draft:
    """A draft's text and its slots, built left to right."""

    text: str = ""
    slots: list[Slot] = field(default_factory=list[Slot])

    def sentence(self, template: str, *, slot: str = "", value: Value | None = None, form: int = 0) -> None:
        """Append one sentence; `{v}` in `template` is `value` rendered in `form` and recorded as `slot`."""
        before, _, after = template.partition("{v}")
        self.text += (" " if self.text else "") + before
        if value is not None:
            rendering = RENDERINGS(value)[form]
            start = len(self.text)
            self.text += rendering
            self.slots.append(Slot(slot, kind(value), value, form, start, len(self.text)))
        self.text += after


@dataclass(frozen=True)
class Plan:
    """How a draft departs from the source: facts left out, facts stated by topic only, facts stated with another
    value or form, sentences added, and absent optional facts said to be absent."""

    omit: frozenset[str] = frozenset()
    topic_only: frozenset[str] = frozenset()
    override: Mapping[str, tuple[Value, int]] = field(default_factory=dict[str, tuple[Value, int]])
    extra: Sequence[Value] = ()
    say_none: frozenset[str] = frozenset()
    lead: str = ""
    tail: Sequence[str] = ()


AS_GIVEN = Plan()
"""The plan of a draft that states every fact of its source as the source states it."""


def summary(source: Source, plan: Plan = AS_GIVEN) -> Draft:
    """The draft of `source` under `plan`, facts in the domain's order."""
    spec = DOMAINS[source.domain]
    draft = Draft()
    if plan.lead:
        draft.sentence(plan.lead)
    for fact in spec.facts:
        slot = fact.slot
        if slot in plan.omit or (slot not in source.facts and slot not in plan.say_none):
            continue
        if slot not in source.facts:
            draft.sentence(spec.none_sentence[slot])
        elif slot in plan.topic_only:
            draft.sentence(fact.topic_only.replace("{item}", source.item))
        else:
            value, form = plan.override.get(slot, (source.facts[slot], source.forms[slot]))
            draft.sentence(fact.with_value.replace("{item}", source.item), slot=slot, value=value, form=form)
    for value in plan.extra:
        draft.sentence(spec.extra[kind(value)], slot="extra", value=value, form=0)
    for text in plan.tail:
        draft.sentence(text)
    return draft


def value_json(value: Value) -> dict[str, Any]:
    if isinstance(value, Money):
        return {"kind": "amount", "cents": value.cents}
    if isinstance(value, Day):
        return {"kind": "date", "iso": value.iso}
    if isinstance(value, Person):
        return {"kind": "name", "first": value.first, "last": value.last}
    return {"kind": "identifier", "prefix": value.prefix, "digits": value.digits}


def value_from_json(data: Mapping[str, Any]) -> Value:
    k = data["kind"]
    if k == "amount":
        return Money(int(data["cents"]))
    if k == "date":
        return Day(str(data["iso"]))
    if k == "name":
        return Person(str(data["first"]), str(data["last"]))
    return Ident(str(data["prefix"]), str(data["digits"]))


def slots_json(draft: Draft) -> list[dict[str, Any]]:
    return [
        {"slot": s.slot, "value": value_json(s.value), "form": s.form, "start": s.start, "end": s.end}
        for s in draft.slots
    ]


def source_json(source: Source) -> dict[str, Any]:
    """A source as fixture rows carry it: its text, and each stated fact with the form the text uses."""
    return {
        "domain": source.domain,
        "source": source.text,
        "facts": {slot: {**value_json(v), "form": source.forms[slot]} for slot, v in source.facts.items()},
    }
