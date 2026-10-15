"""Hostile backend answers: the `malformed responses` and `invalid values` rows of PLAN §4.2.

Each behaviour is an HTTP 200 body served to a real `DecisionsBackend` through `httpx.MockTransport`,
so the vendor wire parsing is what gets attacked. Three outcomes are expected:

- `ENVELOPES`: the body cannot be read as a response at all, so `BackendError(unparseable_response)`;
- `ANSWERS`: one answer is malformed, so that question gets an `InvalidAnswer` and the rest still parse;
- `VALUES`: the answer parses, but `probabilities.interpret` must not commit it
  (`invalid_backend_answer`, or `tie`).

Not shipped: the hostile doubles live in tests/ (PLAN §2).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx

from jevson import DecisionsBackend
from jevson.types import DecisionKind, DecisionNode, Option, OptionSource, Question

SENTINEL_KEY = "sk-SENTINEL-0123456789abcdef-must-never-leak"
MODEL = "gpt-6-luna"
RETURNED_MODEL = "gpt-6-luna-2026-10-01"

OPTIONS = (Option("c0", "Acme"), Option("c1", "Globex"))
LEVELS = (Option("l0", "poor"), Option("l1", "fair"), Option("l2", "good"))
QUESTIONS = (
    Question("paid", DecisionKind.PREDICATE, "Is the invoice paid?"),
    Question("vendor", DecisionKind.CHOICE, "Which vendor issued it?", OPTIONS),
    Question("quality", DecisionKind.SCORE, "How legible is it?", LEVELS),
)
NODES = {
    "paid": DecisionNode("paid", DecisionKind.PREDICATE, "Is the invoice paid?", OptionSource.PREDICATE, "/paid"),
    "vendor": DecisionNode("vendor", DecisionKind.CHOICE, "Which?", OptionSource.SCHEMA_ENUM, "/vendor", OPTIONS),
    "quality": DecisionNode("quality", DecisionKind.SCORE, "How?", OptionSource.SCHEMA_RUBRIC, "/quality", LEVELS),
}

Handler = Callable[[httpx.Request], httpx.Response]


def predicate(p: Any = 0.9, name: str = "q0") -> dict[str, Any]:
    return {"type": "predicate", "name": name, "probability": p}


def choice(probabilities: dict[str, Any] | None = None, chosen: Any = "c1", name: str = "q1") -> dict[str, Any]:
    probabilities = {"c0": 0.2, "c1": 0.8} if probabilities is None else probabilities
    listed = [{"value": v, "probability": p} for v, p in probabilities.items()]
    return {"type": "choice", "name": name, "choice": chosen, "probabilities": listed, "confidence": 0.7}


def score(probabilities: dict[str, Any] | None = None, mean: Any = 1.8, name: str = "q2") -> dict[str, Any]:
    probabilities = {"l0": 0.0, "l1": 0.2, "l2": 0.8} if probabilities is None else probabilities
    listed = [{"value": i, "label": label, "probability": p} for i, (label, p) in enumerate(probabilities.items())]
    return {"type": "score", "name": name, "score": mean, "probabilities": listed, "confidence": 0.6}


def good_answers() -> list[dict[str, Any]]:
    return [predicate(), choice(), score()]


def envelope(answers: Any, *, model: Any = RETURNED_MODEL, input_tokens: Any = 321) -> dict[str, Any]:
    return {"answers": answers, "model": model, "usage": {"input_tokens": input_tokens, "output_tokens": 0}}


def respond(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    """A response; bytes are sent verbatim, anything else as JSON (`NaN` allowed, as Python writes it)."""
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return httpx.Response(status, content=content, headers={"x-request-id": "req-1", **(headers or {})})


def serving(body: Any, status: int = 200) -> Handler:
    return lambda request: respond(body, status)


async def no_sleep(seconds: float) -> None:
    return None


def backend(handler: Handler, **kwargs: Any) -> DecisionsBackend:
    """A `DecisionsBackend` over a mock transport that never sleeps and is never rate-limited."""
    kwargs.setdefault("sleep", no_sleep)
    kwargs.setdefault("requests_per_minute", 60_000_000)  # the limiter never waits unless a test asks it to
    return DecisionsBackend(api_key=SENTINEL_KEY, transport=httpx.MockTransport(handler), **kwargs)


def with_answer(index: int, entry: Any) -> list[Any]:
    answers: list[Any] = good_answers()
    answers[index] = entry
    return answers


# --- the catalogue --------------------------------------------------------------------------

ENVELOPES: dict[str, Any] = {
    "empty body": b"",
    "non-JSON body": b"<html>bad gateway</html>",
    "null": None,
    "a JSON list": [good_answers()],
    "answers is an object": envelope({"q0": predicate()}),
    "answers missing": {"model": RETURNED_MODEL, "usage": {"input_tokens": 1}},
    "model missing": {"answers": good_answers(), "usage": {"input_tokens": 1}},
    "model not a string": envelope(good_answers(), model=7),
    "usage missing": {"answers": good_answers(), "model": RETURNED_MODEL},
    "input_tokens a string": envelope(good_answers(), input_tokens="321"),
    "input_tokens a bool": envelope(good_answers(), input_tokens=True),
    "input_tokens negative": envelope(good_answers(), input_tokens=-1),
    "invalid UTF-8": b'{"answers": "\xff\xfe"}',
}

# (behaviour, the answers list, the index of the question that must be invalid)
ANSWERS: dict[str, tuple[list[Any], int]] = {
    "wrong field name": (with_answer(0, {"type": "predicate", "name": "q0", "probabilty": 0.9}), 0),
    "missing probability": (with_answer(0, {"type": "predicate", "name": "q0"}), 0),
    "probability a string": (with_answer(0, predicate("0.9")), 0),
    "probability a bool": (with_answer(0, predicate(True)), 0),
    "probability null": (with_answer(0, predicate(None)), 0),
    "answer not an object": (with_answer(0, "yes"), 0),
    "answer without a name": (with_answer(0, {"type": "predicate", "probability": 0.9}), 0),
    "answer under another name": (with_answer(0, predicate(name="q9")), 0),
    "answer missing": (good_answers()[:2], 2),
    "name duplicated": ([*good_answers(), choice()], 1),
    "wrong type for the question": (with_answer(1, predicate(name="q1")), 1),
    "unknown answer type": (with_answer(1, {"type": "free_text", "name": "q1", "text": "Acme"}), 1),
    "choice not a string": (with_answer(1, choice(chosen=1)), 1),
    "choice a boolean": (with_answer(1, choice(chosen=True)), 1),
    "probabilities not a list": (with_answer(1, {**choice(), "probabilities": {"c0": 0.2, "c1": 0.8}}), 1),
    "probability entry not an object": (with_answer(1, {**choice(), "probabilities": [0.2, 0.8]}), 1),
    "option value a boolean": (with_answer(1, {**choice(), "probabilities": [{"value": True, "probability": 1}]}), 1),
    "option value repeated": (
        with_answer(1, {**choice(), "probabilities": [{"value": "c1", "probability": 0.5}] * 2}),
        1,
    ),
    "confidence a string": (with_answer(1, {**choice(), "confidence": "high"}), 1),
    "score not a number": (with_answer(2, score(mean="good")), 2),
    "score level without a label": (with_answer(2, {**score(), "probabilities": [{"value": 0, "probability": 1}]}), 2),
}

# Answers that parse, then must not commit: (behaviour, answers, node id, expected reason)
VALUES: dict[str, tuple[list[Any], str, str]] = {
    "option never offered": (with_answer(1, choice({"c0": 0.2, "c9": 0.8}, "c9")), "vendor", "invalid_backend_answer"),
    "option missing from the distribution": (with_answer(1, choice({"c1": 1.0})), "vendor", "invalid_backend_answer"),
    "probability above 1": (with_answer(0, predicate(1.2)), "paid", "invalid_backend_answer"),
    "probability below 0": (with_answer(0, predicate(-0.1)), "paid", "invalid_backend_answer"),
    "probability NaN": (with_answer(0, predicate(float("nan"))), "paid", "invalid_backend_answer"),
    "sum outside tolerance": (with_answer(1, choice({"c0": 0.3, "c1": 0.8})), "vendor", "invalid_backend_answer"),
    "vendor choice is not the argmax": (
        with_answer(1, choice({"c0": 0.2, "c1": 0.8}, "c0")),
        "vendor",
        "invalid_backend_answer",
    ),
    "score outside the levels": (with_answer(2, score(mean=7)), "quality", "invalid_backend_answer"),
    "predicate tie": (with_answer(0, predicate(0.5)), "paid", "tie"),
    "choice tie": (with_answer(1, choice({"c0": 0.47, "c1": 0.53})), "vendor", "tie"),
}
