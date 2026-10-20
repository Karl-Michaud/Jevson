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

from jevson import CachingBackend, FakeBackend, InMemoryCostSink, Jevson, ReplayLLM, Result
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
    assert event.model == "claude-x-1"
    assert result.versions["llm_model"] == "claude-x-1"


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
    recording = ReplayLLM(ScriptedLLM([drafted("Refund of $40.", "claude-x-1")]), tmp_path, llm_id="scripted")
    first, _ = run(GENERATED, FakeBackend(default=passes), recording)
    replayed, _ = run(GENERATED, FakeBackend(default=passes), ReplayLLM(None, tmp_path, llm_id="scripted",
                                                                        replay_only=True))  # fmt: skip
    assert first.versions["llm_model"] == replayed.versions["llm_model"] == "claude-x-1"
    [path] = tmp_path.iterdir()
    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["model"] == "claude-x-1"
    del record["model"]  # a recording made before the model was stored still loads
    path.write_text(json.dumps(record), encoding="utf-8")
    older, _ = run(GENERATED, FakeBackend(default=passes), ReplayLLM(None, tmp_path, llm_id="scripted",
                                                                     replay_only=True))  # fmt: skip
    assert "llm_model" not in older.versions
