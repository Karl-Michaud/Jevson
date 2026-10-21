"""Offline checks of J4b's live harnesses (`live.py`, `redraft.py`, the chat adapter) on fakes; no network."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from jevson.backends.fake import FakeBackend
from jevson.types import JSONValue, LLMResponse, Message, PredicateAnswer, Question
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b import injection, live
from tests.j4b import redraft as R
from tests.j4b.labelling import prepare_items as P
from tests.j4b.labelling.records import ITEM_KEYS

CASES = injection.load_fixture()[:4]


@pytest.mark.parametrize(("layout", "requests"), [("multi", 4), ("single", 8)])
def test_injection_layouts_put_the_drafts_where_plan_says(layout: live.Layout, requests: int) -> None:
    backend = FakeBackend(default=FakeBackend.predicate(0.1))
    judged, tally = asyncio.run(live.run_injection(backend, CASES, layout))
    assert tally.requests == len(backend.calls) == requests
    assert tally.requests_per_resolve == {1}
    state = json.loads(backend.calls[0].state)
    case = CASES[0]
    expected = {f"{f}#generate": case["drafts"][f]["draft"] for f in case["drafts"]}
    if layout == "multi":
        assert state["drafts"] == expected  # both drafts, keyed, in one request
    else:
        assert len(state["drafts"]) == 1
        assert state["drafts"].items() <= expected.items()
    assert injection.regression(CASES, judged)["flips"] == 0


def test_injection_counts_flips_refusals_and_probabilities() -> None:
    def script(q: Question) -> PredicateAnswer:
        return PredicateAnswer(q.name, 0.9) if "refund amount" in q.instructions else FakeBackend.refuse()(q)  # type: ignore[return-value]

    judged, tally = asyncio.run(live.run_injection(FakeBackend(default=script), CASES, "multi"))
    report = injection.regression(CASES, judged)
    assert report["flips"] == 4
    assert report["flipped_drafts_by_role"] == {"injected": 3, "clean_source_injected": 1}
    assert tally.refusals == 4
    assert set(tally.p_true.values()) == {90}


def test_scripted_llm_answers_only_its_prompts() -> None:
    llm = live.ScriptedLLM({"Write it.": "x"})
    assert asyncio.run(llm.complete([Message("user", "Write it.\n\nsource")], None)).arguments == {"value": "x"}
    with pytest.raises(KeyError):
        asyncio.run(llm.complete([Message("user", "Other.\n\nsource")], None))


# --- redraft run ---


class Drafts:
    """Numbered drafts; `repeat` returns the first draft again on a redraft, `broken` returns prose."""

    def __init__(self, mode: str = "fresh") -> None:
        self.n = 0
        self.mode = mode

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        self.n += 1
        if len(messages) > 1 and self.mode == "repeat":
            return LLMResponse({"value": messages[1].content}, messages[1].content, 3, 2)
        if len(messages) > 1 and self.mode == "broken":
            return LLMResponse(None, "no tool call", 3, 2)
        text = f"draft {self.n} after {len(messages)} messages"
        return LLMResponse({"value": text}, text, 3, 2)


def _docs(domain: str, n: int) -> list[R.Document]:
    return [d for d in R.documents() if d.domain == domain][:n]


def test_documents_and_schemas_cover_every_domain() -> None:
    docs = R.documents()
    assert {d.domain for d in docs} == set(R.DOMAINS)
    assert sum(d.domain == "contract" for d in docs) == R.CONTRACTS
    for domain, fields in R.DOMAINS.items():
        assert set(R.draftings(domain)) == {f.pointer for f in fields}
        for f in fields:
            assert [c["id"] for c in R.criteria(f)] == [f"c{i}" for i in range(len(f.criteria))]


def _verdicts(first: float, second: float) -> FakeBackend:
    """`first` for every question of a first draft, `second` after: told apart by the state's draft text."""

    def answer(q: Question) -> PredicateAnswer:
        return PredicateAnswer(q.name, first)

    backend = FakeBackend(default=answer)
    original = backend.ask

    async def ask(state: str, questions: Sequence[Question], model: str) -> Any:
        p = second if "after 3 messages" in state else first
        backend._default = lambda q: PredicateAnswer(q.name, p)  # pyright: ignore[reportPrivateUsage]
        return await original(state, questions, model)

    backend.ask = ask  # type: ignore[method-assign]
    return backend


@pytest.mark.parametrize(
    ("first", "second", "mode", "expect"),
    [
        (0.9, 0.9, "fresh", (True, None, False)),
        (0.1, 0.9, "fresh", (False, "redraft", True)),
        (0.1, 0.1, "fresh", (False, "redraft", False)),
        (0.1, 0.9, "repeat", (False, None, False)),
        (0.1, 0.9, "broken", (False, None, False)),
    ],
)
def test_collect_document_records_each_instance(
    first: float, second: float, mode: str, expect: tuple[bool, str | None, bool]
) -> None:
    doc = _docs("resume", 1)[0]
    spend = R.Spend()
    [inst] = asyncio.run(R.collect_document(_verdicts(first, second), Drafts(mode), doc, spend))
    admitted, redraft, redraft_admitted = expect
    assert inst.instance_id == f"{doc.doc_id}/bio"
    assert inst.first
    assert inst.first_admitted is admitted
    assert (inst.redraft is not None and "after 3" in inst.redraft) == (redraft is not None)
    assert inst.redraft_admitted is redraft_admitted
    assert bool(inst.first_failing) is not admitted
    assert spend.llm_input_tokens > 0
    assert spend.decision_requests >= 1
    assert spend.models == {"fake-backend"}


def test_collect_stops_by_the_rule_and_builds_a_blind_labelling_set() -> None:
    docs = _docs("support_ticket", 12)  # two fields each
    rng = random.Random(7)
    backend = FakeBackend(default=lambda q: PredicateAnswer(q.name, 0.9 if rng.random() < 0.85 else 0.1))
    seen: list[int] = []
    instances, done, _ = asyncio.run(
        R.collect(
            backend, Drafts(), docs, min_rejected=3, min_admitted=3, batch=2, on_batch=lambda _, n: seen.append(n)
        )
    )
    assert seen[-1] == done
    assert done < len(docs)
    assert R.enough(instances, 3, 3)
    assert not R.enough(instances[:0], 1, 0)
    sampled = R.sample_admitted(instances, 2, 1)
    assert sampled == R.sample_admitted(instances, 2, 1)
    assert len(sampled) == 2
    by_id = {d.doc_id: d for d in docs}
    decoys = {
        i.instance_id: asyncio.run(R.decoy(Drafts(), by_id[i.doc_id], i, random.Random(1)))
        for i in instances
        if i.instance_id in sampled
    }
    rows = R.labelling_rows(instances, by_id, sampled, decoys)
    rejected = sum(not i.first_admitted for i in instances)
    assert [r["role"] for r in rows].count("decoy") == 2
    assert len(rows) == 2 * rejected + 4
    items, key = P.split(rows, random.Random(0))
    assert all(set(it) == ITEM_KEYS for it in items)
    assert "admitted" not in json.dumps(items)
    assert "decoy" not in json.dumps(items)
    assert {k["role"] for k in key} == {"first", "redraft", "decoy"}
    summary = R.summary(instances)
    assert summary["first_rejected"] == rejected
    assert set(summary["by_field"]) == {
        "support_ticket/summary",
        "support_ticket/next_step",
    }
    assert R.instance_record(instances[0])["instance_id"] == instances[0].instance_id


def test_a_decoy_identical_to_its_first_draft_is_null() -> None:
    doc = _docs("resume", 1)[0]
    inst = R.Instance("i", doc.doc_id, "resume", "/bio", "same", True, ())
    assert asyncio.run(R.decoy(Drafts("repeat"), doc, inst, random.Random(0))) is None


# --- the chat adapter's request and parsing (no network) ---


def test_chat_adapter_body_and_parse() -> None:
    llm = OpenAIChatLLM("k")
    body = llm.body([Message("user", "hi")], {"type": "object"})
    assert body["tool_choice"]["function"]["name"] == "submit"
    assert body["tools"][0]["function"]["strict"] is True
    assert "tools" not in llm.body([Message("user", "hi")], None)
    assert "k" not in repr(llm)

    def payload(message: dict[str, Any]) -> dict[str, Any]:
        return {"model": "m", "usage": {"prompt_tokens": 5, "completion_tokens": 2}, "choices": [{"message": message}]}

    call = {"tool_calls": [{"function": {"arguments": '{"value": "v"}'}}]}
    assert llm.parse(payload(call)) == LLMResponse({"value": "v"}, '{"value": "v"}', 5, 2, model="m")
    bad = {"tool_calls": [{"function": {"arguments": "{not json"}}]}
    assert llm.parse(payload(bad)).arguments is None
    assert llm.parse(payload({"tool_calls": [{"function": {"arguments": "[1]"}}]})).arguments is None
    assert llm.parse(payload({"content": "prose"})) == LLMResponse(None, "prose", 5, 2, model="m")
    assert llm.returned_models == {"m"}
