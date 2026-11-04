"""PLAN Phase 6: speculative fan-out vs a separate discrimination level, measured live (DESIGN §12).

Opt-in, billed, never in CI: not in pyproject's `testpaths`. 50 fixtures (5 schemas x 10 sources),
each resolved once under each strategy, in alternating order. Run on demand:

    OPENAI_API_KEY=... uv run --frozen pytest tests/integration/test_live_union_fanout.py -m integration -s

It prints per-strategy totals: requests, billed input tokens, questions asked, wall clock (median and
total per resolve), and how many fixtures resolved to the same value under both.
"""

from __future__ import annotations

import asyncio
import os
import statistics
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from jevson import BackendResponse, DecisionsBackend, Jevson, JevsonConfig, Question, Result

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY"),
]


def flag(text: str) -> bool:
    return Field(description=text)  # type: ignore[no-any-return]


class Card(BaseModel):
    """Paid by payment card."""

    network: Literal["visa", "mastercard", "amex"]
    contactless: bool = flag("the card payment was contactless")


class Bank(BaseModel):
    """Paid by bank transfer."""

    speed: Literal["instant", "standard"]
    international: bool = flag("the transfer crossed a border")


class Wallet(BaseModel):
    """Paid with a digital wallet."""

    provider: Literal["apple pay", "google pay", "paypal"]


class Payment(BaseModel):
    method: Card | Bank | Wallet
    refunded: bool = flag("the payment was refunded")


class Person(BaseModel):
    """An individual person."""

    role: Literal["customer", "supplier", "employee"]
    vip: bool = flag("the person is a VIP")


class Company(BaseModel):
    """A company or organisation."""

    size: Literal["small", "medium", "large"]
    listed: bool = flag("the company is publicly listed")


class Contact(BaseModel):
    party: Person | Company
    channel: Literal["email", "phone", "chat"]


class Parcel(BaseModel):
    """A parcel sent by courier."""

    carrier: Literal["ups", "fedex", "dhl"]
    fragile: bool = flag("the parcel is fragile")


class Freight(BaseModel):
    """Bulk freight."""

    mode: Literal["sea", "air", "rail"]
    hazardous: bool = flag("the freight is hazardous")


class Shipment(BaseModel):
    cargo: Parcel | Freight
    delayed: bool = flag("the shipment is delayed")


class Bug(BaseModel):
    """A bug report."""

    severity: Literal["low", "high", "critical"]
    reproducible: bool = flag("the bug can be reproduced")


class Feature(BaseModel):
    """A feature request."""

    area: Literal["user interface", "api", "billing"]


class Query(BaseModel):
    """A question from a user."""

    answered: bool = flag("the question has been answered")


class Ticket(BaseModel):
    issue: Bug | Feature | Query
    priority: Literal["p1", "p2", "p3"]


class Flight(BaseModel):
    """A flight booking."""

    cabin: Literal["economy", "business", "first"]
    refundable: bool = flag("the fare is refundable")


class Hotel(BaseModel):
    """A hotel booking."""

    board: Literal["room only", "breakfast", "all inclusive"]
    long_stay: bool = flag("the stay is longer than three nights")


class CarHire(BaseModel):
    """A car hire booking."""

    transmission: Literal["manual", "automatic"]


class Booking(BaseModel):
    reservation: Flight | Hotel | CarHire
    confirmed: bool = flag("the booking is confirmed")


SOURCES: dict[type[BaseModel], list[str]] = {
    Payment: [
        "Paid 40 EUR with a Visa card, tapped at the till.",
        "Customer paid by Mastercard online; the charge was later refunded.",
        "Settled by SEPA instant transfer from a German account to our French account.",
        "Standard bank transfer received from a local account, three days.",
        "Paid with Apple Pay on an iPhone.",
        "PayPal checkout completed; refund issued next day.",
        "Amex card, chip and PIN, not contactless.",
        "Google Pay used at the kiosk.",
        "Wire transfer from the US, standard speed, arrived Tuesday.",
        "Visa debit card, contactless, no refund requested.",
    ],
    Contact: [
        "Email from Jane, a long-standing VIP customer, about her order.",
        "Acme Corp, a large NYSE-listed firm, called our sales line.",
        "Chat message from Bob in our warehouse team (employee).",
        "A small family-owned supplier phoned about invoices.",
        "Globex Ltd, mid-sized and private, emailed procurement.",
        "Phone call from a supplier rep, Maria, regular account.",
        "Live chat: first-time customer asking about sizes.",
        "Email from a large private manufacturer with 5,000 staff.",
        "Our employee Sam emailed HR about leave.",
        "Chat with a VIP customer complaining about delivery.",
    ],
    Shipment: [
        "Parcel with glassware via DHL, marked FRAGILE, on schedule.",
        "Container shipped by sea from Shanghai, running two weeks late.",
        "FedEx overnight box with documents, arrived on time.",
        "Air freight of lithium batteries (hazmat class 9), delayed at customs.",
        "Rail freight of grain, non-hazardous, on schedule.",
        "UPS ground parcel, books, delayed by weather.",
        "Sea freight of steel coils, on time.",
        "DHL express parcel with a ceramic vase, fragile.",
        "Air cargo of flowers, not hazardous, delayed one day.",
        "FedEx parcel with clothes, no special handling.",
    ],
    Ticket: [
        "App crashes every time I open settings. Steps attached. Urgent, P1.",
        "Would love an export button in the API. Low priority, P3.",
        "How do I reset my password? (answered by support already) P2.",
        "Rare glitch in the chart, could not reproduce it again. P3.",
        "Please add invoices in PDF to billing. P2.",
        "Data loss when saving, reproducible, critical. P1.",
        "Can the UI have a dark mode? P3.",
        "Question: does the plan include SSO? Not yet answered. P2.",
        "Typo on the login page, minor. Reproducible. P3.",
        "Is there an SLA document? We replied with the link. P3.",
    ],
    Booking: [
        "Flight LHR-JFK, business class, flexible refundable fare, confirmed.",
        "Hotel in Rome, 5 nights with breakfast, awaiting confirmation.",
        "Car hire in Lisbon, automatic, confirmed.",
        "Economy flight, non-refundable, booking pending payment.",
        "All-inclusive resort for 7 nights, confirmed.",
        "Manual car rental for a weekend, confirmed.",
        "First class seat to Tokyo, refundable, confirmed.",
        "Room only, 2 nights in Berlin, confirmed.",
        "Automatic car from the airport, not yet confirmed.",
        "Economy return flight, refundable, confirmed.",
    ],
}
FIXTURES = [(schema, source) for schema, sources in SOURCES.items() for source in sources]


@dataclass
class Tally:
    requests: int = 0
    input_tokens: int = 0
    questions: int = 0
    seconds: list[float] = field(default_factory=list[float])
    values: list[object] = field(default_factory=list[object])


async def _measure(jevson: Jevson, schema: type[BaseModel], source: str, tally: Tally, sent: list[int]) -> Result:
    before = sent[0]
    started = time.perf_counter()
    result = await jevson.aresolve(schema, source)
    tally.seconds.append(time.perf_counter() - started)
    tally.requests += result.cost.decision_requests
    tally.input_tokens += result.cost.decision_input_tokens
    tally.questions += sent[0] - before
    tally.values.append(result.value)
    return result


class Counting:
    """Counts the questions sent, around the live backend."""

    def __init__(self, inner: DecisionsBackend, sent: list[int]) -> None:
        self.inner, self.sent = inner, sent

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        self.sent[0] += len(questions)
        return await self.inner.ask(state, questions, model)


PREAMBLE = (
    "This record was exported from the operations system. It is provided for internal processing only. "
    "Fields not mentioned below were not captured at the time of the export, and nothing should be inferred "
    "from their absence. Timestamps are in UTC. Amounts are shown in the currency of the original record. "
) * 6
"""~1,800 neutral characters: the `long` reading puts it before every source, since a request's state is
billed once per request and the fixtures' own sources are far shorter than real documents."""


@pytest.mark.parametrize("length", ["short", "long"])
def test_fan_out_vs_level_on_fifty_fixtures(length: str) -> None:
    assert len(FIXTURES) >= 50
    prefix = PREAMBLE + "\n\n" if length == "long" else ""
    tallies = {"level": Tally(), "fanout": Tally()}

    async def run() -> None:
        sent = [0]
        async with DecisionsBackend() as live:
            backend = Counting(live, sent)
            engines = {
                "level": Jevson(backend, config=JevsonConfig(union_fanout=False)),
                "fanout": Jevson(backend, config=JevsonConfig(union_fanout=True)),
            }
            for i, (schema, source) in enumerate(FIXTURES):
                order = ("level", "fanout") if i % 2 == 0 else ("fanout", "level")
                for name in order:
                    await _measure(engines[name], schema, prefix + source, tallies[name], sent)

    asyncio.run(run())
    agree = sum(a == b for a, b in zip(tallies["level"].values, tallies["fanout"].values, strict=True))
    for name, t in tallies.items():
        print(
            f"[{length}] {name}: requests={t.requests} input_tokens={t.input_tokens} questions={t.questions} "
            f"median_s={statistics.median(t.seconds):.3f} mean_s={statistics.mean(t.seconds):.3f} "
            f"total_s={sum(t.seconds):.2f}"
        )
    print(f"[{length}] same value under both: {agree}/{len(FIXTURES)}")
    assert tallies["fanout"].requests < tallies["level"].requests
