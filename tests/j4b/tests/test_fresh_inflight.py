"""H15, H15b: single-flight drafting and decision calls, cancellation-safe (design §2.3; FEAS48-R5-1)."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from jevson import CachingBackend, DecisionKind, FakeBackend, Jevson, JevsonConfig, LLMError
from jevson.llm.replay import ReplayLLM, replay_key
from jevson.types import BackendResponse, JSONValue, LLMResponse, Message, PredicateAnswer, Question
from tests.integration.openai_chat import OpenAIChatLLM
from tests.j4b.fresh import arms
from tests.j4b.fresh.inflight import SingleFlightBackend, SingleFlightLLM

MESSAGES = (Message("user", "Write the summary for the source below. Return only the value.\n\nRefund: $40."),)
TOOL: Mapping[str, JSONValue] = {"type": "object", "properties": {"value": {"type": "string"}}}
QUESTIONS = (Question("q0", DecisionKind.PREDICATE, "Is it?"),)


class GatedLLM:
    """Counts its calls; each waits for `release` before answering with a numbered draft."""

    def __init__(self) -> None:
        self.calls = 0
        self.release = asyncio.Event()

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        self.calls += 1
        number = self.calls
        await self.release.wait()
        return LLMResponse({"value": f"draft-{number}"}, f"draft-{number}", 3, 4)


class GatedBackend:
    def __init__(self) -> None:
        self.calls = 0
        self.release = asyncio.Event()

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        self.calls += 1
        number = self.calls
        await self.release.wait()
        return BackendResponse((PredicateAnswer("q0", 0.9),), 10, f"req-{number}", "gpt-6-luna")


async def both(
    first: asyncio.Future[object], second: asyncio.Future[object], release: asyncio.Event
) -> tuple[object, object]:
    await asyncio.sleep(0)
    release.set()
    return await first, await second


def test_h15_two_identical_drafting_requests_share_one_call(tmp_path: Path) -> None:
    async def scenario(single: bool) -> tuple[int, object, object]:
        inner = GatedLLM()
        replay = ReplayLLM(inner, tmp_path / ("sf" if single else "bare"), llm_id="m")
        llm = SingleFlightLLM(replay, "m") if single else replay
        a = asyncio.ensure_future(llm.complete(MESSAGES, TOOL))
        b = asyncio.ensure_future(llm.complete(MESSAGES, TOOL))
        first, second = await both(a, b, inner.release)
        return inner.calls, first, second

    calls, first, second = asyncio.run(scenario(single=True))
    assert calls == 1
    assert first == second
    bare_calls, bare_first, bare_second = asyncio.run(scenario(single=False))
    assert bare_calls == 2  # a bare ReplayLLM bills both and judges two different drafts
    assert bare_first != bare_second


def test_h15_two_identical_decision_requests_share_one_request(tmp_path: Path) -> None:
    async def scenario(single: bool) -> int:
        inner = GatedBackend()
        cache = CachingBackend(inner, tmp_path / ("sf" if single else "bare"))
        backend = SingleFlightBackend(cache) if single else cache
        a = asyncio.ensure_future(backend.ask("state", QUESTIONS, "gpt-6-luna"))
        b = asyncio.ensure_future(backend.ask("state", QUESTIONS, "gpt-6-luna"))
        first, second = await both(a, b, inner.release)
        assert first == second or not single
        return inner.calls

    assert asyncio.run(scenario(single=True)) == 1
    assert asyncio.run(scenario(single=False)) == 2


def test_h15b_a_waiter_cancelled_by_its_timeout_never_cancels_the_shared_call(tmp_path: Path) -> None:
    async def scenario() -> None:
        inner = GatedLLM()
        llm = SingleFlightLLM(ReplayLLM(inner, tmp_path / "llm", llm_id="m"), "m")
        a = asyncio.ensure_future(asyncio.wait_for(llm.complete(MESSAGES, TOOL), 0.05))
        b = asyncio.ensure_future(llm.complete(MESSAGES, TOOL))
        with pytest.raises(TimeoutError):
            await a
        assert not b.done()
        inner.release.set()
        assert (await b).raw == "draft-1"
        assert inner.calls == 1
        await llm.drain()
        assert llm.flights.live == {}
        key = replay_key("m", MESSAGES, TOOL)
        assert (tmp_path / "llm" / f"{key}.json").exists()

    asyncio.run(scenario())


def test_h15b_the_same_holds_for_a_decision_key(tmp_path: Path) -> None:
    async def scenario() -> None:
        inner = GatedBackend()
        backend = SingleFlightBackend(CachingBackend(inner, tmp_path / "decisions"))
        a = asyncio.ensure_future(asyncio.wait_for(backend.ask("s", QUESTIONS, "gpt-6-luna"), 0.05))
        b = asyncio.ensure_future(backend.ask("s", QUESTIONS, "gpt-6-luna"))
        with pytest.raises(TimeoutError):
            await a
        inner.release.set()
        assert (await b).request_id == "req-1"
        assert inner.calls == 1
        assert len(list((tmp_path / "decisions").glob("*.json"))) == 1

    asyncio.run(scenario())


def test_h15b_drain_waits_for_the_inner_call_to_end(tmp_path: Path) -> None:
    async def scenario() -> None:
        inner = GatedLLM()
        llm = SingleFlightLLM(ReplayLLM(inner, tmp_path / "llm", llm_id="m"), "m")
        a = asyncio.ensure_future(asyncio.wait_for(llm.complete(MESSAGES, TOOL), 0.01))
        with pytest.raises(TimeoutError):
            await a
        drain = asyncio.ensure_future(llm.drain())
        await asyncio.sleep(0)
        assert not drain.done()
        inner.release.set()
        await drain
        assert llm.flights.live == {}

    asyncio.run(scenario())


def test_h15b_a_timed_out_unit_surfaces_llm_error_timeout_and_its_replay_then_hits(tmp_path: Path) -> None:
    schema = {
        "type": "object",
        "required": ["summary"],
        "properties": {"summary": {"type": "string", "x-jevson": {"generate": {"criteria": ["is short"]}}}},
    }

    async def scenario() -> None:
        inner = GatedLLM()
        llm = SingleFlightLLM(ReplayLLM(inner, tmp_path / "llm", llm_id="m"), "m")
        jevson = Jevson(
            FakeBackend(default=FakeBackend.predicate(0.9)), llm=llm, config=JevsonConfig(step_timeout_s=0.05)
        )
        with pytest.raises(LLMError) as raised:
            await jevson.aresolve(schema, "Refund: $40.")
        assert raised.value.code == "timeout"
        inner.release.set()
        await llm.drain()
        again = await jevson.aresolve(schema, "Refund: $40.")
        assert again.value == {"summary": "draft-1"}
        assert inner.calls == 1

    asyncio.run(scenario())


def test_h15b_every_configuration_outlasts_the_drafting_ladder() -> None:
    defaults = inspect.signature(OpenAIChatLLM).parameters
    retries, timeout = defaults["retries"].default, defaults["timeout_s"].default
    ladder = (retries + 1) * timeout + sum(2**i for i in range(retries))
    assert ladder == 615
    assert all(c.step_timeout_s >= ladder for c in arms.LIBRARY_ARMS.values())
