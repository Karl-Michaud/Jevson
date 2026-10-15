"""`x-jevson` declarations (DESIGN §3.5) and the refusal collector (R14)."""

from __future__ import annotations

import pytest

from jevson.compile.declarations import FieldDeclaration, GenerateDeclaration, Rubric, parse_declaration
from jevson.compile.refusal import Refusals, child_pointer
from jevson.errors import CompileError, RefusalCode, RefusalReason


def parse(raw: object) -> tuple[FieldDeclaration | None, list[str]]:
    refusals = Refusals()
    declaration = parse_declaration(raw, "/f", refusals)
    assert all(r.pointer == "/f" for r in refusals.reasons)
    return declaration, [r.reason for r in refusals.reasons]


def test_a_full_valid_declaration_parses() -> None:
    declaration, codes = parse({"question": "Is it paid?", "ordinal": True, "order": "source"})
    assert codes == []
    assert declaration == FieldDeclaration(question="Is it paid?", ordinal=True, order="source")
    assert declaration.decides


def test_order_alone_does_not_ask_for_a_decision() -> None:
    declaration, codes = parse({"order": "source"})
    assert codes == []
    assert declaration is not None
    assert not declaration.decides


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("text", RefusalCode.MALFORMED_DECLARATION),
        ({"sauce": {}}, RefusalCode.UNKNOWN_DECLARATION_KEY),
        ({"question": "  "}, RefusalCode.MALFORMED_DECLARATION),
        ({"question": 3}, RefusalCode.MALFORMED_DECLARATION),
        ({"ordinal": "yes"}, RefusalCode.MALFORMED_DECLARATION),
        ({"order": "semantic"}, RefusalCode.SEMANTIC_ORDER),
        ({"order": "alphabetical"}, RefusalCode.MALFORMED_DECLARATION),
    ],
)
def test_bad_declarations_refuse_with_a_named_reason(raw: object, code: RefusalCode) -> None:
    assert parse(raw)[1] == [code]


@pytest.mark.parametrize(
    "source",
    [{"extractor": "llm"}, {"extractor": "no-such-extractor"}, {"extractor": "money", "locale": "xx"}, {}, "llm"],
)
def test_source_refuses_only_with_source_selection_dropped_whatever_its_contents(source: object) -> None:
    refusals = Refusals()
    declaration = parse_declaration({"source": source}, "/total", refusals)
    assert [r.reason for r in refusals.reasons] == [RefusalCode.SOURCE_SELECTION_DROPPED]
    assert "Phase 0r" in refusals.reasons[0].message
    assert "generate" in refusals.reasons[0].message
    assert declaration is not None
    assert declaration.declares_source


def test_a_valid_generate_parses_then_refuses_until_phase_4() -> None:
    raw = {
        "generate": {
            "criteria": ["Only states facts in the source"],
            "rubric": {"levels": ["poor", "ok", "good"], "minimum": "ok"},
            "instructions": "One sentence.",
            "max_draft_chars": 200,
        }
    }
    declaration, codes = parse(raw)
    assert codes == [RefusalCode.NOT_YET_SUPPORTED]
    assert declaration is not None
    assert declaration.generate == GenerateDeclaration(
        ("Only states facts in the source",), Rubric(("poor", "ok", "good"), "ok"), "One sentence.", 200
    )


def test_generate_with_no_criteria_parses_as_ungated() -> None:
    declaration, codes = parse({"generate": {}})
    assert codes == [RefusalCode.NOT_YET_SUPPORTED]
    assert declaration is not None
    assert declaration.generate == GenerateDeclaration()


@pytest.mark.parametrize(
    "generate",
    [
        "summarise",
        {"criteria": "one"},
        {"criteria": ["ok", ""]},
        {"rubric": {"levels": ["only"], "minimum": "only"}},
        {"rubric": {"levels": ["a", "a"], "minimum": "a"}},
        {"rubric": {"levels": ["a", "b"], "minimum": "c"}},
        {"rubric": {"levels": ["a", "b"], "minimum": "a", "extra": 1}},
        {"rubric": {"levels": [str(i) for i in range(11)], "minimum": "0"}},
        {"rubric": "a-b"},
        {"instructions": ""},
        {"max_draft_chars": 0},
        {"max_draft_chars": True},
        {"max_draft_chars": "9"},
    ],
)
def test_a_malformed_generate_refuses_as_malformed_not_as_not_yet_supported(generate: object) -> None:
    declaration, codes = parse({"generate": generate})
    assert codes == [RefusalCode.MALFORMED_DECLARATION]
    assert declaration is not None
    assert declaration.generate is None


def test_an_unknown_generate_key_refuses_by_name() -> None:
    assert parse({"generate": {"criterion": ["x"]}})[1] == [RefusalCode.UNKNOWN_DECLARATION_KEY]


def test_source_and_generate_together_refuse_with_every_applicable_reason() -> None:
    codes = parse({"source": {"extractor": "llm"}, "generate": {"criteria": ["x"]}})[1]
    assert set(codes) == {
        RefusalCode.SOURCE_SELECTION_DROPPED,
        RefusalCode.NOT_YET_SUPPORTED,
        RefusalCode.SOURCE_AND_GENERATE,
    }


def test_every_problem_in_one_declaration_is_reported() -> None:
    codes = parse({"order": "semantic", "nope": 1, "ordinal": 2, "source": {}})[1]
    assert set(codes) == {
        RefusalCode.SEMANTIC_ORDER,
        RefusalCode.UNKNOWN_DECLARATION_KEY,
        RefusalCode.MALFORMED_DECLARATION,
        RefusalCode.SOURCE_SELECTION_DROPPED,
    }


# --- refusal.py -----------------------------------------------------------------------------


def test_refusals_collect_in_order_dedupe_and_raise_one_error() -> None:
    refusals = Refusals()
    assert not refusals
    refusals.raise_if_any()
    refusals.add("/a", RefusalCode.TUPLE_FIELD, "tuples")
    refusals.add("/b", RefusalCode.ANY_FIELD, "any")
    refusals.add("/a", RefusalCode.TUPLE_FIELD, "tuples")
    assert refusals
    with pytest.raises(CompileError) as raised:
        refusals.raise_if_any()
    assert raised.value.reasons == (
        RefusalReason("/a", RefusalCode.TUPLE_FIELD, "tuples"),
        RefusalReason("/b", RefusalCode.ANY_FIELD, "any"),
    )


def test_child_pointers_escape_per_rfc_6901() -> None:
    assert child_pointer("", "a") == "/a"
    assert child_pointer("/a", "b/c~d") == "/a/b~1c~0d"


def test_refusal_codes_are_distinct_strings() -> None:
    values = [code.value for code in RefusalCode]
    assert len(values) == len(set(values))
    assert RefusalCode.NOT_YET_SUPPORTED != RefusalCode.SOURCE_SELECTION_DROPPED
    assert RefusalCode.TUPLE_FIELD == "tuple_field"
