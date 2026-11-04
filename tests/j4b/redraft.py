"""J4b's redraft-bar run: generative fields over real corpus documents, and the labelling set (PLAN Phase 4).

**Fields.** Each corpus domain gets one or two realistic generative fields (`DOMAINS`). Jevson's drafting prompt shows
the LLM only the declared `instructions`, never the criteria, so a first draft can fail them; a rejected draft is
redrafted once (`redraft_budget=1`) with its failing criteria passed back. One schema per document holds its domain's
fields, so a document's drafts are adjudicated together under the keyed layout of DESIGN §5.2. Criteria speak only
about the draft and the source, and none counts (sentences, words): counting is a known decision-model weakness and
length belongs in code (`max_draft_chars`), the owner's decision of 2026-10-16.

**Instances.** An instance is one (document, field): its first draft, the decision model's verdict, and, when the
first draft was rejected, its redraft and that verdict. A redraft identical to the first draft is not re-adjudicated
and, like a malformed draft, is recorded as a null draft (never labelled, never admitted).

**Stopping rule** (fixed before the run): documents are taken in a seeded random order, in batches, until at least
`min_rejected` first drafts were rejected and at least `min_admitted` admitted. It looks at first-draft counts only,
never at redrafts.

**Labelling set** (the owner's decisions, 2026-10-16): every rejected first draft and its redraft; a seeded random
sample of `admitted_sample` admitted first drafts; and one **decoy** per sampled admitted first draft, so that every
labelled (source, field) appears exactly twice. A decoy is drafted through Jevson's own redraft prompt with one
criterion, chosen at random (seeded), named as failing; it is never adjudicated and is excluded from every number.
"""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from jevson import Jevson
from jevson.compile.compiler import compile_schema
from jevson.execute.drafting import TOOL_SCHEMA, messages, read
from jevson.protocols import LLM, Backend
from jevson.types import Drafting, JSONValue, LLMResponse, Message, Rejection, StepNode

CORPUS = Path(__file__).resolve().parents[1] / "phase0/datasets/corpus"
CONTRACTS = 100
"""Every contract. Planned as the 40 shortest; raised to all 100 when the pilot rejected 4 of 14 first drafts, too few
for the pool to reach 100 rejections (the owner's decision, 2026-10-16)."""


@dataclass(frozen=True)
class Field:
    pointer: str
    instructions: str
    criteria: tuple[str, ...]


DOMAINS: dict[str, tuple[Field, ...]] = {
    "support_ticket": (
        Field("/summary", "A brief summary for the support agent picking up this ticket.", (
            "The draft states the specific problem the customer reports.",
            "The draft names the software, product or version that the source gives, if the source gives one.",
            "The draft states no fix or cause that the source does not state.",
        )),
        Field("/next_step", "The next step for the support agent.", (
            "The draft proposes one concrete action the support agent can take.",
            "The draft does not claim that the issue is resolved.",
            "The draft does not ask the customer for information that the source already gives.",
        )),
    ),
    "medical_intake": (
        Field("/intake_summary", "A short intake summary of this case.", (
            "The draft states the patient's age and sex as given in the source.",
            "The draft states the presenting complaint or reason for admission.",
            "The draft states no diagnosis, test result or treatment that the source does not state.",
        )),
    ),
    "resume": (
        Field("/bio", "A one-paragraph professional bio of this person.", (
            "The draft states the person's current or most recent position as given in the source.",
            "The draft mentions at least one degree together with its institution, as given in the source.",
            "The draft states no date, title, employer or honour that the source does not state.",
            "The draft is written in the third person.",
        )),
    ),
    "product_listing": (
        Field("/listing_blurb", "A short marketing blurb for this listing.", (
            "The draft names the item or items being sold.",
            "The draft makes no claim about condition, features or quantity that the source does not support.",
            "The draft mentions any condition caveat the source states, such as used, missing parts or repairs needed.",
        )),
    ),
    "contract": (
        Field("/plain_summary", "A plain-English summary of this agreement.", (
            "The draft names all parties to the agreement as given in the source.",
            "The draft states the agreement's term or duration as given in the source, or says the source states none.",
            "The draft states the governing law as given in the source, or says the source states none.",
            "The draft states no obligation, payment or date that the source does not state.",
        )),
    ),
}  # fmt: skip


@dataclass(frozen=True)
class Document:
    doc_id: str
    domain: str
    text: str


def documents(corpus: Path = CORPUS) -> list[Document]:
    """Every document of the domains in `DOMAINS`, contracts limited to the `CONTRACTS` shortest, in a fixed order."""
    rows = [json.loads(line) for line in (corpus / "manifest.jsonl").read_text().splitlines() if line.strip()]
    rows = sorted((r for r in rows if r["domain"] in DOMAINS), key=lambda r: (r["domain"], r["chars"], r["doc_id"]))
    contracts = [r for r in rows if r["domain"] == "contract"][:CONTRACTS]
    kept = [r for r in rows if r["domain"] != "contract"] + contracts
    return [Document(r["doc_id"], r["domain"], (corpus / r["path"]).read_text()) for r in kept]


def criteria(f: Field) -> list[dict[str, str]]:
    return [{"id": f"c{i}", "statement": text} for i, text in enumerate(f.criteria)]


def schema(domain: str) -> dict[str, Any]:
    props = {
        f.pointer.removeprefix("/"): {
            "type": "string",
            "x-jevson": {"generate": {"instructions": f.instructions, "criteria": list(f.criteria)}},
        }
        for f in DOMAINS[domain]
    }
    return {"type": "object", "properties": props, "required": sorted(props)}


def draftings(domain: str) -> dict[str, Drafting]:
    """Each field's compiled drafting, by pointer."""
    graph = compile_schema(schema(domain))
    return {n.target: n.drafting for n in graph.nodes.values() if isinstance(n, StepNode) and n.drafting is not None}


class Capture:
    """Wraps an `LLM` for one document and keeps each response under its field, in call order."""

    def __init__(self, inner: LLM, prompts: Mapping[str, str]) -> None:
        self._inner = inner
        self._pointer = dict(prompts)  # drafting prompt -> pointer
        self.calls: dict[str, list[LLMResponse]] = {}
        self.input_tokens = 0
        self.output_tokens = 0

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, JSONValue] | None) -> LLMResponse:
        response = await self._inner.complete(messages, tool_schema)
        pointer = self._pointer[messages[0].content.split("\n\n", 1)[0]]
        self.calls.setdefault(pointer, []).append(response)
        self.input_tokens += response.input_tokens
        self.output_tokens += response.output_tokens
        return response


@dataclass
class Instance:
    instance_id: str
    doc_id: str
    domain: str
    field: str
    first: str | None
    first_admitted: bool
    first_failing: tuple[str, ...]
    redraft: str | None = None
    redraft_admitted: bool = False
    redraft_failing: tuple[str, ...] = ()


@dataclass
class Spend:
    llm_input_tokens: int = 0
    llm_output_tokens: int = 0
    decision_input_tokens: int = 0
    decision_requests: int = 0
    models: set[str] = field(default_factory=set[str])


async def collect_document(backend: Backend, llm: LLM, doc: Document, spend: Spend) -> list[Instance]:
    drafting = draftings(doc.domain)
    capture = Capture(llm, {d.prompt: pointer for pointer, d in drafting.items()})
    result = await Jevson(backend, llm=capture).aresolve(schema(doc.domain), doc.text, redraft_budget=1)
    spend.llm_input_tokens += capture.input_tokens
    spend.llm_output_tokens += capture.output_tokens
    spend.decision_input_tokens += result.cost.decision_input_tokens
    spend.decision_requests += result.cost.decision_requests
    spend.models.update(result.model)
    unresolved = {u.pointer for u in result.unresolved}
    out: list[Instance] = []
    for pointer, d in drafting.items():
        calls = capture.calls.get(pointer, [])
        rejections = [r for r in result.rejections if r.pointer == pointer]
        first = read(calls[0], d.max_draft_chars).text if calls else None
        inst = Instance(
            f"{doc.doc_id}{pointer}", doc.doc_id, doc.domain, pointer, first, not rejections,
            rejections[0].criteria if rejections else (),
        )  # fmt: skip
        if rejections:
            redraft = read(calls[1], d.max_draft_chars).text if len(calls) > 1 else None
            inst.redraft = None if redraft == first else redraft
            inst.redraft_admitted = pointer not in unresolved and inst.redraft is not None
            inst.redraft_failing = rejections[1].criteria if len(rejections) > 1 else ()
        out.append(inst)
    return out


def enough(instances: Sequence[Instance], min_rejected: int, min_admitted: int) -> bool:
    admitted = sum(i.first_admitted for i in instances)
    return len(instances) - admitted >= min_rejected and admitted >= min_admitted


async def collect(
    backend: Backend,
    llm: LLM,
    docs: Sequence[Document],
    *,
    min_rejected: int,
    min_admitted: int,
    batch: int = 10,
    on_batch: Callable[[list[Instance], int], None] | None = None,
) -> tuple[list[Instance], int, Spend]:
    """Documents in the given order, a batch at a time, until the stopping rule holds; returns the instances, the
    number of documents processed and the spend."""
    instances: list[Instance] = []
    spend = Spend()
    done = 0
    while done < len(docs) and not enough(instances, min_rejected, min_admitted):
        chunk = docs[done : done + batch]
        for part in await asyncio.gather(*(collect_document(backend, llm, d, spend) for d in chunk)):
            instances += part
        done += len(chunk)
        if on_batch is not None:
            on_batch(instances, done)
    return instances, done, spend


async def decoy(llm: LLM, doc: Document, inst: Instance, rng: random.Random) -> str | None:
    """A second draft through Jevson's redraft prompt, with one criterion chosen at random named as failing."""
    d = draftings(doc.domain)[inst.field]
    criterion = rng.choice([c.text for c in d.checks])
    rejection = Rejection(inst.field, (criterion,), inst.first or "")
    text = read(await llm.complete(messages(d, doc.text, rejection), TOOL_SCHEMA), d.max_draft_chars).text
    return None if text == inst.first else text


def sample_admitted(instances: Sequence[Instance], k: int, seed: int) -> list[str]:
    """`k` admitted first drafts' instance ids, a seeded uniform sample, in sorted order."""
    admitted = sorted(i.instance_id for i in instances if i.first_admitted)
    return sorted(random.Random(seed).sample(admitted, min(k, len(admitted))))


def _row(inst: Instance, doc: Document, role: str, draft: str | None, admitted: bool) -> dict[str, Any]:
    spec = next(f for f in DOMAINS[inst.domain] if f.pointer == inst.field)
    return {
        "instance_id": inst.instance_id, "role": role, "source": doc.text, "field": inst.field,
        "criteria": criteria(spec), "draft": draft, "admitted": admitted, "group": inst.domain,
    }  # fmt: skip


def labelling_rows(
    instances: Sequence[Instance],
    docs: Mapping[str, Document],
    sampled: Sequence[str],
    decoys: Mapping[str, str | None],
) -> list[dict[str, Any]]:
    """The run record to label: rejected instances (first + redraft) and sampled admitted ones (first + decoy)."""
    chosen = set(sampled)
    rows: list[dict[str, Any]] = []
    for inst in instances:
        doc = docs[inst.doc_id]
        if not inst.first_admitted:
            rows.append(_row(inst, doc, "first", inst.first, False))
            rows.append(_row(inst, doc, "redraft", inst.redraft, inst.redraft_admitted))
        elif inst.instance_id in chosen:
            rows.append(_row(inst, doc, "first", inst.first, True))
            rows.append(_row(inst, doc, "decoy", decoys[inst.instance_id], False))
    return rows


def summary(instances: Sequence[Instance]) -> dict[str, Any]:
    by_domain: dict[str, dict[str, int]] = {}
    for i in instances:
        d = by_domain.setdefault(f"{i.domain}{i.field}", {"instances": 0, "rejected": 0, "redraft_admitted": 0})
        d["instances"] += 1
        d["rejected"] += not i.first_admitted
        d["redraft_admitted"] += i.redraft_admitted
    rejected = [i for i in instances if not i.first_admitted]
    return {
        "instances": len(instances),
        "first_admitted": len(instances) - len(rejected),
        "first_rejected": len(rejected),
        "first_null": sum(i.first is None for i in instances),
        "redraft_admitted": sum(i.redraft_admitted for i in rejected),
        "redraft_null": sum(i.redraft is None for i in rejected),
        "by_field": by_domain,
        "by_domain": {
            domain: {**counts, "rejected_first_drafts": counts["first_drafts"] - counts["admitted_first_drafts"]}
            for domain, counts in populations(instances).items()
        },
    }


def populations(instances: Sequence[Instance]) -> dict[str, dict[str, int]]:
    """First drafts and admitted first drafts per domain, for the per-domain weighting of C."""
    out: dict[str, dict[str, int]] = {}
    for i in instances:
        d = out.setdefault(i.domain, {"first_drafts": 0, "admitted_first_drafts": 0})
        d["first_drafts"] += 1
        d["admitted_first_drafts"] += i.first_admitted
    return out


def instance_record(inst: Instance) -> dict[str, Any]:
    return asdict(inst)
