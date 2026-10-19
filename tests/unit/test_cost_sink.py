"""PLAN Phase 8: the default `CostSink` keeps every event, in order, from any thread."""

from __future__ import annotations

import threading

from jevson import CostEvent, CostSink, FakeBackend, InMemoryCostSink, Jevson


def test_it_is_a_cost_sink_and_records_a_run() -> None:
    sink = InMemoryCostSink()
    assert isinstance(sink, CostSink)
    schema = {"type": "object", "properties": {"paid": {"type": "boolean", "description": "the bill is paid"}}}
    with Jevson(FakeBackend(default=FakeBackend.predicate(0.9)), cost_sink=sink) as jevson:
        result = jevson.resolve(schema, "Paid.")
    assert [event.component for event in sink.events] == ["decision"]
    assert sink.events[0].request_id == result.cost.decision_request_ids[0]


def test_events_is_a_snapshot_and_clear_forgets() -> None:
    sink = InMemoryCostSink()
    sink.record(CostEvent("llm", input_tokens=3))
    snapshot = sink.events
    sink.record(CostEvent("decision"))
    assert snapshot == (CostEvent("llm", input_tokens=3),)
    assert len(sink.events) == 2
    sink.clear()
    assert sink.events == ()


def test_concurrent_records_from_threads_are_all_kept() -> None:
    sink = InMemoryCostSink()
    barrier = threading.Barrier(8)

    def worker(n: int) -> None:
        barrier.wait()
        for i in range(500):
            sink.record(CostEvent("decision", request_id=f"{n}-{i}"))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    ids = [event.request_id for event in sink.events]
    assert len(ids) == len(set(ids)) == 4000
    for n in range(8):
        mine = [i for i in ids if i is not None and i.startswith(f"{n}-")]
        assert mine == [f"{n}-{i}" for i in range(500)], "one thread's events kept their order"
