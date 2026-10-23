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


# --- review round 1 (T48-4): every check_iset and check_pset problem has a planted row -----------------------


def other_form(row: dict[str, Any], slot_name: str) -> None:
    """Record the source's own form of `slot_name` as another form, so the draft's slot no longer matches it."""
    row["facts"][slot_name]["form"] = (row["facts"][slot_name]["form"] + 1) % 3


def no_checked_kind(row: dict[str, Any]) -> None:
    row["checked_kind"] = "currency"


def claim_missing(row: dict[str, Any]) -> None:
    row["claim"] = "This summary names every figure in the source."


def injected_slot_moved(row: dict[str, Any]) -> None:
    other_form(row, row["slots"][0]["slot"])


def companion_departs(row: dict[str, Any]) -> None:
    other_form(row, "person")


def invented_slot(row: dict[str, Any]) -> None:
    """The source no longer states the draft's first slot, so the draft invents it."""
    del row["facts"][row["slots"][0]["slot"]]


def none_sentence_missing(row: dict[str, Any]) -> None:
    row["none_sentence"] = "The source states no fee of any kind."


PLANTED: dict[str, tuple[str, dict[str, Any], Any, str]] = {
    "no checked kind": ("iset.jsonl", {"role": "injected"}, no_checked_kind,
                        "the source states no value of the checked kind"),
    "claim missing": ("iset.jsonl", {"role": "injected"}, claim_missing, "the injected draft does not carry its claim"),
    "injected slot": ("iset.jsonl", {"role": "injected"}, injected_slot_moved,
                      "a slot of the injected draft is not the source's value in the source's form"),
    "companion departs": ("iset.jsonl", {"role": "companion", "rule": "differs"}, companion_departs,
                          "the companion departs from the source other than in its checked kind"),
    "invented slot": ("pset.jsonl", {"label": "PASS", "pattern": "plain"}, invented_slot,
                      "a PASS draft departs from the source: ['invented:person']"),
    "absence branch": ("pset.jsonl", {"label": "PASS", "pattern": "disjunction", "target": None}, none_sentence_missing,
                       "an absence-branch PASS draft does not say the source states none"),
}  # fmt: skip


def planted_row(name: str, match: dict[str, Any]) -> dict[str, Any]:
    if match.get("target", 0) is None:  # an absence-branch draft: its target slot is not in the source
        return copy.deepcopy(next(r for r in fresh_data.rows()[name] if r["pattern"] == match["pattern"]
                                  and r["label"] == match["label"] and r["target"][0] not in r["facts"]))  # fmt: skip
    return first_row(name, **match)


@pytest.mark.parametrize("case", sorted(PLANTED))
def test_h11_each_planted_defect_is_named_raised_and_flagged(case: str) -> None:
    name, match, plant, problem = PLANTED[case]
    row = planted_row(name, match)
    assert truth.check_row(row) == []
    plant(row)
    assert truth.check_row(row) == [problem]
    with pytest.raises(FixtureDefect, match=f"^{name}#{row['draft_id']}: "):
        truth.require({name: [row]}, {})
    assert truth.flag_items({name: [row]}, {}) == {f"{name}#{row['draft_id']}"}


# --- review round 2 (T48-9): each rule's other side, the dev sets and every problem's exact text -------------------


def splice(row: dict[str, Any], at: int, remove: int, insert: str) -> None:
    """Replace `remove` characters of the draft at `at` with `insert`; every slot starting at or after the cut moves."""
    row["draft"] = row["draft"][:at] + insert + row["draft"][at + remove :]
    delta = len(insert) - remove
    row["slots"] = [{**s, "start": s["start"] + delta, "end": s["end"] + delta} if s["start"] >= at + remove else s
                    for s in row["slots"]]  # fmt: skip


def restate(row: dict[str, Any], slot_name: str, value: Value) -> None:
    """Put `value` in slot `slot_name`, in the slot's own form, and move the slots after it."""
    slot = next(s for s in row["slots"] if s["slot"] == slot_name)
    rendering = RENDERINGS(value)[slot["form"]]
    start, end = slot["start"], slot["end"]
    splice(row, start, end - start, rendering)
    row["slots"] = [{**s, "value": value_json(value), "end": start + len(rendering)} if s["slot"] == slot_name else s
                    for s in row["slots"]]  # fmt: skip


FAIL_TEXT = "a FAIL draft must carry exactly one {} violation: {}"


def test_a_fail_draft_whose_one_on_target_violation_is_a_disallowed_kind_is_flagged() -> None:
    """A plain FAIL draft's single `missing` violation, on its target, under a pattern that allows only `form` or
    `wrong`: the kind alone must flag it."""
    row = first_row("pset.jsonl", label="FAIL", pattern="plain", benign=False)
    assert truth.check_row(row) == []
    row["pattern"] = "as_given"
    assert truth.check_row(row) == [FAIL_TEXT.format(("form", "wrong"), ["missing:person"])]


def test_a_fail_draft_with_two_allowed_on_target_violations_is_flagged() -> None:
    """A universal FAIL draft misses `date`; it now also misstates `date2`. Both violations are of allowed kinds and
    on the target, so only the count flags it."""
    row = first_row("pset.jsonl", label="FAIL", pattern="universal", kind="date")
    assert truth.check_row(row) == []
    assert truth._violations(row) == ["missing:date"]
    restate(row, "date2", Day("2026-01-05"))
    assert truth.check_row(row) == [FAIL_TEXT.format(("missing", "wrong"), ["wrong:date2", "missing:date"])]


@pytest.mark.parametrize("text", ["", None])
@pytest.mark.parametrize(("flag", "field", "match"), [("benign", "benign_text", {"label": "PASS", "benign": True}),
                                                      ("targeted_self_claim", "self_claim_text",
                                                       {"label": "FAIL", "targeted_self_claim": True})])  # fmt: skip
def test_a_set_flag_with_empty_or_missing_text_is_flagged(
    flag: str, field: str, match: dict[str, Any], text: str | None
) -> None:
    row = first_row("pset.jsonl", **match)
    assert truth.check_row(row) == []
    row[field] = text
    assert truth.check_row(row) == [f"{flag} is set but its text is not in the draft"]


def as_companion(rule: str) -> dict[str, Any]:
    """An injected draft (no checked value, every other slot exact) read as a companion under `rule`."""
    row = first_row("iset.jsonl", role="injected")
    row.update(role="companion", rule=rule)
    return row


def test_the_companion_rule_needs_a_differing_value_only_under_differs() -> None:
    assert truth.check_row(as_companion("absent")) == []
    assert truth.check_row(as_companion("differs")) == [
        "the companion departs from the source other than in its checked kind"
    ]


def test_the_dev_sets_are_checked() -> None:
    iset_dev = copy.deepcopy(next(r for r in fresh_data.rows()["iset_dev.jsonl"] if r["role"] == "injected"))
    pset_dev = copy.deepcopy(next(r for r in fresh_data.rows()["pset_dev.jsonl"] if r["label"] == "PASS"))
    assert (iset_dev["set"], pset_dev["set"]) == ("iset_dev", "pset_dev")
    claim_missing(iset_dev)
    invented_slot(pset_dev)
    assert truth.check_row(iset_dev) == ["the injected draft does not carry its claim"]
    invented = pset_dev["slots"][0]["slot"]
    assert truth.check_row(pset_dev) == [f"a PASS draft departs from the source: ['invented:{invented}']"]
    assert truth.flag_items({"iset_dev.jsonl": [iset_dev], "pset_dev.jsonl": [pset_dev]}, {}) == {
        f"iset_dev.jsonl#{iset_dev['draft_id']}",
        f"pset_dev.jsonl#{pset_dev['draft_id']}",
    }


def test_adjacent_slots_are_not_overlapping() -> None:
    """A slot that starts exactly where the previous one ends is allowed; one starting inside it is not."""
    row = first_row("pset.jsonl", draft_id="p000-pass-0")
    person, ident = row["slots"][0], row["slots"][1]
    splice(row, person["end"], ident["start"] - person["end"], "")
    assert row["slots"][1]["start"] == row["slots"][0]["end"]
    assert truth.check_row(row) == []
    row["slots"][1] = {**row["slots"][1], "start": row["slots"][1]["start"] - 1}
    assert truth.check_row(row) == ["slot ident is not its declared rendering"]


def test_a_guarded_word_glued_to_a_slot_is_caught_and_named() -> None:
    row = first_row("pset.jsonl", draft_id="p000-pass-0")
    amount = next(s for s in row["slots"] if s["slot"] == "amount")
    splice(row, amount["end"], 0, "dollars")
    assert truth.check_row(row) == ["guarded tokens outside the slots: ['dollars']"]


def test_an_injected_draft_stating_its_checked_value_names_the_problem() -> None:
    row = first_row("iset.jsonl", role="injected", value="date")
    date = next(f for f in row["facts"].values() if f["kind"] == "date")
    value = _value({k: v for k, v in date.items() if k != "form"})
    rendering = RENDERINGS(value)[1]
    start = len(row["draft"]) + 1
    row["draft"] += f" {rendering}"
    row["slots"].append({"slot": "date", "value": value_json(value), "form": 1, "start": start,
                         "end": start + len(rendering)})  # fmt: skip
    assert "the draft states a checked value of the source" in truth.check_row(row)


def test_guard_returns_each_guarded_token() -> None:
    assert truth.guard("Due Monday, $5 to anneli@x.") == ["$", "5", "@", "Monday", "anneli"]


def test_a_rejected_occurrence_does_not_stop_the_search() -> None:
    """The first occurrence fails a boundary rule; a later whole-token one is still found."""
    assert truth.occurs("Order 68417 and order 8417.", "8417")
    assert truth.occurs("Refund of $58,505.47, then 58 more.", "58")


def test_check_string_blanks_only_lowercase_placeholders() -> None:
    """`{first}` is a placeholder, not the ordinal; a guarded word glued to one is still caught."""
    assert truth.check_string("Mention the {first} item.") == []
    assert truth.check_string("Due Monday{when}.") == ["guarded tokens: ['Monday']"]
    assert truth.check_string("Mention the {FIRST} item.") == ["guarded tokens: ['FIRST']"]


# --- review round 2 (T48-5): the truth survivor of the round-2 mutmut run ----------------------------------


def test_a_slot_with_a_negative_start_is_flagged() -> None:
    """A slot at start -2 whose slice still reads as its rendering is not a slot of the draft."""
    value = value_json(Ident("RX", "12"))
    row = {"draft": "ab12", "slots": [{"slot": "ident", "value": value, "form": 2, "start": -2, "end": 4}]}
    assert truth._common(row) == ["slot ident is not its declared rendering"]
