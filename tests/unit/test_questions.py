"""DESIGN §5.2: class C questions render from the Phase 0 templates, byte for byte (docs/taxonomy.md §1.2)."""

from __future__ import annotations

import re

import pytest

from jevson.compile import questions
from jevson.compile.declarations import FieldDeclaration
from jevson.compile.normalise import Kind, SchemaNode
from tests.phase0 import templates


def test_the_class_c_templates_are_byte_identical_to_the_phase_0_record() -> None:
    assert questions.QUESTION_TEMPLATE_VERSION == templates.QUESTION_TEMPLATE_VERSION == "1.0.0"
    assert questions.ENUM_INSTRUCTIONS == templates.ENUM_INSTRUCTIONS
    assert questions.ENUM_OPTION == templates.ENUM_OPTION
    assert questions.BOOL_INSTRUCTIONS == templates.BOOL_INSTRUCTIONS
    assert questions.ORDINAL_INSTRUCTIONS == templates.ORDINAL_INSTRUCTIONS


def test_rendered_questions_match_the_recorded_templates() -> None:
    assert questions.enum_question("tier") == templates.ENUM_INSTRUCTIONS.format(label="tier")
    assert questions.bool_question("it is paid") == templates.BOOL_INSTRUCTIONS.format(predicate="it is paid")
    assert questions.ordinal_question("rating") == templates.ORDINAL_INSTRUCTIONS.format(label="rating")
    assert questions.option_description(3) == templates.ENUM_OPTION.format(value=3) == '"3"'


def field(description: str | None = None, question: str | None = None) -> SchemaNode:
    declaration = FieldDeclaration(question=question) if question is not None else None
    return SchemaNode("/f", Kind.BOOLEAN, description=description, declaration=declaration)


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        (field("the customer's tier", "the account tier"), "the account tier"),
        (field("the customer's tier."), "the customer's tier"),
        (field("  is it refundable?  "), "is it refundable"),
        (field(), "billing tier"),
        (field("  ."), "billing tier"),
    ],
)
def test_the_label_is_the_question_else_the_description_else_the_name(node: SchemaNode, expected: str) -> None:
    assert questions.label("billing_tier", node) == expected


def test_a_name_that_trims_to_nothing_is_used_as_written() -> None:
    assert questions.label("?", field()) == "?"


NEGATION = re.compile(r"\b(no|not|never|none|neither|nor)\b|n't", re.IGNORECASE)
POSITIONAL = re.compile(r"\[\d+\]")


@pytest.mark.parametrize(
    "rendered",
    [
        questions.enum_question("X"),
        questions.bool_question("X"),
        questions.ordinal_question("X"),
        questions.option_description("X"),
    ],
)
def test_templates_add_no_negation_and_no_positional_reference(rendered: str) -> None:
    assert not NEGATION.search(rendered)
    assert not POSITIONAL.search(rendered)
