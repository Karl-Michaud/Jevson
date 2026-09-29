# Jevson — implementation plan

> **Status:** Planning document, Revision 2, 2026-09-28. Pre-implementation.
>
> **Scope:** How Jevson gets built, in phases, with deliverables and testable exit criteria. The architecture it implements is [`DESIGN.md`](DESIGN.md) Revision 2.1; section references below (§3, §5, §8 …) point there.
>
> **Rule numbers** (R1–R14) refer to the twelve v0 rules plus the two implementation rules in `DESIGN.md` §7.

---

## 1. How this plan is organised

**One phase, one pull request.** Each phase is sized so a reviewer can hold the whole change in their head — a rough ceiling of **500 lines of new implementation code**, tests excluded. Where a phase would exceed that, it splits.

Each phase states:

- **Goal** — the one sentence that says why this PR exists
- **Depends on** — the phases that must land first, so sequencing errors are visible
- **Deliverables** — what lands
- **Exit criteria** — testable checkboxes; the PR does not merge until all pass
- **Abandon criterion** — the specific result that means stop rather than push on
- **Out of scope** — what is deliberately deferred, so review does not drift
- **Answers** — which `DESIGN.md` §12 open question this phase closes

**Phase 3 is a working library.** At that point Jevson resolves bounded schemas with calibrated confidence, provenance, and typed abstention. It is a legitimate stopping point if anything goes wrong upstream.

### 1.1 A note on effort

Phase 0 as specified is **roughly a day of work on its own** — 10 schemas and 150 fields classified across 11 columns, plus 100 disambiguation cases whose ground truth must be labelled by hand *before* any model sees them. The labelling is the expensive part and it cannot be skipped without making the probes unfalsifiable.

Recording this because the working estimate for the project has been "a couple of days," and phases 1–8 do not fit in what remains of that. The phases are individually small; there are nine of them. Nothing here argues for cutting scope — Phase 0 exists precisely so that scope is cut on evidence rather than on schedule pressure — but a plan that silently contradicts its own timeline is one that gets blamed later for the wrong reason.

**Phase 4 is the differentiator.** Everything before it is foundation; everything after it is breadth. A version that stops before Phase 4 does not justify the library's existence — `Kiln-AI/jev_jsonschema` already occupies that ground.

---

## 2. Repository layout

```text
jevson/
  __init__.py           public surface: compile_schema, Jevson, Result
  types.py              DecisionNode, DecisionKind, Span, Provenance,
                        Unresolved, Confidence, Overflow, OptionSource
  graph.py              DecisionGraph, dependency edges, topological levelling
  errors.py             CompileError, RefusalReason, SchemaViolation
  protocols.py          Backend, Extractor, LLM, Normalizer, CostSink
  facade.py             Jevson — wires compiler, extractor, executor, assembler

  compile/
    compiler.py         schema + config -> DecisionGraph
    mapping.py          schema construct -> decision kind (the taxonomy, in code)
    nodes.py            node id derivation from JSON pointers
    refusal.py          loud refusal with JSON pointers (R14)
    unions.py           anyOf/oneOf -> level-0 discrimination nodes

  extract/
    spans.py            Span construction, substring verification (DESIGN 5.5)
    llm.py              LLM-backed candidate extractor
    patterns.py         regex/rule extractor for dates, money, emails

  execute/
    executor.py         levels -> batched, keyed backend calls (R3, R13)
    budget.py           context-window estimation, level splitting (DESIGN 8.2)
    policy.py           retry budget, abstention handling (R2)
    questions.py        keyed question-map construction (R13)

  backends/
    jev.py              the only module importing the Jev SDK
    fake.py             deterministic fake, shipped as a testing tool

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
  adversarial/
    hostile_backend.py  adversarial Backend double  — NOT shipped in the package
    hostile_llm.py      adversarial LLM double      — NOT shipped in the package
  integration/          real Jev key, marked, opt-in
  fixtures/schemas/     the Phase 0 sample, checked in with provenance

docs/
  taxonomy.md           Phase 0 output, including measured spike results
  criteria-guide.md     how to write adjudication criteria that work
```

**Module discipline**, asserted by tests:

- `backends/jev.py` is the only file importing the Jev SDK.
- Nothing in `compile/`, `assemble/`, or `graph.py` imports from `execute/` or `backends/` — dependencies point inward toward `types.py` and `protocols.py`.
- The hostile doubles live in `tests/`, never in the installed package. The *fake* backend ships (users need it); the *hostile* one is a test fixture and shipping it would be shipping a footgun.

**All five protocols live in `protocols.py` from Phase 1.** A protocol is a few lines; defining them together removes the sequencing hazard where a later phase owns an interface an earlier phase needs.

---

## Phase 0 — Taxonomy, feasibility spike, and scope verdict

**Goal:** decide empirically whether Jevson is a broad structured-extraction library or a deliberately narrow disambiguation engine, and confirm the central mechanism works before any of it is built.

**Depends on:** nothing. Requires the live Jev key.

No library code. Two deliverables: one document and one throwaway spike.

### 0a — The taxonomy

Classify every schema construct and extraction operation against `DESIGN.md` §4's classes A–G, **against a named sample of real schemas**, not intuition.

**Sample sources**, each entry cited with its origin:

- `Kiln-AI/jev_jsonschema` test fixtures — the closest prior art's own coverage
- [schemastore.org](https://www.schemastore.org/) — real-world published schemas
- Documentation examples from LangChain, LlamaIndex, and Instructor
- Six **extraction** domains: invoice/receipt, resume/CV, support-ticket triage, contract clause, medical intake, product listing
- **Four non-extraction pipeline schemas:** agent state, tool-call routing, summarisation output, classification-with-rationale

> **On the last group.** The target user we settled on is pipeline authors, and pipelines are often routing, summarisation, and agent state rather than extraction. Sampling only extraction schemas would produce an extraction-shaped verdict, which would then justify an extraction-shaped library — circular. The non-extraction group exists specifically to let the sample contradict us.

Asterion's layer payloads are included as *one sample among several*, never as the specification.

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
| frequency in sample | counted, not guessed |
| semantic importance | how damaging a wrong-but-valid value is |
| **existing alternatives** | **does constrained decoding or plain code already solve this?** |
| v0 candidate? | the scope call |

The **existing alternatives** column does the real work. A construct that maps neatly onto a primitive but is already guaranteed by a grammar is not a differentiator, however elegant the mapping.

### 0b — The feasibility spike

Throwaway code in a scratch directory, **not** part of the library, using the live key. It exists to kill the project early if the central mechanism does not work.

**Thresholds are pre-registered below and are not to be renegotiated after seeing the numbers.** That discipline is the entire reason the spike happens before the build rather than during it.

| probe | what it measures | n | go | conditional | stop |
|---|---|---|---|---|---|
| **1. Disambiguation accuracy** | correct span chosen when the answer *is* present, among 3–5 plausible competitors | 100 | ≥ 0.85 | 0.70–0.85 | < 0.70 |
| **2. Abstention sensitivity** | `none_of_these` chosen when the correct answer is **removed** from the set | 100 | ≥ 0.80 | 0.60–0.80 | < 0.60 |
| **3. False abstention** | `none_of_these` chosen when the answer **is** present — the counter-metric | (same 100 as probe 1) | ≤ 0.10 | 0.10–0.20 | > 0.20 |
| **4. Entity resolution** | pairwise equivalence classes correct on real prose clusters | 50 clusters | ≥ 0.85 | 0.70–0.85 | < 0.70 |
| **5. Batching shape** | keyed vs indexed question maps on our own data | 300 items | reproduces §2.1 | — | indexed is fine → revisit R13 |

> **Probes 2 and 3 must be read together.** A model that abstains on everything scores perfectly on probe 2 and is useless. Probe 3 is what makes probe 2 meaningful, and neither is interpretable alone. This pairing was missing from the first draft of this plan and is the single most important correction in it.

**n = 100** is chosen so a measured rate has a 95% interval of roughly ±8–10 points — enough to separate the bands above. n = 20 would give ±20 points and could not distinguish *go* from *stop*.

**Where the cases come from, and why it matters.** Probe cases are drawn from the **documents behind the sampled schemas in 0a**, not hand-written. Ground truth is labelled **before** any Jev call, and the labelling is recorded in `docs/taxonomy.md` so it can be disputed. Hand-built cases authored by the people who want the project to succeed would measure our imagination rather than the model — and probe 2 in particular is trivially gameable by choosing competitors that are obviously wrong.

Probes 1 and 3 run over the **same** 100 cases and partition their outcomes: correct span, wrong span, or abstained. The bands above leave roughly 5% for wrong-span selections, which is the error the library exists to surface.

**Conditional** means: the candidate architecture ships with a mandatory second gate (an independent verification question per committed span) and the cost is re-evaluated, rather than proceeding as designed.

### Exit criteria

- [ ] At least **10 schemas** sampled from named public sources — 6 extraction, 4 non-extraction — each entry citing where it came from
- [ ] At least **150 fields** classified, with counts by class, reported separately for the extraction and non-extraction groups
- [ ] Every class C and D entry specifies: exact primitive, option source, `none_of_these` requirement, dependency pattern, provenance guarantee, batching behaviour
- [ ] Every entry records its **existing alternatives**
- [ ] All five probes run at the stated n, with measured rates and confidence intervals written into `docs/taxonomy.md` **whether or not they are favourable**
- [ ] Each probe is marked **go / conditional / stop** against the pre-registered bands above
- [ ] The prediction below is marked **CONFIRMED** or **WRONG**, with the numbers that decided it
- [ ] The v0 scope list is frozen and written into `DESIGN.md` §10
- [ ] No library code exists

### Abandon criterion

**Probe 2 below 0.60, or probe 3 above 0.20, stops the project as designed.** Without reliable abstention the candidate architecture is strictly more dangerous than asking an LLM directly, because it launders a wrong answer through a calibrated-looking number (`DESIGN.md` §5.3). The fallback is not "tune it."

**The fallback product is phases 1–3, 5 and 7** — a bounded-decision compiler with union discrimination and criteria-gated generative fields. Note that Phase 7 survives: adjudication does not depend on candidate selection at all, and criteria-gated generative fields are themselves something no prior-art project does. The fallback is smaller than the full design but it is not a consolation prize, and the README says exactly which capability did not ship and why.

### The prediction on record

> **Classes C and D are a narrow band.** Most of JSON Schema is class A (deterministic structure); most *fields* in real extraction schemas are class E (unbounded strings). C and D together cover enums-with-ambiguity, union discrimination, boolean predicates, ordinal ratings, and source-span disambiguation — real and unserved, but **not most of a typical schema**.

If confirmed, the honest product is **a decision-graph compiler for the disambiguation band**, positioned as such — a smaller library and a sharper one, and the outcome we have pre-committed to accepting.

**Recorded before the taxonomy was built, deliberately, so the taxonomy is a test rather than a rationalisation.**

### Answers

`DESIGN.md` §12: calibration on this task (first reading), entity-resolution quality (first reading).

---

## Phase 1 — Core model, protocols, graph, and the fake backend

**Goal:** the type system, every protocol, and the execution skeleton, so everything afterwards can be tested without spending money or waiting on a network.

**Depends on:** Phase 0.

### Deliverables

- `types.py` — `DecisionNode`, `DecisionKind`, `Span`, `Provenance`, `OptionSource`, `Confidence`, `Unresolved`, `Overflow`
- `protocols.py` — **all five protocols**: `Backend`, `Extractor`, `LLM`, `Normalizer`, `CostSink`
- `graph.py` — `DecisionGraph`, dependency edges, topological levelling (R3, R11)
- `backends/fake.py` — deterministic fake, **shipped as a first-class testing tool**, configurable to return specified answers, confidences, and abstentions
- `result.py` — `Result` exactly as pinned in `DESIGN.md` §8.1, including `satisfies_schema`
- `errors.py` — the error hierarchy
- `assemble/assembler.py` — resolved graph → JSON object, for the hand-built case

### Exit criteria

- [ ] A hand-built graph levels correctly, including a diamond dependency
- [ ] A dependency cycle is rejected at construction with the offending node ids
- [ ] The fake backend resolves a hand-built graph and the assembler produces a valid object
- [ ] `Span` verifies against a source by substring match on **character** offsets, half-open, and rejects offsets that do not match (`DESIGN.md` §5.5)
- [ ] Span verification is correct for multi-byte and combining-character content — a test with unicode confusables passes
- [ ] `Unresolved` is a value in the result, never raised; `satisfies_schema` is `False` whenever one is present
- [ ] Property: `levels(graph)` preserves every node exactly once and respects every edge
- [ ] All five protocols are defined here; no later phase introduces a new protocol without amending `DESIGN.md` §8
- [ ] Public API is exported from `__init__.py` and nothing else is

### Abandon criterion

None. If this phase is hard, the type model is wrong and should be reworked in place.

### Out of scope

Compilation from a schema. Any real backend. Candidates. Arrays.

### PR size

~400 lines. Mostly types and protocols.

---

## Phase 2 — The compiler: schema → decision graph

**Goal:** turn a JSON Schema into a decision graph for the bounded subset, and refuse everything else loudly, before any network call.

**Depends on:** Phase 1.

### Deliverables

- `compile/mapping.py` — the Phase 0 taxonomy encoded as routing rules
- `compile/nodes.py` — **node id derivation**: a node id is its JSON pointer plus a role suffix (`/customer/tier#choice`), so ids are stable, human-readable in errors, and independent of dict ordering
- `compile/compiler.py` — schema + config → `DecisionGraph`
- `compile/refusal.py` — `CompileError` carrying **every** offending JSON pointer (R14)
- **Nested object support** — arbitrary object nesting walked deterministically, decision nodes targeted by full JSON pointer
- Pydantic model acceptance, converting to JSON Schema; everything internal works in JSON Schema
- Standalone, network-free `compile_schema()` in the public API

**Mapping, adopted from `jev_jsonschema` and credited:** bool → `noul` at 0.5; number bounded 0–1 → raw probability; string/int enum ≤ 255 → `choice`; integer range of 2–10 levels → `score`.

### Exit criteria

- [ ] Every class A construct is handled by code with no decision node emitted
- [ ] Every class C construct in the Phase 0 v0 list compiles to the primitive the taxonomy specifies
- [ ] **Nesting:** a three-level nested object compiles with every decision node carrying its full JSON pointer, and assembles back to the correct shape
- [ ] Node ids are derived from JSON pointers and are stable across runs and across dict insertion order
- [ ] Refusal is **total and specific**: an unmappable schema produces a `CompileError` listing *every* offending pointer, not the first
- [ ] `compile_schema()` makes **zero network calls** — asserted with the network stubbed to raise
- [ ] Enum > 255 options, ordinal > 10 levels, and unbounded numerics each refuse with a distinct named reason
- [ ] A Pydantic model and its emitted JSON Schema compile to identical graphs
- [ ] Property: over generated schemas, `compile_schema()` returns a graph or raises `CompileError` — never a third outcome, never a partial graph

### Abandon criterion

None.

### Out of scope

Executing anything. Unions (Phase 5). Candidates (Phase 4). Arrays (Phase 6).

### PR size

~450 lines.

---

## Phase 3 — Executor, live backend, and the façade

**Goal:** resolve a graph against the live model in the minimum number of calls, with a real budget and abstention policy, behind the public façade.

**Depends on:** Phase 2.

### Deliverables

- `execute/questions.py` — keyed question-map construction (**R13**; object properties, never array indices)
- `execute/executor.py` — levels → one batched call per level (R3)
- `execute/budget.py` — **context-window estimation and level splitting** (`DESIGN.md` §8.2)
- `execute/policy.py` — retry budget, abstention handling (R2)
- `facade.py` — **`Jevson`**, wiring compiler → executor → assembler; the class every phase references and no earlier phase owned
- `backends/jev.py` — the live backend, the only module importing the Jev SDK
- `cost.py` — questions, input tokens, retries, wall clock split by component
- Integration suite, opt-in and marked, against the real key

### Exit criteria

- [ ] A graph with N independent nodes resolves in exactly **one** backend call — asserted by counting calls, not by timing
- [ ] Question keys are object properties; a test fails if any generated key matches an array-index pattern
- [ ] Supplying more than one source refuses at the call boundary with a named reason (`DESIGN.md` §5.5) — this is a runtime concern, not a schema one, so it does not belong in the compiler
- [ ] **Budget:** a level exceeding the context window splits into multiple calls, and the split is recorded in `cost`
- [ ] **Budget:** a single question whose state exceeds the window refuses with the offending pointer rather than truncating
- [ ] **Retry against a schema-derived option set defaults to zero** — Jev is deterministic, so re-asking an unchanged question is guaranteed waste (`DESIGN.md` §5.4). A test asserts no retry is issued for enum or rubric fields.
- [ ] `none_of_these` resolves to `Unresolved`, never an exception (R2)
- [ ] An unresolved **optional** field yields `satisfies_schema is False` with the hole named; an unresolved **required** field is additionally reported as a schema violation regardless of caller strictness
- [ ] **No default confidence threshold gates a commit** (`DESIGN.md` §6.2) — a test asserts a low-confidence answer is still committed and reported, not dropped
- [ ] `backends/jev.py` is the only module importing the vendor SDK — asserted by an import test
- [ ] Swapping `FakeBackend` for `JevBackend` changes no code outside construction
- [ ] Same input resolves to the same output across runs against the live API
- [ ] Cost is populated on every result, success and failure paths alike

### Abandon criterion

None, but note what this phase is **not**: it is not feature-parity with `jev_jsonschema`. It covers whatever the Phase 0 v0 list contains, which may be narrower. The plan does not claim otherwise.

### Out of scope

Candidates. Unions. Arrays. Generative fields.

### Answers

`DESIGN.md` §12: retry budget's real value (for schema-derived sets — answered negatively by construction); level splitting's effect on answers (first reading).

### PR size

~450 lines.

---

## Phase 4 — Candidates and source selection

**Goal:** the differentiator. Fields whose values come from the source, chosen by Jev among extracted spans, with provenance and mandatory abstention.

**Depends on:** Phase 3. Uses the `Extractor` and `LLM` protocols defined in Phase 1.

### Deliverables

- `extract/spans.py` — span construction and substring verification **before** the Jev call
- `extract/llm.py` — LLM-backed candidate extraction under a provider tool schema
- `extract/patterns.py` — rule-based extraction for dates, money, emails, phone numbers
- Compiler support for `option_source = candidate_spans`
- **Mandatory `none_of_these` injection** on every candidate-backed choice (R1)
- Expanded-extraction retry on abstention, budget 1 (R2, `DESIGN.md` §5.4)
- Provenance emission: `SOURCE_SPAN(source_id, start, end)`

### Exit criteria

- [ ] Every candidate-backed choice includes `none_of_these` — asserted structurally in the compiler, not by convention (R1)
- [ ] **The adversarial coverage test:** when the correct answer is deliberately *absent* from the candidate set, the library abstains rather than committing a confident wrong value, at no worse than the rate Phase 0 probe 2 measured
- [ ] **The false-abstention test:** when the correct answer *is* present, abstention stays at or below the rate probe 3 measured
- [ ] Every committed value verifies against the source by substring match; a span failing verification is rejected before the Jev call
- [ ] A candidate set exceeding 255 options refuses at compile time with a named reason
- [ ] The single-candidate case does **not** route through Jev by default (R4) — a test asserts zero backend calls for an unambiguous field
- [ ] Extraction retry genuinely widens the option set; a test asserts the second call's options differ from the first
- [ ] Extractor is swappable: the same schema and source resolve identically through the LLM extractor and a hand-supplied one
- [ ] Provenance offsets survive assembly unchanged

### Abandon criterion

**If the coverage test cannot be made to pass at the Phase 0 rate, candidate selection does not ship.** The fallback is phases 1–3, 5 and 7, with source selection removed and the README positioned accordingly. This is the same decision as Phase 0's abandon criterion, re-checked with real machinery rather than a spike — and it is the reason Phase 5 and Phase 7 are deliberately independent of Phase 4.

### Out of scope

Arrays of candidates (Phase 6). Generative fields (Phase 7).

### Answers

`DESIGN.md` §12: calibration on this task, retry budget's real value (for candidate-derived sets).

### PR size

~500 lines. Split extraction backends into their own PR if it runs over.

---

## Phase 5 — Union discrimination

**Goal:** `anyOf` / `oneOf` resolved as a level-0 decision that determines which branch is *constructed*, not which is discarded (`DESIGN.md` §3.2).

**Depends on:** Phase 3. Independent of Phase 4 — can land in either order.

### Deliverables

- `compile/unions.py` — union → discrimination node at level 0
- Deferred compilation: branch nodes compile only after the discriminator resolves
- Refusal for unions whose branches are not distinguishable as a bounded choice
- `$ref` resolution where the reference is static and acyclic

### Exit criteria

- [ ] A union resolves the discriminator in level 0, and **only the selected branch's nodes are ever compiled or executed** — asserted by counting compiled nodes
- [ ] A nested union (a branch containing a union) levels correctly
- [ ] An undiscriminable union refuses at compile time with the offending pointer
- [ ] A recursive `$ref` refuses rather than looping
- [ ] The unselected branch's fields never appear in the result, even as nulls
- [ ] Discrimination confidence appears in the confidence map under the union's pointer
- [ ] Discrimination abstention produces `Unresolved` for the whole subtree rather than a guessed branch

### Abandon criterion

None. If unions prove intractable they are refused, which is the status quo for the prior art.

### Out of scope

Recursive references. Dynamic references. `allOf` beyond flat merging.

### PR size

~250 lines. The smallest phase, and a clean differentiator — `jev_jsonschema` refuses unions outright.

---

## Phase 6 — Source-grounded arrays

**Goal:** arrays whose membership is a set of bounded decisions over a candidate set, with entity resolution, ordering, and honest overflow.

**Depends on:** Phase 4.

### Deliverables

- Membership: one `noul` per candidate, batched (R5)
- `assemble/entities.py` — **pairwise `noul` entity resolution** scoped to a declared entity type, building equivalence classes (R6), **capped at n = 30** (`DESIGN.md` §8.2)
- `Normalizer` implementations — canonical representative (earliest span / longest span / user-supplied), declared not baked in
- `assemble/ordering.py` — source order by default; semantic order via per-item `score`, behind a flag (R7)
- `assemble/cardinality.py` — `maxItems` with **overflow retained in the result** (R8)
- Refusal for generative and unbounded arrays

### Exit criteria

- [ ] `"Attendees were Dana, John, Sarah, and Michael"` produces a 4-element array in source order
- [ ] **The dedup case:** `"Dana"` / `"Dana Whitfield"` / `"Ms. Whitfield"` in one document produces **one** element, not three (R6)
- [ ] Entity resolution is scoped to a declared type; two different entity types with identical surface strings are **not** merged
- [ ] Pairwise resolution for n candidates issues **one** backend call with n(n−1)/2 keyed questions
- [ ] **A candidate set above n = 30 refuses** with a named reason rather than approximating (`DESIGN.md` §8.2)
- [ ] `maxItems: 5` with six accepted candidates returns five and **records the sixth in `Result.overflow` with its probability** — silent truncation fails the test (R8)
- [ ] An array with no source grounding refuses at compile time
- [ ] Semantic ordering is behind an explicit flag and documented as unproven
- [ ] Source ordering is deterministic across runs

### Abandon criterion

**If entity resolution falls below the Phase 0 probe 4 rate, deduplication becomes the extractor's declared contract** — the library stops claiming it, documents that candidates must arrive normalised, and the exit criterion above is removed rather than weakened.

### Out of scope

Nested arrays of objects. Cross-item constraints.

### Answers

`DESIGN.md` §12: entity-resolution quality; global ranking coherence; the pairwise cap's real ceiling.

### PR size

~500 lines. Split entity resolution into its own PR if it grows.

---

## Phase 7 — Generative fields and adjudication

**Goal:** fields no candidate set can fill — a summary, a synthesised description — drafted by the LLM under a provider tool schema and admitted only after Jev adjudicates them.

**Depends on:** Phase 3. Uses the `LLM` protocol from Phase 1.

### Deliverables

- Generative fields requested under the **provider's tool schema**, so key presence and spelling are forced by the sampler rather than by instruction
- `adjudicate/criteria.py` — declared criteria → one `noul` each, batched
- `adjudicate/rubrics.py` — optional rubric → `score` with a declared minimum level
- Rejection naming the **failing criterion**, recorded in `Result.rejections`
- Bounded redraft budget, then `Unresolved` (R2)
- `docs/criteria-guide.md`
- A **criteria dry-run tool**: given criteria and example drafts, show Jev's verdicts so authors calibrate criteria empirically before shipping them

### Exit criteria

- [ ] A generative field is requested under a tool schema; the key cannot be missing or misspelled
- [ ] All criteria for a field are adjudicated in **one** batched call
- [ ] Rejection names the specific failing criterion
- [ ] Redraft budget is bounded; exhaustion yields `Unresolved`, never an exception or a silently accepted string
- [ ] Redrafting genuinely changes the input — a test asserts the second draft differs, since an identical draft would get an identical verdict (`DESIGN.md` §5.4)
- [ ] **A generative field's content cannot corrupt the object's shape** — verified against the hostile LLM in §4
- [ ] The dry-run tool runs against the fake backend with no key
- [ ] A field with no declared criteria is accepted with an explicit `no_criteria_declared` marker, so ungated fields are visible rather than invisible

### Abandon criterion

None. If adjudication proves weak, generative fields ship ungated with the marker above and the limitation documented.

### Out of scope

Automatic criteria derivation. A criteria linter. Both are research projects.

### Answers

`DESIGN.md` §12: criteria authoring.

### PR size

~450 lines.

---

## Phase 8 — Packaging and release

**Goal:** the library is usable by someone who did not build it.

**Depends on:** whichever phases survived their abandon criteria.

### Deliverables

- `CostSink` default implementation and documentation
- README rewritten to `DESIGN.md` §9.1 — **the current headline is false under our own analysis and must not survive to release**
- Quickstart, the worked examples from `DESIGN.md` §3.4 and §5.1, and a `jev_jsonschema` comparison that is fair to it
- `pyproject.toml`, MIT licence, `py.typed`, Python 3.11+
- **Versioning policy:** `0.x`, breaking changes permitted between minors and documented in a changelog. No stability promise until the Phase 0 scope verdict has survived contact with real users.
- PyPI release

### Exit criteria

- [ ] README makes no claim outside the tiers in `DESIGN.md` §6, and does not claim guaranteed JSON validity as a differentiator
- [ ] README states the abandon-criteria outcomes honestly — anything that did not ship is named, not quietly omitted
- [ ] Every public symbol is typed and documented
- [ ] Quickstart runs end to end against the fake backend with **no API key**
- [ ] The comparison table states plainly what `jev_jsonschema` does better
- [ ] Installed package exposes only the intended public surface, and contains no hostile test doubles
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
- **Every backend call is counted**, on success and failure paths alike.
- **Determinism.** Same schema, source, and backend produce the same result. Jev is deterministic; anything non-deterministic in our own code is a bug.
- **Retries must change the input.** A retry that re-sends an identical question to a deterministic model is a bug, not a policy.
- **The fake backend keeps working.** Every phase adding a capability adds fake-backend support in the same PR.
- **Protocols earn their place.** No interface without a second real implementation or a named prospect of one.
- **Measured numbers are written down**, favourable or not, in `docs/taxonomy.md`.

---

## 4. Validation strategy

The central claim is that the result survives arbitrary model behaviour. Its evidence standard is higher than anything else in the library.

### 4.1 The central property

Asserted over generated schemas × every hostile behaviour, stated exactly as `DESIGN.md` §6.1:

> A call returns exactly one of:
>
> 1. a `Result` whose `.value` validates against the original schema, with `.satisfies_schema is True`;
> 2. a `Result` carrying `Unresolved` fields, with `.satisfies_schema is False` and every hole named; or
> 3. a typed refusal (`CompileError` or `SchemaViolation`).
>
> Never a fourth outcome. Never a partial object claiming to satisfy the schema. Never an untyped exception from a model's output.

The earlier binary phrasing — "a valid object or a refusal" — was wrong, because outcome 2 is legitimate and satisfies neither branch.

### 4.2 The adversarial suite

`tests/adversarial/` doubles return, deliberately:

| category | behaviours |
|---|---|
| **malformed responses** | wrong field names, missing fields, wrong types, extra keys, empty response, `null` |
| **invalid values** | out-of-enum selections, probabilities outside [0,1], `NaN` confidences, distributions that do not sum |
| **protocol violations** | prose instead of a tool call, a call for a tool not offered, duplicate answers for one key |
| **hostile content** | control characters, enormous strings, unicode confusables, text that looks like JSON |
| **hostile spans** | offsets absent from the source, overlapping spans, spans whose text does not match, duplicates |

### 4.3 Property-based tests

`hypothesis` strategies over the supported subset. Invariants:

- `compile_schema()` returns a graph or raises `CompileError` — never a partial graph
- Levelling preserves every node exactly once and respects every edge
- Assembly of a fully resolved graph always validates against the original schema
- Provenance spans always verify by substring against the source
- Cost is monotonic: retries only increase it

### 4.4 Integration tests

Opt-in and marked. They **measure** rather than assert where the quantity is a property of the model — accuracy, abstention rate, calibration separation — and compare against the Phase 0 pre-registered bands.

They do **not** run on every CI push: the live key has a 1200 req/min limit and a real cost, and a flaky model measurement should not block a docs commit. They run on demand and on release.

---

## 5. Risks

| risk | where it bites | mitigation |
|---|---|---|
| **`none_of_these` doesn't work** | Phase 0b, fatal to Phase 4 | Pre-registered bands; probes 2 and 3 read together; abandon criterion names the fallback product |
| **We abstain on everything and call it safety** | Phase 0b | Probe 3 is the counter-metric; probe 2 alone is uninterpretable |
| **The taxonomy comes back narrow and we pad it** | Phase 0 | Prediction recorded in advance; pre-committed to shipping narrow |
| **The taxonomy samples only extraction and concludes extraction** | Phase 0 | Four non-extraction pipeline schemas in the sample, counted separately |
| **Entity resolution is poor on real prose** | Phase 6 | Probed in Phase 0b; abandon criterion makes dedup the extractor's contract |
| **Candidate extraction becomes the weak link** | Phase 4 onward | The unreliable component moved upstream, it did not disappear. `none_of_these` is the only defence and it is mandatory. |
| **Context window exceeded silently** | Phase 3 onward | Budget estimation, level splitting, loud refusal for single oversized questions |
| **O(n²) pairwise blows the window** | Phase 6 | Capped at n = 30; refuse rather than approximate |
| **Retries burn money against a deterministic model** | Phase 3, 4, 7 | Retry defaults to zero unless the input genuinely widens; cross-cutting rule |
| **Semantic ordering is incoherent** | Phase 6 | Behind a flag, documented as unproven |
| **Jev single-vendor, early access** | everywhere | `Backend` protocol; `AnyJev`/`jevfire` identified; fake backend always working |
| **Scope creep via derived values** | Phase 4+ | Out of v0 (R9); flat provenance map, not a graph |
| **We rebuild `jev_jsonschema` and stop** | Phase 3 | A legitimate stopping point but not the product; Phase 4 is why the library exists |
| **README drifts past what is true** | Phase 8 | Exit criteria bind it to `DESIGN.md` §6 and require naming what did not ship |

---

## 6. Decisions recorded

| decision | call | reasoning |
|---|---|---|
| **Positioning** | General-purpose library; Asterion is its first user, not its specification | Slack model — internal tool first, generalise what survives contact |
| **Target user** | Extraction steps in pipelines where a wrong-but-valid value silently corrupts everything downstream | LangChain already solves shape; the unserved gap is a confidence signal to route on |
| **Language** | Python 3.11+ | Prior art is Python; the ecosystem we wedge into is Python-first; mature JSON Schema tooling |
| **Schema surface** | Pydantic model *or* raw JSON Schema | What Python users expect; Pydantic emits JSON Schema, so internals stay uniform |
| **All protocols in Phase 1** | Yes | A protocol is a few lines; defining them late creates sequencing hazards |
| **Confidence gating** | Reported, never gated by default | A default threshold would assert calibration we have not measured |
| **Retry defaults** | Zero for schema-derived sets, one for candidate-derived | Jev is deterministic; retry without changed input is guaranteed waste |
| **Pairwise cap** | n = 30 | Context budget, not measured degradation — recorded as an open question |
| **Hostile doubles** | `tests/`, never shipped | The fake backend is a tool; the hostile one is a footgun |
| **Integration tests in CI** | On demand and on release, not every push | Live key, rate limits, and flaky model measurements should not block a docs commit |
| **Versioning** | `0.x`, breaking changes permitted between minors | No stability promise before the scope verdict meets real users |
| **Licence** | MIT | Matches the neighbouring projects |
| **Name** | Keep "Jevson" for now | Couples us to a vendor whose replaceability is an explicit goal; revisit at v1 |
| **JS port** | Deferred to v1 | Splitting v0 across two languages finishes neither |
| **Fake backend** | Shipped as a first-class testing tool | It produces the evidence for the central claim, and users need it to test candidate sets without spending money |
| **Scope if the band is narrow** | Ship the narrow version | Pre-committed before the taxonomy, to defeat sunk cost |
| **Derived provenance** | Out of v0 | Requires an expression layer and turns a flat map into a graph |

Reversals from `DESIGN.md` Revision 1 are recorded in `DESIGN.md` §13.

---

## 7. Open questions

Each is assigned to the phase that closes it.

| question | closed by | if the answer is bad |
|---|---|---|
| Does `none_of_these` catch missing answers? | Phase 0b | Stop. Ship the narrow library without source selection. |
| Do we abstain when we shouldn't? | Phase 0b probe 3 | Conditional band: candidate architecture ships with a second gate |
| Is Jev calibrated on source-span disambiguation? | Phase 0b, Phase 4 | Confidence stays reported, never gated; documented as unvalidated |
| Is pairwise entity resolution good on real prose? | Phase 0b, Phase 6 | Dedup becomes the extractor's declared contract |
| Does per-item `score` give coherent global ordering? | Phase 6 | Semantic ordering ships disabled, finding recorded |
| Does splitting a level change Jev's answers? | Phase 3 | Budget refuses instead of splitting; schemas must shrink |
| What is the real pairwise ceiling? | Phase 6 | Cap lowered from 30 with the measurement cited |
| Templates, linter, or docs for criteria? | Phase 7 | Currently dry-run tool plus documentation |
| Is the name right? | v1 | Rename before adoption makes it expensive |

---

## 8. Sequencing summary

```text
Phase 0   taxonomy + spike + scope verdict         no code, gates everything
Phase 1   core model, protocols, graph, fake       ~400 lines
Phase 2   compiler: schema -> graph (incl. nesting) ~450 lines
Phase 3   executor + budget + live backend + façade ~450 lines   ← working library
Phase 4   candidates and source selection          ~500 lines   ← the differentiator
Phase 5   union discrimination                     ~250 lines   (independent of 4)
Phase 6   source-grounded arrays                   ~500 lines   (needs 4)
Phase 7   generative fields and adjudication       ~450 lines   (needs 3)
Phase 8   packaging and release                    ~250 lines
```

**The smallest genuinely useful version is Phase 3.** The smallest version that justifies the library existing is **Phase 4**.

If Phase 0 or Phase 4's abandon criterion fires, the product is **phases 1–3, 5 and 7** — a bounded-decision compiler with union discrimination and criteria-gated generative fields. Phases 5 and 7 are deliberately independent of Phase 4 so that this fallback exists at all; both do things the prior art refuses to do.
