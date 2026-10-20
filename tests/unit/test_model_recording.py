"""R15: every response's model string is recorded (ASTERION-44, audit fold-ins J-6 and K-6).

- J-6: each decision `CostEvent` carries the `model` its response named, cache hits included;
  `Result.model` stays the distinct set and `Decision` gains no field (audit Q13).
- K-6: `LLMResponse.model` is the id the caller's LLM reports; each `llm` `CostEvent` carries it, and
  `Result.versions["llm_model"]` lists the ids seen in first-seen order, joined by "," (audit Q14).
  The key is absent when no LLM response named a model.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from jevson import CachingBackend, CostEvent, FakeBackend, InMemoryCostSink, Jevson, JevsonConfig, ReplayLLM, Result
from jevson.types import DecisionKind, LLMResponse, Question
from tests.adversarial.hostile_llm import ScriptedLLM

BOUNDED = {
    "type": "object",
    "properties": {"paid": {"type": "boolean", "description": "the invoice is paid"}},
    "required": ["paid"],
}
GENERATED = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "x-jevson": {"generate": {"criteria": ["mentions the refund amount stated in the source"]}},
        }
    },
    "required": ["summary"],
}


def passes(question: Question) -> Any:
    if question.kind is DecisionKind.SCORE:
        return FakeBackend.select(question.options[-1].id)(question)
    return FakeBackend.predicate(0.9)(question)


def run(schema: dict[str, Any], backend: Any, llm: Any = None, **kwargs: Any) -> tuple[Result, InMemoryCostSink]:
    sink = InMemoryCostSink()
    result = asyncio.run(Jevson(backend, llm=llm, cost_sink=sink).aresolve(schema, "Refund: $40.", **kwargs))
    return result, sink


def drafted(text: str, model: Any) -> LLMResponse:
    return LLMResponse({"value": text}, "", 7, 3, model)


def test_each_decision_cost_event_names_its_responses_model(tmp_path: Path) -> None:
    result, sink = run(BOUNDED, FakeBackend(default=passes, model="luna-a"))
    [event] = [e for e in sink.events if e.component == "decision"]
    assert event.model == "luna-a"
    assert result.model == ("luna-a",)
    caching = CachingBackend(FakeBackend(default=passes, model="luna-b"), tmp_path)
    run(BOUNDED, caching)
    _, replayed = run(BOUNDED, caching)
    [hit] = [e for e in replayed.events if e.component == "decision"]
    assert hit.cache_hit
    assert hit.model == "luna-b"


def test_each_llm_cost_event_and_the_result_record_the_llms_model() -> None:
    llm = ScriptedLLM([drafted("Refund of $40.", "claude-x-1")])
    result, sink = run(GENERATED, FakeBackend(default=passes), llm)
    [event] = [e for e in sink.events if e.component == "llm"]
    assert event == CostEvent("llm", input_tokens=7, output_tokens=3, model="claude-x-1")
    assert result.versions["llm_model"] == "claude-x-1"


def test_a_failed_draft_still_records_the_model_that_wrote_it() -> None:
    malformed = LLMResponse({"summary": "no value key"}, "", 5, 2, "claude-x-1")
    result, sink = run(GENERATED, FakeBackend(default=passes), ScriptedLLM([malformed]), redraft_budget=0)
    assert [e.model for e in sink.events if e.component == "llm"] == ["claude-x-1"]
    assert result.versions["llm_model"] == "claude-x-1"
    assert [r.pointer for r in result.rejections] == ["/summary"]


def test_several_llm_models_are_listed_once_each_in_first_seen_order() -> None:
    fails_then_passes = iter([0.1, 0.9, 0.9])

    def criterion(question: Question) -> Any:
        return FakeBackend.predicate(next(fails_then_passes))(question)

    llm = ScriptedLLM([drafted("first", "m-2"), drafted("second", "m-1"), drafted("third", "m-2")])
    result, sink = run(GENERATED, FakeBackend(default=criterion), llm, redraft_budget=2)
    assert [e.model for e in sink.events if e.component == "llm"] == ["m-2", "m-1"]
    assert result.versions["llm_model"] == "m-2,m-1"


def test_no_llm_model_means_no_llm_model_key() -> None:
    result, _ = run(BOUNDED, FakeBackend(default=passes))
    assert "llm_model" not in result.versions
    for unreported in (None, "", 42):
        result, sink = run(GENERATED, FakeBackend(default=passes), ScriptedLLM([drafted("Refund.", unreported)]))
        assert "llm_model" not in result.versions
        assert [e.model for e in sink.events if e.component == "llm"] == [None]


def test_replay_llm_records_and_replays_the_model(tmp_path: Path) -> None:
    inner = ScriptedLLM([drafted("Refund of $40.", "claude-x-1")])
    recording = ReplayLLM(inner, tmp_path, llm_id="scripted")
    first, _ = run(GENERATED, FakeBackend(default=passes), recording)
    replayed, _ = run(GENERATED, FakeBackend(default=passes), ReplayLLM(None, tmp_path, llm_id="scripted",
                                                                        replay_only=True))  # fmt: skip
    assert first.versions["llm_model"] == replayed.versions["llm_model"] == "claude-x-1"
    [recording_request] = inner.calls
    [path] = tmp_path.iterdir()
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["model"] == "claude-x-1"
    record["model"] = 42  # a hand-edited or foreign record: a non-string model is not trusted
    path.write_text(json.dumps(record), encoding="utf-8")
    foreign, _ = run(GENERATED, FakeBackend(default=passes), ReplayLLM(None, tmp_path, llm_id="scripted",
                                                                       replay_only=True))  # fmt: skip
    assert "llm_model" not in foreign.versions
    replay = ReplayLLM(None, tmp_path, llm_id="scripted", replay_only=True)
    [messages, tool_schema] = recording_request
    assert asyncio.run(replay.complete(messages, tool_schema)).model is None
    del record["model"]  # a recording made before the model was stored still loads
    path.write_text(json.dumps(record), encoding="utf-8")
    older, _ = run(GENERATED, FakeBackend(default=passes), ReplayLLM(None, tmp_path, llm_id="scripted",
                                                                     replay_only=True))  # fmt: skip
    assert "llm_model" not in older.versions


def test_the_versions_dict_is_pinned_at_the_defaults_and_follows_the_config() -> None:
    result, _ = run(BOUNDED, FakeBackend(default=passes))
    assert dict(result.versions) == {
        "question_templates": "1.1.1",
        "model": "gpt-6-luna",
        "max_input_tokens": "900000",
        "max_questions_per_request": "200",
        "budget_estimator": "bytes/3+160q+8o+dw",
        "tie_margin_hundredths": "10",
        "default_extractor": "none",
        "redraft_budget": "1",
        "union_fanout": "true",
    }
    config = JevsonConfig(
        model="luna-x", max_input_tokens=50000, max_questions_per_request=7, tie_margin_hundredths=5,
        default_extractor="llm", redraft_budget=2, union_fanout=False,
    )  # fmt: skip
    llm = ScriptedLLM([drafted("Refund of $40.", "claude-x-1")])
    sink = InMemoryCostSink()
    jevson = Jevson(FakeBackend(default=passes), llm=llm, config=config, cost_sink=sink)
    result = asyncio.run(jevson.aresolve(GENERATED, "Refund: $40."))
    assert dict(result.versions) == {
        "question_templates": "1.1.1",
        "model": "luna-x",
        "max_input_tokens": "50000",
        "max_questions_per_request": "7",
        "budget_estimator": "bytes/3+160q+8o+dw",
        "tie_margin_hundredths": "5",
        "default_extractor": "llm",
        "redraft_budget": "2",
        "union_fanout": "false",
        "llm_model": "claude-x-1",
    }


def test_two_billed_responses_add_up_in_cost() -> None:
    schema = {
        "type": "object",
        "properties": {
            "paid": {"type": "boolean", "description": "the invoice is paid"},
            "summary": GENERATED["properties"]["summary"],
        },
        "required": ["paid", "summary"],
    }
    llm = ScriptedLLM([drafted("Refund of $40.", "claude-x-1")])
    result, sink = run(schema, FakeBackend(default=passes, model="luna-a"), llm)
    billed = [e for e in sink.events if e.component == "decision"]
    assert len(billed) == 2  # the bounded request, then the adjudication request (ASTERION-50)
    assert [e.model for e in billed] == ["luna-a", "luna-a"]
    assert result.cost.decision_requests == 2
    assert result.cost.decision_input_tokens == sum(e.input_tokens for e in billed)
    assert len(result.cost.decision_request_ids) == 2


def test_a_replayed_malformed_draft_keeps_the_llms_raw_text(tmp_path: Path) -> None:
    malformed = LLMResponse({"summary": "no value key"}, "RAW TEXT FROM THE LLM", 5, 2, "claude-x-1")
    recording = ReplayLLM(ScriptedLLM([malformed]), tmp_path, llm_id="scripted")
    first, _ = run(GENERATED, FakeBackend(default=passes), recording, redraft_budget=0)
    replay = ReplayLLM(None, tmp_path, llm_id="scripted", replay_only=True)
    replayed, _ = run(GENERATED, FakeBackend(default=passes), replay, redraft_budget=0)
    assert [r.draft for r in first.rejections] == ["RAW TEXT FROM THE LLM"]
    assert [r.draft for r in replayed.rejections] == [r.draft for r in first.rejections]
