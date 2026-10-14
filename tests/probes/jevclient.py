"""Shared minimal decision-model HTTP client for red-team probes.

Two backends, chosen by the environment variable ``PROBE_BACKEND``:

- ``decisions`` (default since Phase 0r, 2026-10-14): the OpenAI Decisions API (``POST /v1/decisions``,
  ``gpt-6-luna``). The probes keep building Jev-shaped requests (``state`` plus a map of keyed questions) and read
  Jev-shaped answers; translation happens here, at the wire, through ``tests/phase0/decisions.py`` (predicate and
  choice) plus a ``score`` mapping that lives only in this file:
    request  ``{"type": "score", "instructions", "criteria": [label, ...]}`` -> ``{"type": "score", "name",
             "instructions", "levels": [{"label": label}, ...]}``;
    answer   ``{"score", "probabilities": [{"value": i, "label", "probability"}], "confidence"}`` ->
             ``{"type": "score", "score", "probabilities": {str(i): p}, "confidence", "labels": {str(i): label}}``.
  Two request adaptations for things Jev accepted and the Decisions API types do not: an object ``instructions``
  is sent as JSON text (keys in insertion order), and a choice option whose description is ``None`` is sent
  without a ``description``. The untranslated answers are kept under ``body["decisions_answers"]``.
  Raw output goes to ``tests/probes/out/0r/`` (gitignored) so it never mixes with the Jev pilots' ``out/``.
- ``jev``: the original Jev client (``jev-1.13.0``); its results are recorded in docs/EVIDENCE.md.

- Loads the backend's key (``OPENAI_API_KEY`` / ``TYPESAFE_API_KEY``) from Jevson/.env; never printed, logged or
  written, and every saved file passes through ``redact``.
- Async httpx, bounded concurrency, backoff on 429/529/5xx.
- Counts every HTTP request in a persistent counter file and (decisions) keeps a persistent spend ledger of
  ``usage.input_tokens`` priced at $0.10 per million, 2x above 272k input tokens (docs/EVIDENCE.md D1, D3). A request
  whose estimated cost would take the ledger past ``PROBE_CAP_USD`` (default 3.00) is refused before it is sent.
- Records wall-clock latency, the response ``model`` / ``usage`` fields, the request id and the refusal count.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import random
import sys
import time

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.phase0 import decisions as D  # noqa: E402

BACKEND = os.environ.get("PROBE_BACKEND", "decisions")
_BACKENDS = {
    "jev": ("https://api.typesafe.ai/v1/systemone", "jev-1.13.0", "TYPESAFE_API_KEY", "x-typesafe-request-id", ""),
    "decisions": (D.URL, D.MODEL, D.KEY_NAME, "x-request-id", "0r"),
}
if BACKEND not in _BACKENDS:
    raise RuntimeError(f"PROBE_BACKEND must be one of {sorted(_BACKENDS)}")
URL, MODEL, _KEY_NAME, _RID, _SUB = _BACKENDS[BACKEND]

_OUT = pathlib.Path(__file__).resolve().parent / "out"
SCRATCH = pathlib.Path(os.environ.get("PROBE_OUT", _OUT / _SUB if _SUB else _OUT))
RAW = SCRATCH / "raw"
RAW.mkdir(parents=True, exist_ok=True)
COUNTER = SCRATCH / "request_count.txt"
LEDGER = SCRATCH / "ledger.json"
RESULTS = pathlib.Path(__file__).resolve().parent / "results" / "0r"
CAP_USD = float(os.environ.get("PROBE_CAP_USD", "3.00"))
PRICE_PER_TOKEN = 0.10 / 1e6
LONG_CONTEXT = 272_000


def _load_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(f"{_KEY_NAME}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError(f"{_KEY_NAME} not found in .env")


_KEY = _load_key()


class BudgetExceeded(RuntimeError):
    pass


def _bump(n: int = 1) -> int:
    c = int(COUNTER.read_text()) if COUNTER.exists() else 0
    c += n
    COUNTER.write_text(str(c))
    return c


def cost_usd(input_tokens: int) -> float:
    return input_tokens * PRICE_PER_TOKEN * (2 if input_tokens > LONG_CONTEXT else 1)


def ledger() -> dict:
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"requests": 0, "billed_requests": 0, "input_tokens": 0, "cost_usd": 0.0, "unbilled_estimated_tokens": 0}


def _ledger_add(input_tokens: int | None, est: int) -> None:
    lg = ledger()
    lg["requests"] += 1
    if isinstance(input_tokens, int):
        lg["billed_requests"] += 1
        lg["input_tokens"] += input_tokens
        lg["cost_usd"] = round(lg["cost_usd"] + cost_usd(input_tokens), 6)
    else:
        lg["unbilled_estimated_tokens"] += est
    LEDGER.write_text(json.dumps(lg, indent=1))


def redact(s: str) -> str:
    return s.replace(_KEY, "<REDACTED>") if _KEY else s


# ---------------------------------------------------------------- Decisions translation (score lives here only)
def _to_decisions_question(name: str, q: dict) -> dict:
    q = dict(q)
    if not isinstance(q.get("instructions"), str):
        q["instructions"] = json.dumps(q.get("instructions"), ensure_ascii=False)
    if q["type"] == "score":
        return {"type": "score", "name": name, "instructions": q["instructions"],
                "levels": [{"label": str(lv)} for lv in q["criteria"]]}
    if q["type"] == "choice":
        out = D._question(name, q)
        out["choices"] = [{k: v for k, v in c.items() if not (k == "description" and v is None)} for c in out["choices"]]
        return out
    return D._question(name, q)


def to_request(state, questions: dict, model: str = MODEL) -> dict:
    text = state if isinstance(state, str) else json.dumps(state, ensure_ascii=False)
    return {"model": model, "input": text, "questions": [_to_decisions_question(k, q) for k, q in questions.items()]}


def from_response(body):
    body = D.from_response(body)
    if isinstance(body, dict) and isinstance(body.get("decisions_answers"), list):
        for a in body["decisions_answers"]:
            if isinstance(a, dict) and a.get("type") == "score" and isinstance(a.get("name"), str):
                ps = a.get("probabilities") or []
                body["answers"][a["name"]] = {
                    "type": "score", "score": a.get("score"), "confidence": a.get("confidence"),
                    "probabilities": {str(p["value"]): p["probability"] for p in ps},
                    "labels": {str(p["value"]): p.get("label") for p in ps}}
    return body


class Jev:
    """Same interface as the Jev pilot client: ``await Jev().ask(state, questions)``."""

    def __init__(self, concurrency: int = 8, model: str = MODEL, timeout: float = 300.0):
        self.sem = asyncio.Semaphore(concurrency)
        self.model = model
        self.backend = BACKEND
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"},
        )
        self.count = 0
        self.input_tokens = 0
        self.cost = 0.0
        self.refusals = 0
        self.statuses: dict[int, int] = {}
        self.models: set = set()

    async def aclose(self):
        await self.client.aclose()

    def payload(self, state, questions, model: str | None = None) -> dict:
        if self.backend == "decisions":
            return to_request(state, questions, model or self.model)
        return {"model": model or self.model, "state": state, "questions": questions}

    async def ask(self, state, questions, model: str | None = None, retries: int = 6) -> dict:
        """Returns dict: status, body (translated to Jev shape), latency_s, model, usage, request_id, refusals."""
        raw = json.dumps(self.payload(state, questions, model), ensure_ascii=False).encode("utf-8")
        est = int(len(raw) / 3.0) + 50  # conservative pre-send token estimate
        async with self.sem:
            for attempt in range(retries + 1):
                if self.backend == "decisions":
                    spent = ledger()["cost_usd"]
                    if spent + cost_usd(est) > CAP_USD:
                        raise BudgetExceeded(f"ledger ${spent:.4f} + est ${cost_usd(est):.4f} > cap ${CAP_USD:.2f}")
                t0 = time.perf_counter()
                try:
                    r = await self.client.post(URL, content=raw)
                except httpx.HTTPError as e:  # network error
                    self.count += 1
                    _bump()
                    if self.backend == "decisions":
                        _ledger_add(None, 0)
                    if attempt == retries:
                        return {"status": -1, "error": redact(repr(e)), "latency_s": None}
                    await asyncio.sleep(2 ** attempt)
                    continue
                dt = time.perf_counter() - t0
                self.count += 1
                _bump()
                self.statuses[r.status_code] = self.statuses.get(r.status_code, 0) + 1
                try:
                    body = r.json()
                except Exception:
                    body = redact(r.text)
                usage = body.get("usage") if isinstance(body, dict) else None
                itok = usage.get("input_tokens") if isinstance(usage, dict) else None
                if self.backend == "decisions":
                    _ledger_add(itok, est)
                if isinstance(itok, int):
                    self.input_tokens += itok
                    self.cost += cost_usd(itok)
                if r.status_code in (429, 529) or r.status_code >= 500:
                    if attempt == retries:
                        return {"status": r.status_code, "body": body, "latency_s": dt, "request_id": r.headers.get(_RID)}
                    ra = r.headers.get("retry-after")
                    wait = float(ra) if ra and ra.replace(".", "").isdigit() else 2 ** attempt
                    await asyncio.sleep(wait + random.random())
                    continue
                if self.backend == "decisions":
                    body = from_response(body)
                out = {"status": r.status_code, "body": body, "latency_s": dt, "attempts": attempt + 1,
                       "request_id": r.headers.get(_RID), "model": None, "usage": usage, "refusals": 0}
                if isinstance(body, dict):
                    out["model"] = body.get("model")
                    out["refusals"] = D.refusals(body) if self.backend == "decisions" else 0
                    self.refusals += out["refusals"]
                    if out["model"]:
                        self.models.add(out["model"])
                return out


def save(name: str, obj) -> pathlib.Path:
    p = RAW / f"{name}.json"
    p.write_text(redact(json.dumps(obj, indent=1, default=str)))
    return p


def save_summary(probe: str, clients, measured: dict, n=None, **extra) -> pathlib.Path:
    """Committed, machine-readable Phase 0r summary: tests/probes/results/0r/<probe>.json."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    cs = clients if isinstance(clients, list) else [clients]
    s = {"probe": probe, "backend": BACKEND, "model_requested": MODEL,
         "models_returned": sorted({m for c in cs for m in c.models}), "n": n,
         "requests": sum(c.count for c in cs), "input_tokens": sum(c.input_tokens for c in cs),
         "cost_usd": round(sum(c.cost for c in cs), 6), "refusals": sum(c.refusals for c in cs),
         "http_statuses": {str(k): sum(c.statuses.get(k, 0) for c in cs) for k in sorted({k for c in cs for k in c.statuses})},
         **extra, "measured": measured}
    p = RESULTS / f"{probe}.json"
    p.write_text(redact(json.dumps(s, indent=1, default=str)))
    return p


def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    ph = k / n
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * ((ph * (1 - ph) / n + z * z / (4 * n * n)) ** 0.5) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {k/n:.3f} [95% CI {lo:.3f}-{hi:.3f}]" if n else "0/0"
