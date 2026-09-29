# Jevson — implementation plan

> **Status:** Planning document, 2026-09-28. Pre-implementation.
>
> **Scope:** How Jevson gets built, in phases, with deliverables and testable exit criteria. The architecture it implements is [`DESIGN.md`](DESIGN.md) Revision 2; section references below (§3, §5, §7 …) point there.
>
> **Rule numbers** (R1–R14) refer to the twelve v0 rules plus the two implementation rules in `DESIGN.md` §7.

---

## 1. How this plan is organised

**One phase, one pull request.** Each phase is sized so a reviewer can hold the whole change in their head — a rough ceiling of **500 lines of new implementation code**, tests excluded. Where a phase would exceed that, it splits.

Each phase states:

- **Goal** — the one sentence that says why this PR exists
- **Deliverables** — what lands
- **Exit criteria** — testable checkboxes; the PR does not merge until all pass
- **Out of scope** — what is deliberately deferred, so review does not drift
- **Answers** — which `DESIGN.md` §12 open question this phase closes, if any

**Phases 1–3 are a working library on their own.** At the end of Phase 3, Jevson does what `Kiln-AI/jev_jsonschema` does, plus calibrated confidence, provenance, and typed abstention. That is a legitimate stopping point if anything goes wrong upstream of it.

**Phase 4 is the differentiator.** Everything before it is foundation; everything after it is breadth.

---

## 2. Repository layout

```text
jevson/
  __init__.py           public surface: compile_schema, Jevson, Result
  types.py              DecisionNode, DecisionKind, Span, Provenance,
                        Unresolved, Confidence, OptionSource
  graph.py              DecisionGraph, dependency edges, topological levelling
  errors.py             CompileError, RefusalReason, SchemaViolation

  compile/
    compiler.py         orchestration: schema + config -> DecisionGraph
    mapping.py          schema construct -> decision kind (the taxonomy, in code)
    refusal.py          loud refusal with JSON pointers (R14)
    unions.py           anyOf/oneOf -> level-0 discrimination nodes

  extract/
    protocol.py         Extractor
    spans.py            Span construction, substring verification
    llm.py              LLM-backed candidate extractor
    patterns.py         regex/rule-based extractor for dates, money, emails

  execute/
    executor.py         levels -> batched, keyed backend calls (R3, R13)
    policy.py           retry budget, confidence thresholds, abstention (R2)
    questions.py        keyed question-map construction (R13)

  backends/
    protocol.py         Backend
    jev.py              the only module importing the Jev SDK
    fake.py             deterministic fake, shipped as a testing tool
    hostile.py          adversarial fake, for the validation suite

  assemble/
    assembler.py        resolved graph -> JSON object
    entities.py         pairwise resolution, equivalence classes (R6)
    ordering.py         source order, semantic order (R7)
    cardinality.py      maxItems, overflow capture (R8)

  adjudicate/
    criteria.py         declared criteria -> noul batch
    rubrics.py          rubric -> score

  result.py             Result, provenance map, confidence map, cost
  cost.py               CostSink, accounting

tests/
  unit/
  property/             hypothesis strategies over generated schemas
  adversarial/          the central-claim suite (§9)
  integration/          real Jev key, marked, opt-in
  fixtures/schemas/     the Phase 0 sample, checked in with provenance

docs/
  taxonomy.md           Phase 0 output
  criteria-guide.md     how to write adjudication criteria that work
```

**Module discipline.** `backends/jev.py` is the only file permitted to import the Jev SDK; a test asserts this. Nothing in `compile/`, `assemble/`, or `graph.py` imports from `execute/` or `backends/` — dependencies point inward toward `types.py`.

---

## Phase 0 — Taxonomy, feasibility spike, and scope verdict

**Goal:** decide empirically whether Jevson is a broad structured-extraction library or a deliberately narrow disambiguation engine, and confirm the central mechanism works before any of it is built.

No library code. Two deliverables, one document and one throwaway spike.

### 0a — The taxonomy

Classify every schema construct and extraction operation against `DESIGN.md` §4's classes A–G, **against a named sample of real schemas**, not intuition.

**Sample sources**, each entry cited with its origin:

- `Kiln-AI/jev_jsonschema` test fixtures — the closest prior art's own coverage
- [schemastore.org](https://www.schemastore.org/) — real-world published schemas
- Documentation examples from LangChain, LlamaIndex, and Instructor — these represent what people actually build, which is the population we are pitching to
- Six extraction domains chosen for spread: **invoice/receipt, resume/CV, support-ticket triage, contract clause, medical intake, product listing**
- Asterion's layer payloads — included as *one sample among several*, never as the specification

**Columns**, per `DESIGN.md` §4.1:

| column | why |
|---|---|
| construct / operation | the thing being classified |
| class (A–G) | the routing decision |
| Jev primitive | `choice` / `score` / `noul` / none |
| option source | schema enum, rubric, candidate spans, predicate |
| `none_of_these` required? | R1 |
| dependency pattern | what it must wait for; determines levelling |
| provenance guarantee | span, declared option, or none |
| frequency in sample | how often it actually appears — counted, not guessed |
| semantic importance | how damaging a wrong-but-valid value is |
| **existing alternatives** | **does constrained decoding or plain code already solve this?** |
| v0 candidate? | the scope call |

The **existing alternatives** column does the real work. A construct that maps neatly onto a primitive but is already guaranteed by a grammar is not a differentiator, however elegant the mapping.

### 0b — The feasibility spike

Throwaway code in a scratch directory, **not** part of the library, using the live Jev key. It exists to kill the project early if the central mechanism does not work.

Four probes, each a handful of requests:

1. **Span disambiguation.** Hand-build 20 cases with multiple plausible spans per field. Measure accuracy and whether confidence separates right from wrong.
2. **`none_of_these` sensitivity.** Run the same cases with the correct answer *removed* from the option set. Measure how often Jev abstains rather than confidently picking a wrong candidate. **This is the safety property in R1 and the most important probe.**
3. **Pairwise entity resolution.** `"Dana"` / `"Dana Whitfield"` / `"Ms. Whitfield"` and 10 similar clusters. Measure whether equivalence classes come out right.
4. **Batching shape.** Confirm the keyed-vs-indexed finding (§2.1) on our own data before building the question-map layer around it.

### Exit criteria

- [ ] At least **6 real schemas** sampled from named public sources, each entry citing where it came from
- [ ] At least **150 fields** classified, with counts by class
- [ ] Every class C and D entry specifies: exact primitive, option source, `none_of_these` requirement, dependency pattern, provenance guarantee, batching behaviour
- [ ] Every entry records its **existing alternatives**
- [ ] The prediction below is marked **CONFIRMED** or **WRONG**, with the numbers that decided it
- [ ] Spike probe 2 (`none_of_these` sensitivity) reports an abstention rate; a rate near zero is a **stop-and-redesign** signal, not a tuning problem
- [ ] Spike probes 1, 3, 4 report measured numbers, written down whether or not they are favourable
- [ ] The v0 scope list is frozen and written into `DESIGN.md` §10
- [ ] No library code exists

### The prediction on record

> **Classes C and D are a narrow band.** Most of JSON Schema is class A (deterministic structure); most *fields* in real extraction schemas are class E (unbounded strings). C and D together cover enums-with-ambiguity, union discrimination, boolean predicates, ordinal ratings, and source-span disambiguation — real and unserved, but **not most of a typical schema**.

If confirmed, the honest product is **a decision-graph compiler for the disambiguation band**, positioned as such. That is a smaller library and a sharper one, and it is the outcome we have pre-committed to accepting.

If contradicted, the broader "structured extraction" positioning is earned on evidence.

**This prediction was recorded before the taxonomy was built, deliberately, so the taxonomy is a test rather than a rationalisation.**

### Out of scope

Any library code. Any API surface design beyond what the spike needs.

### Answers

`DESIGN.md` §12: calibration on this task, entity-resolution quality (partially — the spike gives a first reading, Phase 6 gives the real one).

---

## Phase 1 — Core model, graph, and the fake backend

**Goal:** the type system and the execution skeleton, with nothing real behind it, so everything afterwards can be tested without spending money or waiting on the network.

### Deliverables

- `types.py` — `DecisionNode`, `DecisionKind`, `Span`, `Provenance`, `OptionSource`, `Confidence`, `Unresolved`
- `graph.py` — `DecisionGraph`, dependency edges, **topological levelling** (R3, R11)
- `backends/protocol.py` — the `Backend` protocol
- `backends/fake.py` — a deterministic fake, **shipped as a first-class testing tool**, configurable to return specified answers, specified confidences, and abstentions
- `result.py` — `Result` with `value`, `provenance`, `confidence`, `unresolved`, `cost`
- `errors.py` — the error hierarchy
- `assemble/assembler.py` — resolved graph → JSON object, for the hand-built case

### Exit criteria

- [ ] A decision graph constructed by hand levels correctly, including a diamond dependency
- [ ] A graph with a dependency cycle is rejected at construction with the offending node ids
- [ ] The fake backend resolves a hand-built graph and the assembler produces a valid object
- [ ] `Span` verifies itself against a source by substring match, and rejects offsets that do not match
- [ ] `Unresolved` is a value in the result, never raised
- [ ] Round-trip property: for any hand-built graph, `levels(graph)` preserves every node exactly once and respects every edge
- [ ] No module outside `backends/` imports anything from `backends/`
- [ ] Public API surface is exported from `__init__.py` and nothing else is

### Out of scope

Compilation from a schema. Any real backend. Candidates. Arrays.

### PR size

~350 lines. Mostly types.

---

## Phase 2 — The compiler: schema → decision graph

**Goal:** turn a JSON Schema into a decision graph for the bounded subset, and refuse everything else loudly, before any network call.

### Deliverables

- `compile/mapping.py` — the Phase 0 taxonomy encoded as routing rules
- `compile/compiler.py` — schema + config → `DecisionGraph`
- `compile/refusal.py` — `CompileError` carrying every offending JSON pointer (R14)
- Pydantic model acceptance — a model or a raw JSON Schema both work; Pydantic converts to JSON Schema and everything internal works in JSON Schema
- Standalone, network-free `compile_schema()` in the public API

**Mapping, adopted from `jev_jsonschema` and credited:** bool → `noul` at 0.5; number bounded 0–1 → raw probability; string/int enum ≤ 255 → `choice`; integer range of 2–10 levels → `score`.

### Exit criteria

- [ ] Every class A construct is handled by code with no decision node emitted
- [ ] Every class C construct in the Phase 0 v0 list compiles to the primitive the taxonomy specifies
- [ ] Refusal is **total and specific**: an unmappable construct produces a `CompileError` listing *every* offending pointer, not the first
- [ ] `compile_schema()` makes **zero network calls** — asserted by a test with the network stubbed to raise
- [ ] Enum > 255 options, ordinal > 10 levels, and unbounded numerics each refuse with a distinct, named reason
- [ ] A Pydantic model and its emitted JSON Schema compile to identical graphs
- [ ] Property test: over generated schemas, `compile_schema()` either returns a graph or raises `CompileError` — never a third outcome, never a partial graph
- [ ] Compiling a schema twice produces an identical graph, node ids included

### Out of scope

Executing anything. Unions (Phase 5). Candidates (Phase 4). Arrays (Phase 6).

### PR size

~450 lines.

---

## Phase 3 — Executor and the real Jev backend

**Goal:** resolve a graph against the live model, in the minimum number of calls, with a real retry and abstention policy.

### Deliverables

- `execute/questions.py` — keyed question-map construction (**R13**; keys are object properties, never array indices)
- `execute/executor.py` — levels → one batched call per level (R3)
- `execute/policy.py` — retry budget, confidence thresholds, abstention handling (R2)
- `backends/jev.py` — the live backend, and the only module importing the Jev SDK
- `cost.py` — questions, input tokens, retries, wall clock split by backend
- Integration test suite, opt-in, marked, running against the real key

**At the end of this phase Jevson is a working library** — equivalent to `jev_jsonschema` in coverage, plus calibrated confidence, provenance, typed abstention, and level batching.

### Exit criteria

- [ ] A graph with N independent nodes resolves in exactly **one** backend call — asserted by counting calls, not by timing
- [ ] Question keys are object properties; a test fails if any generated key matches an array-index pattern
- [ ] `none_of_these` resolves to a bounded retry and then to `Unresolved`, never to an exception (R2)
- [ ] An unresolved **optional** field yields a partial result with the hole flagged; an unresolved **required** field is reported as a schema violation regardless of caller strictness preference
- [ ] Retry budget is respected exactly and recorded in `cost`
- [ ] `backends/jev.py` is the only module importing the vendor SDK — asserted by an import test
- [ ] Swapping `FakeBackend` for `JevBackend` changes no code outside construction
- [ ] Same input resolves to the same output across runs against the live API (Jev determinism, `DESIGN.md` §2)
- [ ] Cost accounting is populated on every result, including on failure paths

### Out of scope

Candidates. Unions. Arrays. Generative fields.

### Answers

`DESIGN.md` §12: retry budget's real value — measured here for schema-enum fields, re-measured in Phase 4 for candidates.

### PR size

~400 lines.

---

## Phase 4 — Candidates and source selection

**Goal:** the differentiator. Fields whose values come from the source, chosen by Jev among extracted spans, with provenance and mandatory abstention.

### Deliverables

- `extract/protocol.py` — the `Extractor` protocol
- `extract/spans.py` — `Span` construction and **substring verification against the source**
- `extract/llm.py` — LLM-backed candidate extraction under a provider tool schema
- `extract/patterns.py` — rule-based extraction for dates, money, emails, phone numbers
- Compiler support for `option_source = candidate_spans`
- **Mandatory `none_of_these` injection** on every candidate-backed choice (R1)
- Expanded-extraction retry on abstention (R2)
- Provenance emission: `SOURCE_SPAN(source_id, start, end)`

### Exit criteria

- [ ] Every candidate-backed choice includes `none_of_these` — asserted structurally in the compiler, not by convention (R1)
- [ ] **The adversarial coverage test:** when the correct answer is deliberately *absent* from the candidate set, the library abstains rather than committing a confident wrong value. This is the safety property the whole candidate architecture rests on (`DESIGN.md` §5.3)
- [ ] Every committed candidate value is verifiable against the source by substring match; a span that fails verification is rejected before the Jev call, not after
- [ ] A candidate set exceeding 255 options refuses at compile time with a named reason
- [ ] Disambiguation cases from the Phase 0 spike pass at the accuracy the spike measured
- [ ] The single-candidate case does **not** route through Jev by default (R4) — a test asserts zero backend calls for an unambiguous field
- [ ] Extractor is genuinely swappable: the same schema and source resolve through the LLM extractor and a hand-supplied extractor with identical downstream behaviour
- [ ] Provenance offsets survive assembly unchanged

### Out of scope

Arrays of candidates (Phase 6). Generative fields (Phase 7).

### Answers

`DESIGN.md` §12: calibration on this task, retry budget's real value.

### PR size

~500 lines. Split if extraction backends push it over.

---

## Phase 5 — Union discrimination

**Goal:** `anyOf` / `oneOf` resolved as a level-0 decision that determines which branch is *constructed*, not which is discarded (§3.2).

### Deliverables

- `compile/unions.py` — union → discrimination node at level 0
- Deferred compilation: branch nodes compile only after the discriminator resolves
- Refusal for unions whose branches are not distinguishable as a bounded choice
- `$ref` resolution where the reference is static

### Exit criteria

- [ ] A union resolves the discriminator in level 0, and **only the selected branch's nodes are ever compiled or executed** — asserted by counting compiled nodes, not by inspecting output
- [ ] A two-level union (a branch containing a union) levels correctly
- [ ] An undiscriminable union refuses at compile time with the offending pointer
- [ ] The wrong branch's fields never appear in the result, even as nulls
- [ ] Discrimination confidence appears in the result's confidence map under the union's pointer
- [ ] Low-confidence discrimination is surfaced, and below threshold produces `Unresolved` for the whole subtree rather than a guessed branch

### Out of scope

Recursive `$ref`. Dynamic references. `allOf` composition beyond flat merging.

### PR size

~250 lines. The smallest phase, and a clean differentiator — `jev_jsonschema` refuses unions outright.

---

## Phase 6 — Source-grounded arrays

**Goal:** arrays whose membership is a set of bounded decisions over a candidate set, with entity resolution, ordering, and honest overflow.

### Deliverables

- Membership: one `noul` per candidate, all in one batched call (R5)
- `assemble/entities.py` — **pairwise `noul` entity resolution**, scoped to a declared entity type, building equivalence classes (R6)
- `Normalizer` protocol — canonical-representative policy (earliest span / longest span / user-supplied), declared not baked in
- `assemble/ordering.py` — source order by default; semantic order via per-item `score`, marked experimental (R7)
- `assemble/cardinality.py` — `maxItems` enforcement with **overflow retained in the result** (R8)
- Refusal for generative/unbounded arrays

### Exit criteria

- [ ] `"Attendees were Dana, John, Sarah, and Michael"` produces a 4-element array in source order
- [ ] **The dedup case:** `"Dana"` / `"Dana Whitfield"` / `"Ms. Whitfield"` in one document produces **one** element, not three (R6)
- [ ] Entity resolution is scoped to a declared entity type; a test shows two different entity types with identical surface strings are *not* merged
- [ ] Pairwise resolution for n candidates issues **one** backend call, with n(n−1)/2 keyed questions
- [ ] `maxItems: 5` with six accepted candidates returns five and **records the sixth as overflow with its probability** — silent truncation fails the test (R8)
- [ ] An array with no source grounding refuses at compile time
- [ ] Semantic ordering is behind an explicit flag and documented as unproven (`DESIGN.md` §12)
- [ ] Ordering by source offset is deterministic across runs

### Out of scope

Nested arrays of objects. Arrays requiring cross-item constraints.

### Answers

`DESIGN.md` §12: entity-resolution quality; global ranking coherence — tested here, and if it fails, semantic ordering ships disabled with the finding recorded.

### PR size

~500 lines. Split entity resolution into its own PR if it grows.

---

## Phase 7 — Generative fields and adjudication

**Goal:** fields no candidate set can fill — a summary, a synthesised description — drafted by the LLM under a provider tool schema and admitted only after Jev adjudicates them.

### Deliverables

- `LLM` protocol, injected, provider-agnostic
- Generative fields requested under the **provider's tool schema**, so key presence and spelling are forced by the sampler rather than by instruction
- `adjudicate/criteria.py` — declared criteria → one `noul` each, batched
- `adjudicate/rubrics.py` — optional rubric → `score` with a declared minimum level
- Rejection naming the **failing criterion**, not a generic error
- Bounded redraft budget, then `Unresolved` (R2)
- `docs/criteria-guide.md`
- A **criteria dry-run tool**: given criteria and a handful of example drafts, show Jev's verdicts so authors can calibrate criteria empirically before shipping them

### Exit criteria

- [ ] A generative field is requested under a tool schema; the key cannot be missing or misspelled
- [ ] All criteria for a field are adjudicated in **one** batched call
- [ ] Rejection names the specific failing criterion
- [ ] Redraft budget is bounded and exhaustion yields `Unresolved`, never an exception or a silently accepted string
- [ ] **A generative field's content cannot corrupt the object's shape** — verified against the hostile LLM in the adversarial suite (§9)
- [ ] The dry-run tool runs against the fake backend without a key
- [ ] A field with no declared criteria is accepted with an explicit `no_criteria_declared` marker in the result, so ungated fields are visible rather than invisible

### Out of scope

Automatic criteria derivation from the schema. A criteria linter. Both are research projects; the dry-run tool is the honest v0 answer.

### Answers

`DESIGN.md` §12: criteria authoring.

### PR size

~450 lines.

---

## Phase 8 — Result surface, packaging, release

**Goal:** the library is usable by someone who did not build it.

### Deliverables

- Final `Result` surface: `value`, `provenance`, `confidence`, `unresolved`, `overflow`, `rejections`, `cost`
- `CostSink` protocol and default implementation
- README rewritten to the positioning in `DESIGN.md` §9.1 — **the current headline is false under our own analysis and must not survive to release**
- Quickstart, the three worked examples from `DESIGN.md` §3.4 and §5.1, and a `jev_jsonschema` comparison that is fair to it
- `pyproject.toml`, MIT licence, typed (`py.typed`), Python 3.11+
- PyPI release

### Exit criteria

- [ ] README makes no claim outside the tiers in `DESIGN.md` §6 — specifically, it does not claim guaranteed JSON validity as a differentiator
- [ ] Every public symbol is typed and documented
- [ ] Quickstart runs end to end against the fake backend with **no API key**
- [ ] The comparison table states plainly what `jev_jsonschema` does better
- [ ] Installed package exposes only the intended public surface
- [ ] Minimal dependencies: `jsonschema`, `pydantic`, `httpx`. Extractors and LLM providers are extras, never required

### PR size

~250 lines plus documentation.

---

## 3. Cross-cutting requirements

True at every phase; each PR is checked against them.

- **Refusal is loud and early.** Anything unmappable fails at compile time with JSON pointers, before a network call (R14).
- **No silent nulls.** Every absent value is `Unresolved` with a reason, or a declared schema default. Never `None` by accident.
- **No vendor SDK outside `backends/jev.py`.** Asserted by test.
- **Nothing logged by default.** Source text, spans, and values are written nowhere unless the caller supplies a sink.
- **Every backend call is counted.** Cost accounting is populated on success and failure paths alike.
- **Determinism.** Same schema, source, and backend produce the same result. Jev is deterministic (`DESIGN.md` §2); anything non-deterministic in our own code is a bug.
- **The fake backend keeps working.** Every phase that adds a capability adds fake-backend support for it in the same PR.
- **Protocols earn their place.** No interface is introduced without a second real implementation or a concrete, named prospect of one.

---

## 4. Validation strategy

The central claim is *the result's shape survives arbitrary model behaviour*. The evidence standard for it has to be higher than for anything else in the library.

### 4.1 The adversarial suite

`backends/hostile.py` and a hostile LLM double return, deliberately:

| category | behaviours |
|---|---|
| **malformed responses** | wrong field names, missing fields, wrong types, extra keys, empty response, `null` |
| **invalid values** | out-of-enum selections, probabilities outside [0,1], confidences that are `NaN`, contradictory distributions |
| **protocol violations** | prose instead of a tool call, a tool call for a tool that was not offered, duplicated answers for one key |
| **hostile content** | control characters, enormous strings, unicode confusables, text that looks like JSON |
| **hostile spans** | offsets that do not exist in the source, overlapping spans, spans whose text is absent from the source, duplicate candidates |

**The property, asserted over generated schemas × every hostile behaviour:**

> The result is either an object that validates against the original schema, or a typed refusal naming the reason. Never a third outcome. Never a partial object that claims to satisfy the schema.

### 4.2 Property-based tests

`hypothesis` strategies generate schemas across the supported subset. Invariants:

- `compile_schema()` returns a graph or raises `CompileError` — never a partial graph
- Levelling preserves every node exactly once and respects every edge
- Assembly of a fully resolved graph always validates against the original schema
- Provenance spans always verify by substring against the source
- Cost is monotonic: retries only increase it

### 4.3 Integration tests

Opt-in and marked, running against the live key. They measure rather than assert where the quantity is a property of the model rather than of our code — accuracy, abstention rate, calibration separation. **Measured numbers are written down whether or not they are favourable**, in `docs/taxonomy.md` alongside the Phase 0 spike results.

---

## 5. Risks

| risk | where it bites | mitigation |
|---|---|---|
| **`none_of_these` doesn't work** — Jev confidently picks a wrong candidate when the right answer is absent | Phase 0b, fatal to Phase 4 | Probed in the Phase 0 spike *before* anything is built. A near-zero abstention rate is stop-and-redesign, not a tuning problem. |
| **The taxonomy comes back narrow and we pad it anyway** | Phase 0 | Prediction recorded in advance; pre-committed to shipping the narrow version |
| **Entity resolution is poor on real prose** | Phase 6 | Probed in Phase 0b; if it fails, dedup becomes the extractor's declared contract and we say so loudly |
| **Candidate extraction becomes the weak link** | Phase 4 onward | The unreliable component moved upstream, it did not disappear. `none_of_these` is the only defence and it is mandatory. |
| **Semantic ordering is incoherent** | Phase 6 | Shipped behind a flag, documented as unproven; independent scores encode no pairwise preference |
| **Jev single-vendor, early access** | everywhere | `Backend` protocol; `AnyJev`/`jevfire` identified; fake backend always working |
| **Scope creep via derived values** | Phase 4+ | Explicitly out of v0 (R9); flat provenance map, not a graph |
| **We rebuild `jev_jsonschema` and stop** | Phase 3 | Phase 3 is a legitimate stopping point but not the product; Phase 4 is the reason the library exists |
| **README drifts past what is true** | Phase 8 | Exit criterion binds it to the guarantee tiers in `DESIGN.md` §6 |

---

## 6. Decisions recorded

| decision | call | reasoning |
|---|---|---|
| **Positioning** | General-purpose library that stands alone; Asterion is its first user, not its specification | Slack model — internal tool first, generalise what survives contact |
| **Target user** | Extraction steps in pipelines where a wrong-but-valid value silently corrupts everything downstream | LangChain already solves shape via `with_structured_output()`; the unserved gap is a confidence signal to route on |
| **Language** | Python 3.11+ | Prior art is Python; the ecosystem we wedge into (LangChain, LlamaIndex, Instructor, Pydantic) is Python-first; mature JSON Schema tooling |
| **Schema surface** | Pydantic model *or* raw JSON Schema | What Python users expect; Pydantic emits JSON Schema, so internals stay uniform |
| **Licence** | MIT | Matches the neighbouring projects |
| **Name** | Keep "Jevson" for now | Couples us to a vendor whose replaceability is an explicit goal — but Jev is the only backend that exists today. Revisit at v1. |
| **JS port** | Deferred to v1 | The population exists; splitting v0 across two languages with two people does not finish either |
| **Fake backend** | Shipped as a first-class testing tool | It is the instrument producing evidence for the central claim, and users need it to test their own candidate sets without spending money |
| **Logging** | Nothing by default | Source text and extracted values are the sensitive material |
| **Scope if the band is narrow** | Ship the narrow version | Pre-committed before the taxonomy was built, to defeat sunk cost |
| **Derived provenance** | Out of v0 | Requires an expression layer and turns a flat map into a graph — a feature in its own right |
| **Publish timing** | README corrected to honest positioning immediately, regardless of when code ships | The current headline is false under our own analysis |

Reversals from `DESIGN.md` Revision 1 are recorded in `DESIGN.md` §13 with their reasoning.

---

## 7. Open questions

Each is assigned to the phase that closes it. None is papered over.

| question | closed by | if the answer is bad |
|---|---|---|
| Does `none_of_these` actually catch missing answers? | Phase 0b | Stop. The candidate architecture is unsafe without it. |
| Is Jev calibrated on source-span disambiguation specifically? | Phase 0b, Phase 4 | Confidence becomes a reported number, not a gate; thresholds documented as unvalidated |
| Is pairwise entity resolution good enough on real prose? | Phase 0b, Phase 6 | Dedup becomes the extractor's declared contract |
| Does per-item `score` produce coherent global ordering? | Phase 6 | Semantic ordering ships disabled, finding recorded |
| Does the retry budget recover answers, or just cost a round trip? | Phase 3, Phase 4 | Default budget drops to zero; retry becomes opt-in |
| Do we ship criteria templates, a linter, or documentation? | Phase 7 | Currently: dry-run tool plus documentation. Linter deferred. |
| Is the name right? | v1 | Rename before adoption makes it expensive |
| Does a JS port happen? | v1 | Only once the Python surface has stopped moving |

---

## 8. Sequencing summary

```text
Phase 0   taxonomy + spike + scope verdict        no code, gates everything
Phase 1   core model, graph, fake backend         ~350 lines
Phase 2   compiler: schema -> graph               ~450 lines
Phase 3   executor + live Jev backend             ~400 lines   ← working library
Phase 4   candidates and source selection         ~500 lines   ← the differentiator
Phase 5   union discrimination                    ~250 lines
Phase 6   source-grounded arrays                  ~500 lines
Phase 7   generative fields and adjudication      ~450 lines
Phase 8   result surface, packaging, release      ~250 lines
```

**The smallest genuinely useful version is Phase 3.** The smallest version that justifies the library existing is **Phase 4**.
