"""A deterministic fake of both endpoints behind an `httpx.MockTransport`, and a trimmed workload, for the runner's
H-tests. Nothing here reaches the network.

Decisions: every predicate is answered from a hash of (input, instructions), so a replay gives the same answer,
with `model` "gpt-6-luna" and `usage.input_tokens` a third of the body's bytes (inside the bound). Chat
completions: a draft from a hash of the messages, `model` "gpt-5.4-mini-2026-03-17". `plan` lets a test replace
the response to a request (a failure, another model string), by endpoint and call number.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from tests.j4b.fresh import runner, workload
from tests.j4b.fresh.workload import Workload

DECISION_MODEL, CHAT_MODEL = "gpt-6-luna", "gpt-5.4-mini-2026-03-17"
Plan = Callable[[str, int, dict[str, Any]], httpx.Response | None]
"""(endpoint, 1-based call number on that endpoint, request body) -> a response to use instead, or None."""


def fraction(*parts: str) -> float:
    return int.from_bytes(hashlib.sha256("|".join(parts).encode()).digest()[:2], "big") / 65536


@dataclass
class FakeAPI:
    plan: Plan | None = None
    accept: float = 0.6
    """The share of predicates answered 0.9 (the rest 0.1); every answer is a fixed function of its request."""
    calls: dict[str, int] = field(default_factory=lambda: {"decisions": 0, "chat": 0})
    bodies: list[tuple[str, dict[str, Any]]] = field(default_factory=list[tuple[str, dict[str, Any]]])

    def __call__(self, request: httpx.Request) -> httpx.Response:
        endpoint = "chat" if request.url.path.endswith("/chat/completions") else "decisions"
        self.calls[endpoint] += 1
        body = json.loads(request.content)
        self.bodies.append((endpoint, body))
        if self.plan is not None and (planned := self.plan(endpoint, self.calls[endpoint], body)) is not None:
            return planned
        return self.decide(body, len(request.content)) if endpoint == "decisions" else self.draft(body)

    def decide(self, body: dict[str, Any], size: int) -> httpx.Response:
        answers = [
            {"name": q["name"], "type": "predicate",
             "probability": 0.9 if fraction(body["input"], q["instructions"]) < self.accept else 0.1}
            for q in body["questions"]
        ]  # fmt: skip
        return httpx.Response(200, json={"model": DECISION_MODEL, "answers": answers,
                                         "usage": {"input_tokens": size // 3}})  # fmt: skip

    def draft(self, body: dict[str, Any], model: str = CHAT_MODEL) -> httpx.Response:
        text = json.dumps(body["messages"], sort_keys=True)
        value = f"Draft {hashlib.sha256(text.encode()).hexdigest()[:12]}: the source says what it says."
        return httpx.Response(200, json=completion(value, model))


def completion(value: str, model: str = CHAT_MODEL) -> dict[str, Any]:
    call = {"function": {"arguments": json.dumps({"value": value})}}
    return {"model": model, "usage": {"prompt_tokens": 50, "completion_tokens": 20},
            "choices": [{"finish_reason": "stop", "message": {"tool_calls": [call]}}]}  # fmt: skip


async def no_sleep(_: float) -> None:
    return None


@dataclass
class Sleeps:
    waits: list[float] = field(default_factory=list[float])

    async def __call__(self, seconds: float) -> None:
        self.waits.append(seconds)


def trim(w: Workload, *, cases: int = 2, pairs: int = 1, documents: int = 2) -> Workload:
    """A small workload of the same shape: the first few cases of each set, the first `pairs` whole P-set pairs of
    every pattern, a few documents."""
    by_pattern: dict[str, list[str]] = {}
    for c in w.cases["pset"].values():
        listed = by_pattern.setdefault(str(c["pattern"]), [])
        if str(c["pair"]) not in listed:
            listed.append(str(c["pair"]))
    keep_pairs = {p for listed in by_pattern.values() for p in listed[:pairs]}
    kept: dict[str, dict[str, dict[str, Any]]] = {}
    for name, cs in w.cases.items():
        chosen = [k for k, c in cs.items() if name != "pset" or str(c["pair"]) in keep_pairs]
        kept[name] = {k: cs[k] for k in (chosen if name == "pset" else chosen[:cases])}
    docs = dict(list(w.documents.items())[:documents])
    units = {name: [u for u in us if u.key in (docs if name == "rset" else kept[name])] for name, us in w.units.items()}
    rows = {name: [r for r in rs if _kept_row(r, kept, docs)] for name, rs in w.rows.items()}
    return dataclasses.replace(w, cases=kept, documents=docs, units=units, rows=rows)


def _kept_row(row: Mapping[str, Any], kept: dict[str, dict[str, dict[str, Any]]], docs: dict[str, Any]) -> bool:
    if "doc_id" in row:
        return row["doc_id"] in docs
    if "case" in row:
        return row["case"] in kept["iset"]
    return row["draft_id"] in kept["pset"]


def loader(**sizes: int) -> Callable[[str], Workload]:
    cache: dict[str, Workload] = {}

    def load(phase: str) -> Workload:
        if phase not in cache:
            cache[phase] = trim(workload.load(phase), **sizes)
        return cache[phase]

    return load


def passing_pins(command: str, attempt: int) -> dict[str, Any]:
    return {"harness_commit": "0" * 40, "library_tree": "1" * 40, "harness": {}, "appendix_sha256": "a" * 64,
            "frozen_sha256": "f" * 64}  # fmt: skip


def env(root: Path, api: FakeAPI | None = None, **kw: Any) -> tuple[runner.Env, list[str]]:
    """A runner environment over the fake API, with no-op sleeps and passing pins; and the lines it printed."""
    lines: list[str] = []
    defaults: dict[str, Any] = {
        "pins": passing_pins, "transport": httpx.MockTransport(api or FakeAPI()), "key": lambda: "dummy-fake-api",
        "sleep": no_sleep, "client_sleep": no_sleep, "load": loader(), "out": lines.append,
    }  # fmt: skip
    return runner.Env(root, **{**defaults, **kw}), lines


def p7_subset(root: Path, w: Workload) -> Path:
    """A [P7] fixture holding exactly the trimmed workload's cases, for `Env.p7_fixture`."""
    path = root.parent / f"{root.name}-p7.jsonl"
    keep = w.cases.get("p7", {})
    lines = [json.dumps(c, sort_keys=True) + "\n" for c in keep.values()]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def label_all(root: Path, n: int, verdict: Callable[[dict[str, Any]], bool] = lambda _: True) -> None:
    """Grader labels for every exported item of attempt `n` (one chunk file per item chunk)."""
    confirm = root / f"attempt-{n}" / "confirm"
    (confirm / "labels").mkdir(parents=True, exist_ok=True)
    for chunk in sorted((confirm / "export" / "chunks").glob("items-*.jsonl")):
        items = [json.loads(line) for line in chunk.read_text(encoding="utf-8").splitlines()]
        labels = [{"id": i["id"], "criteria": {c["id"]: verdict(i) for c in i["criteria"]}, "note": ""} for i in items]
        out = confirm / "labels" / chunk.name.replace("items-", "labels-")
        out.write_text("".join(json.dumps(x) + "\n" for x in labels), encoding="utf-8")
