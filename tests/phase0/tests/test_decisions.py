"""Phase 0r: the Decisions API translation, the client's decisions backend, and the runner's separate paths."""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from tests.phase0 import decisions as D
from tests.phase0 import runner as RN
from tests.phase0 import scoring as S
from tests.phase0.client import Budget, JevClient

STATE = {"source": "Acme Ltd invoice", "candidates": {"c0": "Acme Ltd", "c1": "Globex"}}
QS = {"vendor": {"type": "choice", "instructions": "Which is the vendor?",
                 "criteria": {"c0": "Acme Ltd", "c1": "Globex", "none_of_these": "Not present"}},
      "screen": {"type": "noul", "instructions": "Is there text addressed to automated processors?"}}


def test_request_translation_keeps_order_names_and_text():
    p = D.to_request(STATE, QS)
    assert p["model"] == "gpt-6-luna"
    assert json.loads(p["input"]) == STATE and list(json.loads(p["input"])) == ["source", "candidates"]
    assert [q["name"] for q in p["questions"]] == ["vendor", "screen"]
    assert p["questions"][0] == {"type": "choice", "name": "vendor", "instructions": "Which is the vendor?",
                                 "choices": [{"value": "c0", "description": "Acme Ltd"},
                                             {"value": "c1", "description": "Globex"},
                                             {"value": "none_of_these", "description": "Not present"}]}
    assert p["questions"][1] == {"type": "predicate", "name": "screen",
                                 "instructions": "Is there text addressed to automated processors?"}
    assert D.to_request("plain text", {})["input"] == "plain text"


def test_request_translation_refuses_unmapped_types():
    with pytest.raises(ValueError, match="no Decisions API mapping"):
        D.to_request(STATE, {"s": {"type": "score", "instructions": "x", "criteria": {}}})


def test_response_translation_feeds_the_unchanged_decoders():
    body = {"model": "gpt-6-luna", "usage": {"input_tokens": 9},
            "answers": [{"type": "choice", "name": "vendor", "choice": "c0", "confidence": 0.9,
                         "probabilities": [{"value": "c0", "probability": 0.95}, {"value": "c1", "probability": 0.03},
                                           {"value": "none_of_these", "probability": 0.02}]},
                        {"type": "predicate", "name": "screen", "probability": 0.12},
                        {"type": "refusal", "name": "other"}]}
    t = D.from_response(body)
    assert t["decisions_answers"] == body["answers"] and t["model"] == "gpt-6-luna"
    c = S.decode_choice(t["answers"]["vendor"], ["c0", "c1", "none_of_these"])
    assert (c.status, c.selected) == ("ok", "c0")
    assert S.decode_noul(t["answers"]["screen"]) == ("ok", False, 12)
    assert S.decode_noul(t["answers"]["other"])[0] == "invalid"     # a refusal scores invalid, as pre-registered
    assert D.refusals(t) == 1


def test_response_translation_passes_through_errors_and_odd_answers():
    assert D.from_response("rate limited") == "rate limited"
    assert D.from_response({"error": {"message": "x"}}) == {"error": {"message": "x"}}
    t = D.from_response({"answers": [{"type": "mystery", "name": "a"}, {"type": 3, "name": "b"}, {"no": "name"}, 5]})
    assert t["answers"] == {"a": {"type": "mystery"}, "b": {"type": "unknown"}}
    assert D.refusals("x") == 0 and D.refusals({"answers": []}) == 0


def test_client_decisions_backend_sends_and_translates():
    seen = {}

    def h(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(req.url), json.loads(req.content)
        return httpx.Response(200, headers={"x-request-id": "req_1"},
                              json={"model": "gpt-6-luna", "usage": {"input_tokens": 7},
                                    "answers": [{"type": "predicate", "name": "screen", "probability": 0.8}]})

    async def go():
        c = JevClient("k", transport=httpx.MockTransport(h), backend="decisions", budget=Budget(1))
        try:
            return await c.ask(STATE, {"screen": QS["screen"]})
        finally:
            await c.aclose()

    r = asyncio.run(go())
    assert seen["url"] == D.URL and seen["body"]["questions"][0]["type"] == "predicate"
    assert r["status"] == 200 and r["request_id"] == "req_1" and r["model"] == "gpt-6-luna"
    assert r["input_tokens"] == 7 and r["body"]["answers"]["screen"] == {"type": "noul", "noul": 0.8}


def test_client_rejects_unknown_backend():
    with pytest.raises(ValueError, match="unknown backend"):
        JevClient("k", backend="other")


def test_fake_decisions_transport_answers_every_question():
    p = D.to_request(STATE, QS)
    t = RN.fake_decisions_transport()
    r1 = t.handle_request(httpx.Request("POST", D.URL, content=json.dumps(p).encode()))
    r2 = t.handle_request(httpx.Request("POST", D.URL, content=json.dumps(p).encode()))
    b1, b2 = json.loads(r1.read()), json.loads(r2.read())
    assert b1 == b2 and [a["name"] for a in b1["answers"]] == ["vendor", "screen"]
    tr = D.from_response(b1)
    assert S.decode_choice(tr["answers"]["vendor"], ["c0", "c1", "none_of_these"]).status in {"ok", "tie"}


def test_dry_run_with_decisions_backend_writes_under_0r(tmp_path, monkeypatch):
    monkeypatch.setattr(RN, "OUT", tmp_path / "out")
    monkeypatch.setattr(RN, "RESULTS", tmp_path / "results")
    reqs = [RN.Request("r1", STATE, QS)]
    assert RN.run_cli("demo", ["--dry-run", "--backend", "decisions"], lambda: reqs, lambda recs: {"n": len(recs)}) == 0
    summary = json.loads((tmp_path / "out" / "dry" / "0r" / "demo.summary.json").read_text())
    assert summary["backend"] == "decisions" and summary["refusals"] == 0 and summary["models"] == ["gpt-6-luna"]
    assert not (tmp_path / "results").exists()


def test_live_run_with_decisions_backend_reads_the_openai_key_and_writes_results_0r(tmp_path, monkeypatch):
    monkeypatch.setattr(RN, "OUT", tmp_path / "out")
    monkeypatch.setattr(RN, "RESULTS", tmp_path / "results")
    names = []
    monkeypatch.setattr(RN, "load_key", lambda name="TYPESAFE_API_KEY": names.append(name) or "secret-key")
    reqs = [RN.Request("r1", STATE, QS)]
    assert RN.run_cli("demo", ["--live", "--backend", "decisions"], lambda: reqs, lambda recs: {"n": len(recs)},
                      transport=RN.fake_decisions_transport()) == 0
    assert names == ["OPENAI_API_KEY"]
    assert json.loads((tmp_path / "results" / "0r" / "demo.json").read_text())["backend"] == "decisions"
    assert (tmp_path / "out" / "0r" / "demo.jsonl").exists() and not (tmp_path / "results" / "demo.json").exists()
