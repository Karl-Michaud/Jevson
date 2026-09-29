"""Shared execution for the thin ``run_probe_*`` runners.

Every request is written, redacted, as one JSON line to ``tests/phase0/out/<name>.jsonl`` as soon as it returns,
so an interrupted run resumes without re-spending: a request id already answered with HTTP 200 is skipped.
Requests that fail at transport level are re-sent in up to ``passes`` passes (docs/taxonomy.md §2.1).
``--dry-run`` swaps in a deterministic fake transport and writes under ``out/dry/``.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import pathlib
import random
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Sequence

import httpx

from tests.phase0 import rules as R
from tests.phase0.client import Budget, JevClient, load_key

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"
RESULTS = HERE / "results"


@dataclass
class Request:
    rid: str
    state: dict | str
    questions: dict
    meta: dict = field(default_factory=dict)


def _fake_answer(q: dict, rng: random.Random) -> dict:
    if q["type"] == "noul":
        return {"type": "noul", "noul": round(rng.random(), 2)}
    keys = list(q["criteria"])
    w = [rng.random() ** 3 for _ in keys]
    cents = [int(100 * x / sum(w)) for x in w]
    cents[max(range(len(keys)), key=lambda i: cents[i])] += 100 - sum(cents)
    probs = {k: c / 100 for k, c in zip(keys, cents)}
    top = max(keys, key=lambda k: probs[k])
    return {"type": q["type"], "choice": top, "probabilities": probs, "confidence": round(max(probs.values()), 2)}


def fake_transport(seed: int = 0) -> httpx.MockTransport:
    """Deterministic plausible answers keyed on the request body: the same request always gets the same answer."""
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        h = hashlib.sha256(request.content + str(seed).encode()).hexdigest()
        rng = random.Random(h)
        answers = {k: _fake_answer(q, rng) for k, q in payload["questions"].items()}
        return httpx.Response(200, json={"answers": answers, "model": payload["model"],
                                         "usage": {"input_tokens": len(request.content) // 4}},
                              headers={"x-typesafe-request-id": "fake-" + h[:12]})
    return httpx.MockTransport(handler)


def request_hash(r: Request) -> str:
    return hashlib.sha256(json.dumps({"state": r.state, "questions": r.questions}, sort_keys=True,
                                     ensure_ascii=False).encode()).hexdigest()


def load_raw(path: pathlib.Path) -> dict[str, dict]:
    """Stored records by request id; an undecodable line (a write cut short) is skipped with a warning."""
    done: dict[str, dict] = {}
    if path.exists():
        for n, raw in enumerate(path.read_bytes().splitlines(), 1):
            try:
                rec = json.loads(raw.decode("utf-8"))
            except ValueError:   # includes UnicodeDecodeError: a write cut short inside a character
                print(f"warning: {path.name}:{n} is not valid JSON and is ignored", file=sys.stderr)
                continue
            done[rec["rid"]] = rec
    return done


async def execute(client: JevClient, requests: Sequence[Request], raw_path: pathlib.Path,
                  passes: int = 3) -> dict[str, dict]:
    """Send every request not yet answered with HTTP 200; returns rid -> response record."""
    if len({r.rid for r in requests}) != len(requests):
        raise ValueError("duplicate request ids")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    done = load_raw(raw_path)
    hashes = {r.rid: request_hash(r) for r in requests}

    def answered(r: Request) -> bool:
        """Final unless it failed at transport level (network error, 429, 5xx: §2.1) or the request changed.
        Records written before hashes were stored carry none and are accepted as they are."""
        rec = done.get(r.rid, {})
        status = rec.get("response", {}).get("status")
        retryable = status is None or status == -1 or status == 429 or status >= 500
        return not retryable and rec.get("request_sha256", hashes[r.rid]) == hashes[r.rid]

    async def one(r: Request) -> None:
        resp = await client.ask(r.state, r.questions)
        rec = {"rid": r.rid, "request_sha256": hashes[r.rid], "meta": r.meta, "response": resp}
        done[r.rid] = rec
        with raw_path.open("ab+") as f:   # written as soon as it returns: nothing paid for is lost
            f.seek(0, 2)
            if f.tell():
                f.seek(-1, 2)
                if f.read(1) != b"\n":   # a previous write was cut short: start a fresh line
                    f.write(b"\n")
            f.write((client.redact(json.dumps(rec, ensure_ascii=False)) + "\n").encode("utf-8"))

    for _ in range(passes):
        pending = [r for r in requests if not answered(r)]
        if not pending:
            break
        await asyncio.gather(*(one(r) for r in pending))
    return {r.rid: done[r.rid] for r in requests}


def answers_of(rec: dict | None) -> dict:
    """The answers map of a response record, or {} when the request failed (its questions score invalid)."""
    if not rec:
        return {}
    resp = rec.get("response") or {}
    body = resp.get("body")
    if resp.get("status") == 200 and isinstance(body, dict) and isinstance(body.get("answers"), dict):
        return body["answers"]
    return {}


def run_cli(name: str, argv: list[str], build: Callable[[], list[Request]],
            score: Callable[[dict[str, dict]], dict], *, transport: httpx.AsyncBaseTransport | None = None,
            runs: int = 1, allow_positional: bool = False) -> int:
    """--estimate prints the request count; --dry-run uses the fake transport; --live spends. Writes the summary
    to results/<name>.json (dry runs: out/dry/<name>.summary.json)."""
    ap = argparse.ArgumentParser(prog=f"run_{name}")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--estimate", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--live", action="store_true")
    ap.add_argument("--budget", type=int, default=R.MAX_REQUESTS)
    a = ap.parse_args(argv)
    reqs = build()
    n = len(reqs) * runs
    print(f"{name}: {n} requests ({len(reqs)} per run x {runs} run(s)); "
          f"{sum(len(r.questions) for r in reqs) * runs} questions")
    if a.estimate:
        return 0
    if a.dry_run:
        key, transport, out = "dry-run-key", transport or fake_transport(), OUT / "dry"
    else:
        key, out = load_key(), OUT
    client = JevClient(key, transport=transport, budget=Budget(a.budget), allow_positional=allow_positional)

    async def go() -> dict[str, dict]:
        allrecs: dict[str, dict] = {}
        try:
            for i in range(runs):
                tag = "" if runs == 1 else f".run{chr(65 + i)}"
                recs = await execute(client, reqs, out / f"{name}{tag}.jsonl")
                allrecs.update({(f"{chr(65 + i)}:{k}" if runs > 1 else k): v for k, v in recs.items()})
        finally:
            await client.aclose()
        return allrecs

    recs = asyncio.run(go())
    summary = score(recs)
    summary["requests_sent_this_invocation"] = client.budget.used
    summary["models"] = sorted({str((v.get("response") or {}).get("model")) for v in recs.values()})
    summary["raw_records_scored"] = len(recs)
    summary["http_status"] = dict(Counter(str((v.get("response") or {}).get("status")) for v in recs.values()))
    summary["request_ids"] = sorted(str((v.get("response") or {}).get("request_id")) for v in recs.values())
    dest = (out / f"{name}.summary.json") if a.dry_run else (RESULTS / f"{name}.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(summary, indent=1, ensure_ascii=False, default=str) + "\n")
    print(f"{name}: summary written to {dest}")
    return 0


def main_guard(fn: Callable[[list[str]], int]) -> None:  # pragma: no cover
    sys.exit(fn(sys.argv[1:]))
