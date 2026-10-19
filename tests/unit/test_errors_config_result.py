from __future__ import annotations

import dataclasses

import pytest

from jevson.config import JevsonConfig
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
    "overrides",
    [
        {"tie_margin_hundredths": -1},
        {"tie_margin_hundredths": 100},
        {"step_timeout_s": 0.0},
        {"redraft_budget": -1},
        {"max_input_tokens": 0},
        {"max_questions_per_request": 0},
    ],
)
def test_config_rejects_out_of_range_settings(overrides: dict[str, float]) -> None:
    with pytest.raises(ValueError, match="must be"):
        JevsonConfig(**overrides)  # type: ignore[arg-type]
