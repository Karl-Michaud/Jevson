"""CachingBackend: exact replay of recorded responses (DESIGN §8.4)."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import httpx
import pytest

from jevson import (
    Backend,
    BackendError,
    BackendResponse,
    CachingBackend,
    ChoiceAnswer,
    DecisionKind,
    FakeBackend,
    InvalidAnswer,
    Option,
    PredicateAnswer,
    Question,
)
from jevson.backends.caching import cache_key
from jevson.probabilities import interpret
from jevson.types import Answer
from tests.adversarial.hostile_backend import (
    MODEL,
    NODES,
    QUESTIONS,
    SENTINEL_KEY,
    backend,
    envelope,
    good_answers,
    respond,
    with_answer,
)


def awkward(question: Question) -> Answer:
    """Raw values that hundredths would not preserve: an invalid raw sum, NaN, an invalid answer."""
    if question.kind is DecisionKind.PREDICATE:
        return PredicateAnswer(question.name, math.nan)
    if question.kind is DecisionKind.CHOICE:
        return ChoiceAnswer(question.name, "c1", {"c0": 0.204, "c1": 0.8093}, 0.123456789)
    return InvalidAnswer(question.name, "recorded as invalid")


def ask(b: Backend, state: str = "source", questions: tuple[Question, ...] = QUESTIONS) -> BackendResponse:
    return asyncio.run(b.ask(state, questions, MODEL))


def test_a_replay_reproduces_the_response_and_spends_nothing(tmp_path: Path) -> None:
    inner = FakeBackend(default=awkward, model="gpt-6-luna-recorded")
    cache = CachingBackend(inner, tmp_path / "cache")
    first = ask(cache)
    second = ask(CachingBackend(FakeBackend(), tmp_path / "cache"))  # a new process, an empty inner
    assert len(inner.calls) == 1
    assert (first.cache_hit, second.cache_hit) == (False, True)
    assert (second.model, second.request_id, second.input_tokens) == (first.model, first.request_id, first.input_tokens)
    assert repr(second.answers) == repr(first.answers)  # NaN != NaN, so compare the exact text
    for question, a, b in zip(QUESTIONS, first.answers, second.answers, strict=True):
        assert repr(interpret(NODES[question.name], a, 10)) == repr(interpret(NODES[question.name], b, 10))
    assert (cache.hits, cache.misses) == (0, 1)


def test_hits_are_counted(tmp_path: Path) -> None:
    cache = CachingBackend(FakeBackend(default=FakeBackend.predicate(0.9)), tmp_path)
    one = (QUESTIONS[0],)
    for _ in range(3):
        ask(cache, questions=one)
    ask(cache, state="other", questions=one)
    assert (cache.hits, cache.misses) == (2, 2)


def test_replay_only_raises_on_a_miss(tmp_path: Path) -> None:
    inner = FakeBackend(default=FakeBackend.predicate(0.9))
    with pytest.raises(BackendError) as raised:
        ask(CachingBackend(inner, tmp_path, replay_only=True))
    assert raised.value.code == "replay_miss"
    assert raised.value.cost.decision_requests == 0
    assert inner.calls == []


def test_a_lone_surrogate_is_passed_through_and_not_cached(tmp_path: Path) -> None:
    inner = FakeBackend(default=awkward)
    cache = CachingBackend(inner, tmp_path)
    for _ in range(2):
        assert ask(cache, state="broken \ud800 text").cache_hit is False
    assert len(inner.calls) == 2
    assert list(tmp_path.iterdir()) == []
    assert cache_key("broken \ud800 text", QUESTIONS, MODEL) is None
    with pytest.raises(BackendError, match="canonicalised"):
        ask(CachingBackend(inner, tmp_path, replay_only=True), state="broken \ud800 text")


def test_the_key_covers_model_state_and_every_question_field() -> None:
    base = cache_key("s", QUESTIONS, MODEL)
    renamed = (Question("other", *[getattr(QUESTIONS[0], f) for f in ("kind", "instructions", "options")]),)
    changed = [
        cache_key("s", QUESTIONS, "gpt-other"),
        cache_key("t", QUESTIONS, MODEL),
        cache_key("s", QUESTIONS[:2], MODEL),
        cache_key("s", renamed + QUESTIONS[1:], MODEL),
        cache_key("s", (QUESTIONS[0], Question("vendor", DecisionKind.CHOICE, "Which vendor issued it?",
                                               (Option("c0", "Acme"), Option("c1", "Initech"))), QUESTIONS[2]), MODEL),
    ]  # fmt: skip
    assert base is not None
    assert base not in changed
    assert len(set(changed)) == len(changed)
    assert cache_key("s", QUESTIONS, MODEL) == base


def test_a_corrupt_record_is_a_backend_error(tmp_path: Path) -> None:
    cache = CachingBackend(FakeBackend(default=awkward), tmp_path)
    ask(cache)
    (record,) = tmp_path.iterdir()
    for text in ("{not json", '{"answers": [{"type": "free_text", "name": "x"}]}', "[]"):
        record.write_text(text)
        with pytest.raises(BackendError) as raised:
            ask(cache)
        assert raised.value.code == "cache_corrupt"


def test_only_the_callers_directory_is_written_and_no_temp_file_is_left(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "cache"
    ask(CachingBackend(FakeBackend(default=awkward), directory))
    assert [p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file()] == [
        next(directory.iterdir()).relative_to(tmp_path)
    ]
    assert next(directory.iterdir()).suffix == ".json"


def test_a_failed_write_leaves_no_temp_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("jevson.backends.caching.json.dump", broken)
    with pytest.raises(OSError, match="disk full"):
        ask(CachingBackend(FakeBackend(default=awkward), tmp_path))
    assert list(tmp_path.iterdir()) == []


def test_exceptions_from_the_inner_backend_are_not_cached(tmp_path: Path) -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return respond({}, 400)

    cache = CachingBackend(backend(handler), tmp_path)
    for _ in range(2):
        with pytest.raises(BackendError):
            ask(cache)
    assert len(calls) == 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "answers", [good_answers(), with_answer(1, {"type": "refusal", "name": "q1"}), with_answer(0, "garbage")]
)
def test_the_key_never_reaches_a_cache_file(tmp_path: Path, answers: list[object]) -> None:
    cache = CachingBackend(backend(lambda request: respond(envelope(answers))), tmp_path)
    ask(cache)
    assert ask(cache).cache_hit is True
    assert SENTINEL_KEY not in repr(cache)
    for path in tmp_path.rglob("*"):
        assert SENTINEL_KEY not in path.read_text(encoding="utf-8")
