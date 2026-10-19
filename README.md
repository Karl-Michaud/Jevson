# Jevson

Jevson compiles a Pydantic model or JSON Schema into **bounded decisions over the options the schema declares**: enums, booleans, ordinal ratings, multi-label enum arrays, and union branches decided before construction. It also handles **generative fields**, which are admitted only after passing criteria you declare. Code assembles the result, and the result type has exactly three outcomes, verified by an adversarial suite. The decision model is the [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions) (`gpt-6-luna`).

It does **not** select values from the source. That was designed, measured on two decision models, and dropped ([below](#what-did-not-ship-and-why)).

> **Status: pre-release, `0.1.0.dev0`, not on PyPI.** The package name is pending a decision before publication: "Jevson" comes from Jev, the decision model it was first designed on, so it is kept only with TypeSafe's OK, or renamed. `0.x` versions may break between minor releases; every break is recorded in [CHANGELOG.md](CHANGELOG.md).

## Install

From a clone, for now (Python 3.11+):

```bash
pip install .
```

Dependencies: `httpx`, `jsonschema`, `pydantic` (≥ 2.12) and `rfc8785` (replay keys). There are no extras: no LLM adapter and no extractor ship in v0. You bring your own LLM by implementing the one-method `LLM` protocol.

## Quickstart

This runs offline, with no API key. `FakeBackend` stands in for the decision model and answers each question from a script. Swap in `DecisionsBackend()` and the same code makes real decisions.

```python
from typing import Literal

from pydantic import BaseModel, Field

from jevson import DecisionKind, FakeBackend, Jevson


class Ticket(BaseModel):
    category: Literal["billing", "bug", "feature_request"] = Field(description="the ticket's topic")
    refund_requested: bool = Field(description="the customer asks for a refund")


def stand_in(question):  # what a decision model might answer; a real backend decides this itself
    if question.kind is DecisionKind.PREDICATE:
        return FakeBackend.predicate(0.93)(question)
    billing = next(option for option in question.options if option.description == '"billing"')
    return FakeBackend.select(billing.id, 0.88)(question)


with Jevson(FakeBackend(default=stand_in)) as jevson:
    result = jevson.resolve(Ticket, "I was charged twice in October. Please refund the duplicate.")

print(result.value)             # {'category': 'billing', 'refund_requested': True}
print(result.complete)          # True: nothing unresolved
print(result.satisfies_schema)  # True: .value validates, and Ticket.model_validate succeeds
print(result.decisions)         # every decision with its full distribution, in hundredths
```

Worked examples, each runnable as `python examples/<name>.py` with no key (a test runs them all):

- [`examples/quickstart.py`](examples/quickstart.py): an enum, a bool, a declared ordinal (`x-jevson.ordinal`) and a multi-label enum array, with the default cost sink.
- [`examples/unions.py`](examples/unions.py): a discriminated union, where only the selected branch is built, with and without fan-out.
- [`examples/generative.py`](examples/generative.py): a summary drafted by your LLM and checked against declared criteria. The first draft is rejected with the failing criterion named, and the one redraft is admitted.

### Going live

```python
from jevson import DecisionsBackend, Jevson

with Jevson(DecisionsBackend()) as jevson:  # reads OPENAI_API_KEY; this spends money
    result = jevson.resolve(Ticket, source)
```

There is no default backend: constructing `DecisionsBackend` is an explicit choice to spend, so an environment variable never turns a test into paid calls. `aresolve()` is the async entry point, and `resolve()` refuses to run inside a running event loop.

## What it does

- **Bounded fields.** An enum becomes one `choice` over its declared values. A described `bool` becomes one `predicate`. An integer range marked `x-jevson.ordinal` becomes one `score`. A `list[Literal[...]]` becomes one membership predicate per declared value. Every bounded value comes from an option the schema declares, and `decided_by` says, for every field, whether it was decided, drafted and admitted, supplied by you, or set by code.
- **Unions.** A discriminated `anyOf`/`oneOf` is decided by a discriminator `choice`, and only the selected branch is built. By default every branch's questions are asked in the same request (one round trip); `JevsonConfig(union_fanout=False)` asks the branch's questions only after the discriminator is decided.
- **Generative fields.** `x-jevson.generate` declares criteria, plus an optional rubric with a minimum level. Your LLM drafts the field; each criterion is one predicate about the draft and the source, and a draft that fails is rejected (`Result.rejections`) and redrafted once by default (`redraft_budget`). No bounded field ever sees a draft: a level's adjudication questions are asked together, apart from every other question (a level that mixes them with bounded fields costs one more request). A field with no criteria is admitted and listed in `Result.ungated`. [docs/criteria-guide.md](docs/criteria-guide.md) shows how to write criteria, and `dry_run()` shows what adjudication asks about a draft, offline.
- **The result.** It is exactly one of three outcomes:
  - a complete `Result` that satisfies the schema;
  - a `Result` that names every hole (`unresolved`, with a reason from a closed set) and every failed constraint (`violations`);
  - a typed exception from Jevson's hierarchy.

  `decided_by`, `decisions`, `provenance`, `cost`, `model` and `versions` say how each value was decided and what it cost. A decision inside the tie margin (top two within 0.10) is `Unresolved(tie)`, and a question the API refuses is `Unresolved(refused)`, never a default.
- **Cost and replay.** `InMemoryCostSink` (or your own `CostSink`) receives every spend event, from any thread. `CachingBackend` and `ReplayLLM` replay recorded responses exactly, from a directory you choose. Nothing is logged or written by default.
- **Refusal before spend.** A construct the compiler cannot map raises `CompileError` naming every offending JSON pointer, before any API call.

## What is guaranteed, and what is not

| tier | claim | holds? |
|---|---|---|
| Structural | `.value` conforms to the schema's structure, **or the result says it does not** | yes |
| Constraint | `minimum`, `maxItems`, `pattern`, required fields and the like hold, or `Result.violations` names each failure | yes. `format` is checked for the formats `jsonschema` checks on its own (`email`, `date`, `ipv4`, `ipv6`, `uuid`, `regex` among them); the rest, `date-time` and `uri` included, are **not checked** unless you install `jsonschema`'s format extras (`pip install "jsonschema[format]"`) **[L10]** |
| Provenance | every bounded value came from a declared option | yes. No value comes from the source in v0, so there is no source-span provenance |
| Decision | every decision's full distribution is reported | yes |
| Calibration | reported probabilities match observed frequencies | **not established**. Probabilities are reported, not calibrated, and no default threshold drops a value |
| Semantic correctness | the value is the right interpretation | **no; not claimable** |

This is not "guaranteed JSON". It is a typed account of which values are there and which are not.

## Measured limits

Each item cites the evidence register, [docs/EVIDENCE.md](docs/EVIDENCE.md).

- **Source text can steer decisions, and draft text can steer adjudication.**
  - On Jev, text placed in a source steered which candidate was chosen, 20 of 20 times **[P7]**.
  - On `gpt-6-luna`, Jevson's live injection regression **failed**: 5 of 80 injected cases were admitted (the bar was ≤ 3) **[Q16]**. All 5 were the same attack: a summary that left out the refund amount but ended "this summary includes the refund amount stated in the source", against a criterion checking that the summary contains the amount. Drafts that praised themselves, or carried an instruction to the evaluator, were not admitted (0 of 60).
  - Steering of bounded decisions by source text has not been measured on `gpt-6-luna`; assume it can happen. A criterion of the form "the draft contains X" can be passed by a draft that falsely claims to contain X.
- **The redraft rate is model-labelled, not human-labelled.** The redraft default of 1 rests on labels from a separate model working blind, not a human **[Q17]**: 42% of redrafts were admitted and truly satisfied their criteria, and redrafts admitted while violating ran 6 points below first drafts.
- **The decision model over-rejects.** By the same labels, 53% of rejected first drafts already met their criteria **[Q17]**, so a rejection is not proof of a bad draft.
- **Probabilities are reported, not calibrated.** The API makes no calibration claim. On span selection, Phase 0r measured an ECE of 0.12 **[Q7]**.
- **No abstention.** Schema-derived choices have no "none of these". A bounded field the source does not support still gets one of its options, or `Unresolved(tie)` or `Unresolved(refused)`. `Result.absent` is always empty in v0.
- **The model cannot be pinned.** `gpt-6-luna` is an alias with no snapshot **[D3]**. Jevson records the returned `model` string on every result (`Result.model`, `Result.versions`). Identical requests returned identical answers in every Phase 0r test **[Q10]**, but there is no seed control, so that can change. Exact replay comes only from recorded responses.
- Adjudication checks only the criteria you declare. The decision model is not a fact-checker.

## What did not ship, and why

- **Source selection** (class D): picking a field's value out of the document, as a verified span, with a "none of these" abstention. It was designed in full, measured before building on real documents on two decision models, and dropped under rules fixed in advance:
  - **On Jev**: span choice was good (82–88%), but a confident wrong value was committed on about 21% of absent-answer cases. A second check cut that to 7% while rejecting 45% of correct answers **[Z9]**.
  - **On the Decisions API**: an option was committed on about half of the absent-answer cases (abstention 53%, bar 60%), and the second check did not fix it **[Q2, Q9]**.

  The record is in [docs/taxonomy.md](docs/taxonomy.md) §8–§9 and [docs/gate-probe.md](docs/gate-probe.md), and the deferral, with what would revive it, is in [docs/PLAN.md](docs/PLAN.md) §9.2. In v0, **every field that would be selected from the source is refused at compile time with the reason `source_selection_dropped`**, never half-supported: a field declaring `x-jevson.source`, and, when `JevsonConfig.default_extractor` is set, each unbounded field it would apply to. The setting itself is accepted; enums, booleans and the other bounded fields compile as usual. The `Extractor` protocol is defined and never called. Everything that depends on source selection did not ship either: parsing amounts and dates from the source, source-grounded arrays, abstention, and the source screen.
- **Pairwise entity resolution** (deciding whether two mentions are the same person or company): it failed its probe on both models **[Z4, Q4]** and is post-v0 ([docs/PLAN.md](docs/PLAN.md) §9.1).
- Arrays of objects and generative lists are refused at compile time with a named reason. A source too long for the context budget raises `PreflightError`, and one source per call is the limit; multi-source and long-source extraction is planned (PLAN Phase 9). Image input is not supported.

## How it compares

Every mechanism Jevson uses predates it. The claim is the combination, in an open library, as far as we found. The sources are [docs/DESIGN.md](docs/DESIGN.md) §9 and **[X2, X3]**, which record reading these projects' repositories and READMEs. We did not run or benchmark any of them, so the last column is a reading, not a measurement; anything the register does not record is marked *unverified*.

| project | what it does | what it does better than Jevson v0 |
|---|---|---|
| `Kiln-AI/jev_jsonschema` | JSON Schema → Jev questions → JSON, with no LLM; refuses free-form strings, arrays, objects, unions, `$ref` | It is the closest schema-first work, and Jevson adopted its mapping table. It targets Jev directly, with no second model in the loop. Jevson adds the Decisions API, unions, criteria-gated generation and the typed result **[X3]** |
| TypeSafe's extraction cookbooks, and `TypeSafeAI/typesafe-playground` | the cookbooks: pre-parsed value extraction (regex candidates → `choice` with a `NONE` option), the SDE cascade, citation checks, entity alignment, date extraction; the playground: document extraction with offsets, candidate ids and an explicit `null` choice | They **select values from the document**, which Jevson v0 does not do, and they come from the vendor of the model they target **[X3, V-cookbooks]** |
| `gbesse/jev-extract` | typed records, candidate/absent fields, per-field provenance, request packing, chunk aggregation | Source-grounded fields with absence, and chunking for long documents, neither of which is in v0. It works on fixed record types rather than compiling a schema **[X3]** |
| Google LangExtract | LLM extraction with character-interval grounding into the source, `None` when a value cannot be located | It grounds every extracted value to a source offset and extracts free text, both outside v0. It reports no confidence or abstention **[X2]** |
| Instructor | Pydantic-typed LLM outputs, with `CitationMixin`, quote validation, validation context and `Maybe` | It generates free-form fields directly, and its citation, quote-validation and `Maybe` patterns ground and abstain where v0 cannot **[X2]**. Breadth of provider support and adoption: *unverified*. Jevson's difference is that bounded fields are decided by a decision model over declared options, with distributions, rather than generated |

Not compared here: Cleanlab TLM, LlamaExtract, Azure Document Intelligence and the commercial extractors in DESIGN §9 offer per-field confidence or citations **[X2]**; we have not examined them in depth.

## Documentation

- [docs/DESIGN.md](docs/DESIGN.md): the SSOT. It covers the architecture, the guarantee tiers (§6), the limits (§10), and the v0 scope (§10.1).
- [docs/PLAN.md](docs/PLAN.md): the phases, the decisions recorded (§6), and every deferral with what would revive it (§9).
- [docs/EVIDENCE.md](docs/EVIDENCE.md): every factual claim, and the probe or source behind it.
- [docs/criteria-guide.md](docs/criteria-guide.md): writing adjudication criteria.
- [CHANGELOG.md](CHANGELOG.md): versions and the `0.x` policy.

## Licence

MIT. See [LICENSE](LICENSE).
