"""`CachingBackend`: exact replay of recorded backend responses (DESIGN §8.4).

A request re-sent to the API is a new measurement, never a replay; replay reads recorded responses
only. The key is the SHA-256 of the RFC 8785 canonical JSON of the model, state and questions
([L21]). Responses are stored whole, with the returned `model` string. Probabilities are stored as
the raw floats the backend returned, not hundredths, so the raw sum check reads the same values on
replay and a replayed `Result` is identical (an invalid raw sum would otherwise round into a valid one).

A request that cannot be canonicalised (a lone surrogate) is passed through and not cached. A hit
spends nothing and is flagged `cache_hit`; with `replay_only=True` a miss raises
`BackendError(replay_miss)`. Files are written only under the caller's directory, atomically.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import rfc8785

from jevson.errors import BackendError
from jevson.protocols import Backend
from jevson.result import Result
from jevson.types import (
    Answer,
    BackendResponse,
    ChoiceAnswer,
    InvalidAnswer,
    PredicateAnswer,
    Question,
    Refusal,
    ScoreAnswer,
)

FORMAT_VERSION = 1


class CachingBackend:
    def __init__(self, inner: Backend, directory: str | os.PathLike[str], *, replay_only: bool = False) -> None:
        self._inner = inner
        self._directory = Path(directory)
        self._replay_only = replay_only
        self.hits = 0
        self.misses = 0

    def __repr__(self) -> str:
        return f"CachingBackend(directory={str(self._directory)!r}, replay_only={self._replay_only})"

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        key = cache_key(state, questions, model)
        path = self._directory / f"{key}.json" if key is not None else None
        if path is not None and path.exists():
            self.hits += 1
            return replace(_load(path), cache_hit=True)
        self.misses += 1
        if self._replay_only:
            reason = "no recorded response" if key is not None else "the request cannot be canonicalised"
            raise BackendError("replay_miss", reason, Result({}, False))
        response = await self._inner.ask(state, questions, model)
        if path is not None:
            _store(path, response)
        return response


def cache_key(state: str, questions: Sequence[Question], model: str) -> str | None:
    request = {
        "version": FORMAT_VERSION,
        "model": model,
        "state": state,
        "questions": [
            {
                "name": q.name,
                "kind": q.kind.value,
                "instructions": q.instructions,
                "options": [{"id": o.id, "description": o.description} for o in q.options],
            }
            for q in questions
        ],
    }
    try:
        canonical = rfc8785.dumps(request)
    except rfc8785.CanonicalizationError:
        return None
    return hashlib.sha256(canonical).hexdigest()


def _store(path: Path, response: BackendResponse) -> None:
    record = {
        "version": FORMAT_VERSION,
        "model": response.model,
        "request_id": response.request_id,
        "input_tokens": response.input_tokens,
        "answers": [_dump_answer(a) for a in response.answers],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as file:
            json.dump(record, file)  # floats round-trip exactly through repr; NaN is written as NaN
        Path(temporary).replace(path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def _load(path: Path) -> BackendResponse:
    try:
        record = cast("dict[str, Any]", json.loads(path.read_text(encoding="utf-8")))
        return BackendResponse(
            answers=tuple(_load_answer(a) for a in record["answers"]),
            input_tokens=int(record["input_tokens"]),
            request_id=str(record["request_id"]),
            model=str(record["model"]),
        )
    except (ValueError, KeyError, TypeError) as error:
        raise BackendError("cache_corrupt", f"{path.name}: {type(error).__name__}", Result({}, False)) from None


def _dump_answer(answer: Answer) -> dict[str, Any]:
    match answer:
        case PredicateAnswer(name, probability):
            return {"type": "predicate", "name": name, "probability": probability}
        case ChoiceAnswer(name, choice, probabilities, confidence):
            return {"type": "choice", "name": name, "choice": choice, "probabilities": dict(probabilities),
                    "confidence": confidence}  # fmt: skip
        case ScoreAnswer(name, score, probabilities, confidence):
            return {"type": "score", "name": name, "score": score, "probabilities": dict(probabilities),
                    "confidence": confidence}  # fmt: skip
        case Refusal(name):
            return {"type": "refusal", "name": name}
        case InvalidAnswer(name, detail):
            return {"type": "invalid", "name": name, "detail": detail}


def _load_answer(record: dict[str, Any]) -> Answer:
    kind, name = record["type"], record["name"]
    if kind == "predicate":
        return PredicateAnswer(name, record["probability"])
    if kind == "choice":
        return ChoiceAnswer(name, record["choice"], record["probabilities"], record["confidence"])
    if kind == "score":
        return ScoreAnswer(name, record["score"], record["probabilities"], record["confidence"])
    if kind == "refusal":
        return Refusal(name)
    if kind == "invalid":
        return InvalidAnswer(name, record["detail"])
    raise ValueError(f"unknown answer type {kind!r}")
