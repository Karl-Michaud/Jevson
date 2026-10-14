"""Translation between the Phase 0 request shape (Jev's) and the OpenAI Decisions API, for Phase 0r.

Phase 0r re-runs the pre-registered Phase 0 probes on the Decisions API with every template, rule and threshold
unchanged (docs/PLAN.md Phase 0r). So the probes keep building Jev-shaped requests (``state`` plus a map of keyed
questions), and this module translates at the wire:

- ``state`` (an object or a string) becomes ``input``: an object is serialised as JSON text, keys in insertion
  order, so the instructions' paths (``candidates.c0``, ``drafts.x``) still name what is in the input.
- Each question key becomes the question's ``name`` (unique, as Agents/CLAUDE.md §5 requires); ``noul`` becomes
  ``predicate``; a choice's ``criteria`` map becomes ``choices`` (``value`` = key, ``description`` = text), in order.
- Each answer is mapped back by ``name`` into the shape the scorer reads: ``{"noul": p}`` for a predicate, and
  ``{"choice", "probabilities": {value: p}, "confidence"}`` for a choice. Phase 0 asks no ``score`` questions,
  so none is mapped (an unknown type raises). A ``refusal`` stays
  ``{"type": "refusal"}``, which the pre-registered decoders score as invalid; runners count refusals separately.

Sources: the Decisions guide and openai-python 3.31.0 types (docs/EVIDENCE.md D1, D2).
"""
from __future__ import annotations

import json
from typing import Any

URL = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
KEY_NAME = "OPENAI_API_KEY"


def _question(name: str, q: dict) -> dict:
    kind = q["type"]
    if kind == "noul":
        return {"type": "predicate", "name": name, "instructions": q["instructions"]}
    if kind == "choice":
        choices = [{"value": k, "description": d} for k, d in q["criteria"].items()]
        return {"type": "choice", "name": name, "instructions": q["instructions"], "choices": choices}
    raise ValueError(f"question {name!r}: no Decisions API mapping for type {kind!r}")


def to_request(state: dict | str, questions: dict, model: str = MODEL) -> dict:
    """The ``/v1/decisions`` payload for one Phase 0 request."""
    text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    return {"model": model, "input": text, "questions": [_question(k, q) for k, q in questions.items()]}


def _answer(a: dict) -> dict:
    kind = a.get("type")
    if kind == "predicate":
        return {"type": "noul", "noul": a.get("probability")}
    if kind == "choice":
        probs = {p["value"]: p["probability"] for p in a.get("probabilities") or []}
        return {"type": "choice", "choice": a.get("choice"), "probabilities": probs, "confidence": a.get("confidence")}
    return {"type": kind if isinstance(kind, str) else "unknown"}


def from_response(body: Any) -> Any:
    """The Decisions response re-keyed into the Phase 0 shape: ``answers`` becomes a map by question name.
    The original list is kept under ``decisions_answers`` so nothing the API returned is lost."""
    if not isinstance(body, dict) or not isinstance(body.get("answers"), list):
        return body
    answers: dict[str, dict] = {}
    for a in body["answers"]:
        if isinstance(a, dict) and isinstance(a.get("name"), str):
            answers[a["name"]] = _answer(a)
    return {**body, "answers": answers, "decisions_answers": body["answers"]}


def refusals(body: Any) -> int:
    """How many answers in a (translated) response are refusals."""
    if not isinstance(body, dict) or not isinstance(body.get("answers"), dict):
        return 0
    return sum(1 for a in body["answers"].values() if isinstance(a, dict) and a.get("type") == "refusal")
