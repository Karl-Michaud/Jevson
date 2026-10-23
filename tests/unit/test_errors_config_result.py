from __future__ import annotations

import ast
import dataclasses
import inspect
import re
import typing
from pathlib import Path

import pytest

from jevson import compile_schema
from jevson import config as config_module
from jevson.checks import Check
from jevson.compile import questions
from jevson.compile.generative import GenerativeOptions
from jevson.compile.questions import CRITERION_TEMPLATES
from jevson.config import DEFAULT_CRITERION_TEMPLATE, DEFAULT_DRAFT_SCREEN, CriterionTemplate, JevsonConfig
from jevson.errors import (
    BackendError,
    CompileError,
    ExtractorError,
    JevsonError,
    LLMError,
    MissingCredentials,
    PreflightError,
    RefusalReason,
    SchemaViolation,
    UsageError,
)
from jevson.result import Result
from jevson.types import Cost, Unresolved, UnresolvedReason


def test_every_error_is_a_jevson_error() -> None:
    for cls in (
        CompileError,
        PreflightError,
        UsageError,
        MissingCredentials,
        SchemaViolation,
        BackendError,
        LLMError,
        ExtractorError,
    ):
        assert issubclass(cls, JevsonError)


def test_compile_error_names_every_offending_pointer() -> None:
    error = CompileError([RefusalReason("/a", "not_yet_supported", "tuples"), RefusalReason("/b", "x", "y")])
    assert [r.pointer for r in error.reasons] == ["/a", "/b"]
    assert "/a: not_yet_supported (tuples)" in str(error)
    assert "/b: x (y)" in str(error)


def test_spent_errors_carry_the_partial_result_and_its_cost() -> None:
    result = Result(value={}, satisfies_schema=False, cost=Cost(decision_requests=3))
    violation = SchemaViolation("required field unresolved", result)
    assert violation.result is result
    assert violation.cost.decision_requests == 3
    for cls in (BackendError, LLMError, ExtractorError):
        error = cls("timeout", "step took too long", result)
        assert error.code == "timeout"
        assert error.result is result
        assert str(error) == "timeout: step took too long"


def test_result_has_every_field_and_complete_follows_unresolved() -> None:
    names = {f.name for f in dataclasses.fields(Result)}
    assert names == {
        "value",
        "satisfies_schema",
        "provenance",
        "decided_by",
        "decisions",
        "unresolved",
        "violations",
        "absent",
        "ungated",
        "overflow",
        "rejections",
        "cost",
        "model",
        "versions",
    }
    empty = Result(value={}, satisfies_schema=True)
    assert empty.complete is True
    assert empty.unresolved == ()
    assert empty.decisions == {}
    assert empty.cost == Cost()
    holed = Result(value={}, satisfies_schema=False, unresolved=(Unresolved("/a", UnresolvedReason.TIE),))
    assert holed.complete is False


def test_config_defaults_match_design() -> None:
    config = JevsonConfig()
    assert config.tie_margin_hundredths == 10
    assert config.redraft_budget == 1
    assert config.step_timeout_s == 120.0
    assert (config.max_input_tokens, config.max_questions_per_request) == (900_000, 200)
    assert config.default_extractor is None
    assert config.raise_on_unresolved_required is False
    assert not hasattr(config, "retry_budget")
    assert not hasattr(config, "source_screen")
    # Transport retries belong to the backend: DecisionsBackend(transport_retries=...) (DESIGN §6.1).
    assert not hasattr(config, "transport_retries")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"tie_margin_hundredths": -1}, "tie_margin_hundredths must be in [0, 100)"),
        ({"tie_margin_hundredths": 100}, "tie_margin_hundredths must be in [0, 100)"),
        ({"step_timeout_s": 0.0}, "step_timeout_s must be positive"),
        ({"redraft_budget": -1}, "redraft_budget must be >= 0"),
        ({"max_input_tokens": 0}, "max_input_tokens must be >= 1"),
        ({"max_questions_per_request": 0}, "max_questions_per_request must be >= 1"),
    ],
)
def test_config_rejects_out_of_range_settings(overrides: dict[str, float], message: str) -> None:
    with pytest.raises(ValueError, match=f"^{re.escape(message)}$"):
        JevsonConfig(**overrides)  # type: ignore[arg-type]


# --- the opt-in adjudication options (DESIGN §3.5, §5.2, §6.3; ASTERION-48) ---------------------------

SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string", "x-jevson": {"generate": {"criteria": ["names the amount"]}}}},
    "required": ["summary"],
}


def test_adjudication_options() -> None:
    config = JevsonConfig(draft_screen=True, criterion_template="1.2.0")
    assert (config.draft_screen, config.criterion_template) == (True, "1.2.0")
    with pytest.raises(ValueError, match="criterion_template must be"):
        JevsonConfig(criterion_template="9.9.9")  # type: ignore[arg-type]
    with pytest.raises(UsageError, match="criterion_template") as raised:
        compile_schema(SCHEMA, criterion_template="9.9.9")
    assert isinstance(raised.value, JevsonError)


def test_criterion_template_lists_agree() -> None:
    assert typing.get_args(CriterionTemplate) == tuple(CRITERION_TEMPLATES)
    tree = ast.parse(Path(config_module.__file__ or "").read_text(encoding="utf-8"))
    imported = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    imported += [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not [name for name in imported if name == "jevson" or name.startswith("jevson.")]


def test_option_defaults_have_one_source() -> None:
    signature = inspect.signature(compile_schema).parameters
    fields = {f.name: f.default for f in dataclasses.fields(JevsonConfig)}
    assert signature["criterion_template"].default == fields["criterion_template"] == DEFAULT_CRITERION_TEMPLATE
    assert signature["draft_screen"].default == fields["draft_screen"] == DEFAULT_DRAFT_SCREEN
    assert inspect.signature(questions.criterion_question).parameters["template"].default is inspect.Parameter.empty
    assert {f.name: f.default for f in dataclasses.fields(GenerativeOptions)} == {
        "criterion_template": dataclasses.MISSING,
        "draft_screen": dataclasses.MISSING,
    }
    assert {f.name: f.default for f in dataclasses.fields(Check)}["rule"] is dataclasses.MISSING
