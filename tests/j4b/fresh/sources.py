"""The typed fact inventory and the deterministic source renderer of the synthetic sets (design §2.1-§2.2), and the
R-set document loader (design §2.3).

Three synthetic domains: a support e-mail about a return, a travel-booking change and a utility-billing dispute.
Each source states six typed facts: a person's name, an identifier, two amounts and two dates; the secondary amount
and date may be absent. `RENDERINGS(value)` is the **only** list of surface forms: sources and drafts are rendered
from it, and `truth.py` matches against it (plan §4.1). Every non-slot text a draft can carry is in `DOMAINS` and
holds no digit, month, weekday, number word, currency word or name (the guard of `truth.py` checks it).

`load_rset_documents(ids)` reads the corpus manifest and returns exactly the picked documents, in `ids` order, with
no domain filter, cap or sort (`redraft.documents()` drops the receipts, FEAS48-R10-1).
"""

from __future__ import annotations

import datetime
import json
import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from tests.j4b import redraft

SEED = 20261019
"""The builder seed (design §2.5); [P7]'s is 777."""


class FixtureDefect(Exception):
    """A fixture string or row that breaks truth by construction; the build stops, nothing is dropped."""


@dataclass(frozen=True)
class Money:
    cents: int


@dataclass(frozen=True)
class Day:
    iso: str


@dataclass(frozen=True)
class Person:
    first: str
    last: str


@dataclass(frozen=True)
class Ident:
    prefix: str
    digits: str


Value = Money | Day | Person | Ident
KINDS = ("amount", "date", "name", "identifier")
MONTHS = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)  # fmt: skip


def kind(value: Value) -> str:
    return {Money: "amount", Day: "date", Person: "name", Ident: "identifier"}[type(value)]


def RENDERINGS(value: Value) -> tuple[str, ...]:
    """Every surface form of `value`, the source's forms first: an amount with and without its sign and thousands
    separator; a date long, ISO and day-month; a name in full and by each token; an identifier with and without
    its prefix."""
    if isinstance(value, Money):
        whole, cents = divmod(value.cents, 100)
        grouped, plain = f"{whole:,}.{cents:02d}", f"{whole}.{cents:02d}"
        return tuple(dict.fromkeys((f"${grouped}", grouped, f"${plain}", plain)))
    if isinstance(value, Day):
        d = datetime.date.fromisoformat(value.iso)
        month = MONTHS[d.month - 1]
        return (f"{month} {d.day}, {d.year}", value.iso, f"{d.day} {month} {d.year}")
    if isinstance(value, Person):
        return (f"{value.first} {value.last}", value.first, value.last)
    return (f"{value.prefix}-{value.digits}", f"{value.prefix} {value.digits}", value.digits)


@dataclass(frozen=True)
class Fact:
    slot: str
    kind: str
    with_value: str
    """The draft sentence that states the fact; `{v}` is the value, `{item}` the source's item."""
    topic_only: str
    """The same sentence without the value: the topic word stays."""
    optional: bool = False


@dataclass(frozen=True)
class Domain:
    name: str
    facts: tuple[Fact, ...]
    items: tuple[str, ...]
    """Item phrases (a product, a city, a service) for confirm sources; `dev_items` for dev sources."""
    dev_items: tuple[str, ...]
    source: str
    """The source text; `{slot}` is that fact's rendering, `{item}` the item, `{first}` the first name, and
    `[[slot|clause]]` a clause kept only when the optional fact is present."""
    extra: dict[str, str]
    """For each kind, a draft sentence that adds a value the source does not state."""
    none_sentence: dict[str, str]
    """For each optional slot, the sentence a draft uses when the source states none (absence branch)."""


def _facts(*rows: tuple[str, str, str, str, bool]) -> tuple[Fact, ...]:
    return tuple(Fact(slot, k, w, t, opt) for slot, k, w, t, opt in rows)


DOMAINS: dict[str, Domain] = {
    "return_email": Domain(
        "return_email",
        _facts(
            ("person", "name", "{v} sent back the {item}.",
             "The customer sent back the {item}.", False),
            ("ident", "identifier", "The return is for order {v}.",
             "The return is for an order on file.", False),
            ("amount", "amount", "A refund of {v} is confirmed.",
             "A refund is confirmed.", False),
            ("amount2", "amount", "A restocking fee of {v} applies.",
             "A restocking fee applies.", True),
            ("date", "date", "The replacement is due on {v}.",
             "A replacement is on its way.", False),
            ("date2", "date", "The item went back on {v}.",
             "The item has gone back.", True),
        ),
        ("rice cooker", "trail backpack", "desk fan", "camera tripod", "blender", "yoga mat", "bookshelf", "kettle"),
        ("monitor arm", "space heater", "water filter", "garden hose", "toaster oven", "hiking poles"),
        "From: {person}\nHello, I sent back the {item} from order {ident}[[date2| on {date2}]]. Your team confirmed "
        "a refund of {amount}.[[amount2| A restocking fee of {amount2} applies.]] The replacement is due on {date}. "
        "Could you confirm? Best, {first}",
        {
            "amount": "A further charge of {v} was also mentioned.",
            "date": "A follow-up call is planned for {v}.",
            "name": "{v} also wrote in about it.",
            "identifier": "Another reference, {v}, is listed.",
        },
        {"amount2": "The source states no restocking fee.", "date2": "The source states no return date."},
    ),
    "travel_change": Domain(
        "travel_change",
        _facts(
            ("person", "name", "{v} changed the trip to {item}.",
             "The traveller changed the trip to {item}.", False),
            ("ident", "identifier", "The change is under booking {v}.",
             "The change is under the existing booking.", False),
            ("amount", "amount", "A change fee of {v} is due.",
             "A change fee is due.", False),
            ("amount2", "amount", "The fare difference is {v}.",
             "There is a fare difference.", True),
            ("date", "date", "The new departure is on {v}.",
             "The departure has moved.", False),
            ("date2", "date", "The original departure was {v}.",
             "The original departure is cancelled.", True),
        ),
        ("Lisbon", "Bergen", "Krakow", "Ghent", "Tallinn", "Seville", "Turku", "Ljubljana"),
        ("Porto", "Valencia", "Graz", "Aarhus", "Riga", "Bilbao"),
        "Booking {ident}\nTraveller: {person}\nThe trip to {item} now departs on {date}[[date2| instead of "
        "{date2}]]. A change fee of {amount} applies.[[amount2| The fare difference is {amount2}.]] Kind regards, "
        "{first}",
        {
            "amount": "An extra charge of {v} was quoted too.",
            "date": "A return flight is booked for {v}.",
            "name": "{v} is travelling as well.",
            "identifier": "A linked booking, {v}, is mentioned.",
        },
        {"amount2": "The source states no fare difference.", "date2": "The source states no original departure date."},
    ),
    "billing_dispute": Domain(
        "billing_dispute",
        _facts(
            ("person", "name", "{v} disputes the {item} bill.",
             "The account holder disputes the {item} bill.", False),
            ("ident", "identifier", "The bill is for account {v}.",
             "The bill is for the account on file.", False),
            ("amount", "amount", "The disputed charge is {v}.",
             "A charge is in dispute.", False),
            ("amount2", "amount", "A credit of {v} was offered.",
             "A credit was offered.", True),
            ("date", "date", "Payment is due on {v}.",
             "A payment deadline applies.", False),
            ("date2", "date", "The bill was issued on {v}.",
             "The bill has been issued.", True),
        ),
        ("water", "electricity", "gas", "broadband", "district heating", "waste collection", "sewer", "mobile"),
        ("landline", "solar feed-in", "recycling", "parking permit", "street lighting", "pool membership"),
        "Account {ident}\nDear billing team, I am writing about my {item} bill[[date2| dated {date2}]]. I dispute "
        "the charge of {amount}.[[amount2| You offered a credit of {amount2}.]] Payment is due on {date}. Regards, "
        "{person}",
        {
            "amount": "A late fee of {v} is also mentioned.",
            "date": "A meter check is set for {v}.",
            "name": "{v} shares the account.",
            "identifier": "An older account, {v}, is cited.",
        },
        {"amount2": "The source states no credit.", "date2": "The source states no bill date."},
    ),
}  # fmt: skip
"""The three synthetic domains, rotated as design §2.1 rotates them."""

FIRST = ("Anneli", "Bertrand", "Chiamaka", "Desmond", "Esperanza", "Folasade", "Gunnar", "Hiroshi", "Imogen",
         "Jovana", "Kasimir", "Leocadia", "Mateusz", "Nadezhda", "Oluwaseun", "Perpetua", "Rosalind", "Sigrun",
         "Thaddeus", "Ulrike", "Valentin", "Wilhelmina", "Xiomara", "Yevgenia", "Zbigniew")  # fmt: skip
LAST = ("Abernathy", "Bjornstad", "Castellanos", "Dragomir", "Esterhazy", "Fitzwilliam", "Gallardo", "Hakobyan",
        "Ivanova", "Jankowski", "Kowalczyk", "Lindgren", "Montague", "Nakashima", "Oyelaran", "Pellegrino",
        "Quintero", "Rasmussen", "Szabo", "Thorvaldsen", "Uchenna", "Valderrama", "Wojcik", "Xenakis",
        "Zielinski")  # fmt: skip
PREFIX = {"return_email": "RX", "travel_change": "BK", "billing_dispute": "AC"}


@dataclass(frozen=True)
class Source:
    """One synthetic source: its domain, item phrase, the facts it states (absent optional facts omitted), the
    rendering index of each, and its text."""

    domain: str
    item: str
    facts: dict[str, Value]
    forms: dict[str, int]
    text: str


def draw_value(rng: random.Random, k: str, domain: str) -> Value:
    if k == "amount":
        return Money(rng.randint(100_000, 980_000))
    if k == "date":
        return Day(datetime.date(2026, rng.randint(1, 12), rng.randint(1, 28)).isoformat())
    if k == "name":
        return Person(rng.choice(FIRST), rng.choice(LAST))
    return Ident(PREFIX[domain], str(rng.randint(10_000, 99_999)))


def different(rng: random.Random, value: Value, avoid: Sequence[Value], domain: str) -> Value:
    """`value` if it shares no rendering with any of `avoid`, else a fresh value of its kind that does not."""
    taken = {r for v in avoid for r in RENDERINGS(v)}
    other = value
    for _ in range(1000):
        if not taken & set(RENDERINGS(other)):
            return other
        other = draw_value(rng, kind(value), domain)
    raise FixtureDefect(f"no value different from {value!r}")  # pragma: no cover - 1000 draws never all collide


SOURCE_FORMS = {"date": (0, 1, 2), "name": (0,), "identifier": (0,)}
"""The forms a source states a value in: a date in any form; a name in full; an identifier whole; an amount in any
form with its sign (`source_forms`)."""
SMALL_AMOUNT = (2_000, 95_000)
"""The secondary amount (a fee, a fare difference, a credit) is under a thousand, so it has no grouped form."""


def source_forms(value: Value) -> tuple[int, ...]:
    if isinstance(value, Money):
        return tuple(i for i, r in enumerate(RENDERINGS(value)) if r.startswith("$"))
    return SOURCE_FORMS[kind(value)]


OPTIONAL_CLAUSE = re.compile(r"\[\[(\w+)\|(.*?)\]\]", re.DOTALL)


def make_source(rng: random.Random, domain: str, items: Sequence[str], absent: Sequence[str] = ()) -> Source:
    """A source of `domain` stating every fact except the optional ones in `absent`, each in a source form; two
    values of one kind never share a rendering."""
    spec = DOMAINS[domain]
    facts: dict[str, Value] = {}
    forms: dict[str, int] = {}
    for fact in spec.facts:
        same_kind = [v for v in facts.values() if kind(v) == fact.kind]
        drawn = Money(rng.randint(*SMALL_AMOUNT)) if fact.slot == "amount2" else draw_value(rng, fact.kind, domain)
        value = different(rng, drawn, same_kind, domain)
        form = rng.choice(source_forms(value))
        if fact.slot not in absent:
            facts[fact.slot], forms[fact.slot] = value, form
    item = rng.choice(list(items))
    return Source(domain, item, facts, forms, render_source(spec, item, facts, forms))


def render_source(spec: Domain, item: str, facts: dict[str, Value], forms: dict[str, int]) -> str:
    """The source text: optional clauses kept only for present facts, every value in its source form."""
    person = facts["person"]
    assert isinstance(person, Person)
    text = OPTIONAL_CLAUSE.sub(lambda m: m.group(2) if m.group(1) in facts else "", spec.source)
    text = text.replace("{item}", item).replace("{first}", person.first)
    for slot, value in facts.items():
        text = text.replace(f"{{{slot}}}", RENDERINGS(value)[forms[slot]])
    return text


def load_rset_documents(ids: Sequence[str]) -> list[redraft.Document]:
    """Exactly the documents named by `ids`, in `ids` order, read from the corpus manifest (design §2.3)."""
    rows = [json.loads(line) for line in (redraft.CORPUS / "manifest.jsonl").read_text().splitlines() if line.strip()]
    by_id = {r["doc_id"]: r for r in rows}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        raise FixtureDefect(f"{len(unknown)} R-set ids are not in the corpus manifest, e.g. {unknown[0]}")
    return [
        redraft.Document(i, by_id[i]["domain"], (redraft.CORPUS / by_id[i]["path"]).read_text(encoding="utf-8"))
        for i in ids
    ]
