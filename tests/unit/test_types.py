from __future__ import annotations

import pytest

from jevson.types import (
    Cost,
    DecisionKind,
    DecisionNode,
    Option,
    OptionSource,
    Span,
    StepKind,
    StepNode,
    UnresolvedReason,
)


def options(*ids: str) -> tuple[Option, ...]:
    return tuple(Option(i, f"option {i}") for i in ids)


def test_unresolved_reasons_are_the_closed_set_of_design_6_1() -> None:
    assert {r.value for r in UnresolvedReason} == {
        "abstained",
        "no_candidates",
        "tie",
        "invalid_backend_answer",
        "too_many_candidates",
        "budget_exceeded",
        "unparseable",
        "entity_conflict",
        "redraft_exhausted",
        "source_flagged",
        "verification_failed",
        "dependency_unresolved",
        "refused",
    }
    assert "not_yet_supported" not in {r.value for r in UnresolvedReason}


@pytest.mark.parametrize(("start", "end"), [(-1, 3), (3, 3), (5, 2)])
def test_span_rejects_bad_offsets(start: int, end: int) -> None:
    with pytest.raises(ValueError, match="0 <= start < end"):
        Span("doc", start, end)


def test_span_is_half_open_code_point_range_with_a_source_id() -> None:
    span = Span("doc", 0, 14)
    assert (span.source_id, span.start, span.end) == ("doc", 0, 14)


def test_valid_nodes_construct() -> None:
    DecisionNode("/a#predicate", DecisionKind.PREDICATE, "q", OptionSource.PREDICATE, "/a")
    DecisionNode("/b#choice", DecisionKind.CHOICE, "q", OptionSource.SCHEMA_ENUM, "/b", options("o0", "o1"))
    DecisionNode("/c#score", DecisionKind.SCORE, "q", OptionSource.SCHEMA_RUBRIC, "/c", options("l0", "l1", "l2"))


@pytest.mark.parametrize(
    ("kind", "source", "opts", "message"),
    [
        (DecisionKind.PREDICATE, OptionSource.SCHEMA_ENUM, (), "only a predicate"),
        (DecisionKind.CHOICE, OptionSource.PREDICATE, options("a", "b"), "only a predicate"),
        (DecisionKind.PREDICATE, OptionSource.PREDICATE, options("a", "b"), "has no options"),
        (DecisionKind.CHOICE, OptionSource.SCHEMA_ENUM, options("a"), "needs 2-255"),
        (DecisionKind.CHOICE, OptionSource.SCHEMA_ENUM, options(*(f"o{i}" for i in range(256))), "needs 2-255"),
        (DecisionKind.SCORE, OptionSource.SCHEMA_RUBRIC, options("a", "a"), "unique"),
    ],
)
def test_invalid_decision_nodes_are_rejected(
    kind: DecisionKind, source: OptionSource, opts: tuple[Option, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        DecisionNode("/x", kind, "q", source, "/x", opts)


def test_step_nodes_name_their_protocol() -> None:
    assert StepNode("/a#extract", StepKind.EXTRACT, "/a").protocol == "Extractor"
    assert StepNode("/b#generate", StepKind.GENERATE, "/b").protocol == "LLM"


def test_no_candidate_option_source_in_v0() -> None:
    assert {s.value for s in OptionSource} == {"schema_enum", "schema_rubric", "predicate"}


def test_cost_starts_at_zero() -> None:
    cost = Cost()
    assert cost.decision_requests == 0
    assert cost.decision_request_ids == ()
    assert cost.wall_clock_by_component == {}
