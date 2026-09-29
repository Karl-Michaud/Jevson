# Jevson — implementation plan

> **Status:** Planning document, Revision 9.1, 2026-09-29. Pre-implementation.
>
> **Scope:** How Jevson gets built, in phases, with deliverables and testable exit criteria. The architecture it implements is [`DESIGN.md`](DESIGN.md) Revision 9.1. **References are written `DESIGN §n` or `PLAN §n`**; a bare `§` never appears. Evidence tags such as **[P3]** resolve in [`docs/EVIDENCE.md`](EVIDENCE.md).
>
> **Rule numbers** (R1–R16) refer to `DESIGN §7`.

---

## 1. How this plan is organised

**One phase, one pull request.** Each phase is sized so a reviewer can hold the whole change in their head — a rough ceiling of **500 lines of new implementation code**, tests excluded. Where a phase would exceed that, it splits.

Each phase states:

- **Goal** — the one sentence that says why this PR exists
- **Depends on** — the phase that must land first
- **Deliverables** — what lands
- **Exit criteria** — testable checkboxes; the PR does not merge until all pass
- **Abandon criterion** — the specific result that means stop rather than push on
- **Out of scope** — what is deliberately deferred, so review does not drift
- **Answers** — which open question (`DESIGN §12`, `PLAN §7`) this phase closes, and by which exit criterion

**Phases run strictly in order.** Each phase depends on the one before it, and the next starts only once the previous one has merged or fired its abandon criterion. A phase that abandons is skipped, and later phases proceed unless they state otherwise. The only exception is stated in the phase itself (Phase 11).

**Order.** Foundation (1–3), then generative fields and adjudication (4), then candidate selection (5), then unions (6) and arrays (7), then release (8). **The fallback product**, if candidate selection stops (Phase 0 or Phase 5), is phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7; it is stated this way everywhere. Post-v0 phases (9–11) are planned, not optional extras. **The order is the project owner's decision (2026-09-29).** Round-1 review argued for running Phase 5 before Phase 4 whenever Phase 0 says *go*, because Phase 5 is the existential test of source-grounded extraction; the owner considered and kept this order, and PLAN §5 records the risk.

**Phase 3 is a working library** for bounded schemas. **Phase 5 is what makes Jevson a source-grounded extraction library** rather than a bounded-schema compiler, which `jev_jsonschema` already provides **[X3]**. Phase 4 alone already combines things we found in no single existing project **[X3]**.

### 1.1 A note on effort

Recorded so the plan does not silently contradict its own timeline:

- **Phase 0 is several days, dominated by labelling.** 10+ schemas and 150+ fields classified across 12 columns; ≥ 450 pre-labelled probe cases for probes 1–3 drawn from real documents; 50 entity clusters; a hostile-source set; single-candidate cases. Labelling cannot be skipped without making the probes unfalsifiable.
- **Phase 5 needs a second, disjoint labelled corpus**: ≥ 150 present-answer and ≥ 150 absent-answer cases for coverage; ≥ 100 constructed extraction-miss cases and ≥ 300 absent cases for the retry bar; ≥ 1,000 decisions (up to 3,000 if the power check requires) for calibration; ≥ 300 benign and ≥ 150 attacked documents for the source screen. This is the largest labelling effort in the project.
- **Phase 10 is a second implementation of the library**, not a port script.

Phases 1–8 do not fit in "a couple of days". Phase 0 exists so that scope is cut on evidence rather than schedule pressure.

---

## 2. Repository layout

```text
jevson/
  __init__.py           public surface: compile_schema, Jevson, Result, JevBackend, FakeBackend,
                        CachingBackend, ReplayLLM
  types.py              DecisionNode, StepNode, DecisionKind, Span, Provenance, OptionSource,
                        Decision, Unresolved, UnresolvedReason, Absent, Violation, Overflow,
                        Rejection, Cost
  graph.py              DecisionGraph, dependency edges, acyclicity, topological levelling
  errors.py             CompileError, RefusalReason, PreflightError, UsageError, SchemaViolation,
                        BackendError, LLMError, ExtractorError, MissingCredentials
  protocols.py          Backend, Extractor, LLM (async); Normalizer, CostSink (sync) — DESIGN §8
  facade.py             Jevson: resolve / aresolve; wires compiler, executor, assembler
  probabilities.py      integer hundredths, sum tolerance, tie margin (DESIGN §2.1, DESIGN §6.2)
  config.py             JevsonConfig: tie margin, conflict floor, entity rule variant, caps, budgets
  unicode/
    graphemes.py        UAX #29 boundaries from a vendored, generated table (DESIGN §5.9)
    tables/             generated table + the Unicode version it came from

  compile/
    normalise.py        DESIGN §3.5 normalisation table
    declarations.py     the x-jevson keyword: parse, validate, refuse unknown keys
    compiler.py         normalised schema + declarations -> DecisionGraph
    mapping.py          schema construct -> class and primitive (DESIGN §4.2)
    questions.py        versioned question templates (DESIGN §5.2)
    nodes.py            node ids from target instance pointers + role suffix
    refusal.py          loud refusal with every offending pointer (R14)
    unions.py           anyOf/oneOf with >= 2 non-null branches -> discrimination node
    generative.py       x-jevson.generate -> generate step + criterion nodes

  extract/
    spans.py            Span construction; substring + grapheme-boundary verification
    occurrences.py      every occurrence of a repeated text, with context windows
    llm.py              LLM-backed candidate extractor (Jevson locates its strings)
    patterns.py         money, date, email, phone, URL candidates

  execute/
    executor.py         step nodes + decision levels -> backend calls (R3, R13); emits to CostSink
    budget.py           preflight on declared maxima, two limits, level splitting (DESIGN §8.2)
    policy.py           decision retry, redraft loop, transport retry
    state.py            state construction: collections keyed by opaque id, never by position
    ratelimit.py        per-key token bucket on threading.Lock, shared across backends and loops
    loop.py             the library-owned event loop thread behind the synchronous resolve()

  backends/
    jev.py              raw httpx; the only module that knows the vendor wire format
    fake.py             deterministic fake, shipped as a testing tool
    caching.py          CachingBackend: RFC 8785 keys, caller-supplied directory

  llm/
    replay.py           ReplayLLM: exact replay of LLM responses

  assemble/
    assembler.py        resolved graph -> JSON object; absent / unresolved handling
    entities.py         pre-merge, pairwise resolution over members, internal rule + Phase 0 variant (R6)
    ordering.py         source order (R7); semantic order refused in v0
    cardinality.py      maxItems, overflow capture (R8)
    parse.py            class F on a selected span: money, number, date

  adjudicate/
    criteria.py         declared criteria -> noul batch
    rubrics.py          rubric -> score, value = most probable level
    dryrun.py           criteria dry-run tool

  screen.py             opt-in source screen (DESIGN §5.8)
  result.py             Result (DESIGN §8.1)

tests/
  unit/
  property/             hypothesis strategies over generated schemas
  conformance/          GraphemeBreakTest.txt at the pinned Unicode version
  adversarial/
    hostile_backend.py  adversarial Backend double             — NOT shipped
    hostile_llm.py      adversarial LLM double                 — NOT shipped
    hostile_extractor.py raising, never-returning (cooperative infinite await), and lying extractors — NOT shipped
    hostile_sources/    injected and self-advocating sources   — NOT shipped
    hostile_transport.py timeouts, 429, 5xx, malformed HTTP    — NOT shipped
  integration/          real key, marked, opt-in
  fixtures/schemas/     the Phase 0 sample, checked in with provenance

tests/probes/           the probes and checks behind docs/EVIDENCE.md; raw material for the test suite (not part of the package)

docs/
  DESIGN.md             the design SSOT
  PLAN.md               this plan
  EVIDENCE.md           evidence register: every tagged claim, its method, its result
  taxonomy.md           Phase 0 output, including measured probe results
  criteria-guide.md     how to write adjudication criteria that work

.env.example            TYPESAFE_API_KEY template; the real .env is gitignored
```

**Module discipline**, asserted by tests:

- `backends/jev.py` is the only file that knows the vendor URL, headers, or wire format; `typesafe-sdk` is not a dependency (`DESIGN §8`).
- Nothing in `compile/`, `assemble/`, or `graph.py` imports from `execute/` or `backends/`.
- The hostile doubles live in `tests/`, never in the installed package. The fake backend ships.

**All five protocols live in `protocols.py` from Phase 1**, with the signatures pinned in `DESIGN §8`.

---

## Phase 0 — Taxonomy, feasibility probes, and scope verdict

**Goal:** decide empirically whether Jevson is a broad structured-extraction library or a deliberately narrow disambiguation engine, and confirm the central mechanism on real documents before any of it is built.

**Depends on:** nothing. Requires the live key (available).

No library code. Two deliverables: one document and a set of throwaway probes. **The red-team pilots in `docs/EVIDENCE.md` [P1–P23] are not substitutes:** they used synthetic, author-written cases, which the rules below exist to exclude.

### 0a — The taxonomy

Classify every schema construct and extraction operation against `DESIGN §4`'s classes A–G, **against a named sample of real schemas**, not intuition.

**Sample sources**, each entry cited with its origin:

- `Kiln-AI/jev_jsonschema` test fixtures
- [schemastore.org](https://www.schemastore.org/) — real-world published schemas
- Documentation examples from LangChain, LlamaIndex, and Instructor
- Six **extraction** domains: invoice/receipt, resume/CV, support-ticket triage, contract clause, medical intake, product listing — at least one with non-English source documents
- **Four non-extraction pipeline schemas:** agent state, tool-call routing, summarisation output, classification-with-rationale

> The non-extraction group exists so the sample can contradict an extraction-shaped conclusion. Asterion's layer payloads, if included, are one sample among several, never the specification.

**Columns:**

| column | why |
|---|---|
| construct / operation | the thing being classified |
| class (A–G) | the routing decision |
| Jev primitive | `choice` / `score` / `noul` / none |
| option source | schema enum, rubric, candidate spans, predicate |
| `none_of_these` required? | R1 |
| dependency pattern | determines levelling |
| provenance guarantee | span, declared option, or none |
| frequency in sample | counted, not guessed |
| semantic importance | how damaging a wrong-but-valid value is |
| **existing alternatives** | does constrained decoding or plain code already solve this? |
| **existing Jev implementations** | do the vendor cookbooks, `typesafe-playground`, `jev-extract`, or `jev-reviewer` already handle it? **[X3]** |
| v0 candidate? | the scope call |

### 0b — The probes

Throwaway code in `scripts/phase0/`, using the live key and the pinned model `jev-1.13.0`. **Every threshold, decision rule, and question template below is pre-registered** and not renegotiated after seeing the numbers.

**Question templates.** Before any probe runs, the question templates of `DESIGN §5.2` — including the complete-value wording — are written into `docs/taxonomy.md` with a template version. Phase 2 encodes those exact templates in `compile/questions.py`, so Phase 0's verdicts describe the library that ships.

**Corpus rules** (probes 1–4, 6, 8):

- Cases come from the **real documents behind the 0a schemas**, not written by the team. The one exception is probe 6's injected notes, which the team writes into real documents.
- **At least 30% of probe 1–3 cases come from long, multi-entity documents** (several parties, invoices, or addresses) or contain **superseded values** — the only regime where the pilot failed **[P5]**. At least 20 cases contain the correct text at more than one offset **[P15]**.
- Ground truth is labelled **before any Jev call**, recorded in `docs/taxonomy.md`, and disputable.
- Absent-answer cases (probe 2) remove the correct span from a set whose competitors were produced by the real extractor, not chosen by hand.

| probe | what it measures | n | go | conditional | stop |
|---|---|---|---|---|---|
| **1. Disambiguation accuracy** | correct span chosen when the answer is present, among 3+ plausible competitors; ties (top-two margin ≤ 0.10) count as not correct and their rate is reported | 150 | ≥ 0.85 | 0.70–0.85 | < 0.70 |
| **2. Abstention sensitivity** | `none_of_these` chosen when the correct answer is removed; a tie counts as not abstaining, and the tie rate is reported | 150 | ≥ 0.80 | 0.60–0.80 | < 0.60 |
| **3. False abstention** | `none_of_these` chosen when the answer is present — the counter-metric; a tie is not a false abstention | same 150 as probe 1 | ≤ 0.10 | 0.10–0.20 | > 0.20 |
| **4. Entity resolution** | component outcomes on real prose clusters (below) | 50 clusters | ≥ 0.85 correct and ≤ 0.05 silently wrong | 0.70–0.85 correct | < 0.70 correct or > 0.05 silently wrong |
| **5. State referencing** | re-run `tests/probes/probe_04_batching.py` on the pinned model | 320 items | reproduces **[P4]** | — | indexed references are fine → revisit R13 |
| **6. Hostile source** | on 50 real documents with an injected note advocating a wrong span: steered selections and abstention collapse; and the source screen's true- and false-positive rates on those 50 and on 50 unmodified documents that include ordinary processing notes (routing, filing, portal instructions), which triggered 28/60 false positives in the pilot **[P21]** | 50 + 50 | reading only | — | — |
| **7. Calibration reading** | reliability of p(selected) over probes 1–3, tie-safe equal-mass bins, CI reported | from probes 1–3 | reading only | — | — |
| **8. Single candidates and partials** | lone correct, lone wrong-role, and lone partial candidates as `choice([c0, none_of_these])` under the complete-value template; and, per field type, sources that state only a partial value, where abstention is the intended answer **[P18]** | 50 each | reading only; informs R4 | — | — |

**Decision rule, pre-registered.** Each probe's verdict is the band containing its **point estimate**, with the Wilson 95% interval reported beside it. With n = 150 the half-width near p = 0.85 is about ±6 points (−6.2/+5.1) **[L12]**; a true rate exactly at a band edge is a coin flip under any rule, which is why the bands are wide. The operating characteristic — the probability of each verdict at each band edge, including the joint probability for probes 1 and 3, which share cases and are correlated (≈ −0.8) **[L12]** — is recorded in `docs/taxonomy.md` before any probe runs.

**Probes 2 and 3 must be read together.** A model that abstains on everything scores perfectly on probe 2 and is useless.

**Probe 4 in detail.** Pairwise nouls in one keyed call per cluster, all probabilities stored, run twice. The clusters include role-noun mentions ("the Landlord", "the engineer"), which produced the pilot's only splits **[P10, P17]**. Recorded: pair accuracy, the non-transitive-triple rate, clique completeness, and the flip rate across the two runs. `conflict_floor` is chosen by a rule fixed now: *the largest value in {0.05, 0.10, …, 0.45} such that same-entity pairs at or below it are ≤ 2% of all same-entity pairs; if no value qualifies, the floor is 0.05 and probe 4 is recorded as stop;* whether the grid top binds is recorded. Component outcomes (correct, `Unresolved`, silently wrong — merges and splits counted separately) are then scored under both variants of `DESIGN §5.7`, and **the variant is chosen by a rule fixed now: the one with the lower silently-wrong point estimate; if equal, the one with more correct components.** The verdict uses the chosen variant.

**Conditional** on probes 1–3 means Phase 5 ships the **second gate** described in Phase 5.

### Exit criteria

- [ ] At least **10 schemas** sampled — 6 extraction, 4 non-extraction — each citing its source
- [ ] At least **150 fields** classified, with counts by class, reported separately for extraction and non-extraction
- [ ] Every class C and D entry specifies primitive, option source, `none_of_these` requirement, dependency pattern, provenance guarantee, and batching behaviour
- [ ] Every entry records **existing alternatives** and **existing Jev implementations**
- [ ] The question templates and the decision rule's operating characteristic are recorded **before** any probe runs
- [ ] All eight probes run at the stated n on the pinned model, with measured rates and intervals written into `docs/taxonomy.md` **whether or not they are favourable**
- [ ] Probes 1–4 are marked **go / conditional / stop**; `conflict_floor` and the entity rule variant are written into `DESIGN §5.7` with the data that chose them
- [ ] The prediction below is marked **CONFIRMED** or **WRONG**, with the numbers
- [ ] The v0 scope list is frozen and written into `DESIGN §10`
- [ ] No library code exists

### Abandon criterion

**Probe 1 below 0.70, probe 2 below 0.60, or probe 3 above 0.20 stops candidate selection as designed.** Without accurate selection and reliable abstention, the candidate architecture launders wrong answers through calibrated-looking numbers (`DESIGN §5.4`). The fallback is not "tune it".

**The fallback product is phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7**: a bounded-decision compiler with criteria-gated generative fields and union discrimination. The README says exactly which capability did not ship and why.

A probe 6 result showing that injected notes steer selection on real documents does **not** stop the project — the pilot already showed it **[P7]** and `DESIGN §5.8` states the limit — but it sets the priority of the Phase 5 source screen.

### The prediction on record

> **Classes C and D are a narrow band.** Most of JSON Schema is class A; most *fields* in real extraction schemas are class E (unbounded strings) or D. C and D together cover enums-with-ambiguity, union discrimination, boolean predicates, ordinal ratings, and source-span disambiguation — real and unserved as a general compiler, but **not most of a typical schema**.

If confirmed, the honest product is **a decision-graph compiler for the disambiguation band**. Recorded before the taxonomy was built, so the taxonomy is a test rather than a rationalisation.

### Answers

`DESIGN §12`: entity resolution, `conflict_floor`, and the component rule (probe 4); calibration, first reading (probe 7); source screening, first reading (probe 6).

---

## Phase 1 — Core model, protocols, graph, and the fake backend

**Goal:** the type system, every protocol, and the execution skeleton, so everything afterwards can be tested without spending money or waiting on a network.

**Depends on:** Phase 0.

### Deliverables

- `types.py` — every type in the layout, with `UnresolvedReason` as the closed set of `DESIGN §6.1`
- `protocols.py` — all five protocols (the three I/O protocols async, `Normalizer` and `CostSink` sync), with the signatures pinned in `DESIGN §8`
- `graph.py` — `DecisionGraph`, dependency edges, acyclicity check, topological levelling of decision nodes around step nodes (R3, R11)
- `probabilities.py` — integer hundredths, the sum tolerance, the argmax-vs-vendor-`choice` check, and the tie margin (`DESIGN §2.1`, `DESIGN §6.2`)
- `config.py` — `JevsonConfig` (`DESIGN §3.5`)
- `backends/fake.py` — deterministic fake, configurable to return specified answers, distributions, ties, and abstentions
- `result.py` — `Result` exactly as pinned in `DESIGN §8.1`
- `errors.py` — the full hierarchy
- `unicode/graphemes.py` — UAX #29 boundaries from a vendored table generated at Unicode 17.0 (~1.2 KB compressed, pure Python **[L19]**)
- `extract/spans.py` — span construction and verification (`DESIGN §5.9`)
- `assemble/assembler.py` — resolved graph → JSON object, including the absent/null/unresolved table of `DESIGN §5.6`

### Exit criteria

- [ ] A hand-built graph with decision and step nodes levels correctly, including a diamond dependency
- [ ] A dependency cycle is rejected at construction with the offending node ids
- [ ] The fake backend resolves a hand-built graph and the assembler produces a valid object
- [ ] `Span` verifies by substring match on **code-point** offsets into the original source, half-open, and rejects mismatches
- [ ] **Graphemes:** `unicode/graphemes.py` passes every line of `GraphemeBreakTest.txt` for Unicode 17.0 and agrees with the `regex` module's `\X` on a generated differential corpus (the conformance file alone missed a real GB11 bug in a first draft **[L19]**); spans with a non-boundary endpoint are rejected (including CR|LF, after ZWJ, inside a flag pair, Hangul jamo, Indic conjuncts **[L11]**); precomposed-vs-decomposed and `\r\n`-vs-`\n` mismatches are rejected and counted, never repaired
- [ ] **Absence:** for each row of the `DESIGN §5.6` table, an abstention produces the specified value and lands in `absent` or `unresolved`; `complete` is true when only `absent` entries exist; for `Optional[str] = "x"` the key is omitted and Pydantic's `model_validate` yields `"x"` **[L18]**
- [ ] `Unresolved` is a value in the result, never raised; the unresolved key is omitted from `.value`; an unresolved root yields `{}`; `satisfies_schema` is computed by validation, not inferred, and a fully resolved object that fails `maxLength` yields `complete is True`, `satisfies_schema is False`, and a `Violation` naming the keyword
- [ ] **Probabilities:** a distribution summing to 0.99 with K = 3 is accepted; one summing to 0.95 is an invalid answer; on a bool, p = 0.45 and p = 0.55 are ties, p = 0.56 is true and p = 0.44 false; a choice at 0.52/0.42/0.06 is a tie; a vendor `choice` naming a non-argmax option outside the margin is invalid
- [ ] Property: `levels(graph)` preserves every node exactly once and respects every edge
- [ ] All five protocols are defined here; no later phase introduces one without amending `DESIGN §8`
- [ ] Public API is exported from `__init__.py` and nothing else is

### Abandon criterion

None. If this phase is hard, the type model is wrong and is reworked in place.

### Out of scope

Compilation from a schema. Any real backend. Candidates. Arrays.

### PR size

~500 lines. Split `unicode/` into its own PR if it runs over.

---

## Phase 2 — The compiler: schema → decision graph

**Goal:** turn idiomatic Pydantic models and JSON Schema into a decision graph for the bounded subset, and refuse everything else loudly, before any network call.

**Depends on:** Phase 1.

### Deliverables

- `compile/normalise.py` — the normalisation table of `DESIGN §3.5`, reading Pydantic's `mode="validation"` schema (Pydantic ≥ 2.12) and merging sibling keywords beside a `$ref` **[L3, L16, L18]**
- `compile/declarations.py` — the `x-jevson` keyword: every key of `DESIGN §3.5` parsed and validated; unknown keys refused
- `compile/mapping.py` — the Phase 0 taxonomy as routing rules with the `DESIGN §4.2` table: bool → `noul` with the tie margin; enum → `choice` over opaque ids; integer range declared `ordinal: true` → `score`; other integer ranges and 0–1 numbers are numbers, not ratings or probabilities
- `compile/questions.py` — the versioned templates recorded in Phase 0 (`DESIGN §5.2`)
- `compile/nodes.py` — node ids from the **target instance pointer** plus a role suffix
- `compile/compiler.py`, `compile/refusal.py` — `CompileError` carrying **every** offending pointer (R14)
- Standalone, network-free `compile_schema(schema, extractors={names}, default_extractor=None)` — class G depends on which extractors exist

### Exit criteria

- [ ] Every class A construct is handled by code with no decision node emitted
- [ ] Every class C construct in the Phase 0 v0 list compiles to the primitive the taxonomy specifies, **except union discrimination and enum arrays**, which refuse with `not_yet_supported` until Phases 6 and 7
- [ ] **Idiomatic Pydantic compiles:** a model with a nested submodel, an `Enum` field, a single-member `Enum`, an `Optional[Literal[...]]` field, a `Literal` field, and undeclared defaulted leaf fields (`str = "USD"`, `Tier = Tier.basic`, treated as class A) compiles without refusal; an `Optional[Address] = None` whose leaves are enums or bools compiles to decision nodes (not class A), and one whose leaves declare sources refuses only with `not_yet_supported` (not class A), and `list[Literal[...]] = []` and `Field(default_factory=list)` are treated identically (both refuse `not_yet_supported` until Phase 7); an `Optional[Decimal]` field and a `Decimal` field, each declaring a source, normalise correctly and then refuse only with `not_yet_supported` (lifted in Phase 5) **[L3, L16, L18]**
- [ ] `x-jevson` declared on a field whose type is a nested model (placed beside the `$ref`) is found and applied; a model-level `json_schema_extra` inside `$defs` is not mistaken for a field declaration **[L18]**
- [ ] A flat `allOf` of object schemas merges; a non-flat `allOf` refuses; `oneOf` + `discriminator` refuses with `not_yet_supported`
- [ ] A three-level nested object compiles with every node carrying its full instance pointer, and assembles back to the correct shape
- [ ] Two fields sharing one `$defs` type produce distinct, stable node ids
- [ ] A Pydantic model and its emitted JSON Schema compile to identical graphs
- [ ] Refusal is **total and specific**: an unmappable schema lists *every* offending pointer
- [ ] `compile_schema()` makes **zero network calls** — asserted with the network stubbed to raise
- [ ] Each of these refuses with a distinct named reason: enum > 255 or < 2 values; ordinal > 10 or < 2 levels; unbounded strings or numbers with no `source` or `generate` declaration and no default extractor; an unknown extractor name; recursive or dynamic `$ref`; `dict[str, X]`; tuples; `Any`; `bytes`; unknown `x-jevson` keys; `x-jevson.order: semantic`
- [ ] `x-jevson.source` fields, `x-jevson.generate` fields, and unions with ≥ 2 non-null branches refuse with `not_yet_supported` (lifted in Phases 5, 4, and 6)
- [ ] Rendered questions contain no negation from the template and match the recorded template version
- [ ] Property: over generated schemas, `compile_schema()` returns a graph or raises `CompileError` — never a third outcome, never a partial graph

### Abandon criterion

None.

### Out of scope

Executing anything. Generative fields (Phase 4). Candidates (Phase 5). Unions (Phase 6). Arrays (Phase 7) — which refuse with `not_yet_supported` until then.

### PR size

~500 lines. Split `normalise.py` and `declarations.py` into their own PR if it runs over.

---

## Phase 3 — Executor, live backend, and the façade

**Goal:** resolve a graph against the live model in the minimum number of calls, with a real budget, typed failures, and cost accounting, behind the public façade.

**Depends on:** Phase 2.

### Deliverables

- `execute/state.py` — every collection in state is an object keyed by opaque ids, never a list referenced by position (R13)
- `execute/executor.py` — runs step nodes through their protocols and decision levels as one batched call each (R3); `resolve()` and `aresolve()`; emits every cost event to the `CostSink`
- `execute/budget.py` — **preflight on declared maxima** against both limits (`DESIGN §8.2`); `PreflightError` before any spend
- `execute/policy.py` — transport retry for 429/5xx/timeout with backoff, bounded by `transport_retries` (default 2), counted separately; no retry for other 4xx; `max_tokens_exceeded` mapped to split or refusal, never an identical retry
- `execute/ratelimit.py` — one token bucket per API key on `threading.Lock`, shared across backends, threads, and event loops **[L20]**
- `execute/loop.py` — the library-owned event loop in a daemon thread; `resolve()` submits `aresolve()` to it and refuses inside a running loop **[L20]**
- `backends/jev.py` — raw `httpx`; one long-lived client on the library loop and per-call clients on caller loops (`DESIGN §8`); pinned model; **aliases refused**; HTTP 400 bodies mapped to typed errors **[P2]**; `usage.input_tokens` and `x-typesafe-request-id` recorded **[P8]**; the API key is a constructor argument, falling back to `TYPESAFE_API_KEY` (`DESIGN §8.3`)
- `backends/caching.py` — `CachingBackend` with RFC 8785 keys (the `rfc8785` package **[L21]**), writing only to a caller-supplied directory (`DESIGN §8.4`)
- `facade.py` — `Jevson(backend=..., config=...)` with **no default backend**; `resolve(source, known=...)`, with `known=` values validated before any spend
- `tests/adversarial/hostile_backend.py`, `hostile_transport.py` — every backend and transport row of PLAN §4.2
- Integration suite, opt-in and marked, against the real key. Locally the key lives in a gitignored `.env`; only the test harness reads it

### Exit criteria

- [ ] A graph with N independent nodes resolves in exactly **one** backend call — asserted by counting calls
- [ ] A graph with a (fake) step node runs the step before the decisions that depend on it
- [ ] **R13:** no template text or state path references a collection element by position — a test fails on any `[<digits>]` reference outside interpolated source or option text
- [ ] **Budget:** a level exceeding the total limit splits, recorded in `Cost.level_splits`; a declaration whose maxima exceed the per-question limit raises `PreflightError` before the *first* call
- [ ] **Invalid backend answers** in a well-formed HTTP 200 (an option never offered, malformed or mis-typed JSON for a question, a probability outside [0, 1], a sum outside tolerance) resolve to `Unresolved(invalid_backend_answer)` for the affected questions; an unparseable HTTP response is a `BackendError`; neither is an untyped exception
- [ ] **Step timeouts:** a fake step that never returns raises `ExtractorError(timeout)` after `step_timeout_s`, with the partial `Result`
- [ ] **Lifecycle:** `Jevson` and `JevBackend` work as context managers; a closed instance raises `UsageError`; `resolve()` inside a running loop raises `UsageError`
- [ ] **Ties:** a bool noul at 0.45, 0.50, or 0.55, and a choice whose top two differ by ≤ 0.10, yield `Unresolved(tie)`
- [ ] **Run-time overflow:** a fake backend returning `max_tokens_exceeded` for one question in a level causes a bisection that isolates it; that field is `Unresolved(budget_exceeded)` and the others resolve
- [ ] **Lifecycle on caller loops:** 20 sequential `asyncio.run(aresolve(...))` calls leave no live client for a dead loop **[L22]**; two `aresolve()` calls run concurrently under `asyncio.gather` on one loop both succeed and leave no open client; inside `async with JevBackend(...)` the calls share one client, closed on exit; `resolve()` succeeds in a forked child, including when the parent was blocked mid-request on a mock transport
- [ ] **Async:** two sequential `resolve()` calls on one backend both succeed; `resolve()` from 4 threads at once succeeds; `aresolve()` from two different event loops succeeds; `resolve()` inside a running loop raises with a pointer to `aresolve()`; the per-key limiter holds its rate across all of these **[L20]**
- [ ] **Known values:** a `known=` value that fails its field schema raises `PreflightError` before any call; a valid one skips its nodes and is recorded as `decided_by: caller`
- [ ] **Satisfies schema:** for a Pydantic input, a `.value` that passes `jsonschema` but fails `model_validate` yields `satisfies_schema is False` **[L18]**
- [ ] **Transport:** every hostile transport behaviour yields `BackendError` carrying the partial `Result` and `Cost`; transport retries are counted separately
- [ ] **Central property (PLAN §4.1)** holds over generated schemas × every hostile backend and transport behaviour
- [ ] An unresolved required field yields `satisfies_schema is False` by default and `SchemaViolation` with `raise_on_unresolved_required=True`
- [ ] **No default probability threshold drops a commit** — a committed low-probability answer is reported, not dropped
- [ ] **Determinism of our code:** with the fake backend, identical inputs produce identical `Result`s excluding wall-clock timings; a run replayed through `CachingBackend` reproduces the original `Result`, excluding `Cost` and wall clock, with every call counted as a cache hit; with `replay_only=True` a miss raises `BackendError(replay_miss)`; a request containing a lone surrogate is not cached
- [ ] **Live stability is measured, not asserted:** ≥ 100 schema-derived decisions with a top-two margin ≥ 0.20 are chosen in a separate selection run; two further live runs are compared, where a flip is any change of committed value or between a value and `tie`, and the flip rate is written down; the suite fails only if it exceeds 2% **[P1, P12]**. The model id is recorded; a change is a re-baseline
- [ ] **Credentials:** an explicit `api_key` wins; with neither argument nor environment (or with empty strings), `JevBackend()` raises `MissingCredentials` before any network call; the library never reads a `.env` file
- [ ] **The key never leaks:** a sentinel key appears in no exception message, `repr`, log record, cache file, or `Result`, across success, 4xx, 5xx, and timeout paths
- [ ] **Rate limit:** two `JevBackend` instances with one key share one limiter
- [ ] **No vendor SDK** in the dependency closure
- [ ] Cost is populated on every result and on every exception raised after the first spend (`SchemaViolation`, `BackendError`, `LLMError`, `ExtractorError`), and every event reaches the `CostSink`

### Abandon criterion

None. Note what this phase is **not**: it is not feature parity with `jev_jsonschema`. It covers whatever the Phase 0 v0 list contains.

### Out of scope

Candidates. Unions. Arrays. Generative fields.

### Answers

None open. (Level splitting was closed by evidence **[P1]**.)

### PR size

~500 lines. Split `backends/` and transport policy into their own PR if it runs over.

---

## Phase 4 — Generative fields and adjudication

**Goal:** fields no candidate set can fill — a summary, a synthesised description — drafted by the caller's LLM and admitted only after Jev adjudicates them against declared criteria.

**Depends on:** Phase 3. Independent of candidate selection, so it survives Phase 5's abandon criterion.

### Deliverables

- `compile/generative.py` — `x-jevson.generate` (`DESIGN §3.5`, `DESIGN §6.3`) compiles to a `generate` **step node** plus one criterion `noul` per criterion (and an optional rubric `score`) depending on it; lifts the Phase 2 `not_yet_supported` refusal for generated fields
- The `generate` step: the LLM is asked for the one-field tool schema `{value: string}`, passed as JSON Schema for the `LLM` adapter to render per provider (strict OpenAI/Anthropic envelopes differ from Gemini's **[L20]**); drafts longer than `max_draft_chars` are failed drafts; drafting prompts are templates in `compile/questions.py`
- `execute/policy.py` — the **redraft loop**, bounded by `redraft_budget` (default 1): failing criteria are passed back; a draft identical to one already adjudicated is not re-adjudicated and counts against the budget
- `adjudicate/criteria.py` (each criterion passes at p ≥ 0.56; the tie margin yields a tie, counted as a failed criterion for redraft), `adjudicate/rubrics.py` (most probable level ≥ declared minimum); state follows the keyed level layout of `DESIGN §5.2` (`drafts: {node id: draft}`)
- `llm/replay.py` — `ReplayLLM`
- Rejections naming the failing criteria, in `Result.rejections`
- `adjudicate/dryrun.py` and `docs/criteria-guide.md`
- `tests/adversarial/hostile_llm.py`, including the draft-injection variants from **[P7]**

### Exit criteria

- [ ] A declared generative field compiles to a step plus criterion nodes; an unbounded string with neither `source` nor `generate` still refuses
- [ ] All criteria for a field are adjudicated in **one** batched call
- [ ] Rejection names the specific failing criteria
- [ ] Redraft budget is bounded; exhaustion yields `Unresolved(redraft_exhausted)`, never an exception or a silently accepted string
- [ ] A fake LLM that repeats its draft triggers **no** second adjudication call, and the repeat counts against the budget
- [ ] Preflight accounts for `max_draft_chars`; an over-length draft is a failed draft, not a context-limit error after spend
- [ ] **Central property (PLAN §4.1)** holds with every hostile LLM behaviour: wrong keys, prose instead of a tool call, non-string values, enormous strings, text that looks like JSON, exceptions from the LLM (→ `LLMError` with partial result)
- [ ] **Injection regression:** over the **[P7]** draft-injection set (20 sources × 4 variants, 80 cases, 0 flips in the pilot), the suite fails if more than 3 failing drafts are judged passing (the Wilson upper bound for 0/80 is ≈ 0.046); it is run under the keyed multi-draft level layout of `DESIGN §5.2`, with each injected draft placed beside a second, clean draft that fails its own criteria, and a flip of either draft's verdict counts; if that layout fails where the single-draft layout passes, adjudication issues one call per draft
- [ ] **Criterion ties:** a criterion inside the tie margin counts as failed, is named in `rejections`, and triggers a redraft; `Result.decisions` holds `…@0` and `…@1` for one redraft
- [ ] `ReplayLLM` reproduces a recorded run exactly
- [ ] The dry-run tool runs against the fake backend with no key
- [ ] A field with no declared criteria is admitted with `no_criteria_declared` and listed in `Result.ungated`
- [ ] **Redraft bar, measured against human labels:** over ≥ 100 rejected drafts, each redraft labelled after generation by a labeller who does not see Jev's verdict, the rate at which a redraft is admitted *and* truly satisfies the criteria is written down, together with the rate at which a redraft is admitted while violating them, and the paired difference from first drafts with its 95% interval; the default `redraft_budget` stays 1 only if the first is ≥ 10% and the second is no more than 2 points above the same rate for first drafts, otherwise it becomes 0

### Abandon criterion

None. If adjudication proves weak, generative fields ship with the measured rates documented and `no_criteria_declared` visible.

### Out of scope

Automatic criteria derivation. A criteria linter.

### Answers

`PLAN §7`: do redrafts recover? (last exit criterion).

### PR size

~450 lines.

---

## Phase 5 — Candidates and source selection

**Goal:** the capability that makes Jevson a source-grounded extraction library. Fields whose values come from the source, chosen by Jev among verified spans, with provenance and mandatory abstention.

**Depends on:** Phase 4.

### Deliverables

- Lifts the Phase 2 `not_yet_supported` refusal for fields declaring `x-jevson.source`, and for unbounded fields when `JevsonConfig(default_extractor=...)` is set; built-in pattern extractors apply only when declared by name (`DESIGN §3.5`)
- `extract/llm.py` — LLM-backed extraction; the extractor returns strings and **Jevson locates them in the original source**; unlocatable strings are rejected and counted
- `extract/patterns.py` — money, date, email, phone, and URL candidates
- `extract/occurrences.py` — every occurrence of a repeated candidate text, each with a ±40-character context window in its option description (`DESIGN §5.1`) **[P15]**
- `assemble/parse.py` — class F parsing of a **selected** span into number, money, or date
- Candidate-backed choices with **opaque option ids**, **mandatory `none_of_these`** (R1), and the complete-value template (`DESIGN §5.2`)
- **Single candidates** asked by default; `direct_extraction: true` opt-in, listed in `Result.ungated` (R4)
- `max_candidates` (default 50) enforcement at run time → `Unresolved(too_many_candidates)`; zero candidates → absent or `Unresolved(no_candidates)` without a Jev call; for fields whose value is the verbatim span, candidates violating the field's `maxLength`/`minLength`/`pattern` rejected before the question (`DESIGN §5.3`, `DESIGN §5.6`)
- Class F parsing of a selected span under the field's `locale` (default `en-US`); a span that does not parse → `Unresolved(unparseable)`; decimals emitted in string form (`DESIGN §3.5`)
- **Retry** (`DESIGN §5.5`): exclusions; Jev call only on a new verified span; old ∪ new; batched per level; `retry_budget` per call
- `screen.py` — the **opt-in source screen** (`DESIGN §5.8`), asked in the first decision level, flagging at p ≥ 0.56; the tested wording flagged 28/60 benign documents **[P21]**, so this phase searches for a wording on a development split and measures it on a held-out split
- `tests/adversarial/hostile_extractor.py` and `hostile_sources/`
- **If Phase 0 was *conditional* on probes 1–3:** a second gate — an independent verification noul per committed span, batched into the same call; a failed verification yields `Unresolved(verification_failed)`; the cost delta is recorded. The measurements below run **with the gate on**
- **Measurement corpus**, disjoint from Phase 0, labelled before any run, under the Phase 0 corpus rules

### Exit criteria

- [ ] Every candidate-backed choice includes `none_of_these` — asserted structurally in the compiler (R1)
- [ ] A text occurring twice is offered twice, with context windows, and a fixture with the correct occurrence second resolves to the second offset
- [ ] **Coverage and false abstention use the Phase 0 rule and bands** on the fresh corpus (≥ 150 present-answer and ≥ 150 absent-answer cases): point-estimate verdicts, Wilson intervals reported, operating characteristic recorded before the run. Aligning the two phases means a Phase 0 *conditional* is not converted into a near-certain Phase 5 failure by a stricter rule **[L15]**
- [ ] No parameter changes between the first coverage measurement and the verdict except bug fixes, and every run is recorded
- [ ] Every committed value verifies against the source by substring and grapheme boundary; failures are rejected before the Jev call
- [ ] A candidate count above `max_candidates`, counted in options after repeated-text expansion, yields `Unresolved(too_many_candidates)` with texts and counts in `detail`; zero candidates follow the `DESIGN §5.6` table with no backend call (an optional field → `absent`, a required one → `Unresolved(no_candidates)`)
- [ ] **Pre-filter:** a verbatim field's candidates failing `maxLength`/`pattern` are rejected before the question; a class F field's candidate `"$1,204.50"` is not rejected by the `Decimal` pattern, and its parsed value is validated after selection
- [ ] **Direct extraction with several candidates:** two distinct candidates on a `direct_extraction: true` field are asked as an ordinary choice, and the field is not listed in `ungated`
- [ ] **Object absence:** an `Optional[Address] = None` whose source-selected fields are all missing from the source is omitted and listed once in `absent`, even though `Address` has an enum field `kind` (whose value is discarded); with one source-selected field present, its missing required fields are `Unresolved(abstained)`; a `generate` field under an absent object is not drafted; a root whose only source field abstains still returns its enum answers and drafts its generated fields (the root is never abstained); an optional object containing a source-grounded array that accepted no member is absent
- [ ] **Retry record:** a field retried once leaves `…@0` and `…@1` in `Result.decisions`
- [ ] **Step timeouts:** a never-returning hostile extractor yields `ExtractorError(timeout)`
- [ ] A single candidate produces a two-option choice; `direct_extraction: true` produces zero backend calls and an `ungated` entry
- [ ] **Absence:** a **required** nullable field that abstains is `null` and listed in `absent`; a not-required one is omitted and listed in `absent`; a required non-nullable one is `Unresolved(abstained)`
- [ ] **Retry mechanics:** the second call offers old ∪ new and contains at least one span absent from the first; no retry call is issued when extraction returns nothing new
- [ ] **Retry bar, two-sided:** recovery is measured on ≥ 100 **constructed extraction-miss cases** (the correct span withheld from the first extraction pass only; the second pass is the unmodified extractor with exclusions, and whether it finds the span is part of what is measured) and the false-commit change on ≥ 300 truly-absent cases; both by point estimate. The paired difference is reported with its 95% interval beside the point estimate. The default `retry_budget` stays 1 only if recovery ≥ 10% **and** the false-commit increase is ≤ 2 points (≤ 6 of 300), otherwise it becomes 0 **[L15]**
- [ ] **Calibration reading:** over ≥ 1,000 decisions, the `DESIGN §6.2` power check is computed on the observed distribution first, the corpus extended (up to 3,000) if it fails, and then ECE with its one-sided bootstrap bound, the Wilson rule at τ, a reliability diagram, and Brier score are written down whatever they show. This is the evidence the deferred default threshold (PLAN §9) waits on
- [ ] **Hostile sources:** the rates at which injected notes steer selection and suppress abstention are measured and written down; in later releases the suite fails if a rate's point estimate exceeds the previous release's Wilson upper bound
- [ ] **Source screen:** measured on a held-out ≥ 300 benign real documents (including processing notes) and ≥ 150 attacked ones, after wording development on a separate split; it becomes eligible to be on by default (in v1) only with ≤ 7 false positives and ≥ 130 true positives **[L15]**; the rates are written down either way
- [ ] Parsing a selected money span yields the right decimal string (a number for `type: number` fields), with the span as provenance; `$1,204` parses to 1204 under the default `en-US` locale; `1.204,50` is `Unresolved(unparseable)` under the default and 1204.50 with `locale: de-DE`; an unsupported `locale` tag refuses at compile time
- [ ] Extractor swap: a hand-supplied extractor returning the same (recorded) candidate set as the LLM extractor resolves identically
- [ ] **Central property (PLAN §4.1)** holds with hostile spans, hostile sources, and hostile extractors (raising → `ExtractorError` with partial result)
- [ ] Provenance offsets survive assembly unchanged

### Abandon criterion

**If coverage or false abstention lands in the Phase 0 stop band on the fresh corpus, candidate selection does not ship.** The fallback is phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7, with source selection removed and the README positioned accordingly.

### Out of scope

Arrays of candidates (Phase 7). More than one source (Phase 9).

### Answers

`DESIGN §12`: retry's real value; calibration on this task; source screening.

### PR size

~500 lines. Split extractors and the source screen into their own PRs if it runs over.

---

## Phase 6 — Union discrimination

**Goal:** `anyOf` / `oneOf` with two or more non-null branches resolved as a decision that determines which branch is *executed* (`DESIGN §3.2`).

**Depends on:** Phase 5 in sequence. Its content needs only Phase 3, so it proceeds if Phase 5 abandons.

### Deliverables

- `compile/unions.py` — discrimination `choice` over branches (no `none_of_these` in v0); **every branch compiled and validated statically**; Pydantic discriminated unions (`discriminator` keyword) supported; lifts the Phase 2 refusal
- Execution of the selected branch only; the unselected branches' steps never run
- A measured choice between a separate discrimination level and **speculative fan-out** (`DESIGN §3.2`) for branches whose nodes are pure Jev questions

### Exit criteria

- [ ] A union resolves its discriminator first, and **only the selected branch's nodes are executed** — asserted by counting executed nodes and backend questions
- [ ] An unmappable construct inside **any** branch refuses at compile time, before any call
- [ ] Branches whose required properties and descriptions are identical after normalisation refuse as undiscriminable
- [ ] A nested union levels correctly
- [ ] The unselected branch's fields never appear in the result, even as nulls
- [ ] The discrimination decision appears in `Result.decisions`; a tie or invalid answer yields `Unresolved` for the whole subtree (reason `tie` or `invalid_backend_answer`, children `dependency_unresolved`)
- [ ] **Fan-out vs level:** latency and tokens for both strategies measured on ≥ 50 fixtures; the default is chosen from the numbers, which are written down

### Abandon criterion

None. If unions prove intractable they are refused, which is the prior art's status quo.

### Out of scope

`allOf` beyond flat merging (tracked in PLAN §9).

### Answers

`DESIGN §12`: union execution strategy.

### PR size

~300 lines.

---

## Phase 7 — Source-grounded arrays

**Goal:** arrays whose membership is a set of bounded decisions over candidates, with entity resolution, source order, and honest overflow.

**Depends on:** Phase 6 in sequence, and on Phase 5's candidate machinery. **If Phase 5 abandoned, this phase is cancelled** — except multi-label enum arrays, which need no candidates and ship regardless.

### Deliverables

- Membership: one `noul` per candidate with the tie margin, batched with the pairwise questions in the same level (R5, `DESIGN §3.3`); candidates keyed by opaque id (R13)
- **Multi-label enum arrays**: one membership noul per declared value; declared enum order; `maxItems` keeps the first k with overflow retained (`DESIGN §4.2`)
- `assemble/entities.py` (`DESIGN §5.7`): lossless pre-merge (casefold opt-in; never initials or first names); pairwise nouls, capped; the internal-consistency rule, plus the cross-component variant if Phase 0 chose it, with `conflict_floor` from Phase 0
- `Normalizer` canonical representative: earliest span, longest span, or user-supplied
- `assemble/ordering.py` — source order; `order: semantic` refuses (R7)
- `assemble/cardinality.py` — membership → pre-merge → pairwise → components ordered by earliest span → `maxItems` keeps the first k; each overflowed element records its spans and minimum membership probability (R8)
- An experiment on reducing pair jitter by asking both orderings of each pair and averaging, measured against single-order asking on ≥ 40 documents × 2 identical runs (`DESIGN §12`); it doubles pair questions, so it is measured only at question counts already covered by keyed-batching evidence

### Exit criteria

- [ ] `"Attendees were Dana, John, Sarah, and Michael"` produces a 4-element array in source order
- [ ] **The chain case:** with a fake backend answering Dana = Dana Whitfield (0.9), Dana Whitfield = Ms. Whitfield (0.9), Dana vs Ms. Whitfield (0.4), no cross-component pairs in the uncertain band, and a floor of 0.30, the three produce **one** element
- [ ] **The internal-conflict case:** A = B, B = C, A vs C ≤ floor → that component is `Unresolved(entity_conflict)` naming the pairs; other components are emitted
- [ ] **The split case:** under the cross-component variant, two components linked by a pair at 0.40 (above a 0.30 floor) → both are `Unresolved(entity_conflict)`; under the internal-only variant, both are emitted
- [ ] **Enum arrays:** a multi-label enum array emits members in declared order, with ties unresolved and `maxItems` overflow retained; this ships even if Phase 5 abandoned
- [ ] **Pre-merge:** `"Acme Corp"` and `"Acme  Corp"` merge with zero backend questions; `"US"` and `"us"` do **not** merge by default; with casefold opted in they do; identical strings under different entity types never merge
- [ ] Pairwise resolution for n candidates issues n(n−1)/2 keyed questions in one call, split only by the budget
- [ ] A candidate count above the cap yields `Unresolved(too_many_candidates)`
- [ ] **Cap measured:** component outcomes at n ∈ {10, 20, 30} on ≥ 20 real arrays per n (including how many arrays are incomplete only through membership ties), and keyed-batching accuracy at the resulting question count (measured only to 320 so far **[P4]**), are written down; the default cap is the largest n meeting the Phase 0 probe 4 go band
- [ ] **Jitter experiment** results are written down; both-orderings asking is adopted only if it at least halves the pair-decision flip rate between identical runs and component accuracy is not lower (point estimates)
- [ ] `maxItems: 5` with six accepted elements returns five and records the sixth in `Result.overflow`
- [ ] An array declaring semantic order refuses; an array of unbounded items with no `source` refuses
- [ ] **Members only:** a rejected candidate linked at 0.9 to two members A and B, with A–B at 0.10 (≤ floor), does not merge them: A and B are emitted as two elements under both variants
- [ ] **Array holes:** an array with one unresolved component is emitted with its other elements, and the hole is one `Unresolved` at the array pointer; a tied value in a multi-label enum array likewise
- [ ] Source ordering is deterministic across runs

### Abandon criterion

**If component outcomes on real prose fall below the Phase 0 probe 4 go band, deduplication becomes the extractor's declared contract**: the library stops claiming it, documents that candidates must arrive normalised, and the dedup exit criteria are removed rather than weakened. Membership, ordering, and overflow still ship.

### Out of scope

Nested arrays of objects. Cross-item constraints. Semantic ordering. (All tracked in PLAN §9.)

### Answers

`DESIGN §12`: the pairwise quality ceiling; pair-jitter reduction.

### PR size

~500 lines. Split entity resolution into its own PR if it grows.

---

## Phase 8 — Packaging and release

**Goal:** the library is usable by someone who did not build it.

**Depends on:** Phase 7, or whichever phases survived their abandon criteria.

### Deliverables

- `CostSink` default implementation and documentation
- README rewritten to `DESIGN §9.1`, describing only what shipped
- Quickstart and worked examples **using only capabilities that shipped**
- A fair comparison with `jev_jsonschema`, the vendor's extraction cookbooks and playground, `jev-extract`, LangExtract, and Instructor, stating plainly what each does better **[X2, X3]**
- `pyproject.toml`, MIT licence, `py.typed`, Python 3.11+
- **The name is decided before the PyPI release**, after asking TypeSafe whether a "Jev" name is acceptable (`jevson` is free on PyPI and npm **[X6]**; no TypeSafe naming policy was found **[X4]**)
- **Versioning policy:** `0.x`, breaking changes permitted between minors and recorded in a changelog
- PyPI release

### Exit criteria

- [ ] README makes no claim outside the tiers in `DESIGN §6`, states the source-trust limit, and does not claim guaranteed JSON validity or novelty of candidate selection
- [ ] README names anything that did not ship and why
- [ ] Every public symbol is typed and documented
- [ ] Quickstart runs end to end against the fake backend with **no API key**
- [ ] Installed package exposes only the intended public surface and contains no hostile test doubles
- [ ] Dependencies: `jsonschema`, `pydantic` (≥ 2.12), `httpx`. Extractors and LLM providers are extras. `format` keywords are documented as unchecked unless the caller installs `jsonschema`'s format extras **[L10]**
- [ ] The package name is recorded in PLAN §6 before publication

### PR size

~250 lines plus documentation.

---

## Phase 9 — Multi-source and long-source extraction *(post-v0, planned)*

**Goal:** one call over several sources (an email thread and its attachment) or over one source longer than the per-question limit, with every committed value still traceable to one exact span in one named source.

**Depends on:** Phase 8. Deferred on cost and risk: it multiplies the context budget and interacts with the pairwise cap. `source_id` has been in `Span` since Phase 1. Prior art: `choxos/jev-reviewer` and `gbesse/jev-extract` already do multi-file or chunked extraction for fixed record types **[X3]**.

### Deliverables

- Multiple named sources per call; the call-boundary refusal is lifted
- Chunking of a long source into windows under the per-question limit, with candidates carrying offsets into the original source
- Candidates carry their `source_id`; verification runs against the named source
- Budgeting across sources and chunks: split, never truncate
- Cross-source entity resolution under the Phase 7 rules and cap

### Exit criteria

- [ ] A value found in source 2 carries `SOURCE_SPAN(source_2, start, end)` and verifies against source 2 only
- [ ] Identical text at different offsets in two sources never verifies against the wrong one
- [ ] A source longer than the per-question limit resolves through chunking with correct original-source offsets
- [ ] Sources that together exceed the budget split or refuse loudly; none is silently truncated
- [ ] A single-source call behaves identically to v0

### Out of scope

Retrieval over a corpus. Non-text sources.

---

## Phase 10 — JavaScript / TypeScript port *(post-v0, planned)*

**Goal:** the same library for Node pipelines (LangChain.js, plain TypeScript), behaving identically to the Python one.

**Depends on:** Phase 9. A second implementation, not a port script.

### Deliverables

- **A language-neutral conformance suite first**, extracted from the Python tests: JSON fixtures of schema + source + recorded backend responses → expected `Result`. Python must pass it before the port starts
- A TypeScript package implementing `DESIGN` at whatever scope Python shipped, with the same grapheme table version and RFC 8785 cache keys
- Zod (v4 `toJSONSchema`) and JSON Schema as the schema surface **[X7]**
- Credentials: an explicit `apiKey` argument; the `TYPESAFE_API_KEY` fallback in Node only

### Exit criteria

- [ ] Both packages pass the same conformance suite in CI
- [ ] Span offsets agree across languages: Python offsets are code points, JavaScript strings index UTF-16 code units, so the port converts explicitly **[L2, X7]**; fixtures include astral-plane characters, and a span whose boundary would fall inside a surrogate pair is rejected
- [ ] Cache keys computed in JavaScript equal those computed in Python for the same request
- [ ] The JS package passes the central-property adversarial suite (PLAN §4.1)

---

## Phase 11 — Credentials from Infisical *(post-v0, planned, lowest priority)*

**Goal:** contributors and CI fetch the Jev key from the team's Infisical project at run time instead of keeping it in a local `.env`.

**Depends on:** Phase 10 in sequence; no technical dependency, so it may be pulled earlier whenever convenient.

**Developer and CI tooling only. The library does not change**: outside users never need Infisical.

### Deliverables

- Integration tests and scripts runnable as `infisical run -- <command>`, which injects secrets as environment variables into the child process **[X8]**
- CI authenticates with an Infisical machine identity rather than a repository secret **[X8]**
- `CONTRIBUTING.md` documents both routes, and documents that the Infisical CLI keeps a local copy of fetched secrets for offline use **[X8]**

### Exit criteria

- [ ] The integration suite runs with no `.env` present, using only Infisical
- [ ] The key is written to no file in the repository and to no CI log — asserted by planting a sentinel and searching the CI log and working tree

---

## PLAN §3. Cross-cutting requirements

True at every phase; each PR is checked against them.

- **Refusal is loud and early** — compile time or call-time preflight, before any network call (R14).
- **No silent nulls.** Every missing value is `absent` or `Unresolved` with a reason, or a declared default.
- **Only `backends/jev.py` knows the vendor wire format.** No vendor SDK.
- **The model is pinned** (R15). Measurements record the model id.
- **Probabilities are integer hundredths**; the tie margin applies to every committing decision (`DESIGN §6.2`).
- **Nothing logged or written by default.**
- **Every backend call is counted**, on success and failure paths alike, with its request id.
- **Determinism of our code.** Given identical backend, LLM, and extractor responses, Jevson produces an identical `Result`, excluding wall-clock timings. Exact replay goes through `CachingBackend` and `ReplayLLM`.
- **Decision retries must change the input.** Transport retries are separate, bounded, and counted.
- **State is never referenced by position** (R13).
- **The source is untrusted** (R16): hostile-source cases are part of every phase that touches sources.
- **The fake backend keeps working.** Every phase adding a capability adds fake-backend support in the same PR.
- **Measured numbers are written down**, favourable or not.

---

## PLAN §4. Validation strategy

### 4.1 The central property

Asserted over generated schemas × every hostile behaviour, exactly as `DESIGN §6.1`: a call returns a complete `Result` that satisfies the schema; a `Result` that is incomplete or invalid, with every hole in `unresolved` and every failed constraint in `violations`; or a typed exception from Jevson's hierarchy. Never a fourth outcome.

Owned by: Phase 3 (backend, transport), Phase 4 (LLM), Phase 5 (spans, sources, extractors), Phase 10 (JS).

### 4.2 The adversarial suite

| category | behaviours | owner |
|---|---|---|
| **malformed responses** | wrong field names, missing fields, wrong types, extra keys, empty body, `null`, non-JSON body | Phase 3 |
| **invalid values** | options never offered, probabilities outside [0,1], `NaN`, sums outside tolerance, ties | Phase 3 |
| **transport** | timeouts, 429, 5xx, connection reset, unparseable HTTP responses, 400 `max_tokens_exceeded` | Phase 3 |
| **hostile LLM** | prose instead of a tool call, wrong tool, missing or misspelled keys, non-string values, enormous strings, text that looks like JSON, repeated drafts, exceptions | Phase 4 |
| **hostile drafts** | self-advocacy, targeted false claims, injected overrides **[P7]** | Phase 4 |
| **hostile extractors** | exceptions, never returning, unlocatable strings, offsets that do not match, empty and oversized candidate sets | Phase 5 |
| **hostile spans** | offsets absent from the source, overlaps, mismatched text, grapheme-splitting boundaries, duplicates | Phase 5 |
| **hostile sources** | injected notes to automated systems, self-advocating spans, planted near-duplicates, the correct text repeated in a wrong role **[P7, P15]** | Phase 5 |

### 4.3 Property-based tests

`hypothesis` strategies over the supported subset:

- `compile_schema()` returns a graph or raises `CompileError` — never a partial graph
- Levelling preserves every node exactly once and respects every edge
- Assembly of a fully resolved graph either validates against the original schema or yields `satisfies_schema is False` naming the violated keyword **[L9]**
- Provenance spans always verify against the original source and lie on grapheme boundaries
- Cost is monotonic within a call

### 4.4 Integration tests

Opt-in and marked. They **measure** where the quantity is a property of the model, compare against pre-registered bars, and run on the pinned model. They run on demand and on release, not on every push: the live key has a rate limit and a cost.

---

## PLAN §5. Risks

| risk | where it bites | mitigation |
|---|---|---|
| **`none_of_these` doesn't work on real documents** | Phase 0, fatal to Phase 5 | pre-registered bands; long multi-entity and repeated-text cases required; probes 2 and 3 read together; fallback product named |
| **We build Phase 4 before learning Phase 5 fails** | Phases 4–5 | accepted by the owner with the order (PLAN §1); Phase 4 survives the fallback, so the work is not wasted |
| **We abstain on everything and call it safety** | Phase 0 | probe 3 is the counter-metric |
| **Source text steers selection** | Phase 5 onward | measured **[P7]**; stated limit; the screen does not work yet **[P21]**; hostile-source suite |
| **Right text, wrong provenance** when a value repeats | Phase 5 | every occurrence offered with context **[P15]**; repeated-text cases in Phase 0 and the hostile suite |
| **Our novelty is overstated** | Phase 8 | prior art credited (`DESIGN §9`); comparison in the README; "existing Jev implementations" column |
| **The taxonomy comes back narrow and we pad it** | Phase 0 | prediction recorded in advance; narrow scope pre-accepted |
| **Entity resolution silently merges or splits** | Phase 7 | internal rule; cross-component variant chosen in Phase 0 **[P10, P17]**; abandon criterion |
| **Pair questions jitter** | Phase 7 | floor measured on two runs; both-orderings experiment **[P12]** |
| **Candidate extraction is the weak link** | Phase 5 onward | `none_of_these` mandatory, including for single candidates; complete-value template **[P11]** |
| **Context limits exceeded** | Phase 3 onward | preflight on declared maxima (default 50 × 120); split, bisect, or refuse; never truncate **[P14]** |
| **Sync wrapper over async code breaks** | Phase 3 | library loop thread; per-call clients on caller loops; thread-lock limiter **[L20, L22]** |
| **Live answers jitter** | Phase 3 onward | tie margin (removes most, not all, flips); stability measured, not asserted; cache for exact replay **[P1, P12, P20]** |
| **Vendor model changes under us** | everywhere | pinned model id; aliases refused; re-baseline on version change |
| **Vendor SDK churn, hidden retries, body logging** | Phase 3 | raw `httpx`; SDK not a dependency **[V-sdk]** |
| **Idiomatic Pydantic refused** | Phase 2 | the normalisation table **[L3, L16]** |
| **Adjudication admits bad drafts** | Phase 4 | criteria rule; dry-run tool; `no_criteria_declared` visible; injection regression; labelled redraft bar |
| **Retries burn money** | Phases 3–5 | decision retries only on changed input; two-sided retry bar; per-call budgets |
| **Scope creep via derived values** | Phase 5+ | out of v0 (R9) except parsing a selected span |
| **README drifts past what is true** | Phase 8 | exit criteria bind it to `DESIGN §6` |

---

## PLAN §6. Decisions recorded

| decision | call | reasoning |
|---|---|---|
| **Positioning** | General-purpose open-source library for anyone's pipeline; Asterion is its first user, not its specification | Built for its use case, not one consumer. Deferrals are justified by cost, risk, or sequencing and are planned (PLAN §9), never dropped |
| **Public claim** | Generalises the vendor's "select, don't generate" pattern into a schema compiler | Every mechanism predates us **[X2, X3]**; the combination does not, as far as we found |
| **Target user** | Extraction steps in pipelines where a wrong-but-valid value silently corrupts everything downstream | The unserved gap is a signal to route on, as a general compiler |
| **Language** | Python 3.11+ first | The target pipeline ecosystem (LangChain, LlamaIndex, Instructor) is Python-first; much Jev prior art is JS/TS **[X3]**, which is why a JS port is planned (Phase 10) |
| **Schema surface** | Pydantic (validation-mode schema) or JSON Schema draft 2020-12, with one `x-jevson` keyword | One declaration syntax for both surfaces |
| **Phase order** | Strictly sequential: 0 → 8, then 9 → 11; adjudication (4) before candidates (5) | **Set by the project owner.** Round-1 review E-40 (run 5 before 4 when Phase 0 says *go*) was considered and declined; Phase 4 survives Phase 5's abandon criterion |
| **Vendor access** | Raw `httpx`; `typesafe-sdk` not a dependency | Pre-1.0 churn, retries that may be billed, unredacted body logging **[V-sdk, X5]** |
| **Model version** | Pinned exact release (`jev-1.13.0`); aliases refused | Aliases move; evidence expires silently **[P9, V-models]** |
| **Credentials** | `api_key` argument, falling back to `TYPESAFE_API_KEY`; empty counts as missing; the library never reads `.env` | Anyone can use it with no project tooling |
| **Default backend** | None; `Jevson(backend=...)` is required | An environment variable must never silently turn tests into paid calls |
| **Protocols** | I/O protocols async, `Normalizer` and `CostSink` sync, pinned in DESIGN from Phase 1; sync `resolve()` on one library loop thread; per-call clients on caller loops; per-key limiter on `threading.Lock` | Pipelines are async; the rate limit is per key; a loop per call breaks shared clients **[L20]** |
| **State referencing** | Opaque-id objects, never positions | 62% vs 0% wrong **[P4]** |
| **Candidate options** | Opaque ids; every occurrence of repeated text offered with a context window | 40/40 vs 22/40; offering only one occurrence misattributes provenance **[P15]** |
| **Question wording** | Versioned templates; complete-value wording; no negations | Partials 32/42 → 0/42 **[P11]**; literal reading **[V-jagged]** |
| **Single candidates** | Asked with `none_of_these` by default; direct extraction opt-in | 84/84 wrong-role lone candidates abstained **[P11]** |
| **Abstention mechanism** | `none_of_these` inside the choice, not a separate noul gate | The gate was worse: 0.56 vs 0.89 **[P5]** |
| **Probabilities** | Integer hundredths; sum tolerance; one tie margin ≤ 0.10 for every committing decision | Rounding and jitter are measured; ±0.05 left 11/180 choice flips, 0.10 left 1/180 **[L17, P12, P20]** |
| **Confidence gating** | Reported, never gated by default | A default threshold would assert calibration we have not measured |
| **Calibration bar** | Tie-safe bins, one-sided bootstrap ECE bound, Wilson rule at τ, mandatory power check on the observed distribution | The bar's power depends on the distribution **[L13, L14]** |
| **Retry defaults** | Zero for schema-derived sets; one for candidates, old ∪ new, two-sided bar on constructed misses | Near-deterministic model; relative distributions; harm as well as benefit **[L15]** |
| **Entity resolution** | Lossless pre-merge; components over accepted members only; internal-consistency rule; cross-component variant and floor chosen in Phase 0 | Casefold merges distinct entities **[L1]**; the variant helped in-sample **[P10]** and did nothing out of sample **[P17]** |
| **Pairwise cap** | n = 30, lowered if Phase 7 measures a lower quality ceiling | Token-feasible with a lean template **[L7]**; quality unmeasured |
| **Grapheme boundaries** | UAX #29 from a vendored generated table at Unicode 17.0; conformance plus differential tests | The shorthand rule was wrong in 13–15 of 20 classes **[L11]**; ~1.2 KB, no new dependency **[L19]** |
| **Replay** | `CachingBackend` and `ReplayLLM`, RFC 8785 keys (`rfc8785` / `canonicalize`), caller-supplied directory | Identical hashes across languages **[L21]**; nothing written by default |
| **Source trust** | Untrusted; stated limit; screen off until a wording meets its bar | Selection is steerable **[P7]**; the tested screen wording flagged 28/60 benign documents **[P21]** |
| **Candidate defaults** | `max_candidates` 50 options (after repeated-text expansion), `max_candidate_chars` 120 | ~1.6k tokens, so the source ceiling stays high **[P22]** |
| **Undeclared defaulted leaf fields** | Class A: omitted so the default applies; objects and arrays compile from their contents | Neither decided nor refused; declare `source` or `generate` to have them decided |
| **Step timeouts** | `step_timeout_s` (default 120) on every caller step | A never-returning step must not hang every synchronous caller |
| **Absence** | Not required → omitted (defaults apply); required nullable → null; required → unresolved | A nullable field with a default must keep its default **[L18]** |
| **Semantic ordering** | Out of v0; declaring it refuses | Unproven; refusing beats silently wrong order |
| **Adjudication criteria** | About the draft and the source only | Jev is not a fact-checker |
| **Multi-source and long sources** | Out of v0, planned as Phase 9 | Budget and cross-source resolution |
| **JS port** | Planned as Phase 10 | Two languages in v0 finish neither |
| **Hostile doubles** | `tests/`, never shipped | The fake backend is a tool; the hostile one is a footgun |
| **Integration tests in CI** | On demand and on release | Rate limit and cost |
| **Versioning** | `0.x` | No stability promise before the scope verdict meets users |
| **Licence** | MIT | Permissive, like most neighbours (jevc and AnyJev are Apache-2.0) **[X6]** |
| **Name** | Keep "Jevson" for now; ask TypeSafe, then decide before the Phase 8 release | Vendor coupling; renaming after publication breaks users |
| **Fake backend** | Shipped | Users need it to test without spending |
| **Scope if the band is narrow** | Ship the narrow version | Pre-committed, to defeat sunk cost |

Reversals are recorded in `DESIGN §13`.

---

## PLAN §7. Open questions

| question | closed by | if the answer is bad |
|---|---|---|
| Does `none_of_these` catch missing answers on real documents? | Phase 0 probe 2, Phase 5 | Stop candidate selection; ship the fallback |
| Do we select accurately and abstain only when we should? | Phase 0 probes 1 and 3, Phase 5 | Conditional band: Phase 5 ships the second gate |
| Which entity rule variant, and what `conflict_floor`? | Phase 0 probe 4 | Dedup becomes the extractor's contract (Phase 7) |
| Is Jev calibrated on span disambiguation? | Phase 0 probe 7, Phase 5 | Probabilities stay reported, never gated |
| Can any screen wording flag hostile sources without flagging ordinary processing notes? | Phase 0 probe 6, Phase 5 | The screen stays off, with its rates documented |
| Do decision retries recover answers without adding false commits? | Phase 5 | Default retry budget becomes 0 |
| Do redrafts recover rejected drafts without admitting bad ones? | Phase 4 | Default redraft budget becomes 0 |
| Level or speculative fan-out for unions? | Phase 6 | Whichever the measurement favours |
| What is the pairwise quality ceiling? Can pair jitter be reduced? | Phase 7 | Cap lowered with the measurement cited; banding only |
| Is the name right? | before Phase 8 | Rename before publication |

**Closed by evidence:** level splitting is answer-neutral **[P1]**; keyed state references matter **[P4]**; a noul gate is a worse abstention mechanism **[P5]**; lone candidates are safer asked **[P11]**; the score value is the most probable level **[P13]**; the complete-value wording costs nothing when the full value is present **[P18]**; mixed option descriptions showed no decision bias at near-ceiling accuracy **[P19]**.

---

## PLAN §8. Sequencing summary

```text
Phase 0   taxonomy + probes + scope verdict           no code, gates everything
Phase 1   core model, protocols, graph, fake, spans   ~500 lines
Phase 2   normaliser + declarations + compiler        ~500 lines
Phase 3   executor + budget + live backend + façade   ~500 lines   ← working library
Phase 4   generative fields and adjudication          ~450 lines
Phase 5   candidates and source selection             ~500 lines   ← source-grounded extraction
Phase 6   union discrimination                        ~300 lines
Phase 7   source-grounded arrays                      ~500 lines   (cancelled if 5 abandons, except enum arrays)
Phase 8   packaging and release                       ~250 lines   ← v0
--- post-v0, planned ---
Phase 9   multi-source and long-source extraction
Phase 10  JavaScript / TypeScript port
Phase 11  credentials from Infisical                               (lowest priority)
```

Every phase starts only after the previous one has merged or abandoned. If Phase 0 or Phase 5's abandon criterion fires, the product is **phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7**.

---

## PLAN §9. Tracked deferrals

Nothing deferred is dropped. Each entry names what it waits on.

| deferred item | why deferred | revisit when | where it lands |
|---|---|---|---|
| **Default probability threshold** | Would assert calibration we have not measured (`DESIGN §6.2`) | Phase 5 calibration reading | v1, only if the pre-registered bar is met, citing the measurement |
| **Source screen on by default** | Wording is fragile **[P7]** | Phase 5 screen measurement | v1, only if its bar is met |
| **Semantic array ordering** | Unproven | After Phase 7 | A post-v0 phase with its own probe (pairwise preference vs. per-item `score`) |
| **Derived provenance** (R9) | Needs an expression layer | After Phase 8 | A post-v0 phase |
| **Multi-source and long sources** | Budget and cross-source resolution | After Phase 8 | Phase 9 |
| **JS / TS port** | Two languages in v0 finish neither | After Phase 9 | Phase 10 |
| **Infisical credentials** | Team convenience, not a library feature | Any time; lowest priority | Phase 11 |
| **Recursive and dynamic `$ref`, `allOf` beyond flat merge, `dict[str, X]`, tuples, `Any`, `bytes`** | Refused loudly (`DESIGN §3.5`) | After Phase 8 | A post-v0 phase |
| **Nested arrays of objects, cross-item constraints** | Out of Phase 7 scope | After Phase 8 | A post-v0 phase |
| **`none_of_these` on schema enums and union discriminators** ("not determinable from the source") | Schema-derived choices have no abstention path in v0 | After Phase 5 measures abstention | A post-v0 phase |
| **Relative and partial dates** ("next Friday", "the 3rd") | v0 parses selected absolute date spans only | After Phase 5 | A post-v0 phase using date-part choices with "not stated", as in the vendor's date-extraction cookbook **[V-cookbooks]** |
