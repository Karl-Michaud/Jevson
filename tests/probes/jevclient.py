"""Shared minimal Jev HTTP client for red-team probes.

- Loads TYPESAFE_API_KEY from Jevson/.env (never printed, logged or written).
- Async httpx, bounded concurrency, backoff on 429/529/5xx.
- Counts every HTTP request in a persistent counter file (budget tracking).
- Records wall-clock latency and the response `model` / `usage` fields.
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import random
import time

import httpx

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRATCH = pathlib.Path(os.environ.get("PROBE_OUT", pathlib.Path(__file__).resolve().parent / "out"))
RAW = SCRATCH / "raw"
RAW.mkdir(parents=True, exist_ok=True)
COUNTER = SCRATCH / "request_count.txt"
URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"


def _load_key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("TYPESAFE_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("TYPESAFE_API_KEY not found in .env")


_KEY = _load_key()


def _bump(n: int = 1) -> int:
    c = int(COUNTER.read_text()) if COUNTER.exists() else 0
    c += n
    COUNTER.write_text(str(c))
    return c


def redact(s: str) -> str:
    return s.replace(_KEY, "<REDACTED>") if _KEY else s


class Jev:
    def __init__(self, concurrency: int = 8, model: str = MODEL, timeout: float = 120.0):
        self.sem = asyncio.Semaphore(concurrency)
        self.model = model
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={"Authorization": f"Bearer {_KEY}", "Content-Type": "application/json"},
        )
        self.count = 0

    async def aclose(self):
        await self.client.aclose()

    async def ask(self, state, questions, model: str | None = None, retries: int = 6) -> dict:
        """Returns dict: status, body (parsed or text), latency_s, model, usage."""
        payload = {"model": model or self.model, "state": state, "questions": questions}
        async with self.sem:
            for attempt in range(retries + 1):
                t0 = time.perf_counter()
                try:
                    r = await self.client.post(URL, json=payload)
                except httpx.HTTPError as e:  # network error
                    self.count += 1
                    _bump()
                    if attempt == retries:
                        return {"status": -1, "error": redact(repr(e)), "latency_s": None}
                    await asyncio.sleep(2 ** attempt)
                    continue
                dt = time.perf_counter() - t0
                self.count += 1
                _bump()
                if r.status_code in (429, 529) or r.status_code >= 500:
                    if attempt == retries:
                        return {"status": r.status_code, "body": redact(r.text), "latency_s": dt}
                    ra = r.headers.get("retry-after")
                    wait = float(ra) if ra and ra.replace(".", "").isdigit() else 2 ** attempt
                    await asyncio.sleep(wait + random.random())
                    continue
                try:
                    body = r.json()
                except Exception:
                    body = redact(r.text)
                out = {"status": r.status_code, "body": body, "latency_s": dt,
                       "attempts": attempt + 1}
                if isinstance(body, dict):
                    out["model"] = body.get("model")
                    out["usage"] = body.get("usage")
                return out


def save(name: str, obj) -> pathlib.Path:
    p = RAW / f"{name}.json"
    p.write_text(redact(json.dumps(obj, indent=1, default=str)))
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
