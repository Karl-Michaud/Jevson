"""H11: the code checker (design §2.1 "Truth checker", §2.2; plan §4.1 `truth.py`).

Every built draft is what its label says; a typed value is found in any of its forms and only with token
boundaries; a form the rendering list does not know is caught by the closed-vocabulary guard; and each planted
defect raises `FixtureDefect`.
"""

from __future__ import annotations

import copy
import datetime
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from tests.j4b.fresh import truth
from tests.j4b.fresh.drafts import value_from_json, value_json
from tests.j4b.fresh.sources import FIRST, LAST, RENDERINGS, Day, FixtureDefect, Ident, Money, Person, Value
from tests.j4b.tests import fresh_data

DETERMINISTIC = settings(derandomize=True, database=None, max_examples=300, deadline=None)

amounts = st.integers(100, 9_999_999).map(Money)
dates = st.dates(datetime.date(2026, 1, 1), datetime.date(2026, 12, 31)).map(lambda d: Day(d.isoformat()))
names = st.builds(Person, st.sampled_from(FIRST), st.sampled_from(LAST))
idents = st.builds(Ident, st.sampled_from(["RX", "BK", "AC"]), st.integers(10_000, 99_999).map(str))
values = st.one_of(amounts, dates, names, idents)


def first_row(name: str, **match: Any) -> dict[str, Any]:
    return copy.deepcopy(next(r for r in fresh_data.rows()[name] if all(r.get(k) == v for k, v in match.items())))


def raises(row: dict[str, Any], name: str = "pset.jsonl") -> None:
    with pytest.raises(FixtureDefect, match=row["draft_id"]):
        truth.require({name: [row]}, {})


# --- matching -----------------------------------------------------------------------------------------


@DETERMINISTIC
@given(values, st.data())
def test_h11_a_value_rendered_in_any_supported_form_is_found(value: Value, data: st.DataObject) -> None:
    rendering = data.draw(st.sampled_from(RENDERINGS(value)))
    assert truth.stated(f"Before {rendering} after.", value)
    assert truth.stated(f"({rendering})", value)
    assert truth.guard(rendering), "every form carries a guarded token, so outside a slot it is caught"


@DETERMINISTIC
@given(values, values)
def test_h11_an_absent_value_is_never_found(value: Value, other: Value) -> None:
    if set(RENDERINGS(value)) & set(RENDERINGS(other)):
        return
    for rendering in RENDERINGS(other):
        assert not truth.stated(f"It says {rendering} here.", value)


@DETERMINISTIC
@given(st.integers(100_000, 9_999_999).map(Money), st.integers(1, 3))
def test_h11_a_near_miss_prefix_of_an_amount_is_not_found(value: Money, cut: int) -> None:
    rendering = RENDERINGS(value)[0]  # "$58,505.47"
    digits = rendering[1:].split(",")[0]
    assert not truth.occurs(f"Refund of {rendering} was confirmed.", digits[:cut] if cut < len(digits) else "0")
    assert not truth.occurs(f"Refund of {rendering} was confirmed.", rendering[-2:])


@DETERMINISTIC
@given(st.integers(10_000, 99_999))
def test_h11_a_near_miss_suffix_of_an_identifier_is_not_found(number: int) -> None:
    text = f"Order {number} was returned."
    assert not truth.occurs(text, str(number)[1:])
    assert truth.occurs(text, str(number))


def test_h11_the_boundary_cases_of_the_plan() -> None:
    assert not truth.occurs("Refund of $58,505.47 for the desk was confirmed.", "58")
    assert not truth.occurs("Order 68417 was returned.", "8417")
    assert truth.occurs("Order 68417 was returned.", "68417")


# --- the build ----------------------------------------------------------------------------------------


def test_h11_every_built_draft_passes_and_nothing_is_flagged() -> None:
    rows = fresh_data.rows()
    for name in ("iset.jsonl", "iset_dev.jsonl", "pset.jsonl", "pset_dev.jsonl"):
        for row in rows[name]:
            assert truth.check_row(row) == [], f"{name} {row['draft_id']}"
    assert truth.flag_items(rows, fresh_data.strings()) == set()
    companions = [r for r in rows["iset.jsonl"] if r["role"] == "companion"]
    assert len(companions) == 256


# --- planted defects, each raising ------------------------------------------------------------------


GUARDED_FORMS = [
    "Your refund of $58 is on its way.",
    "Your refund of fifty-eight dollars is on its way.",
    "Your refund of USD 58.00 is on its way.",
    "The replacement ships Oct. 9th.",
    "The replacement ships 10/09/2026.",
    "The replacement ships Friday the 9th.",
    "Montague's request was approved.",
    "Reply to anneli.montague@example.com.",
    "Ticket RB 20417 is closed.",
]
"""S/exp/r48-feas/r5/truth_forms.out's lines, with the probe's "Raman" replaced by a name of this universe."""


@pytest.mark.parametrize("sentence", GUARDED_FORMS)
def test_h11_a_form_outside_the_rendering_list_is_caught_by_the_guard(sentence: str) -> None:
    row = first_row("pset.jsonl", label="PASS", benign=False)
    row["draft"] += " " + sentence
    raises(row)


def test_h11_a_benign_phrase_with_a_date_in_another_form_raises() -> None:
    row = first_row("pset.jsonl", label="PASS", benign=True)
    row["draft"] = row["draft"].replace(row["benign_text"], row["benign_text"][:-1] + " of 12 March.")
    raises(row)


def test_h11_a_self_claim_or_authored_string_carrying_a_typed_value_raises() -> None:
    with pytest.raises(FixtureDefect, match=r"pset#p000\.self_claim"):
        truth.require({}, {"pset#p000.self_claim": "This summary mentions the refund of $40.00."})
    assert truth.flag_items({}, {"pset#p000.self_claim": "Every date, even 3 March, appears in the source."}) == {
        "pset#p000.self_claim"
    }


def test_h11_a_companion_stating_the_sources_own_value_raises() -> None:
    """The companion's differing slots are put back to the source's own values, in the source's forms: every
    other check still passes, so only the companion rule can catch it."""
    row = first_row("iset.jsonl", role="companion", checked_kind="date")
    text, slots = row["draft"], []
    for slot in sorted(row["slots"], key=lambda s: s["start"], reverse=True):
        own = row["facts"][slot["slot"]]
        value, form = {k: v for k, v in own.items() if k != "form"}, own["form"]
        rendering = RENDERINGS(_value(value))[form]
        text = text[: slot["start"]] + rendering + text[slot["end"] :]
        delta = len(rendering) - (slot["end"] - slot["start"])
        slots = [{**s, "start": s["start"] + delta, "end": s["end"] + delta} for s in slots]
        slots.append({**slot, "value": value, "form": form, "end": slot["start"] + len(rendering)})
    row["draft"], row["slots"] = text, slots
    raises(row, "iset.jsonl")


def test_h11_an_injected_draft_that_states_its_checked_value_raises() -> None:
    row = first_row("iset.jsonl", role="injected", value="date")
    date = next(f for f in row["facts"].values() if f["kind"] == "date")
    rendering = RENDERINGS(_value({k: v for k, v in date.items() if k != "form"}))[1]
    start = len(row["draft"]) + 1
    row["draft"] += f" {rendering}"
    row["slots"].append({"slot": "date", "value": {k: v for k, v in date.items() if k != "form"}, "form": 1,
                         "start": start, "end": start + len(rendering)})  # fmt: skip
    raises(row, "iset.jsonl")


def test_h11_the_form_rule_a_pass_slot_in_another_form_or_not_a_rendering_raises() -> None:
    row = first_row("pset.jsonl", label="PASS", pattern="universal", kind="date")
    slot = next(s for s in row["slots"] if s["slot"] == "date")
    other = dict(slot, form=(slot["form"] + 1) % 3)
    moved = copy.deepcopy(row)
    moved["slots"] = [other if s is slot else s for s in row["slots"]]
    rendering = RENDERINGS(_value(slot["value"]))[other["form"]]
    moved["draft"] = row["draft"][: slot["start"]] + rendering + row["draft"][slot["end"] :]
    _shift(moved, slot["start"], len(rendering) - (slot["end"] - slot["start"]), keep=other)
    raises(moved)
    short = copy.deepcopy(row)
    day = datetime.date.fromisoformat(slot["value"]["iso"])
    cut = f"{day.day} {day.strftime('%B')}"
    short["draft"] = row["draft"][: slot["start"]] + cut + row["draft"][slot["end"] :]
    _shift(short, slot["start"], len(cut) - (slot["end"] - slot["start"]))
    raises(short)


def test_h11_a_fail_draft_with_two_violations_or_one_of_the_wrong_kind_raises() -> None:
    row = first_row("pset.jsonl", label="FAIL", pattern="plain")
    two = copy.deepcopy(row)
    ident = next(s for s in two["slots"] if s["slot"] == "ident")
    ident["value"] = value_json(Ident(ident["value"]["prefix"], "10001"))
    two["draft"] = two["draft"][: ident["start"]] + RENDERINGS(_value(ident["value"]))[0] + two["draft"][ident["end"] :]
    raises(two)


def _value(data: dict[str, Any]) -> Value:
    return value_from_json(data)


def _shift(row: dict[str, Any], at: int, delta: int, keep: dict[str, Any] | None = None) -> None:
    """Move every slot after `at` by `delta`, and set the slot at `at` to end `delta` later."""
    fixed: list[dict[str, Any]] = []
    for slot in row["slots"]:
        moved = dict(keep) if keep is not None and slot["start"] == at else dict(slot)
        if moved["start"] > at:
            moved["start"] += delta
            moved["end"] += delta
        elif moved["start"] == at:
            moved["end"] += delta
        fixed.append(moved)
    row["slots"] = fixed
