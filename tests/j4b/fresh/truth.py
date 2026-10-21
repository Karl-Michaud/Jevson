"""The code checker: truth by construction, made exact against the text the judge reads (design §2.1-§2.2).

No rule is decided here; it only proves that each built draft is what its label says (OWNER-DECISIONS item 3).

- **Slots.** Every typed value in a draft sits in a declared slot whose text is exactly one `RENDERINGS` form of it.
- **Guard.** Outside the slots, a draft and every authored string hold no digit, month or month abbreviation,
  weekday, number or ordinal word, currency sign or word, `@`, or token of the synthetic name universe. A form the
  rendering list does not know (`$58`, "fifty-eight dollars", "Oct. 9th") is caught whatever its value.
- **Matching** has token boundaries: no adjacent word character and no digit group running on through `,` or
  `.`, so `58` is not found in `$58,505.47`, nor `8417` in `68417`.
- **I-set.** The injected draft states none of the source's values of the checked kind, in any form, and carries
  its claim; the companion states its kind's values only as values the source does not have.
- **P-set.** A PASS draft states every slot in the source's exact form; a FAIL draft carries exactly one
  violation of its pattern, and every other slot is the source's rendering byte for byte.

`check_row` and `check_string` return the problems; `flag_items` returns the keys of failing items without raising
(`pins.check` calls it for a fixture amendment); `require` raises `FixtureDefect` on the first problem.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from tests.j4b.fresh.drafts import value_from_json
from tests.j4b.fresh.sources import FIRST, LAST, MONTHS, RENDERINGS, FixtureDefect, Value, kind

_NUMBER_WORDS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "million",
    "billion",
    "dozen",
    "first",
    "second",
    "third",
    "fourth",
    "fifth",
    "sixth",
    "seventh",
    "eighth",
    "ninth",
    "tenth",
    "eleventh",
    "twelfth",
    "thirteenth",
    "fourteenth",
    "fifteenth",
    "sixteenth",
    "seventeenth",
    "eighteenth",
    "nineteenth",
    "twentieth",
    "thirtieth",
]
_CALENDAR = [m.lower() for m in MONTHS] + [
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
]
_WEEKDAYS = "monday tuesday wednesday thursday friday saturday sunday mon tue tues wed thu thur thurs fri sat sun"
_CURRENCY = [
    "usd",
    "eur",
    "gbp",
    "jpy",
    "dollar",
    "dollars",
    "cent",
    "cents",
    "euro",
    "euros",
    "pound",
    "pounds",
    "yen",
]
GUARDED = frozenset([*_NUMBER_WORDS, *_CALENDAR, *_WEEKDAYS.split(), *_CURRENCY])
NAME_UNIVERSE = frozenset(n.lower() for n in (*FIRST, *LAST))
_SIGNS = re.compile(r"[\d$€£¥@]")
_WORD = re.compile(r"[A-Za-z]+")


def guard(text: str) -> list[str]:
    """Every guarded token in `text`: any digit, currency sign or `@`, and every banned or name-universe word
    (each part of a hyphenated word counts)."""
    found = [m.group() for m in _SIGNS.finditer(text)]
    for word in _WORD.findall(text):
        lowered = word.lower()
        if lowered in GUARDED or lowered in NAME_UNIVERSE:
            found.append(word)
    return found


def occurs(text: str, rendering: str) -> bool:
    """Whether `rendering` occurs in `text` as a whole token: no word character on either side, and no digit group
    continuing through a `,` or `.`."""
    for m in re.finditer(re.escape(rendering), text):
        before, after = text[: m.start()], text[m.end() :]
        if (before and before[-1].isalnum()) or (after and after[0].isalnum()):
            continue
        if re.search(r"\d[.,]$", before) or re.match(r"[.,]\d", after):
            continue
        return True
    return False


def stated(text: str, value: Value) -> bool:
    return any(occurs(text, r) for r in RENDERINGS(value))


def _slots(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(row["slots"])


def _outside_slots(row: Mapping[str, Any]) -> str:
    text = row["draft"]
    for slot in sorted(_slots(row), key=lambda s: s["start"], reverse=True):
        text = text[: slot["start"]] + " " + text[slot["end"] :]
    return text


def _common(row: Mapping[str, Any]) -> list[str]:
    problems: list[str] = []
    end = -1
    for slot in sorted(_slots(row), key=lambda s: s["start"]):
        value = value_from_json(slot["value"])
        if slot["start"] < end or row["draft"][slot["start"] : slot["end"]] != RENDERINGS(value)[slot["form"]]:
            problems.append(f"slot {slot['slot']} is not its declared rendering")
        end = slot["end"]
    if bad := guard(_outside_slots(row)):
        problems.append(f"guarded tokens outside the slots: {bad}")
    return problems


def _facts(row: Mapping[str, Any]) -> dict[str, tuple[Value, int]]:
    return {slot: (value_from_json(v), int(v["form"])) for slot, v in row["facts"].items()}


def _exact(row: Mapping[str, Any], slot: dict[str, Any]) -> bool:
    facts = _facts(row)
    return slot["slot"] in facts and facts[slot["slot"]] == (value_from_json(slot["value"]), slot["form"])


def check_iset(row: Mapping[str, Any]) -> list[str]:
    """Both drafts of every case are known FAILs: the checked values are absent, or present only as values the
    source does not have (the companion's "differs" rule)."""
    problems = _common(row)
    checked = [v for v, _ in _facts(row).values() if kind(v) == row["checked_kind"]]
    if not checked:
        problems.append("the source states no value of the checked kind")
    if any(stated(row["draft"], v) for v in checked):
        problems.append("the draft states a checked value of the source")
    if row["role"] == "injected" and row["claim"] not in row["draft"]:
        problems.append("the injected draft does not carry its claim")
    others = [s for s in _slots(row) if value_from_json(s["value"]) not in checked and not _exact(row, s)]
    differs = [s for s in others if kind(value_from_json(s["value"])) == row["checked_kind"]]
    if row["role"] == "injected" and others:
        problems.append("a slot of the injected draft is not the source's value in the source's form")
    if row["role"] == "companion" and (len(differs) != len(others) or (row["rule"] == "differs" and not differs)):
        problems.append("the companion departs from the source other than in its checked kind")
    return problems


def _violations(row: Mapping[str, Any]) -> list[str]:
    """Each way the draft departs from the source, as the P-set patterns count them."""
    facts = _facts(row)
    found: list[str] = []
    seen = {s["slot"] for s in _slots(row)}
    for slot in _slots(row):
        if slot["slot"] == "extra":
            found.append("extra")
        elif slot["slot"] not in facts:
            found.append(f"invented:{slot['slot']}")
        elif value_from_json(slot["value"]) != facts[slot["slot"]][0]:
            found.append(f"wrong:{slot['slot']}")
        elif slot["form"] != facts[slot["slot"]][1]:
            found.append(f"form:{slot['slot']}")
    found += [f"missing:{s}" for s in facts if s not in seen and s in row["required"]]
    return found


ALLOWED = {
    "plain": ("missing",),
    "as_given": ("form", "wrong"),
    "negated": ("extra",),
    "disjunction": ("missing", "wrong"),
    "universal": ("missing", "wrong"),
}
"""The one violation a FAIL draft of each pattern carries; a form change is never a universal FAIL, so truth is
the same under the F3 rewrite that drops "as given" (design §3 "Truth form")."""


def check_pset(row: Mapping[str, Any]) -> list[str]:
    problems = _common(row)
    found = _violations(row)
    target = row["target"]
    if row["label"] == "PASS" and found:
        problems.append(f"a PASS draft departs from the source: {found}")
    if row["label"] == "FAIL":
        kinds = [f.split(":")[0] for f in found]
        on_target = all(f == "extra" or f.split(":")[1] in target for f in found)
        if len(found) != 1 or kinds[0] not in ALLOWED[row["pattern"]] or not on_target:
            problems.append(f"a FAIL draft must carry exactly one {ALLOWED[row['pattern']]} violation: {found}")
    absent_branch = row["pattern"] == "disjunction" and row["label"] == "PASS" and target[0] not in row["facts"]
    if absent_branch and row["none_sentence"] not in row["draft"]:
        problems.append("an absence-branch PASS draft does not say the source states none")
    for flag, text in (("benign", row.get("benign_text")), ("targeted_self_claim", row.get("self_claim_text"))):
        if row[flag] and (not text or text not in row["draft"]):
            problems.append(f"{flag} is set but its text is not in the draft")
    return problems


def check_row(row: Mapping[str, Any]) -> list[str]:
    if row["set"] in ("iset", "iset_dev"):
        return check_iset(row)
    if row["set"] in ("pset", "pset_dev"):
        return check_pset(row)
    return []


def check_string(text: str) -> list[str]:
    """An authored string holds no guarded token (its `{placeholders}` aside)."""
    bad = guard(re.sub(r"\{[a-z_]+\}", " ", text))
    return [f"guarded tokens: {bad}"] if bad else []


def flag_items(rows: Mapping[str, Iterable[Mapping[str, Any]]], strings: Mapping[str, str]) -> set[str]:
    """The keys of every row (`<file>#<draft id>`) and authored string (`<set>#<record>.<attribute>`) that fails."""
    flagged = {f"{name}#{row['draft_id']}" for name, file_rows in rows.items() for row in file_rows if check_row(row)}
    return flagged | {key for key, text in strings.items() if check_string(text)}


def require(rows: Mapping[str, Iterable[Mapping[str, Any]]], strings: Mapping[str, str]) -> None:
    """Raise `FixtureDefect` naming the first failing item; the build never drops a case."""
    for name, file_rows in rows.items():
        for row in file_rows:
            if problems := check_row(row):
                raise FixtureDefect(f"{name}#{row['draft_id']}: {problems[0]}")
    for key, text in strings.items():
        if problems := check_string(text):
            raise FixtureDefect(f"{key}: {problems[0]}")
