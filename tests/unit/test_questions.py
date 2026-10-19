"""DESIGN §5.2: class C questions render from the versioned templates (docs/taxonomy.md §1.2).

Version 1.1.x keeps the Phase 0 enum, ordinal, and option strings byte for byte and replaces the bool one;
1.1.1 drops a label's leading article."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jevson.compile import questions
from jevson.compile.declarations import FieldDeclaration
from jevson.compile.normalise import Kind, SchemaNode
from tests.phase0 import templates


def test_1_1_0_keeps_the_phase_0_enum_ordinal_and_option_strings_and_replaces_the_bool_one() -> None:
    assert questions.QUESTION_TEMPLATE_VERSION == "1.1.1"
    assert templates.QUESTION_TEMPLATE_VERSION == "1.0.0"  # the Phase 0 record does not move
    assert questions.ENUM_INSTRUCTIONS == templates.ENUM_INSTRUCTIONS
    assert questions.ENUM_OPTION == templates.ENUM_OPTION
    assert questions.ORDINAL_INSTRUCTIONS == templates.ORDINAL_INSTRUCTIONS
    assert questions.BOOL_INSTRUCTIONS != templates.BOOL_INSTRUCTIONS


def test_the_1_1_0_strings_are_recorded_in_taxonomy_md() -> None:
    doc = (Path(__file__).resolve().parents[2] / "docs" / "taxonomy.md").read_text(encoding="utf-8")
    assert f"QUESTION_TEMPLATE_VERSION = {questions.QUESTION_TEMPLATE_VERSION}" in doc
    assert questions.BOOL_INSTRUCTIONS in doc
    assert questions.BOOL_SCOPED_INSTRUCTIONS in doc


def test_rendered_questions_match_the_templates() -> None:
    assert questions.enum_question("tier") == templates.ENUM_INSTRUCTIONS.format(label="tier")
    assert questions.ordinal_question("rating") == templates.ORDINAL_INSTRUCTIONS.format(label="rating")
    assert questions.option_description(3) == templates.ENUM_OPTION.format(value=3) == '"3"'
    assert questions.bool_question("it is paid") == "According to the source, is it true that it is paid?"
    assert (
        questions.bool_question("it is paid", "billing")
        == "According to the source, for the billing, is it true that it is paid?"
    )


def field(description: str | None = None, question: str | None = None) -> SchemaNode:
    declaration = FieldDeclaration(question=question) if question is not None else None
    return SchemaNode("/f", Kind.BOOLEAN, description=description, declaration=declaration)


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (field("the customer's tier", "the account tier"), "account tier"),
        (field("the customer's tier."), "customer's tier"),
        (field("An order's state"), "order's state"),
        (field("theme"), "theme"),
        (field("the"), "the"),
        (field("  is it refundable?  "), "is it refundable"),
        (field(), "billing tier"),
        (field("  ."), "billing tier"),
    ],
)
def test_the_label_is_the_question_else_the_description_else_the_name(node: SchemaNode, expected: str) -> None:
    assert questions.label("billing_tier", node) == expected


@pytest.mark.parametrize("text", ["the ticket's topic", "The ticket's topic", "a ticket's topic", "an ticket's topic"])
def test_a_template_that_says_the_never_renders_a_second_article(text: str) -> None:
    # 1.1.0 rendered "Which of these is the the ticket's topic?" from a description starting "the".
    label = questions.label("topic", field(text))
    assert questions.enum_question(label) == "Which of these is the ticket's topic?"
    assert questions.ordinal_question(label) == "Which level best describes the ticket's topic?"
    assert questions.union_question(label) == "Which of these does the source describe as the ticket's topic?"
    assert questions.member_question("x", label) == 'According to the source, is "x" one of the ticket\'s topic?'
    assert (
        questions.generate_prompt(label, None)
        == "Write the ticket's topic for the source below. Return only the value."
    )
    assert questions.redraft_prompt(label, ["c"]).endswith("Write the ticket's topic again. Return only the value.")


def test_a_name_that_trims_to_nothing_is_used_as_written() -> None:
    assert questions.label("?", field()) == "?"


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (field("the invoice is paid", "it ships today."), "it ships today"),
        (field("the invoice is paid."), "the invoice is paid"),
        (field("Whether the invoice is paid"), "the invoice is paid"),
        (field("if it ships today"), "it ships today"),
        (field("whether"), "whether"),
        (field(), None),
        (field("  ?"), None),
        (field(" . ", "  "), None),
    ],
)
def test_a_bools_predicate_is_its_question_else_its_description_never_its_name(
    node: SchemaNode, expected: str | None
) -> None:
    assert questions.predicate(node) == expected


def labelled(label: str, *ancestors: str, verbatim: bool = False) -> questions.Labelled:
    return questions.Labelled(label, ancestors, verbatim)


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ([labelled("kind", "billing"), labelled("kind", "shipping")], ("billing", "shipping")),
        ([labelled("kind", "billing"), labelled("tier", "shipping")], ("", "")),
        ([labelled("the kind", "billing"), labelled("Kind", "shipping")], ("billing", "shipping")),
        (
            [labelled("kind", "order", "billing_address"), labelled("kind", "refund", "billing_address")],
            ("order billing address", "refund billing address"),
        ),
        ([labelled("kind"), labelled("kind", "x"), labelled("kind", "y", "x")], ("", "x", "y x")),
        ([labelled("Which kind", "a", verbatim=True), labelled("Which kind", "b", verbatim=True)], ("", "")),
        ([labelled("kind"), labelled("kind")], ("", "")),
        ([], ()),
    ],
)
def test_scopes_add_the_fewest_nearest_ancestors_that_make_each_label_unique(
    fields: list[questions.Labelled], expected: tuple[str, ...]
) -> None:
    assert questions.scopes(fields) == expected


@pytest.mark.parametrize(
    ("label", "scope", "expected"),
    [
        ("kind", "", "kind"),
        ("kind", "billing", "billing kind"),
        ("The kind", "billing", "billing kind"),
        ("an address type", "shipping", "shipping address type"),
        ("theme", "site", "site theme"),
    ],
)
def test_a_scoped_label_puts_the_scope_in_front_of_the_noun(label: str, scope: str, expected: str) -> None:
    assert questions.scoped_label(label, scope) == expected


NEGATION = re.compile(r"\b(no|not|never|none|neither|nor)\b|n't", re.IGNORECASE)
POSITIONAL = re.compile(r"\[\d+\]")


@pytest.mark.parametrize(
    "rendered",
    [
        questions.enum_question("X"),
        questions.bool_question("X"),
        questions.bool_question("X", "Y"),
        questions.ordinal_question("X"),
        questions.option_description("X"),
    ],
)
def test_templates_add_no_negation_and_no_positional_reference(rendered: str) -> None:
    assert not NEGATION.search(rendered)
    assert not POSITIONAL.search(rendered)
