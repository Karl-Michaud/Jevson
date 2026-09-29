from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from tests.phase0 import client as C
from tests.phase0 import runner as RN

KEY = "sk-test-KEY-abcdef0123456789"
Q = {"q1": {"type": "noul", "instructions": "Is it?"}}


async def _nosleep(_s):
    return None


def mk(handler, **kw):
    kw.setdefault("sleep", _nosleep)
    kw.setdefault("limiter", C.RateLimiter(per_min=10**9, sleep=_nosleep))
    return C.JevClient(KEY, transport=httpx.MockTransport(handler), **kw)


def ok_body(req):
    return httpx.Response(200, json={"answers": {"q1": {"noul": 0.9}}, "model": "jev-1.13.0",
                                     "usage": {"input_tokens": 12}}, headers={"x-typesafe-request-id": "r1"})


def run(coro):
    return asyncio.run(coro)


def test_success_records_usage_and_request_id():
    seen = {}

    def h(req):
        seen["auth"] = req.headers["authorization"]
        seen["body"] = json.loads(req.content)
        return ok_body(req)

    async def go():
        c = mk(h)
        r = await c.ask({"source": "s"}, Q)
        await c.aclose()
        return c, r
    c, r = run(go())
    assert r["status"] == 200 and r["request_id"] == "r1" and r["input_tokens"] == 12 and r["attempts"] == 1
    assert seen["body"]["model"] == "jev-1.13.0" and seen["auth"] == f"Bearer {KEY}"
    assert KEY not in repr(c) and c.budget.used == 1


@pytest.mark.parametrize("first", [httpx.Response(429, headers={"retry-after": "1.5"}), httpx.Response(503),
                                   httpx.Response(429, headers={"retry-after": "soon"})])
def test_backoff_then_success(first):
    calls, sleeps = [], []

    async def sl(s):
        sleeps.append(s)

    def h(req):
        calls.append(1)
        return first if len(calls) == 1 else ok_body(req)

    async def go():
        c = mk(h, sleep=sl)
        r = await c.ask({"source": "s"}, Q)
        await c.aclose()
        return r
    r = run(go())
    assert r["status"] == 200 and r["attempts"] == 2 and len(calls) == 2
    assert sleeps and sleeps[0] in (1.5, 2.0)


def test_persistent_429_returns_after_retries_and_network_error_returns_minus_one():
    def h429(req):
        return httpx.Response(429)

    def hnet(req):
        raise httpx.ConnectError(f"boom {KEY}")

    async def go():
        c = mk(h429, max_retries=2)
        r1 = await c.ask({"source": "s"}, Q)
        c2 = mk(hnet, max_retries=1)
        r2 = await c2.ask({"source": "s"}, Q)
        await c.aclose()
        await c2.aclose()
        return r1, r2
    r1, r2 = run(go())
    assert r1["status"] == 429 and r1["attempts"] == 3
    assert r2["status"] == -1 and KEY not in r2["error"] and "<REDACTED>" in r2["error"]


def test_network_error_then_success():
    calls = []

    def h(req):
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("slow")
        return ok_body(req)

    async def go():
        c = mk(h)
        r = await c.ask({"source": "s"}, Q)
        await c.aclose()
        return r
    assert run(go())["status"] == 200


def test_non_json_body_is_redacted_and_400_not_retried():
    def h(req):
        return httpx.Response(400, text=f"bad {KEY}")

    async def go():
        c = mk(h)
        r = await c.ask({"source": "s"}, Q)
        await c.aclose()
        return r
    r = run(go())
    assert r["status"] == 400 and r["body"] == "bad <REDACTED>" and r["attempts"] == 1 and r["input_tokens"] is None


def test_budget_and_r13_guard():
    async def go():
        c = mk(ok_body, budget=C.Budget(limit=1))
        await c.ask({"source": "s"}, Q)
        with pytest.raises(C.BudgetExceeded):
            await c.ask({"source": "s"}, Q)
        with pytest.raises(ValueError):
            await c.ask({"items": [1]}, {"q": {"type": "noul", "instructions": "Is `items[0]` a fruit?"}})
        await c.aclose()
        assert c.budget.used == 1
    run(go())


def test_rate_limiter_spaces_starts():
    t = [0.0]
    slept = []

    async def sl(s):
        slept.append(s)
        t[0] += s

    lim = C.RateLimiter(per_min=60, clock=lambda: t[0], sleep=sl)

    async def go():
        for _ in range(3):
            await lim.wait()
    run(go())
    assert slept == [1.0, 1.0]


def test_redact_empty_key_and_load_key(tmp_path):
    c = C.JevClient("", transport=httpx.MockTransport(ok_body))
    assert c.redact("abc") == "abc"
    run(c.aclose())
    (tmp_path / ".env").write_text(f"X=1\nTYPESAFE_API_KEY='{KEY}'\n")
    assert C.load_key(tmp_path / ".env") == KEY
    (tmp_path / ".env").write_text("TYPESAFE_API_KEY=\n")
    with pytest.raises(RuntimeError):
        C.load_key(tmp_path / ".env")


# ---------------------------------------------------------------- runner

def test_fake_transport_is_deterministic_and_valid():
    t = RN.fake_transport(3)
    body = json.dumps({"model": "m", "state": {}, "questions": {
        "a": {"type": "choice", "instructions": "x", "criteria": {"c0": "1", "c1": "2", "none_of_these": "n"}},
        "b": {"type": "noul", "instructions": "y"}}}).encode()
    r1 = t.handle_request(httpx.Request("POST", "http://x", content=body))
    r2 = t.handle_request(httpx.Request("POST", "http://x", content=body))
    a1, a2 = json.loads(r1.read())["answers"], json.loads(r2.read())["answers"]
    assert a1 == a2
    assert sum(round(v * 100) for v in a1["a"]["probabilities"].values()) == 100
    assert 0 <= a1["b"]["noul"] <= 1


def test_execute_resumes_and_retries(tmp_path):
    calls = []

    def h(req):
        calls.append(json.loads(req.content)["state"]["source"])
        if json.loads(req.content)["state"]["source"] == "flaky" and calls.count("flaky") == 1:
            return httpx.Response(503)
        return ok_body(req)

    reqs = [RN.Request("r1", {"source": "a"}, Q), RN.Request("r2", {"source": "flaky"}, Q, {"doc": "d"})]
    raw = tmp_path / "x.jsonl"

    async def go(c):
        out = await RN.execute(c, reqs, raw)
        await c.aclose()
        return out
    out = run(go(mk(h, max_retries=0)))
    assert out["r1"]["response"]["status"] == 200 and out["r2"]["response"]["status"] == 200
    n_before = len(calls)
    run(go(mk(h, max_retries=0)))                   # everything answered: nothing re-sent
    assert len(calls) == n_before
    assert len(raw.read_text().splitlines()) == 3   # r1, failed r2, retried r2
    with pytest.raises(ValueError):
        run(RN.execute(mk(h), [reqs[0], reqs[0]], raw))


def test_answers_of():
    assert RN.answers_of(None) == {}
    assert RN.answers_of({"response": {"status": 400, "body": "x"}}) == {}
    assert RN.answers_of({"response": {"status": 200, "body": {"answers": {"q": 1}}}}) == {"q": 1}


def test_run_cli_estimate_dry_and_live(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(RN, "OUT", tmp_path / "out")
    monkeypatch.setattr(RN, "RESULTS", tmp_path / "results")
    build = lambda: [RN.Request("r1", {"source": "a"}, Q)]  # noqa: E731
    score = lambda recs: {"n": len(recs), "answers": [RN.answers_of(v) for v in recs.values()]}  # noqa: E731
    assert RN.run_cli("t", ["--estimate"], build, score) == 0
    assert "t: 1 requests" in capsys.readouterr().out
    assert RN.run_cli("t", ["--dry-run"], build, score, runs=2) == 0
    s = json.loads((tmp_path / "out" / "dry" / "t.summary.json").read_text())
    assert s["n"] == 2 and s["requests_sent_this_invocation"] == 2
    monkeypatch.setattr(RN, "load_key", lambda: KEY)
    assert RN.run_cli("t", ["--live"], build, score, transport=httpx.MockTransport(ok_body)) == 0
    s = json.loads((tmp_path / "results" / "t.json").read_text())
    assert s["n"] == 1 and KEY not in (tmp_path / "out" / "t.jsonl").read_text()
