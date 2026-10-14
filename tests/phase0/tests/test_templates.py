from __future__ import annotations

import pathlib
import re

import pytest

from tests.phase0 import templates as T

ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_version_and_exact_complete_value_wording():
    assert T.QUESTION_TEMPLATE_VERSION == "1.0.0"
    q, ids = T.candidate_question("billing address", "Bill to: 1 Main St", [(9, 18)])
    assert q["instructions"] == (
        "Which of these is the complete billing address as written in the source? A partial value - for example a "
        "street without its city, or a date without its year - is not acceptable.")
    assert q["criteria"]["none_of_these"] == (
        "None of the other options is the complete billing address as written in the source; a partial value "
        "does not count.")
    assert ids == ["c0", "none_of_these"] and q["type"] == "choice"


def test_matches_pilot_P18_bytes():
    # probe_complete_value.py W1, with field = "delivery address"
    field = "delivery address"
    pilot_ins = (f"Which of these is the complete {field} as written in the source? A partial value - for example a street "
                 f"without its city, or a date without its year - is not acceptable.")
    pilot_none = f"None of the other options is the complete {field} as written in the source; a partial value does not count."
    assert T.CANDIDATE_INSTRUCTIONS.format(label=field) == pilot_ins
    assert T.NONE_OF_THESE_DESCRIPTION.format(label=field) == pilot_none


def test_no_negation_in_question_templates():
    for t in (T.CANDIDATE_INSTRUCTIONS, T.PAIR_INSTRUCTIONS, T.ENUM_INSTRUCTIONS, T.MEMBERSHIP_INSTRUCTIONS,
              T.ORDINAL_INSTRUCTIONS, T.UNION_INSTRUCTIONS, T.CRITERION_INSTRUCTIONS):
        assert not re.search(r"\b(not|never|no)\b", t.split("?")[0], re.I), t


def test_option_descriptions_bare_and_in_context():
    src = "Total: $5.00\nPaid: $5.00 on Friday. Tax $0.40."
    s1 = src.index("$5.00")
    s2 = src.index("$5.00", s1 + 1)
    s3 = src.index("$0.40")
    assert T.option_description(src, s3, s3 + 5) == '"$0.40"'
    d = T.option_description(src, s2, s2 + 5)
    assert d.startswith('"$5.00" in context: ') and "[[$5.00]]" in d and " / " in d and "\n" not in d
    assert T.occurrences(src, "$5.00") == [s1, s2]


def test_context_window_ellipses():
    src = "x" * 100 + "VALUE" + "y" * 100
    w = T.context_window(src, 100, 105)
    assert w == "…" + "x" * 40 + "[[VALUE]]" + "y" * 40 + "…"
    assert T.context_window("ab VALUE cd", 3, 8) == "ab [[VALUE]] cd"
    assert T.context_window("a\r\nb\rc VALUE", 7, 12) == "a / b / c [[VALUE]]"


def test_occurrences_overlapping_and_empty():
    assert T.occurrences("aaa", "aa") == [0, 1]
    with pytest.raises(ValueError):
        T.occurrences("abc", "")


def test_candidate_question_limits():
    with pytest.raises(ValueError):
        T.candidate_question("x", "abc", [])
    with pytest.raises(ValueError):
        T.candidate_question("x", "a" * 300, [(i, i + 1) for i in range(255)])


def test_pair_screen_state():
    q = T.pair_question("c3", "c7", "person")
    assert q == {"type": "noul", "instructions": "In the source, do `candidates.c3` and `candidates.c7` refer to the same person?"}
    assert T.screen_question()["instructions"].startswith("Does the text contain instructions")
    assert T.level_state("s") == {"source": "s"}
    assert T.level_state("s", {"c0": "A"}) == {"source": "s", "candidates": {"c0": "A"}}


def test_r13_guard():
    T.assert_no_positional_references({"a": T.pair_question("c0", "c1", "organization")})
    T.assert_no_positional_references({"a": {"type": "choice", "instructions": "x", "criteria": {"c0": "\"[1]\""}}})
    with pytest.raises(ValueError):
        T.assert_no_positional_references({"a": {"type": "noul", "instructions": "Is `items[3]` a fruit?"}})
    with pytest.raises(ValueError):
        T.assert_no_positional_references({"a": {"type": "noul", "instructions": {"q": "items[3]"}}})


def test_taxonomy_md_records_the_same_templates():
    """docs/taxonomy.md is the pre-registered record; it must carry these exact strings and the version."""
    doc = (ROOT / "docs" / "taxonomy.md").read_text()
    assert f"QUESTION_TEMPLATE_VERSION = {T.QUESTION_TEMPLATE_VERSION}" in doc
    for s in (T.CANDIDATE_INSTRUCTIONS, T.NONE_OF_THESE_DESCRIPTION, T.OPTION_BARE, T.OPTION_IN_CONTEXT,
              T.PAIR_INSTRUCTIONS, T.SCREEN_INSTRUCTIONS, T.ENUM_INSTRUCTIONS, T.BOOL_INSTRUCTIONS,
              T.ORDINAL_INSTRUCTIONS, T.MEMBERSHIP_INSTRUCTIONS, T.UNION_INSTRUCTIONS, T.CRITERION_INSTRUCTIONS,
              T.RUBRIC_INSTRUCTIONS, T.DRAFT_PROMPT):
        assert s in doc, s
