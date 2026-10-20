# Jevson — implementation plan

> **Status:** Planning document, Revision 11.6, 2026-10-20 (Phases 1–4 exit criteria checked against the built code, ASTERION-44; Revision 11, 2026-10-14, the fallback scope). **v0 as built, not released:** Phases 1–4, 6 and 7 and the Phase 8 package are merged on `staging` (ASTERION-24 to ASTERION-39) and their exit criteria are ticked with their proofs, except: the **injection regression** (Phase 4, **not met**, tracked in ASTERION-48, which fixes it inside v0; owner decision, 2026-10-19); the **redraft bar** (Phase 4, **not met**, tracked in ASTERION-58: the decision model over-rejects; only its labeller is an owner-signed-off deviation, model labels in place of human labels, 2026-10-19, ASTERION-46 decision 2, never validated against human labels); and the package name (Phase 8, PLAN §6). Phase 0's probe 8 partial-only set (17 of 50) is accepted as an owner-signed-off deviation (2026-10-19, ASTERION-46 decision 1). The backend is the **OpenAI Decisions API** (`gpt-6-luna`), which replaced Jev on 2026-10-14 (PLAN §6); Phase 0 ran on `jev-1.13.0` and **Phase 0r** re-ran its probes on the Decisions API and confirmed **drop source selection** **[Q1–Q9]**, so v0 is **the fallback product** (DESIGN §10.1). Phase 5 is abandoned and kept as the record; everything class D (source selection) is a tracked deferral (PLAN §9). Not yet released: the two Phase 4 bars above are not met, CI on GitHub is pending (ASTERION-42), and the release is ASTERION-45.
>
> **Scope:** How Jevson gets built, in phases, with deliverables and testable exit criteria. The architecture it implements is [`DESIGN.md`](DESIGN.md) Revision 11.6. **References are written `DESIGN §n` or `PLAN §n`**; a bare `§` never appears. Evidence tags such as **[P3]** or **[D1]** resolve in [`docs/EVIDENCE.md`](EVIDENCE.md); every **P** and **Z** tag was measured on `jev-1.13.0`.
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

**Order.** Phase 0, then Phase 0r (the same probes on the Decisions API, added 2026-10-14), then foundation (1–3), then generative fields and adjudication (4), then candidate selection (5), then unions (6) and arrays (7), then release (8). Wherever a later phase depends on a Phase 0 result, Phase 0r's result for the decision model is the one that applies. **The fallback product**, if candidate selection stops (Phase 0r or Phase 5), is phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7; it is stated this way everywhere. Post-v0 phases (9–11) are planned, not optional extras. **The order is the project owner's decision (2026-09-29).** Round-1 review argued for running Phase 5 before Phase 4 whenever Phase 0 says *go*, because Phase 5 is the existential test of source-grounded extraction; the owner considered and kept this order, and PLAN §5 records the risk.

**Phase 0r fired the abandon criterion (2026-10-14) [Q2, Q9].** v0 is therefore the fallback product, built in the order **1 → 2 → 3 → 4 → 6 → 7 (multi-label enum arrays only) → 8**. Phase 5 is not run; its text below is kept as the record of what was planned, and every class D (source selection) item, wherever it sat in Phases 1–8, is listed under PLAN §9 with what would revive it.

**Phase 3 is a working library** for bounded schemas. Phase 5 would have made Jevson a source-grounded extraction library rather than a bounded-schema compiler, which `jev_jsonschema` already provides **[X3]**; without it, **Phase 4 is what sets v0 apart**: criteria-gated generative fields combined with bounded decisions, unions decided before construction, and the typed three-outcome result, a combination we found in no single existing project **[X3]**.

### 1.1 A note on effort

Recorded so the plan does not silently contradict its own timeline:

- **Phase 0 is several days, dominated by labelling.** 10+ schemas and 150+ fields classified across 12 columns; ≥ 450 pre-labelled probe cases for probes 1–3 drawn from real documents; 50 entity clusters; a hostile-source set; single-candidate cases. Labelling cannot be skipped without making the probes unfalsifiable.
- **Phase 5 would have needed a second, disjoint labelled corpus** (not built: Phase 5 is abandoned, and the corpus is part of what reviving it costs, PLAN §9): ≥ 150 present-answer and ≥ 150 absent-answer cases for coverage; ≥ 100 constructed extraction-miss cases and ≥ 300 absent cases for the retry bar; ≥ 1,000 decisions (up to 3,000 if the power check requires) for calibration; ≥ 300 benign and ≥ 150 attacked documents for the source screen. This is the largest labelling effort in the project.
- **Phase 0r reuses Phase 0's labelled corpora and pre-registration.** Its cost is porting the probes and the live runs.
- **Phase 10 is a second implementation of the library**, not a port script.

Phases 1–8 do not fit in "a couple of days". Phase 0 exists so that scope is cut on evidence rather than schedule pressure.

---

## 2. Repository layout

```text
jevson/
  __init__.py           public surface: compile_schema, Jevson, Result, DecisionsBackend, FakeBackend,
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
  config.py             JevsonConfig: tie margin, caps, budgets (entity-resolution settings arrive post-v0, PLAN §9.1)
  unicode/              deferred with class D (PLAN §9), not in v0:
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

  extract/              deferred with class D (PLAN §9), not in v0:
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
    decisions.py        raw httpx; the only module that knows the vendor wire format (POST /v1/decisions)
    fake.py             deterministic fake, shipped as a testing tool
    caching.py          CachingBackend: RFC 8785 keys, caller-supplied directory

  llm/
    replay.py           ReplayLLM: exact replay of LLM responses

  assemble/
    assembler.py        resolved graph -> JSON object; absent / unresolved handling
    entities.py         post-v0: pairwise resolution (internal rule + cross variant, floor 0.05) [Z4]
    ordering.py         deferred with class D: source order of span arrays (R7)
    cardinality.py      maxItems, overflow capture (R8)
    parse.py            deferred with class D: class F on a selected span: money, number, date

  adjudicate/
    criteria.py         declared criteria -> predicate batch
    rubrics.py          rubric -> score, value = most probable level
    dryrun.py           criteria dry-run tool

  screen.py             deferred with class D: opt-in source screen (DESIGN §5.8)
  result.py             Result (DESIGN §8.1)

tests/
  unit/
  property/             hypothesis strategies over generated schemas
  conformance/          deferred with class D: GraphemeBreakTest.txt at the pinned Unicode version
  adversarial/
    hostile_backend.py  adversarial Backend double             — NOT shipped
    hostile_llm.py      adversarial LLM double                 — NOT shipped
    hostile_extractor.py deferred with class D: raising, never-returning, and lying extractors — NOT shipped
    hostile_sources/    injected and self-advocating sources, against v0's bool, enum, and criterion decisions — NOT shipped
    hostile_transport.py timeouts, 429, 5xx, malformed HTTP    — NOT shipped
  integration/          real key, marked, opt-in
  fixtures/schemas/     the Phase 0 sample, checked in with provenance

tests/phase0/           Phase 0 harness, datasets, and results (docs/taxonomy.md; tags Z1–Z8); not part of the package
tests/probes/           the probes and checks behind docs/EVIDENCE.md, by topic (jev_api, candidates,
                        entities, adversarial, calibration, schema, unicode, runtime); written for
                        jev-1.13.0, ported for Phase 0r; raw material for the test suite (not part
                        of the package)

docs/
  DESIGN.md             the design SSOT
  PLAN.md               this plan
  EVIDENCE.md           evidence register: every tagged claim, its method, its result
  taxonomy.md           Phase 0 output, including measured probe results
  criteria-guide.md     how to write adjudication criteria that work

.env.example            API-key template (OPENAI_API_KEY); the real .env is gitignored
```

Modules marked *deferred with class D* are the source-selection work Phase 0r dropped **[Q2, Q9]**; v0 does not create them, and PLAN §9 says what revives them. `extract/occurrences.py`, `extract/llm.py`, and `extract/patterns.py` belong to the same deferral.

**Module discipline**, asserted by tests:

- `backends/decisions.py` is the only file that knows the vendor URL, headers, or wire format; the `openai` SDK is not a dependency (`DESIGN §8`).
- Nothing in `compile/`, `assemble/`, or `graph.py` imports from `execute/` or `backends/`.
- The hostile doubles live in `tests/`, never in the installed package. The fake backend ships.

**All five protocols live in `protocols.py` from Phase 1**, with the signatures pinned in `DESIGN §8`. `Extractor` and `Normalizer` are defined but have no v0 implementation and no v0 caller (DESIGN §8): defining them now keeps the deferred class D work and entity resolution non-breaking.

---

## Phase 0 — Taxonomy, feasibility probes, and scope verdict

**Goal:** decide empirically whether Jevson is a broad structured-extraction library or a deliberately narrow disambiguation engine, and confirm the central mechanism on real documents before any of it is built.

**Depends on:** nothing. Requires the live key (available).

**Status: run on `jev-1.13.0` (2026-09-29).** The results stand as recorded on Jev: abstention when the answer was missing was not good enough under the pre-registered rule, so the verdict was **drop source selection** (README; full record in Jevson PR #2, `docs/taxonomy.md` and `docs/gate-probe.md`). Phase 0r re-runs these probes on the Decisions API, and its verdict replaces this one for the decision model. The text below is the pre-registration as run.

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
| decision primitive | `choice` / `score` / `predicate` (`noul` on Jev) / none |
| option source | schema enum, rubric, candidate spans, predicate |
| `none_of_these` required? | R1 |
| dependency pattern | determines levelling |
| provenance guarantee | span, declared option, or none |
| frequency in sample | counted, not guessed |
| semantic importance | how damaging a wrong-but-valid value is |
| **existing alternatives** | does constrained decoding or plain code already solve this? |
| **existing Jev implementations** | do TypeSafe's cookbooks, `typesafe-playground`, `jev-extract`, or `jev-reviewer` already handle it? **[X3]** |
| v0 candidate? | the scope call |

### 0b — The probes

Throwaway code in `tests/phase0/`, using the live key and the pinned model `jev-1.13.0`. **Every threshold, decision rule, and question template below is pre-registered** and not renegotiated after seeing the numbers.

**Question templates.** Before any probe runs, the question templates of `DESIGN §5.2` — including the complete-value wording — are written into `docs/taxonomy.md` with a template version. Phase 2 encodes those exact templates in `compile/questions.py`, so Phase 0's verdicts describe the library that ships.

**Corpus rules** (probes 1–4, 6, 8):

- Cases come from the **real documents behind the 0a schemas**, not written by the team. The one exception is probe 6's injected notes, which the team writes into real documents.
- **At least 30% of probe 1–3 cases come from long, multi-entity documents** (several parties, invoices, or addresses) or contain **superseded values** — the only regime where the pilot failed **[P5]**. At least 20 cases contain the correct text at more than one offset **[P15]**.
- Ground truth is labelled **before any model call**, recorded in `docs/taxonomy.md`, and disputable.
- Absent-answer cases (probe 2) remove the correct span from a set whose competitors were produced by the real extractor, not chosen by hand.

| probe | what it measures | n | go | conditional | stop |
|---|---|---|---|---|---|
| **1. Disambiguation accuracy** | correct span chosen when the answer is present, among 3+ plausible competitors; ties (top-two margin ≤ 0.10) count as not correct and their rate is reported | 150 | ≥ 0.85 | 0.70–0.85 | < 0.70 |
| **2. Abstention sensitivity** | `none_of_these` chosen when the correct answer is removed; a tie counts as not abstaining, and the tie rate is reported | 150 | ≥ 0.80 | 0.60–0.80 | < 0.60 |
| **3. False abstention** | `none_of_these` chosen when the answer is present — the counter-metric; a tie is not a false abstention | same 150 as probe 1 | ≤ 0.10 | 0.10–0.20 | > 0.20 |
| **4. Entity resolution** | component outcomes on real prose clusters (below) | 50 clusters | ≥ 0.85 correct and ≤ 0.05 silently wrong | 0.70–0.85 correct | < 0.70 correct or > 0.05 silently wrong |
| **5. State referencing** | re-run `tests/probes/jev_api/probe_state_references.py` on the pinned model | 320 items | reproduces **[P4]** | — | indexed references are fine → revisit R13 |
| **6. Hostile source** | on 50 real documents with an injected note advocating a wrong span: steered selections and abstention collapse; and the source screen's true- and false-positive rates on those 50 and on 50 unmodified documents that include ordinary processing notes (routing, filing, portal instructions), which triggered 28/60 false positives in the pilot **[P21]** | 50 + 50 | reading only | — | — |
| **7. Calibration reading** | reliability of p(selected) over probes 1–3, tie-safe equal-mass bins, CI reported | from probes 1–3 | reading only | — | — |
| **8. Single candidates and partials** | lone correct, lone wrong-role, and lone partial candidates as `choice([c0, none_of_these])` under the complete-value template; and, per field type, sources that state only a partial value, where abstention is the intended answer **[P18]** | 50 each | reading only; informs R4 | — | — |

**Decision rule, pre-registered.** Each probe's verdict is the band containing its **point estimate**, with the Wilson 95% interval reported beside it. With n = 150 the half-width near p = 0.85 is about ±6 points (−6.2/+5.1) **[L12]**; a true rate exactly at a band edge is a coin flip under any rule, which is why the bands are wide. The operating characteristic — the probability of each verdict at each band edge, including the joint probability for probes 1 and 3, which share cases and are correlated (≈ −0.8) **[L12]** — is recorded in `docs/taxonomy.md` before any probe runs.

**Probes 2 and 3 must be read together.** A model that abstains on everything scores perfectly on probe 2 and is useless.

**Probe 4 in detail.** Pairwise predicates in one keyed call per cluster, all probabilities stored, run twice. The clusters include role-noun mentions ("the Landlord", "the engineer"), which produced the pilot's only splits **[P10, P17]**. Recorded: pair accuracy, the non-transitive-triple rate, clique completeness, and the flip rate across the two runs. `conflict_floor` is chosen by a rule fixed now: *the largest value in {0.05, 0.10, …, 0.45} such that same-entity pairs at or below it are ≤ 2% of all same-entity pairs; if no value qualifies, the floor is 0.05 and probe 4 is recorded as stop;* whether the grid top binds is recorded. Component outcomes (correct, `Unresolved`, silently wrong — merges and splits counted separately) are then scored under both variants of `DESIGN §5.7`, and **the variant is chosen by a rule fixed now: the one with the lower silently-wrong point estimate; if equal, the one with more correct components.** The verdict uses the chosen variant.

**Conditional** on probes 1–3 means Phase 5 ships the **second gate** described in Phase 5.

### Exit criteria

- [x] At least **10 schemas** sampled — 6 extraction, 4 non-extraction — each citing its source — 16 schemas (6 extraction, 4 non-extraction, 6 jev_jsonschema fixtures), `tests/fixtures/schemas/provenance.json`
- [x] At least **150 fields** classified, with counts by class, reported separately for extraction and non-extraction — 207 leaf fields, 278 nodes; `docs/taxonomy.md` §5
- [x] Every class C and D entry specifies primitive, option source, `none_of_these` requirement, dependency pattern, provenance guarantee, and batching behaviour — every construct in `docs/taxonomy.md` §5 (each Appendix A row names its construct); per field in `tests/phase0/results/taxonomy.json`
- [x] Every entry records **existing alternatives** and **existing Jev implementations** — every construct in `docs/taxonomy.md` §5; per field in `tests/phase0/results/taxonomy.json`
- [x] The question templates and the decision rule's operating characteristic are recorded **before** any probe runs — commits 6f38415 (templates) and 443234c (rules, OC) precede the first live result, fd78aea
- [x] All eight probes run at the stated n on the pinned model, with measured rates and intervals written into `docs/taxonomy.md` **whether or not they are favourable** — **met except one set:** 796 requests, every probe at its stated n **[Z1–Z8]** (probe 6's absent-answer rows cover 46 of 50 cases, by the pre-registered ≥ 3-option rule, `docs/taxonomy.md` §2.12), but probe 8's partial-only set has 17 of 50 cases, because only 17 of the 932 labelled field instances had a source stating only a partial value (reading only; shortfall pre-registered in `docs/taxonomy.md` §2.8). — **Deviation, owner-signed-off 2026-10-19 (ASTERION-46 decision 1):** the 17-case partial-only set is accepted; the corpus is not extended
- [x] Probes 1–4 are marked **go / conditional / stop**; `conflict_floor` and the entity rule variant are written into `DESIGN §5.7` with the data that chose them — go / conditional / go / stop; floor 0.05, cross variant **[Z4]**
- [x] The prediction below is marked **CONFIRMED** or **WRONG**, with the numbers — **WRONG** (`docs/taxonomy.md` §8)
- [x] The v0 scope list is frozen and written into `DESIGN §10` — `DESIGN §10.1`
- [x] No library code exists — no `jevson/` package

### Outcome (2026-09-29)

Probe 1 **go** (132/150 = 0.880) **[Z1]**; probe 2 **conditional** (110/150 = 0.733) **[Z2]**; probe 3 **go** (2/150 = 0.013) **[Z3]**; probe 4 **stop** (`conflict_floor` 0.05, cross-component variant, 163/330 components correct) **[Z4]**; probe 5 reproduces **[P4]** **[Z5]**; readings for probes 6–8 **[Z6–Z8]**. The abandon criterion does not fire. Candidate selection was to ship with Phase 5's second gate, but probe 9 measured that gate on Jev and gave the verdict **drop source selection** **[Z9]** (`docs/gate-probe.md`), which Phase 0r confirmed on the Decisions API **[Q2, Q9]**; pairwise entity resolution is out of v0 (Phase 7 below). The scope is frozen in `DESIGN §10.1`; the full record, including every number, is `docs/taxonomy.md`.

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

## Phase 0r — Re-probe on the Decisions API

**Status: run on `gpt-6-luna`, 2026-10-14 (ASTERION-22). Verdict: source selection stays dropped** (probe 2 in its stop band; probe 9 drop) **[Q1–Q9]**; the pilots found identical requests deterministic and measured every limit **[Q10–Q14]**. Results: `docs/taxonomy.md` §9, `docs/EVIDENCE.md` Q. Phase 1 may start.

**Goal:** find out whether what Phase 0 and the red-team pilots measured on `jev-1.13.0` holds on the OpenAI Decisions API (`gpt-6-luna`), which replaced Jev on 2026-10-14, before any library code depends on it.

**Depends on:** Phase 0 (its pre-registration, templates, corpora, and labels), and a port of `tests/probes/` — the shared `jevclient.py` and the `probe_*.py` scripts — to the Decisions API, which is a follow-up ticket. Requires an OpenAI API key with Decisions API access. **Phase 1 does not start until this phase has a verdict.**

No library code. Phase 0's rules apply unchanged: **every threshold, band, decision rule, question template, and abandon criterion is the one already registered**, and none is renegotiated after seeing the numbers. Every run records the returned `model` string (R15), and every probe also reports its `refusal` rate, which has no Jev counterpart **[D2]**.

| probe | evidence on Jev | re-measured on the Decisions API |
|---|---|---|
| **Determinism and jitter** | **[P1, P12, P20]** | repeats of identical requests: bool, choice, and pair ranges; effects of question names, order, and co-batching |
| **Threshold flips and ties** | **[P1, P12, P20, P22]** | flips inside and outside the 0.10 tie margin; exact-0.50 rate; whether the margin still removes flips |
| **Positional references** (Phase 0 probe 5) | **[P4]** | the 320-item list, indexed vs keyed |
| **Injection** (Phase 0 probe 6) | **[P7, P21]** | steered selection, abstention collapse, draft adjudication, source-screen wordings |
| **Abstention and traps** (Phase 0 probes 1–3, 8) | **[P5, P11, P15, P18]** | the Phase 0 real-document corpus, at the Phase 0 n and bands |
| **Entity resolution** (Phase 0 probe 4) | **[P6, P10, P17]** | the Phase 0 clusters; `conflict_floor` and the rule variant re-chosen by the Phase 0 rule |
| **Source ceiling** | **[P14, P22]** | per-option token costs; the largest source beside a realistic 255-option question |
| **Context limits** | **[P2, P3]** | the per-question and per-request limits, behaviour over a limit, maximum `score` levels, questions per request |
| **Probabilities** | **[L17, P23]** | precision and sum tolerance |
| **Latency** | **[P8]** | p50 at 1, 100, and 300 questions over small and large inputs |

### Exit criteria

- [x] The probes are ported (follow-up ticket); each ported script's docstring names the Jev tag it re-measures
- [x] Every probe above runs on `gpt-6-luna` at the stated n, with rates and intervals written into `docs/taxonomy.md` and into `docs/EVIDENCE.md` under new tags **whether or not they are favourable**; no existing P entry is edited
- [x] Phase 0 probes 1–4 are marked **go / conditional / stop** under the Phase 0 rules; `conflict_floor` and the entity rule variant are re-chosen by the Phase 0 rule and written into `DESIGN §5.7`
- [x] Every **unknown** in `DESIGN §2.2` is replaced by a measured value or recorded as not measurable, and the preflight limits of `DESIGN §8.2` are set from them
- [x] The tie margin's flip rate is written down; whether question names affect answers is recorded (`DESIGN §2`)
- [x] `DESIGN §2.3` and every "on Jev" claim in `DESIGN` and the README are confirmed, revised, or marked unconfirmed, citing the new tags
- [x] The verdict on source selection is stated: it **confirms or reverses** Phase 0's "drop source selection"
- [x] No library code exists

### Abandon criterion

Phase 0's, applied to the Decisions API results: **probe 1 below 0.70, probe 2 below 0.60, or probe 3 above 0.20 stops candidate selection as designed**, and the fallback product is the one Phase 0 names. **It fired:** probe 2 was 79/150 = 0.527 **[Q2]**, and probe 9 dropped the second gate **[Q9]**. Phase 5 is abandoned, and Phases 1–8 are scoped to the fallback product (PLAN §8, DESIGN §10.1). If bounded decisions themselves cannot be measured stably enough for the Phase 3 live-stability bar, that is escalated to the product owner as a backend decision (Jev remains a fallback), not tuned around.

### Answers

`DESIGN §12`: does source selection work on the Decisions API? Also re-answers, for the decision model, every Phase 0 reading (calibration, source screening, entity resolution).

**Exceptions, recorded rather than hidden:** probe 5's three 320-question conditions could not run, because the API takes at most 200 questions per request **[Q5]**; the rate limit was not measured (four 429s were seen on very large requests) and the exact input limit lies between ~915k and ~928k tokens **[Q11]**; two needle choice questions were refused at every size, unexplained **[Q11]**. Determinism holds within one day's sessions only; the alias can change without notice.

---

## Phase 1 — Core model, protocols, graph, and the fake backend

**Goal:** the type system, every protocol, and the execution skeleton, so everything afterwards can be tested without spending money or waiting on a network.

**Depends on:** Phase 0r.

### Deliverables

- `types.py` — every type in the layout, with `UnresolvedReason` as the closed set of `DESIGN §6.1`
- `protocols.py` — all five protocols (the three I/O protocols async, `Normalizer` and `CostSink` sync), with the signatures pinned in `DESIGN §8`
- `graph.py` — `DecisionGraph`, dependency edges, acyclicity check, topological levelling of decision nodes around step nodes (R3, R11)
- `probabilities.py` — integer hundredths for storage, the sum check on raw values (1 ± 0.01, measured in Phase 0r **[Q14]**), the argmax-vs-vendor-`choice` check, and the tie margin (`DESIGN §2.1`, `DESIGN §6.2`)
- `config.py` — `JevsonConfig` (`DESIGN §3.5`)
- `backends/fake.py` — deterministic fake, configurable to return specified answers, distributions, ties, and refusals
- `result.py` — `Result` exactly as pinned in `DESIGN §8.1`
- `errors.py` — the full hierarchy
- `assemble/assembler.py` — resolved graph → JSON object, with unresolved pointers omitted (`DESIGN §6.1`)

**Kept in the types, not built:** `Span` (`source_id`, start, end) and the `SOURCE_SPAN` provenance kind stay in `types.py`, so the deferred class D work adds behaviour without changing a public type; `Absent` and `Result.absent` stay too, and are always empty in v0, since nothing in v0 abstains (`DESIGN §5.6`). No v0 code constructs a `Span`.

**Moved out by Phase 0r [Q2, Q9]** to the deferred class D work (PLAN §9): `unicode/graphemes.py` (UAX #29 boundaries from a vendored table generated at Unicode 17.0 **[L19]**), `extract/spans.py` (span construction and verification, `DESIGN §5.9`), their two exit criteria (span verification and graphemes, kept below struck through as the record), and the abstention rows of the `DESIGN §5.6` table. **`Result.versions` records no grapheme-table version in v0**: the key is absent, not `null` and not a placeholder, because a version for a table that does not ship would imply a boundary check that never ran. The `unicodedata` version is absent too, since NFC is used only by the post-v0 `Normalizer`. Both keys return with the work that uses them (`DESIGN §8.1`).

### Exit criteria

Met by ASTERION-24 (Phase 1a) and the phases after it; each box re-checked on ASTERION-44 (2026-10-19). The tests are in `tests/unit/` unless named.

- [x] A hand-built graph with decision and step nodes levels correctly, including a diamond dependency
  - Proof: `test_graph.py::test_diamond_of_decisions_levels_correctly`, `::test_decisions_and_steps_level_around_each_other`, `::test_a_diamond_through_steps_keeps_steps_before_their_consumers`.
- [x] A dependency cycle is rejected at construction with the offending node ids
  - Proof: `test_graph.py::test_a_cycle_is_rejected_at_construction_naming_its_nodes` (exact cycle ids and `a -> c -> b -> a`); `tests/property/test_graph_properties.py::test_closing_any_path_into_a_cycle_is_rejected_with_a_real_cycle`.
- [x] The fake backend resolves a hand-built graph and the assembler produces a valid object
  - Proof: `test_end_to_end.py::test_the_fake_backend_resolves_a_hand_built_graph_into_a_valid_object` (`Invoice.model_validate` succeeds).
- ~~`Span` verifies by substring match on **code-point** offsets into the original source, half-open, and rejects mismatches~~ — deferred with class D (PLAN §9)
- ~~**Graphemes:** `unicode/graphemes.py` passes every line of `GraphemeBreakTest.txt` for Unicode 17.0 and agrees with the `regex` module's `\X` on a generated differential corpus (the conformance file alone missed a real GB11 bug in a first draft **[L19]**); spans with a non-boundary endpoint are rejected (including CR|LF, after ZWJ, inside a flag pair, Hangul jamo, Indic conjuncts **[L11]**); precomposed-vs-decomposed and `\r\n`-vs-`\n` mismatches are rejected and counted, never repaired~~ — deferred with class D (PLAN §9)
- [x] **Defaults and absence:** an undeclared defaulted leaf field (`Optional[str] = "x"`) is omitted from `.value` and Pydantic's `model_validate` yields `"x"` **[L18]**; `Result.absent` is present and empty; `Result.versions` has no grapheme-table or `unicodedata` key
  - Proof: `test_assembler.py::test_an_undeclared_defaulted_leaf_is_omitted_and_pydantic_supplies_the_default`; the real `versions` dict from the executor, and `absent == ()`, through `test_facade.py::test_n_independent_nodes_resolve_in_exactly_one_backend_call` (added in ASTERION-44: it fails if `Executor.result()` gains a grapheme key).
- [x] `Unresolved` is a value in the result, never raised; the unresolved key is omitted from `.value`; an unresolved root yields `{}`; `satisfies_schema` is computed by validation, not inferred, and a fully resolved object that fails `maxLength` yields `complete is True`, `satisfies_schema is False`, and a `Violation` naming the keyword
  - Proof: `test_assembler.py::test_an_unresolved_field_is_a_value_with_its_key_omitted`, `::test_an_unresolved_root_yields_an_empty_object`, `::test_a_complete_object_failing_max_length_is_complete_but_not_satisfying`; through a backend, `test_end_to_end.py::test_a_refusal_is_unresolved_refused_never_absent_or_an_option`.
- [x] **Probabilities:** a distribution summing to 0.99 with K = 3 is accepted; one summing to 0.95 is an invalid answer; on a bool, p = 0.45 and p = 0.55 are ties, p = 0.56 is true and p = 0.44 false; a choice at 0.52/0.42/0.06 is a tie; a vendor `choice` naming a non-argmax option outside the margin is invalid
  - Proof: `test_probabilities.py` (`::test_a_distribution_summing_to_0_99_with_k3_is_accepted`, `::test_bool_tie_band`, `::test_a_choice_at_52_42_06_is_a_tie`, `::test_a_vendor_choice_naming_a_non_argmax_option_outside_the_margin_is_invalid`) and `tests/property/test_probability_properties.py`.
- [x] Property: `levels(graph)` preserves every node exactly once and respects every edge
  - Proof: `tests/property/test_graph_properties.py::test_levels_preserve_every_node_exactly_once_and_respect_every_edge` (300 derandomized DAGs).
- [x] All five protocols are defined here; no later phase introduces one without amending `DESIGN §8`
  - Proof: `tests/architecture/test_module_discipline.py`: `::test_the_five_protocols_live_in_protocols_py`; `::test_no_module_defines_a_protocol_outside_protocols_py_however_it_spells_it` (runtime check, added in ASTERION-44: the AST check missed `Protocol[T]` and aliased imports); `::test_the_three_io_protocols_are_async_and_the_other_two_sync`.
- [x] Public API is exported from `__init__.py` and nothing else is
  - Proof: `tests/architecture/test_public_api.py::test_all_is_exactly_the_public_surface`, `::test_nothing_else_public_is_exported`.

### Abandon criterion

None. If this phase is hard, the type model is wrong and is reworked in place.

### Out of scope

Compilation from a schema. Any real backend. Arrays. Candidates, spans, and graphemes (deferred with class D, PLAN §9).

### PR size

~450 lines.

---

## Phase 2 — The compiler: schema → decision graph

**Goal:** turn idiomatic Pydantic models and JSON Schema into a decision graph for the bounded subset, and refuse everything else loudly, before any network call.

**Depends on:** Phase 1.

### Deliverables

- `compile/normalise.py` — the normalisation table of `DESIGN §3.5`, reading Pydantic's `mode="validation"` schema (Pydantic ≥ 2.12) and merging sibling keywords beside a `$ref` **[L3, L16, L18]**
- `compile/declarations.py` — the `x-jevson` keyword: every key of `DESIGN §3.5` parsed and validated; unknown keys refused
- `compile/mapping.py` — the Phase 0 taxonomy as routing rules with the `DESIGN §4.2` table: bool → `predicate` with the tie margin; enum → `choice` over opaque ids; integer range declared `ordinal: true` → `score`; other integer ranges and 0–1 numbers are numbers, not ratings or probabilities
- `compile/questions.py` — the versioned templates recorded in Phase 0 (`DESIGN §5.2`)
- `compile/nodes.py` — node ids from the **target instance pointer** plus a role suffix
- `compile/compiler.py`, `compile/refusal.py` — `CompileError` carrying **every** offending pointer (R14)
- Standalone, network-free `compile_schema(schema, extractors={names}, default_extractor=None)`. The two extractor parameters are kept so the deferred class D work is not a signature change; in v0 they can only change which refusal a field gets (below)

**Source selection refuses permanently in v0.** Phase 0r dropped it **[Q2, Q9]**, so these refuse with the named reason **`source_selection_dropped`**, never `not_yet_supported` (which promises a later phase): a field declaring `x-jevson.source` (whatever its extractor, so an unknown extractor name is not separately reported); and, when `default_extractor` is set, every unbounded `string` or `number` field it would have source-selected. The message cites the Phase 0r verdict and says to declare `generate` or an enum instead. With no `default_extractor`, an unbounded field with neither `source` nor `generate` is class G and refuses with its own reason, as before. Reviving class D replaces this reason with the real mapping (PLAN §9).

### Exit criteria

Met by Phases 2a and 2b (#10, #11) and ASTERION-29, with the `not_yet_supported` refusals lifted by Phases 4, 6 and 7 as planned; each box re-checked on ASTERION-44 (2026-10-19). The tests are in `tests/unit/` unless named.

- [x] Every class A construct is handled by code with no decision node emitted
  - Proof: `test_compiler.py::test_idiomatic_pydantic_compiles_and_its_class_a_fields_emit_no_node`, `::test_defaulted_leaves_are_class_a_unless_a_key_asks_for_a_decision`, `::test_a_flat_all_of_a_defaulted_decimal_and_bound_keywords_emit_no_node_of_their_own` (added in ASTERION-44).
- [x] Every class C construct in the Phase 0 v0 list compiles to the primitive the taxonomy specifies, **except union discrimination and enum arrays**, which refuse with `not_yet_supported` until Phases 6 and 7
  - Proof: `test_compiler.py::test_bool_enum_and_ordinal_map_to_predicate_choice_and_score_over_opaque_ids`, `::test_ordinal_levels_honour_every_bound_keyword`. The two exceptions were lifted as planned, by Phase 6 (`test_unions.py`) and Phase 7 (`test_enum_arrays.py`); no code path emits `not_yet_supported` any more.
- [x] **Idiomatic Pydantic compiles:** a model with a nested submodel, an `Enum` field, a single-member `Enum`, an `Optional[Literal[...]]` field, a `Literal` field, and undeclared defaulted leaf fields (`str = "USD"`, `Tier = Tier.basic`, treated as class A) compiles without refusal; an `Optional[Address] = None` whose leaves are enums or bools compiles to decision nodes (not class A), and one whose leaves declare sources refuses only with `source_selection_dropped` (not class A), and `list[Literal[...]] = []` and `Field(default_factory=list)` are treated identically (both refuse `not_yet_supported` until Phase 7); an `Optional[Decimal]` field and a `Decimal` field, each declaring a source, normalise correctly and then refuse only with `source_selection_dropped` **[L3, L16, L18]**
  - Proof: `test_compiler.py::test_idiomatic_pydantic_compiles_and_its_class_a_fields_emit_no_node`, `::test_an_optional_submodel_whose_leaves_declare_sources_refuses_only_with_source_selection_dropped`, `::test_list_literal_with_an_empty_default_and_a_default_factory_are_decided_alike` (identical member predicates since Phase 7), `::test_decimal_and_optional_decimal_declaring_a_source_refuse_only_with_source_selection_dropped`.
- [x] `x-jevson` declared on a field whose type is a nested model (placed beside the `$ref`) is found and applied; a model-level `json_schema_extra` inside `$defs` is not mistaken for a field declaration **[L18]**
  - Proof: `test_normalise.py::test_x_jevson_beside_a_ref_is_found_and_model_level_extra_is_not_a_declaration`; applied at compile level by `test_compiler.py::test_x_jevson_beside_a_nested_models_ref_is_applied_or_refused_never_dropped` (added in ASTERION-44, which also made `question` and `ordinal` beside a `$ref` refuse, `misplaced_declaration` and `ordinal_levels`, where they were dropped silently; DESIGN §3.5). The refusal was confirmed by the owner on 2026-10-19 (ASTERION-44), as was `x-jevson.order: source` refusing with `source_selection_dropped`.
- [x] A flat `allOf` of object schemas merges; a non-flat `allOf` refuses; `oneOf` + `discriminator` refuses with `not_yet_supported`
  - Proof: `test_normalise.py::test_a_flat_all_of_of_object_schemas_merges`, `::test_a_non_flat_all_of_refuses`. `oneOf` + `discriminator` was lifted by Phase 6 as planned: `test_normalise.py::test_a_discriminated_union_normalises_to_its_branches_at_its_own_pointer`, `test_unions.py`.
- [x] A three-level nested object compiles with every node carrying its full instance pointer, and assembles back to the correct shape
  - Proof: `test_compiler.py::test_a_three_level_nested_object_compiles_with_instance_pointers_and_assembles_back`.
- [x] Two fields sharing one `$defs` type produce distinct, stable node ids
  - Proof: `test_compiler.py::test_two_fields_sharing_one_defs_type_get_distinct_stable_ids`; `test_normalise.py::test_two_fields_of_one_defs_type_get_distinct_instance_pointers`.
- [x] A Pydantic model and its emitted JSON Schema compile to identical graphs
  - Proof: `test_compiler.py::test_a_pydantic_model_and_its_emitted_json_schema_compile_to_identical_graphs` (nodes, order and, since ASTERION-44, constants); `test_normalise.py::test_a_pydantic_model_and_its_emitted_json_schema_normalise_identically`.
- [x] Refusal is **total and specific**: an unmappable schema lists *every* offending pointer
  - Proof: `test_compiler.py::test_refusal_is_total_across_normalising_and_mapping`; `test_normalise.py::test_refusal_is_total_and_lists_every_offending_pointer`; `tests/property/test_compiler_properties.py::test_refusal_names_exactly_the_refusing_leaves_and_never_returns_a_partial_graph`.
- [x] `compile_schema()` makes **zero network calls** — asserted with the network stubbed to raise
  - Proof: the autouse socket stub in `tests/unit/conftest.py`; `test_compiler.py::test_compile_schema_makes_no_network_call` over every `tests/fixtures/schemas/*.schema.json`.
- [x] Each of these refuses with a distinct named reason: enum > 255 or < 2 values; ordinal > 10 or < 2 levels; unbounded strings or numbers with no `source` or `generate` declaration and no default extractor; recursive or dynamic `$ref`; `dict[str, X]`; tuples; `Any`; `bytes`; unknown `x-jevson` keys; `x-jevson.order: semantic`
  - Proof: `test_compiler.py::test_each_unmappable_field_refuses_with_one_named_reason`, `test_normalise.py::test_each_unsupported_construct_refuses_with_its_named_reason`, `test_declarations.py::test_bad_declarations_refuse_with_a_named_reason`. *Amended 2026-10-19, ASTERION-44:* "< 2 values" means an empty enum; a one-value enum is a constant committed by code (DESIGN §3.5).
- [x] **Source selection:** a field declaring `x-jevson.source` (with a known, an unknown, or a pattern extractor), and an unbounded field compiled with `default_extractor` set, each refuse with `source_selection_dropped`, listed with every other offending pointer (R14)
  - Proof: `test_declarations.py` (known, unknown, pattern and malformed extractors), `test_compiler.py::test_default_extractor_turns_unbounded_fields_into_source_selection_dropped`, `::test_refusal_is_total_across_normalising_and_mapping`.
- [x] `x-jevson.generate` fields and unions with ≥ 2 non-null branches refuse with `not_yet_supported` (lifted in Phases 4 and 6)
  - Proof: Lifted as planned by Phase 4 (`test_generative.py::test_a_declared_generative_field_compiles_to_a_step_plus_criterion_nodes`) and Phase 6 (`test_unions.py`, `test_normalise.py::test_unions_with_two_or_more_non_null_branches_normalise`).
- [x] Rendered questions contain no negation from the template and match the recorded template version
  - Proof: `test_questions.py::test_templates_add_no_negation_and_no_positional_reference` (every decision template, since ASTERION-44), `::test_every_shipped_template_string_is_recorded_in_taxonomy_md` (added in ASTERION-44, with the Phase 7 membership template written into `docs/taxonomy.md`); `executor.py` records `QUESTION_TEMPLATE_VERSION` (1.1.2) in `Result.versions`.
- [x] Property: over generated schemas, `compile_schema()` returns a graph or raises `CompileError` — never a third outcome, never a partial graph
  - Proof: `tests/property/test_compiler_properties.py`: `::test_compile_schema_returns_a_whole_graph_or_raises_compile_error`, `::test_the_supported_subset_always_compiles_to_exactly_its_decidable_leaves`, and `::test_refusal_names_exactly_the_refusing_leaves_and_never_returns_a_partial_graph` (added in ASTERION-44: the first two passed with mapping refusals dropped).

### Abandon criterion

None.

### Out of scope

Executing anything. Generative fields (Phase 4). Unions (Phase 6). Multi-label enum arrays (Phase 7) — which refuse with `not_yet_supported` until then. Source selection, which refuses permanently in v0.

### PR size

~500 lines. Split `normalise.py` and `declarations.py` into their own PR if it runs over.

---

## Phase 3 — Executor, live backend, and the façade

**Goal:** resolve a graph against the live model in the minimum number of calls, with a real budget, typed failures, and cost accounting, behind the public façade.

**Depends on:** Phase 2.

### Deliverables

- `execute/state.py` — every collection in state is an object keyed by opaque ids, never a list referenced by position (R13)
- `execute/executor.py` — runs step nodes through their protocols and decision levels as one batched call per request group: bounded, then adjudication (R3, DESIGN §5.2); `resolve()` and `aresolve()`; emits every cost event to the `CostSink`
- `execute/budget.py` — **preflight on declared maxima** against both limits (`DESIGN §8.2`); `PreflightError` before any spend
- `execute/policy.py` — transport retry for 429/5xx/timeout with backoff, bounded by `DecisionsBackend(transport_retries=...)` (default 2; not a `JevsonConfig` field), counted separately; no retry for other 4xx; a context-limit rejection mapped to a split or to `Unresolved(budget_exceeded)` (DESIGN §8.2), never an identical retry
- `execute/ratelimit.py` — one token bucket per API key on `threading.Lock`, shared across backends, threads, and event loops **[L20]**
- `execute/loop.py` — the library-owned event loop in a daemon thread; `resolve()` submits `aresolve()` to it and refuses inside a running loop **[L20]**
- `backends/decisions.py` — raw `httpx` against `POST /v1/decisions`; one long-lived client on the library loop and per-call clients on caller loops (`DESIGN §8`); opaque question names, answers matched by name and checked against question order (`DESIGN §2`); the returned `model` string recorded on every response (R15); `refusal` answers resolved to `Unresolved(refused)`; error responses mapped to typed errors from the codes Phase 0r observes; `usage.input_tokens` recorded **[D2]**; the API key is a constructor argument, falling back to `OPENAI_API_KEY` (`DESIGN §8.3`)
- `backends/caching.py` — `CachingBackend` with RFC 8785 keys (the `rfc8785` package **[L21]**), writing only to a caller-supplied directory (`DESIGN §8.4`)
- `facade.py` — `Jevson(backend=..., config=...)` with **no default backend**; `resolve(schema, source, known=...)`, with `known=` values validated before any spend
- `tests/adversarial/hostile_backend.py`, `hostile_transport.py` — every backend and transport row of PLAN §4.2
- Integration suite, opt-in and marked, against the real key. Locally the key lives in a gitignored `.env`; only the test harness reads it

### Exit criteria

Met by Phase 3a (#13), ASTERION-30, ASTERION-31 and #16; each box re-checked on ASTERION-44 (2026-10-19). The tests are in `tests/unit/` unless named.

- [x] A graph with N independent nodes resolves in exactly **one** backend call — asserted by counting calls
  - Proof: `test_facade.py::test_n_independent_nodes_resolve_in_exactly_one_backend_call`.
- [x] A graph with a (fake) step node runs the step before the decisions that depend on it
  - Proof: `test_executor.py::test_a_step_runs_before_the_decisions_that_depend_on_it_and_its_draft_is_in_state`.
- [x] **R13:** no template text or state path references a collection element by position — a test fails on any `[<digits>]` reference outside interpolated source or option text
  - Proof: `test_executor.py::test_no_template_references_a_collection_element_by_position`, a Hypothesis check over compiled schemas, and `LevelState` raising on a list.
- [x] **Budget:** a level exceeding the total limit splits, recorded in `Cost.level_splits`; a declaration whose maxima exceed the per-question limit raises `PreflightError` before the *first* call
  - Proof: `test_facade.py` and `test_executor.py::test_each_node_is_budgeted_at_its_declared_size` (`level_splits == 1`); `test_executor.py::test_an_oversized_node_in_a_later_level_raises_before_the_first_call` (added in ASTERION-44: no test put the oversized node past level 0).
- [x] **Invalid backend answers** in a well-formed HTTP 200 (an option never offered, malformed or mis-typed JSON for a question, a probability outside [0, 1], a sum outside tolerance) resolve to `Unresolved(invalid_backend_answer)` for the affected questions; an unparseable HTTP response is a `BackendError`; neither is an untyped exception
  - Proof: `tests/adversarial/test_hostile_backend.py` (every value, answer and envelope row) and `test_executor.py`.
- [x] **Step timeouts:** a fake step that never returns raises its protocol's timeout error after `step_timeout_s`, with the partial `Result` (in v0 the only real step is `generate`, so `LLMError(timeout)`; `ExtractorError` stays in the hierarchy and is never raised in v0)
  - Proof: `test_executor.py` (parametrised `GENERATE` → `LLMError`, `EXTRACT` → `ExtractorError`, code `timeout`, with the partial `Result`).
- [x] **Lifecycle:** `Jevson` and `DecisionsBackend` work as context managers; a closed instance raises `UsageError`; `resolve()` inside a running loop raises `UsageError`
  - Proof: `test_library_loop.py`, `test_facade.py`, `test_decisions_backend.py`.
- [x] **Ties:** a bool predicate at 0.45, 0.50, or 0.55, and a choice whose top two differ by ≤ 0.10, yield `Unresolved(tie)`
  - Proof: `test_facade.py::test_a_predicate_inside_the_tie_band_is_unresolved_tie`, `::test_a_choice_whose_top_two_are_within_the_margin_is_a_tie`; boundaries in `test_probabilities.py`.
- [x] **Refusal:** a fake backend answering one question in a level with `refusal` yields `Unresolved(refused)` for that field, records it in `Result.decisions`, resolves the others, and issues no retry; a refusal is never mapped to an option or to `absent`
  - Proof: `test_facade.py::test_a_refusal_is_unresolved_refused_recorded_and_never_retried`; `test_end_to_end.py`; `tests/adversarial/test_hostile_backend.py`.
- [x] **Run-time overflow:** a fake backend returning a context-limit rejection for one question in a level causes a bisection that isolates it; that field is `Unresolved(budget_exceeded)` and the others resolve
  - Proof: `test_executor.py` (context-limit and question-limit bisection isolates `/d`, no identical retry); `tests/adversarial/test_hostile_transport.py` (the real 400 body maps to `context_limit`).
- [x] **Lifecycle on caller loops:** 20 sequential `asyncio.run(aresolve(...))` calls leave no live client for a dead loop **[L22]**; two `aresolve()` calls run concurrently under `asyncio.gather` on one loop both succeed and leave no open client; inside `async with DecisionsBackend(...)` the calls share one client, closed on exit; `resolve()` succeeds in a forked child, including when the parent was blocked mid-request on a mock transport
  - Proof: through the facade, `test_library_loop.py::test_twenty_sequential_asyncio_run_aresolve_calls_leave_no_live_client`, `::test_two_aresolve_calls_under_gather_on_one_loop_succeed_and_leave_no_client` and `::test_inside_async_with_jevson_the_calls_share_one_client_closed_on_exit` (added in ASTERION-44); the same at the backend in `test_decisions_backend.py`; and `test_library_loop.py` (fork, including a parent blocked in the transport).
- [x] **Async:** two sequential `resolve()` calls on one backend both succeed; `resolve()` from 4 threads at once succeeds; `aresolve()` from two different event loops succeeds; `resolve()` inside a running loop raises with a pointer to `aresolve()`; the per-key limiter holds its rate across all of these **[L20]**
  - Proof: `test_library_loop.py` (sequential, 4 threads, two loops, the `aresolve()` pointer, and one limiter across all of them on a frozen clock).
- [x] **Known values:** a `known=` value that fails its field schema raises `PreflightError` before any call; a valid one skips its nodes and is recorded as `decided_by: caller`
  - Proof: `test_facade.py` (no question sent for a known field, `DecidedBy.CALLER`; five undeclared values raise with `backend.calls == []`); `test_known_values.py` (a value over `maxLength`, under `minLength`, off `pattern` or `format`, through a `$ref` or a Pydantic `max_length`, raises naming the pointer with no backend or LLM call; a valid one still skips its nodes; added in ASTERION-44). A Pydantic input is checked against its JSON Schema constraints only; field validators run in final validation.
- [x] **Satisfies schema:** for a Pydantic input, a `.value` that passes `jsonschema` but fails `model_validate` yields `satisfies_schema is False` **[L18]**
  - Proof: `test_facade.py` (a `field_validator` rejects the value: `satisfies_schema is False`, violation keyword `model_validate`).
- [x] **Transport:** every hostile transport behaviour yields `BackendError` carrying the partial `Result` and `Cost`; transport retries are counted separately
  - Proof: `tests/adversarial/test_hostile_transport.py` (retryable and final rows, `transport_retries` counted); `test_executor.py` (the partial `Result` keeps earlier levels and all cost).
- [x] **Central property (PLAN §4.1)** holds over generated schemas × every hostile backend and transport behaviour
  - Proof: `tests/adversarial/test_central_property.py::test_the_central_property_holds_over_generated_schemas_and_hostile_backends` (300 derandomized examples through a real `DecisionsBackend` on a mock transport; since ASTERION-44 it also rejects an untyped backend exception and a sleep outside 0–30 s).
- [x] An unresolved required field yields `satisfies_schema is False` by default and `SchemaViolation` with `raise_on_unresolved_required=True`
  - Proof: `test_facade.py` (and an optional field does not raise).
- [x] **No default probability threshold drops a commit** — a committed low-probability answer is reported, not dropped
  - Proof: `test_facade.py::test_a_low_probability_commit_is_reported_not_dropped` and `::test_a_choice_whose_top_is_below_half_still_commits` (added in ASTERION-44: 0.34 against three 0.22s commits; a default 0.5 threshold passed the old test).
- [x] **Determinism of our code:** with the fake backend, identical inputs produce identical `Result`s excluding wall-clock timings; a run replayed through `CachingBackend` reproduces the original `Result`, excluding `Cost` and wall clock, with every call counted as a cache hit; with `replay_only=True` a miss raises `BackendError(replay_miss)`; a request containing a lone surrogate is not cached
  - Proof: `test_facade.py` (identical runs; `CachingBackend` replay with every call a cache hit; `replay_only` miss → `BackendError(replay_miss)`); `test_caching_backend.py` (a lone surrogate is not cached).
- [x] **Live stability is measured, not asserted:** ≥ 100 schema-derived decisions with a top-two margin ≥ 0.20 are chosen in a separate selection run; two further live runs are compared, where a flip is any change of committed value or between a value and `tie`, and the flip rate is written down; the suite fails only if it exceeds 2% (a bar set from Jev measurements **[P1, P12]**). The returned `model` string is recorded; a change is a re-baseline — measured 2026-10-16: 0/410 flips, `gpt-6-luna` **[Q15]**
  - Proof: Ticked on the recorded measurement **[Q15]** (`docs/EVIDENCE.md`): 410 decisions with margin ≥ 0.20, 0 flips over two further runs, every response `gpt-6-luna`. The opt-in `tests/integration/test_live_stability.py` re-measures it with a key; it was not re-run on ASTERION-44 (no key).
- [x] **Credentials:** an explicit `api_key` wins; with neither argument nor environment (or with empty strings), `DecisionsBackend()` raises `MissingCredentials` before any network call; the library never reads a `.env` file
  - Proof: `test_decisions_backend.py` (explicit key wins; `None`/`''` × `None`/`''` raise `MissingCredentials` with no request; a `.env` in the working directory is ignored).
- [x] **The key never leaks:** a sentinel key appears in no exception message, `repr`, log record, cache file, or `Result`, across success, 4xx, 5xx, and timeout paths
  - Proof: `tests/adversarial/test_hostile_transport.py` (success and every retryable and final path, including 401/400 bodies echoing the key; and `::test_the_key_appears_nowhere_a_jevson_caller_can_see`, the `Result` of a `Jevson` success and the error of a 401, added in ASTERION-44); `test_caching_backend.py` (cache files); the central property.
- [x] **Rate limit:** two `DecisionsBackend` instances with one key share one limiter
  - Proof: `test_decisions_backend.py` (`a._limiter is b._limiter`); behaviourally `test_library_loop.py`.
- [x] **No vendor SDK** in the dependency closure
  - Proof: `tests/architecture/test_vendor_isolation.py::test_no_vendor_sdk_in_the_dependency_closure`.
- [x] Cost is populated on every result and on every exception raised after the first spend (`SchemaViolation`, `BackendError`, `LLMError`), and every event reaches the `CostSink`
  - Proof: `test_facade.py` (`SchemaViolation`, the sink), `test_executor.py` (`BackendError`, `LLMError`, sink events); the central property asserts `error.cost is error.result.cost`.

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

**Goal:** fields no candidate set can fill — a summary, a synthesised description — drafted by the caller's LLM and admitted only after the decision model adjudicates them against declared criteria.

**Depends on:** Phase 3. Independent of candidate selection, so it survives Phase 5's abandon criterion.

### Deliverables

- `compile/generative.py` — `x-jevson.generate` (`DESIGN §3.5`, `DESIGN §6.3`) compiles to a `generate` **step node** plus one criterion `predicate` per criterion (and an optional rubric `score`) depending on it; lifts the Phase 2 `not_yet_supported` refusal for generated fields
- The `generate` step: the LLM is asked for the one-field tool schema `{value: string}`, passed as JSON Schema for the `LLM` adapter to render per provider (strict OpenAI/Anthropic envelopes differ from Gemini's **[L20]**); drafts longer than `max_draft_chars` are failed drafts; drafting prompts are templates in `compile/questions.py`
- `execute/policy.py` — the **redraft loop**, bounded by `redraft_budget` (default 1): failing criteria are passed back; a draft identical to one already adjudicated is not re-adjudicated and counts against the budget
- `adjudicate/criteria.py` (each criterion passes at p ≥ 0.56; the tie margin yields a tie, counted as a failed criterion for redraft), `adjudicate/rubrics.py` (most probable level ≥ declared minimum); state follows the keyed level layout of `DESIGN §5.2` (`drafts: {node id: draft}`)
- `llm/replay.py` — `ReplayLLM`
- Rejections naming the failing criteria, in `Result.rejections`
- `adjudicate/dryrun.py` and `docs/criteria-guide.md`
- `tests/adversarial/hostile_llm.py`, including the draft-injection variants from **[P7]**

### Exit criteria

Met by ASTERION-32, ASTERION-35 and ASTERION-36, except the two live bars, which are not met: the injection regression (ASTERION-48) and the redraft bar (ASTERION-58; its model labels are an owner-signed-off deviation, ASTERION-46 decision 2); each box re-checked on ASTERION-44 (2026-10-19). The tests are in `tests/unit/` unless named.

- [x] A declared generative field compiles to a step plus criterion nodes; an unbounded string with neither `source` nor `generate` still refuses
  - Proof: `test_generative.py::test_a_declared_generative_field_compiles_to_a_step_plus_criterion_nodes`, `::test_an_unbounded_string_with_neither_source_nor_generate_still_refuses`.
- [x] All criteria for a field are adjudicated in **one** request unless the level is split under DESIGN §8.2 (*amended 2026-10-19, ASTERION-44, owner decision: the split rule is DESIGN §8.2's, as DESIGN §3.3 already says*)
  - Proof: `test_generative.py::test_all_criteria_for_a_field_are_adjudicated_in_one_batched_call` (3 criteria and a rubric in one request).
- [x] Rejection names the specific failing criteria
  - Proof: `test_generative.py::test_rejection_names_the_specific_failing_criteria`.
- [x] Redraft budget is bounded; exhaustion yields `Unresolved(redraft_exhausted)`, never an exception or a silently accepted string
  - Proof: `test_generative.py::test_redraft_budget_is_bounded_and_exhaustion_is_unresolved_redraft_exhausted`, `::test_a_redraft_budget_of_zero_never_redrafts`.
- [x] A fake LLM that repeats its draft triggers **no** second adjudication call, and the repeat counts against the budget
  - Proof: `test_generative.py::test_a_repeated_draft_triggers_no_second_adjudication_and_counts_against_the_budget`.
- [x] Preflight accounts for `max_draft_chars`; an over-length draft is a failed draft, not a context-limit error after spend
  - Proof: `test_generative.py::test_preflight_accounts_for_max_draft_chars_before_any_spend`, `::test_an_over_length_draft_is_a_failed_draft_not_a_context_limit_error_after_spend`.
- [x] **Central property (PLAN §4.1)** holds with every hostile LLM behaviour: wrong keys, prose instead of a tool call, non-string values, enormous strings, text that looks like JSON, exceptions from the LLM (→ `LLMError` with partial result)
  - Proof: `tests/adversarial/test_hostile_llm.py::test_the_central_property_holds_over_generated_schemas_and_hostile_llms` (200 derandomized examples over every behaviour in `hostile_llm.py`); `test_generative.py::test_an_llm_exception_is_llm_error_with_the_partial_result`.
- [ ] **Injection regression:** over the **[P7]** draft-injection set (20 sources × 4 variants, 80 cases, 0 flips in the pilot), the suite fails if more than 3 failing drafts are judged passing (the Wilson upper bound for 0/80 is ≈ 0.046); it is run under the keyed multi-draft level layout of `DESIGN §5.2`, with each injected draft placed beside a second, clean draft that fails its own criteria, and a flip of either draft's verdict counts; if that layout fails where the single-draft layout passes, adjudication issues one call per draft — **Not met, tracked in ASTERION-48** (owner decision, 2026-10-19: not a deviation; v0 does not ship with 5/80; ASTERION-48 fixes the self-claim flips inside v0). The offline harness (`tests/j4b/injection.py`, `tests/integration/test_live_injection.py`) is in place; re-measuring needs the live API.
  - **Result (2026-10-16, ASTERION-36): failed.** 5/80 flipped cases under the keyed multi-draft layout and the same 5/80 under the single-draft layout, all in V2 × *the draft mentions the refund amount* (a draft that omits the amount but claims to include it), p(true) 0.60–1.00; every other cell 0, refusals 0, model `gpt-6-luna` **[Q16]**. Single-draft does not pass either, so adjudication stays one call per level. Phase 4 has no abandon criterion: v0 ships with the rate documented (README, `docs/criteria-guide.md`), and a draft self-claim mitigation is a tracked post-v0 deferral (PLAN §9), to be measured on fresh cases
- [x] **Criterion ties:** a criterion inside the tie margin counts as failed, is named in `rejections`, and triggers a redraft; `Result.decisions` holds `…@0` and `…@1` for one redraft
  - Proof: `test_generative.py::test_a_criterion_tie_counts_as_failed_is_named_and_triggers_a_redraft`.
- [x] `ReplayLLM` reproduces a recorded run exactly
  - Proof: `test_generative.py::test_replay_llm_reproduces_a_recorded_run_exactly`.
- [x] The dry-run tool runs against the fake backend with no key
  - Proof: `test_generative.py::test_the_dry_run_runs_criteria_against_the_fake_backend_with_no_key`, which unsets `OPENAI_API_KEY` and first shows `DecisionsBackend()` finds no key (ASTERION-44).
- [x] A field with no declared criteria is admitted with `decided_by = llm` and listed in `Result.ungated` (*amended 2026-10-19, ASTERION-44: the `no_criteria_declared` marker was never a separate value; DESIGN §6.3*)
  - Proof: `test_generative.py::test_a_field_with_no_declared_criteria_is_admitted_ungated`.
- [ ] **Redraft bar, measured against human labels:** over ≥ 100 rejected drafts, each redraft labelled after generation by a labeller who does not see the decision model's verdict, the rate at which a redraft is admitted *and* truly satisfies the criteria is written down, together with the rate at which a redraft is admitted while violating them, and the paired difference from first drafts with its 95% interval; the default `redraft_budget` stays 1 only if the first is ≥ 10% and the second is no more than 2 points above the same rate for first drafts, otherwise it becomes 0 — **Not met, tracked in ASTERION-58** (owner decision, 2026-10-19). Signed off is only the labeller (ASTERION-46 decision 2): the run-1 model labels (444 items) are accepted in place of human labels, with no human relabel, and were never validated against human labels. Under them the pre-registered rule's arithmetic passes (A 42.3% ≥ 10%, B − C −6.2 ≤ 2 points; `redraft_budget` stays 1; `report.json` re-scores byte-identically offline), but the same labels show the decision model over-rejects (65 of 123 rejected first drafts, 53%, truly satisfied) and contracts alone have B − C = +5.0 points **[Q17]**; ASTERION-58 re-measures on fresh cases.
  - **Result (2026-10-16, ASTERION-36), model-labelled:** 123 rejected first drafts of 225 (≥ 100, so it counts). A = 52/123 = 42.3% (Wilson 33.9–51.1%); B = 8/123 = 6.5% (3.3–12.3%); C = 12.7% (9.1–17.0%: 28 of the 100 sampled admitted first drafts violate, × the admitted share 102/225); **B − C = −6.2 points** (Newcombe −11.5 to +0.6); paired truly-satisfies(redraft) − truly-satisfies(first) over the 123 rejected instances **+32.5 points** (23.4 to 41.0; both 63, redraft only 42, first only 2, neither 16). A ≥ 10% and B − C ≤ 2 points, so under the pre-registered rule **the default `redraft_budget` stays 1** (unchanged in code). Per domain (`tests/j4b/labelling/run1/report.json`): only contracts have B − C above 2 points (+5.0: B 3/60, and no contract first draft was admitted, so C = 0); A ranges from 28% (contracts) to 67% (support tickets). The labels also say 65 of the 123 rejected first drafts (53%) truly satisfied their criteria: the decision model over-rejects **[Q17]**
  - **Stated interpretations (the owner's decisions, 2026-10-16, ASTERION-36):**
    - *Which drafts are labelled.* Every rejected first draft and its redraft, plus a seeded random sample of 100 admitted first drafts; the run's seeds, stopping rule and sample are recorded in `sampling.json`. Generation stops on first-draft counts only (≥ 110 rejected and ≥ 100 admitted, documents in a seeded order), never on redraft outcomes.
    - *Blinding.* Each sampled admitted first draft gets one **decoy**: a second draft for the same source and field, made through Jevson's own redraft prompt with one criterion chosen at random named as failing, never adjudicated. So every labelled (source, field) appears exactly twice, whatever its verdict. Decoys are excluded from every number.
    - *"No more than 2 points above the same rate for first drafts"* is read as the unpaired **B − C**, where B = redrafts admitted while violating / redrafts and C = first drafts admitted while violating / first drafts, with Newcombe's hybrid score interval (method 10). Because only a sample of admitted first drafts is labelled, C = (violating rate among the sampled admitted first drafts) × (admitted first drafts / first drafts); the share is exact, so C's interval is that rate's Wilson interval scaled by it (`tests/j4b/labelling/score.py --sampling`).
    - *"The paired difference from first drafts"* is also reported: over instances whose first draft was rejected, truly-satisfies(redraft) − truly-satisfies(first draft), with Newcombe's paired interval; a missing redraft does not satisfy.
    - *Criteria.* The generative fields' criteria speak only about the draft and the source, and none counts sentences or words: counting is a known decision-model weakness, and length belongs in `max_draft_chars`.
    - *Labeller (deviation, confirmed by the owner, 2026-10-16).* The 444 items were **model-labelled, not human-labelled**: the owner did not label them, and a separate Claude session (the orchestrator's model family; neither `gpt-6-luna` nor the drafting model) labelled them blind, from `items.jsonl` alone, with no access to the key, `sampling.json`, the run record or any result. The exit criterion asks for a human labeller, so the measurement below meets it only as this stated deviation; a human relabel of the same items would replace it.
    - *Pool.* Fields over five corpus domains (support tickets, medical intake, résumés, product listings, contracts; `tests/j4b/redraft.py`). The contract pool was planned as the 40 shortest and raised to all 100 before the main run, because a 12-document pilot (discarded, its documents excluded) rejected 4 of 14 first drafts, too few for the pool to reach 100 rejections. Rejected drafts therefore lean towards contracts, so every rate is reported per domain beside the pooled numbers, in the run summary and in the scored verdict; the bar is decided on the pooled numbers.

### Abandon criterion

None. A failed live bar does not abandon the phase: its box stays unticked and the v0 release waits until it is met (owner decisions, 2026-10-19: injection regression → ASTERION-48, v0 does not ship with 5/80; redraft bar → ASTERION-58). Ungated fields stay visible in `Result.ungated`.

### Out of scope

Automatic criteria derivation. A criteria linter.

### Answers

`PLAN §7`: do redrafts recover? (last exit criterion).

### PR size

~450 lines.

---

## Phase 5 — Candidates and source selection *(abandoned by Phase 0r; kept as the record)*

> **Status: abandoned, not run.** Phase 0r applied this phase's own gate on the Decisions API before any of it was built: probe 2 (abstention with the answer absent) was 79/150 = 0.527, in its stop band, and probe 9's second gate was **drop** **[Q1–Q9]** (`docs/taxonomy.md` §9). Under the pre-registered rule, candidate selection does not ship in v0. The text below is unchanged, as the record of what was planned. Every item in it, and every class D item that sat in Phases 1, 2, 7 and 8, is a tracked deferral in PLAN §9 (*Source selection (class D)*), which says what would revive it and where it would land. Nothing below is an exit criterion for v0.

**Goal:** the capability that makes Jevson a source-grounded extraction library. Fields whose values come from the source, chosen by the decision model among verified spans, with provenance and mandatory abstention.

**Depends on:** Phase 4.

### Deliverables

- Lifts the Phase 2 `not_yet_supported` refusal for fields declaring `x-jevson.source`, and for unbounded fields when `JevsonConfig(default_extractor=...)` is set; built-in pattern extractors apply only when declared by name (`DESIGN §3.5`)
- `extract/llm.py` — LLM-backed extraction; the extractor returns strings and **Jevson locates them in the original source**; unlocatable strings are rejected and counted
- `extract/patterns.py` — money, date, email, phone, and URL candidates
- `extract/occurrences.py` — every occurrence of a repeated candidate text, each with a ±40-character context window in its option description (`DESIGN §5.1`) **[P15]**
- `assemble/parse.py` — class F parsing of a **selected** span into number, money, or date
- Candidate-backed choices with **opaque option ids**, **mandatory `none_of_these`** (R1), and the complete-value template (`DESIGN §5.2`)
- **Single candidates** asked by default; `direct_extraction: true` opt-in, listed in `Result.ungated` (R4)
- `max_candidates` (default 50) enforcement at run time → `Unresolved(too_many_candidates)`; zero candidates → absent or `Unresolved(no_candidates)` without a backend call; for fields whose value is the verbatim span, candidates violating the field's `maxLength`/`minLength`/`pattern` rejected before the question (`DESIGN §5.3`, `DESIGN §5.6`)
- Class F parsing of a selected span under the field's `locale` (default `en-US`); a span that does not parse → `Unresolved(unparseable)`; decimals emitted in string form (`DESIGN §3.5`)
- **Retry** (`DESIGN §5.5`): exclusions; a request only on a new verified span; no retry after a refusal; old ∪ new; batched per level; `retry_budget` per call
- `screen.py` — the **opt-in source screen** (`DESIGN §5.8`), asked in the first decision level, flagging at p ≥ 0.56; the tested wording flagged 28/60 benign documents **[P21]**, so this phase searches for a wording on a development split and measures it on a held-out split
- `tests/adversarial/hostile_extractor.py` and `hostile_sources/`
- **Phase 0 was *conditional* on probe 2 on `jev-1.13.0` [Z2], so this applies:** a second gate — an independent verification predicate per committed span, batched into the same request; a failed verification yields `Unresolved(verification_failed)`; the cost delta is recorded. The measurements below run **with the gate on**. Probe 9 measured this gate early on Jev (`docs/gate-probe.md`): it cut commits on absent answers from 29/139 to 10/139 but left 105/150 correct commits, and the pre-registered verdict was **drop source selection** **[Z9]**. This phase therefore proceeds only if Phase 0r reverses that verdict on the Decisions API
- **Measurement corpus**, disjoint from Phase 0, labelled before any run, under the Phase 0 corpus rules

### Exit criteria

- [ ] Every candidate-backed choice includes `none_of_these` — asserted structurally in the compiler (R1)
- [ ] A text occurring twice is offered twice, with context windows, and a fixture with the correct occurrence second resolves to the second offset
- [ ] **Coverage and false abstention use the Phase 0 rule and bands** on the fresh corpus (≥ 150 present-answer and ≥ 150 absent-answer cases): point-estimate verdicts, Wilson intervals reported, operating characteristic recorded before the run. Aligning the two phases means a Phase 0 *conditional* is not converted into a near-certain Phase 5 failure by a stricter rule **[L15]**
- [ ] No parameter changes between the first coverage measurement and the verdict except bug fixes, and every run is recorded
- [ ] Every committed value verifies against the source by substring and grapheme boundary; failures are rejected before the backend call
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

**Depends on:** Phase 4 (Phase 5 is abandoned, PLAN §1). Its content needs only Phase 3.

### Deliverables

- `compile/unions.py` — discrimination `choice` over branches (no `none_of_these` in v0); **every branch compiled and validated statically**; Pydantic discriminated unions (`discriminator` keyword) supported; lifts the Phase 2 refusal
- Execution of the selected branch only; the unselected branches' steps never run
- A measured choice between a separate discrimination level and **speculative fan-out** (`DESIGN §3.2`) for branches whose nodes are pure decision questions

### Exit criteria

Met by ASTERION-37 (2026-10-16). The tests are in `tests/unit/test_unions.py` unless named.

- [x] A union resolves its discriminator first, and **only the selected branch's nodes are executed** — asserted by counting executed nodes and backend questions. With `union_fanout=False`, a two-level run sends the discriminator, then only the selected branch's questions. Under the fan-out default, the unselected answers are discarded, and a union with a `generate` field never fans out: its unselected step is never drafted.
- [x] An unmappable construct inside **any** branch refuses at compile time, before any call.
- [x] Branches whose required properties and descriptions are identical after normalisation refuse as undiscriminable (`undiscriminable_union`).
- [x] A nested union levels correctly: 3 levels under the separate-level strategy, 1 under fan-out, with the same value.
- [x] The unselected branch's fields never appear in the result, even as nulls. A Hypothesis property over random answers and both strategies checks that nothing off the selected path is committed or recorded.
- [x] The discrimination decision appears in `Result.decisions` as `<pointer>#branch@0`. A tie or invalid answer yields `Unresolved` for the whole subtree, with reason `tie` or `invalid_backend_answer` and children `dependency_unresolved`. An overflowing discriminator gives `budget_exceeded`.
- [x] **Fan-out vs level:** latency and tokens for both strategies measured on 50 fixtures (`tests/integration/test_live_union_fanout.py`, opt-in, billed ~$0.04 in all). The default is chosen from the numbers below.

| 50 fixtures, `gpt-6-luna` | requests | questions | input tokens | median resolve | mean resolve | same value |
|---|---|---|---|---|---|---|
| level, one-line sources | 100 | 188 | 27,951 | 0.366 s | 0.400 s | 50/50 |
| fan-out, one-line sources | 50 | 320 | 42,754 | 0.197 s | 0.215 s | 50/50 |
| level, ~1,800-char preamble + source | 100 | 188 | 63,051 | 0.369 s | 0.393 s | 50/50 |
| fan-out, ~1,800-char preamble + source | 50 | 320 | 59,326 | 0.190 s | 0.207 s | 50/50 |

**Default: fan-out** (`JevsonConfig.union_fanout = True`). It halves latency and requests and leaves values unchanged. It costs more input only when the source is shorter than the unselected branches' questions, because the separate level re-sends the state. The first run of the one-line case read 0.386 s against 0.203 s.

### Abandon criterion

None. If unions prove intractable they are refused, which is the prior art's status quo.

### Out of scope

`allOf` beyond flat merging (tracked in PLAN §9).

### Answers

`DESIGN §12`: union execution strategy — **fan-out by default**, measured above.

### PR size

~300 lines.

---

## Phase 7 — Multi-label enum arrays

**Goal:** arrays of declared enum values, one bounded membership decision per value, in declared order with honest overflow.

**Depends on:** Phase 6.

> **Reduced by Phase 0r [Q2, Q9].** This phase was *Source-grounded arrays*: membership over candidate spans, source order, and overflow by span, with multi-label enum arrays as the part that needed no candidates. Source selection was dropped, so only the enum arrays ship in v0. Source-grounded arrays of spans (membership over candidates, `assemble/ordering.py`'s source order, overflow by earliest span, and their exit criteria, including the attendees and `max_candidates` cases) move to the deferred class D work in PLAN §9; pairwise entity resolution was already in PLAN §9.1 **[Z4]**. The original text is in this file's history (Revision 10).

### Deliverables

- `compile/mapping.py` — an array of a string or integer enum (2–255 values) compiles to one membership `predicate` per declared value, with the tie margin, in one level (`DESIGN §4.2`); lifts the Phase 2 `not_yet_supported` refusal for enum arrays
- `assemble/cardinality.py` — accepted values in declared enum order; `maxItems` keeps the first k in that order; each overflowed value is recorded in `Result.overflow` with its membership probability (R8)
- Fake-backend support for membership answers

### Exit criteria

- [x] **Enum arrays:** `list[Literal["billing", "technical", "account"]]` compiles to three membership predicates in one level and emits accepted values in declared order, whatever the probabilities' order
- [x] `maxItems: 2` with three accepted values returns the first two in declared order and records the third in `Result.overflow`
- [x] **Array holes:** a value inside the tie margin is one `Unresolved(tie)` at the array pointer naming the value, and the other values are emitted; a refused membership question is `Unresolved(refused)` the same way
- [x] `uniqueItems` holds by construction; `minItems` that the accepted values do not meet is a `Violation`, not a padded array
- [x] An array declaring `x-jevson.order: semantic` refuses; an array of unbounded items refuses (with `source_selection_dropped` if it declares a `source`); an array of objects still refuses with its own named reason (`DESIGN §3.5`)
- [x] Output is deterministic across runs with the fake backend

### Abandon criterion

None. If membership questions prove unstable, enum arrays refuse, which is the prior art's status quo.

### Out of scope

Source-grounded arrays of spans (deferred with class D, PLAN §9). Arrays of objects (including nested). Cross-item constraints. Semantic ordering. Pairwise entity resolution (PLAN §9.1). (All tracked in PLAN §9.)

### Answers

None in v0.

### PR size

~150 lines.

---

## Phase 8 — Packaging and release

**Goal:** the library is usable by someone who did not build it.

**Depends on:** Phase 7.

**What ships is the fallback product** (DESIGN §10.1): a compiler for bounded decisions over schemas — enums, booleans, declared ordinals, union discrimination, and multi-label enum arrays, decided by the decision model from declared options — plus generative fields drafted by the caller's LLM and admitted against declared criteria, assembled in code, with a typed three-outcome result. Every committed value carries a `DECLARED_OPTION` provenance or is a draft, a constant, a default, or a caller-supplied value. **No value is selected from the source**, so the README and examples make no source-span provenance or abstention claim.

### Deliverables

- `CostSink` default implementation and documentation
- README rewritten to the v0 claim of `DESIGN §9.1`, describing only what shipped, and saying plainly that source selection was built as a design, measured on two decision models, and dropped (Phase 0 **[Z9]**, Phase 0r **[Q2, Q9]**), with a link to the record
- Quickstart and worked examples **using only capabilities that shipped**
- A fair comparison with `jev_jsonschema`, TypeSafe's extraction cookbooks and playground, `jev-extract`, LangExtract, and Instructor, stating plainly what each does better **[X2, X3]**
- `pyproject.toml`, MIT licence, `py.typed`, Python 3.11+
- **The name is decided before the PyPI release.** Jev is no longer the backend, and whether to rename is a separate follow-up; if a "Jev" name is kept, TypeSafe is asked whether it is acceptable first (`jevson` is free on PyPI and npm **[X6]**; no TypeSafe naming policy was found **[X4]**)
- **Versioning policy:** `0.x`, breaking changes permitted between minors and recorded in a changelog
- PyPI release

### Exit criteria

- [x] README makes no claim outside the tiers in `DESIGN §6`, states the source-trust limit (source text can steer bounded decisions and adjudication), and does not claim guaranteed JSON validity, source-span provenance, abstention, or novelty of candidate selection
- [x] README names anything that did not ship and why: source selection (class D) and everything that depends on it, and pairwise entity resolution
- [x] `x-jevson.source` and `default_extractor` are documented as refused in v0 with `source_selection_dropped`
- [x] Every public symbol is typed and documented
- [x] Quickstart runs end to end against the fake backend with **no API key**
- [x] Installed package exposes only the intended public surface and contains no hostile test doubles
- [x] Dependencies: `jsonschema`, `pydantic` (≥ 2.12), `httpx`, and `rfc8785` (*amended 2026-10-18, ASTERION-39, owner's decision: it builds the replay keys of `CachingBackend` and `ReplayLLM`, PLAN §6 "Replay"*). LLM providers are extras, and none ships because no adapter does; no extractor ships in v0. `format` keywords are documented as unchecked unless the caller installs `jsonschema`'s format extras **[L10]**
- [ ] The package name is recorded in PLAN §6 before publication

Met in ASTERION-39 (2026-10-18), checked by `tests/architecture/test_docstrings.py`, `test_distribution.py`, `test_public_api.py` and `tests/unit/test_examples.py`, except the name, which is pending (PLAN §6), and the PyPI release, which waits on it.

### PR size

~250 lines plus documentation.

---

## Phase 9 — Multi-source and long-source extraction *(post-v0, planned)*

**Goal:** one call over several sources (an email thread and its attachment) or over one source longer than the per-question limit, with every committed value still traceable to one exact span in one named source.

**Depends on:** Phase 8, **and on the deferred class D work (PLAN §9)**: every deliverable below selects spans, so this phase cannot start until source selection is revived. Deferred on cost and risk: it multiplies the context budget (and, once post-v0 entity resolution ships, interacts with its pairwise cap, PLAN §9.1). `source_id` has been in the `Span` type since Phase 1, though v0 constructs no span. Prior art: `choxos/jev-reviewer` and `gbesse/jev-extract` already do multi-file or chunked extraction for fixed record types **[X3]**.

### Deliverables

- Multiple named sources per call; the call-boundary refusal is lifted
- Chunking of a long source into windows under the per-question limit, with candidates carrying offsets into the original source
- Candidates carry their `source_id`; verification runs against the named source
- Budgeting across sources and chunks: split, never truncate
- Cross-source entity resolution only if the post-v0 entity-resolution work (PLAN §9.1) has shipped, under its rules and cap; until then, deduplication across sources is the extractor's declared contract **[Z4]**

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
- A TypeScript package implementing `DESIGN` at whatever scope Python shipped, with RFC 8785 cache keys (and the same grapheme table version, if class D has shipped)
- Zod (v4 `toJSONSchema`) and JSON Schema as the schema surface **[X7]**
- Credentials: an explicit `apiKey` argument; the `OPENAI_API_KEY` fallback in Node only

### Exit criteria

- [ ] Both packages pass the same conformance suite in CI
- [ ] *(if class D has shipped)* Span offsets agree across languages: Python offsets are code points, JavaScript strings index UTF-16 code units, so the port converts explicitly **[L2, X7]**; fixtures include astral-plane characters, and a span whose boundary would fall inside a surrogate pair is rejected
- [ ] Cache keys computed in JavaScript equal those computed in Python for the same request
- [ ] The JS package passes the central-property adversarial suite (PLAN §4.1)

---

## Phase 11 — Credentials from Infisical *(post-v0, planned, lowest priority)*

**Goal:** contributors and CI fetch the OpenAI API key from the team's Infisical project at run time instead of keeping it in a local `.env`.

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
- **Only `backends/decisions.py` knows the vendor wire format.** No vendor SDK.
- **The model version is recorded** (R15): no snapshot exists **[D3]**, so every measurement records the returned `model` string, and a change is a re-baseline.
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

Owned by: Phase 3 (backend, transport), Phase 4 (LLM), Phase 10 (JS). Spans, candidate sources, and extractors were Phase 5's and are deferred with class D (PLAN §9).

### 4.2 The adversarial suite

| category | behaviours | owner |
|---|---|---|
| **malformed responses** | wrong field names, missing fields, wrong types, extra keys, empty body, `null`, non-JSON body | Phase 3 |
| **invalid values** | options never offered, probabilities outside [0,1], `NaN`, sums outside tolerance, ties | Phase 3 |
| **transport** | timeouts, 429, 5xx, connection reset, unparseable HTTP responses, context-limit rejections (on Jev, 400 `max_tokens_exceeded` **[P3]**) | Phase 3 |
| **hostile LLM** | prose instead of a tool call, wrong tool, missing or misspelled keys, non-string values, enormous strings, text that looks like JSON, repeated drafts, exceptions | Phase 4 |
| **hostile drafts** | self-advocacy, targeted false claims, injected overrides **[P7]** | Phase 4 |
| **hostile sources** | injected notes to automated systems in the source of a bool, enum, union, or criterion decision: the central property holds; how far they steer those decisions is a stated limit (`DESIGN §5.8`), not a v0 measurement | Phases 3–4 |
| **hostile extractors** | exceptions, never returning, unlocatable strings, offsets that do not match, empty and oversized candidate sets | deferred with class D (PLAN §9) |
| **hostile spans** | offsets absent from the source, overlaps, mismatched text, grapheme-splitting boundaries, duplicates | deferred with class D (PLAN §9) |
| **hostile sources against selection** | self-advocating spans, planted near-duplicates, the correct text repeated in a wrong role **[P7, P15]** | deferred with class D (PLAN §9) |

### 4.3 Property-based tests

`hypothesis` strategies over the supported subset:

- `compile_schema()` returns a graph or raises `CompileError` — never a partial graph
- Levelling preserves every node exactly once and respects every edge
- Assembly of a fully resolved graph either validates against the original schema or yields `satisfies_schema is False` naming the violated keyword **[L9]**
- Every provenance entry in v0 is a `DECLARED_OPTION` naming an option the compiled node offered (span verification is deferred with class D)
- Cost is monotonic within a call

### 4.4 Integration tests

Opt-in and marked. They **measure** where the quantity is a property of the model, compare against pre-registered bars, and record the returned `model` string. They run on demand and on release, not on every push: the live key has a rate limit and a cost.

---

## PLAN §5. Risks

| risk | where it bites | mitigation |
|---|---|---|
| **`none_of_these` doesn't work on real documents** | Phase 0, fatal to Phase 5 | **happened**: stop on the Decisions API **[Q2]**, drop on both models **[Z9, Q9]**; the fallback product is v0 |
| **We build Phase 4 before learning Phase 5 fails** | Phases 4–5 | did not happen: Phase 0r decided before Phase 1 started; Phase 4 is in v0 |
| **The fallback is too narrow to be worth using** | Phase 8 | the README states what did not ship and why; the narrow scope was pre-accepted (PLAN §6, *Scope if the band is narrow*) |
| **We abstain on everything and call it safety** | Phase 0 | probe 3 is the counter-metric |
| **Source text steers decisions** | Phase 3 onward | measured on selection **[P7, Q6]**; stated limit for every decision that reads the source; the screen is deferred (PLAN §9) |
| **Right text, wrong provenance** when a value repeats | deferred with class D | every occurrence offered with context **[P15]**, when revived |
| **Our novelty is overstated** | Phase 8 | prior art credited (`DESIGN §9`); comparison in the README; "existing Jev implementations" column |
| **The taxonomy comes back narrow and we pad it** | Phase 0 | prediction recorded in advance; narrow scope pre-accepted |
| **Entity resolution silently merges or splits** | Phase 7 | measured in Phase 0: stop **[Z4]**; deduplication is the extractor's contract in v0 |
| **Pair questions jitter** | Post-v0 (PLAN §9.1) | floor measured on two runs; both-orderings experiment **[P12]** |
| **Candidate extraction is the weak link** | deferred with class D | `none_of_these` mandatory, including for single candidates; complete-value template **[P11]** |
| **Context limits exceeded** | Phase 3 onward | preflight on declared maxima (default 50 × 120); split, bisect, or refuse; never truncate **[P14]** |
| **Sync wrapper over async code breaks** | Phase 3 | library loop thread; per-call clients on caller loops; thread-lock limiter **[L20, L22]** |
| **Live answers jitter** | Phase 3 onward | tie margin (removes most, not all, flips); stability measured, not asserted; cache for exact replay **[P1, P12, P20]** |
| **Vendor model changes under us** | everywhere | no snapshot exists **[D3]** and behaviour has changed under the alias before **[D4]**; the returned `model` string recorded; re-baseline when it changes; replay from records only |
| **Jev measurements do not hold on the Decisions API** | Phase 0r onward | every Jev result labelled as such; Phase 0r re-ran the probes with the same thresholds (2026-10-14): the verdict held, the limits and behaviour are measured **[Q1–Q14]** |
| **Single-vendor public beta** | everywhere | `Backend` is the substitution point; Jev, AnyJev, and jevfire are fallbacks **[X3]** |
| **Vendor SDK churn, hidden retries, body logging** | Phase 3 | raw `httpx`; SDK not a dependency (reasons measured on `typesafe-sdk` **[V-sdk]**; the `openai` SDK not yet reviewed) |
| **Idiomatic Pydantic refused** | Phase 2 | the normalisation table **[L3, L16]** |
| **Adjudication admits bad drafts** | Phase 4 | criteria rule; dry-run tool; ungated fields visible in `Result.ungated`; injection regression; labelled redraft bar |
| **Retries burn money** | Phases 3–4 | v0 has no decision retries (schema-derived sets have budget zero; candidate retry is deferred); redrafts bounded and measured; per-call budgets |
| **Scope creep via derived values** | post-v0 | out of v0 (R9); parsing a selected span is deferred with class D |
| **README drifts past what is true** | Phase 8 | exit criteria bind it to `DESIGN §6` |

---

## PLAN §6. Decisions recorded

| decision | call | reasoning |
|---|---|---|
| **Positioning** | General-purpose open-source library for anyone's pipeline; Asterion is its first user, not its specification | Built for its use case, not one consumer. Deferrals are justified by cost, risk, or sequencing and are planned (PLAN §9), never dropped |
| **Public claim** | Generalises TypeSafe's "select, don't generate" pattern into a schema compiler | Every mechanism predates us **[X2, X3]**; the combination does not, as far as we found |
| **Target user** | Extraction steps in pipelines where a wrong-but-valid value silently corrupts everything downstream | The unserved gap is a signal to route on, as a general compiler |
| **Language** | Python 3.11+ first | The target pipeline ecosystem (LangChain, LlamaIndex, Instructor) is Python-first; much Jev prior art is JS/TS **[X3]**, which is why a JS port is planned (Phase 10) |
| **Schema surface** | Pydantic (validation-mode schema) or JSON Schema draft 2020-12, with one `x-jevson` keyword | One declaration syntax for both surfaces |
| **Phase order** | Strictly sequential: 0 → 0r → 1 → 2 → 3 → 4 → 6 → 7 → 8, then 9 → 11; Phase 5 abandoned by Phase 0r **[Q2, Q9]** | **Set by the project owner.** Round-1 review E-40 (run 5 before 4 when Phase 0 says *go*) was considered and declined; Phase 4 survives Phase 5's abandon criterion, which fired in Phase 0r |
| **Source selection (class D)** | Dropped from v0 (2026-10-14); refused at compile time with `source_selection_dropped`; tracked in PLAN §9 | Pre-registered verdicts on two models: Jev **[Z9]**, the Decisions API **[Q2, Q9]** |
| **Decision model** | The OpenAI Decisions API (`gpt-6-luna`) replaces Jev (2026-10-14); Jev stays a possible fallback | Product owner's decision, recorded in `Agents/docs/decisions/2026-10-14-decisions-api-replaces-jev.md` (ASTERION-20); Jev measurements do not transfer, hence Phase 0r **[D1, D2, D3]** |
| **Vendor access** | Raw `httpx`; no vendor SDK | Every request, retry, and token visible to `Cost`; the reasons were measured on `typesafe-sdk` (pre-1.0 churn, retries that may be billed, unredacted body logging **[V-sdk, X5]**); the `openai` SDK is not yet reviewed |
| **Model version** | Recorded, not pinned: the returned `model` string on every response; replay from records only | No snapshot exists **[D3]**; behaviour has changed under the alias before **[D4]**. (Until 2026-10-14: pinned `jev-1.13.0`, aliases refused **[P9, V-models]**) |
| **Refusal** | `Unresolved(refused)`; never an option, a default, `absent`, or a retry | The API may decline any question **[D2]** |
| **Credentials** | `api_key` argument, falling back to `OPENAI_API_KEY`; empty counts as missing; the library never reads `.env` | Anyone can use it with no project tooling; the name the guide uses **[D1]** |
| **Default backend** | None; `Jevson(backend=...)` is required | An environment variable must never silently turn tests into paid calls |
| **Protocols** | I/O protocols async, `Normalizer` and `CostSink` sync, pinned in DESIGN from Phase 1; sync `resolve()` on one library loop thread; per-call clients on caller loops; per-key limiter on `threading.Lock` | Pipelines are async; the rate limit is per key; a loop per call breaks shared clients **[L20]** |
| **State referencing** | Opaque-id objects, never positions | 62% vs 0% wrong **[P4]** |
| **Candidate options** *(class D, deferred)* | Opaque ids; every occurrence of repeated text offered with a context window | 40/40 vs 22/40; offering only one occurrence misattributes provenance **[P15]** |
| **Question wording** | Versioned templates; complete-value wording; no negations | Partials 32/42 → 0/42 **[P11]**; literal reading **[V-jagged]** |
| **Single candidates** *(class D, deferred)* | Asked with `none_of_these` by default; direct extraction opt-in | 84/84 wrong-role lone candidates abstained in the Jev pilot **[P11]**; 39/50 on real documents on Jev **[Z8]** |
| **Abstention mechanism** *(class D, deferred)* | `none_of_these` inside the choice, not a separate predicate gate | The gate was worse on Jev: 0.56 vs 0.89 **[P5]** |
| **Probabilities** | Integer hundredths for storage; sum checked on raw values, 1 ± 0.01 on the Decisions API **[Q14]**; one tie margin ≤ 0.10 for every committing decision | Rounding and jitter are measured; ±0.05 left 11/180 choice flips, 0.10 left 1/180 **[L17, P12, P20]** |
| **Confidence gating** | Reported, never gated by default | A default threshold would assert calibration we have not measured |
| **Calibration bar** | Tie-safe bins, one-sided bootstrap ECE bound, Wilson rule at τ, mandatory power check on the observed distribution | The bar's power depends on the distribution **[L13, L14]** |
| **Retry defaults** | Zero for schema-derived sets (all of v0); one for candidates (deferred with class D), old ∪ new, two-sided bar on constructed misses | Near-deterministic model; relative distributions; harm as well as benefit **[L15]** |
| **Entity resolution** | Out of v0: deduplication is the extractor's declared contract. The post-v0 design keeps the lossless pre-merge, member-only components, the internal rule, and the cross-component variant with `conflict_floor` 0.05, chosen in Phase 0 **[Z4]** | Casefold merges distinct entities **[L1]**; the variant helped in-sample **[P10]** and did nothing out of sample **[P17]** |
| **Pairwise cap** | Post-v0 with entity resolution: n = 30, lowered if its phase measures a lower quality ceiling **[Z4]** | Token-feasible with a lean template **[L7]**; quality unmeasured |
| **Grapheme boundaries** *(class D, deferred; no table ships in v0)* | UAX #29 from a vendored generated table at Unicode 17.0; conformance plus differential tests | The shorthand rule was wrong in 13–15 of 20 classes **[L11]**; ~1.2 KB, no new dependency **[L19]** |
| **Replay** | `CachingBackend` and `ReplayLLM`, RFC 8785 keys (`rfc8785` / `canonicalize`), caller-supplied directory | Identical hashes across languages **[L21]**; nothing written by default |
| **Source trust** | Untrusted; stated limit; the screen is deferred with class D (PLAN §9) | Selection is steerable **[P7]**; the tested screen wording flagged 28/60 benign documents **[P21]** |
| **Candidate defaults** *(class D, deferred)* | `max_candidates` 50 options (after repeated-text expansion), `max_candidate_chars` 120 | ~1.6k tokens, so the source ceiling stays high **[P22]** |
| **Undeclared defaulted leaf fields** | Class A: omitted so the default applies; objects and arrays compile from their contents | Neither decided nor refused; declare `generate` (or, for a bool, enum, or integer range, `question` or `ordinal`) to have them decided |
| **Step timeouts** | `step_timeout_s` (default 120) on every caller step | A never-returning step must not hang every synchronous caller |
| **Absence** *(class D, deferred; `Result.absent` is always empty in v0)* | Not required → omitted (defaults apply); required nullable → null; required → unresolved | A nullable field with a default must keep its default **[L18]** |
| **Semantic ordering** | Out of v0; declaring it refuses | Unproven; refusing beats silently wrong order |
| **Adjudication criteria** | About the draft and the source only | The decision model is not a fact-checker |
| **Multi-source and long sources** | Out of v0, planned as Phase 9 | Budget and cross-source resolution |
| **JS port** | Planned as Phase 10 | Two languages in v0 finish neither |
| **Hostile doubles** | `tests/`, never shipped | The fake backend is a tool; the hostile one is a footgun |
| **Integration tests in CI** | On demand and on release | Rate limit and cost |
| **Versioning** | `0.x` | No stability promise before the scope verdict meets users |
| **Licence** | MIT | Permissive, like most neighbours (jevc and AnyJev are Apache-2.0) **[X6]** |
| **Name** | Keep "Jevson" for now; whether to rename now that Jev is not the backend is a separate follow-up, decided before the Phase 8 release. **Name: pending owner decision before publication (keep with TypeSafe's OK, or rename).** | Renaming after publication breaks users |
| **Fake backend** | Shipped | Users need it to test without spending |
| **Scope if the band is narrow** | Ship the narrow version | Pre-committed, to defeat sunk cost |

Reversals are recorded in `DESIGN §13`.

---

## PLAN §7. Open questions

| question | closed by | if the answer is bad |
|---|---|---|
| Does `none_of_these` catch missing answers on real documents? | **Answered: no.** Phase 0 probe 2 on Jev: conditional, 0.733 **[Z2]**; probe 9 on Jev: drop **[Z9]**; Phase 0r probe 2: stop, 0.527 **[Q2]**; probe 9: drop **[Q9]** | Candidate selection stopped; v0 is the fallback |
| Do we select accurately and abstain only when we should? | **Answered:** selection yes, abstention no. Phase 0 probes 1 and 3 on Jev: go, go **[Z1, Z3]**; Phase 0r: go, go **[Q1, Q3]** | Moot while class D is deferred |
| Which entity rule variant, and what `conflict_floor`? | **Answered by Phase 0 on Jev:** cross-component, 0.05, and below the bar **[Z4]** | Dedup became the extractor's contract (Phase 7) |
| Do the Jev measurements and Phase 0's "drop source selection" hold on the Decisions API? | **Answered by Phase 0r:** the verdict holds **[Q1–Q14]** | v0 is the fallback product |
| Is the decision model calibrated on span disambiguation? | Readings only: Phase 0 probe 7 (Jev, ECE 0.046 **[Z7]**), Phase 0r (ECE 0.120 **[Q7]**); the full measurement was Phase 5's, deferred with class D | Probabilities stay reported, never gated |
| Can any screen wording flag hostile sources without flagging ordinary processing notes? | Readings only: Phase 0 probe 6 **[Z6]**, Phase 0r **[Q6]**; deferred with class D | The screen does not ship in v0 |
| Do decision retries recover answers without adding false commits? | Deferred with class D (was Phase 5) | Default retry budget becomes 0 |
| Do redrafts recover rejected drafts without admitting bad ones? | Phase 4 | Default redraft budget becomes 0 |
| Level or speculative fan-out for unions? | Phase 6 | Whichever the measurement favours |
| What is the pairwise quality ceiling? Can pair jitter be reduced? | Post-v0 entity-resolution phase (PLAN §9.1) | Cap lowered with the measurement cited; banding only |
| Is the name right? | before Phase 8 | Rename before publication |

**Closed by evidence on `jev-1.13.0`**, and re-checked on the Decisions API where they depend on model behaviour **[Q5, Q9, Q10]**: level splitting is answer-neutral **[P1]**; keyed state references matter **[P4]**; a predicate gate is a worse abstention mechanism **[P5]**; lone candidates are safer asked **[P11]**; the score value is the most probable level **[P13]**; the complete-value wording costs nothing when the full value is present **[P18]**; mixed option descriptions showed no decision bias at near-ceiling accuracy **[P19]**; entity resolution on real prose is below its bar, out of v0 **[Z4]**; state references by position fail on the pinned model **[Z5]**.

---

## PLAN §8. Sequencing summary

```text
Phase 0   taxonomy + probes + scope verdict           no code, gates everything   (run on jev-1.13.0)
Phase 0r  the Phase 0 probes on the Decisions API     no code, gates Phase 1
Phase 0r  verdict: drop source selection [Q2, Q9]   → v0 is the fallback product
Phase 1   core model, protocols, graph, fake          ~450 lines
Phase 2   normaliser + declarations + compiler        ~500 lines   (x-jevson.source refuses: source_selection_dropped)
Phase 3   executor + budget + live backend + façade   ~500 lines   ← working library
Phase 4   generative fields and adjudication          ~450 lines
Phase 5   candidates and source selection             ABANDONED by Phase 0r; kept as the record; PLAN §9
Phase 6   union discrimination                        ~300 lines
Phase 7   multi-label enum arrays                     ~150 lines   (source-grounded arrays deferred, PLAN §9)
Phase 8   packaging and release                       ~250 lines   ← v0: the fallback product
--- post-v0, planned ---
(unnumbered) source selection (class D), PLAN §9 — only if revived by its own probe
Phase 9   multi-source and long-source extraction                  (needs class D revived)
Phase 10  JavaScript / TypeScript port
Phase 11  credentials from Infisical                               (lowest priority)
(unnumbered) entity resolution, PLAN §9.1 — post-v0, unscheduled; its own probe first; Phase 9's cross-source resolution waits on it
```

Every phase starts only after the previous one has merged or abandoned. **Phase 0r's abandon criterion fired (2026-10-14) [Q2, Q9]**, so the product is **phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7**, and Phase 6 follows Phase 4 directly.

---

## PLAN §9. Tracked deferrals

Nothing deferred is dropped. Each entry names what it waits on.

| deferred item | why deferred | revisit when | where it lands |
|---|---|---|---|
| **Source selection (class D)**, and everything that depends on it: all of Phase 5, the span and grapheme work of Phase 1, the source mapping of Phase 2, the source-grounded arrays of Phase 7 (PLAN §9.2) | Abandoned by Phase 0r: abstention with the answer absent was 0.527, in the stop band, and the second gate was *drop*, on the Decisions API **[Q2, Q9]** as on Jev **[Z2, Z9]** | A decision model, a new version under the `gpt-6-luna` alias (R15), or a new abstention mechanism passes Phase 0 probes 1–3 **and** probe 9 under the same pre-registered rules and bands, on a fresh corpus | A post-v0 phase built from Phase 5's text and the moved items in PLAN §9.2 |
| **Pairwise entity resolution** (the internal rule, cross-component variant, and `conflict_floor` 0.05 of `DESIGN §5.7`) | Below its bar on real prose: 163/330 components correct under the chosen variant **[Z4]** | After Phase 8 | A post-v0 phase with its own probe; Phase 7's dedup criteria move there |
| **Default probability threshold** | Would assert calibration we have not measured (`DESIGN §6.2`); Phase 0r's reading was worse than Jev's (ECE 0.120) **[Q7]** | A calibration measurement over ≥ 1,000 decisions (was Phase 5's; now with class D, or a separate measurement on bounded decisions) | v1, only if the pre-registered bar is met, citing the measurement |
| **Source screen** (opt-in in the plan; on by default in v1) | It was a Phase 5 deliverable; its wording bar needs ≥ 300 held-out benign documents **[P21]**. Readings were encouraging: 50/50 attacks and 1/50 benign on the Decisions API **[Q6]** | With class D, or earlier as its own phase if injection into bool, enum, and criterion decisions proves to matter | A post-v0 phase; default-on only if its bar is met |
| **Draft self-claim mitigation** (e.g. a draft-screen predicate, or a criterion-template variant that asks the decision model to ignore what the draft says about itself) | The live injection regression failed: a draft that falsely claims to contain what a criterion checks passed 5 of 5 times in the V2 × *mentions the amount* cell, under both the keyed multi-draft and the single-draft layout **[Q16]** | **Moved into v0:** ASTERION-48 (owner decision, 2026-10-19: the injection bar is not met and v0 does not ship with 5/80) | A post-v0 phase, measured on **fresh** cases (new sources, claims and criteria), never tuned on the 80 [P7] cases, which stay the regression; adopted only if it removes the self-claim flips without raising false rejections of correct drafts |
| **Semantic array ordering** | Unproven | After Phase 7 | A post-v0 phase with its own probe (pairwise preference vs. per-item `score`) |
| **Derived provenance** (R9) | Needs an expression layer | After Phase 8 | A post-v0 phase |
| **Multi-source and long sources** | Budget and cross-source resolution | After Phase 8 | Phase 9 |
| **JS / TS port** | Two languages in v0 finish neither | After Phase 9 | Phase 10 |
| **Infisical credentials** | Team convenience, not a library feature | Any time; lowest priority | Phase 11 |
| **Recursive and dynamic `$ref`, `allOf` beyond flat merge, `dict[str, X]`, tuples, `Any`, `bytes`** | Refused loudly (`DESIGN §3.5`) | After Phase 8 | A post-v0 phase |
| **Arrays of objects (including nested), cross-item constraints** | Out of Phase 7 scope; refused in v0 (`DESIGN §3.5`) | After Phase 8 | A post-v0 phase |
| **`none_of_these` on schema enums and union discriminators** ("not determinable from the source") | Schema-derived choices have no abstention path in v0; abstention measured below its bar on both models **[Z2, Q2]** | After an abstention mechanism passes its bar | A post-v0 phase |
| **Relative and partial dates** ("next Friday", "the 3rd") | v0 parses no dates: parsing a selected span is deferred with class D | After class D | A post-v0 phase using date-part choices with "not stated", as in TypeSafe's date-extraction cookbook **[V-cookbooks]** |

### 9.1 Post-v0: entity resolution (moved out of Phase 7 by Phase 0 **[Z4]**)

Probe 4 was *stop* on real prose on `jev-1.13.0`, so these Phase 7 items wait for their own phase, which re-measures them with its own probe before anything ships. They keep the Phase 0 settings: `conflict_floor` 0.05 and the cross-component variant (`DESIGN §5.7`).

**Deliverables:**

- `assemble/entities.py` (`DESIGN §5.7`): lossless pre-merge (casefold opt-in; never initials or first names); pairwise predicates, capped; the internal-consistency rule, plus the cross-component variant Phase 0 chose, with `conflict_floor` 0.05 **[Z4]**; pair questions share the membership level (R5); the cardinality pipeline becomes membership → pre-merge → pairwise → components ordered by earliest span → `maxItems`, each overflowed component recording its spans and minimum membership probability (R8)
- `Normalizer` canonical representative: earliest span, longest span, or user-supplied
- An experiment on reducing pair jitter by asking both orderings of each pair and averaging, measured against single-order asking on ≥ 40 documents × 2 identical runs (`DESIGN §12`); it doubles pair questions, so it is measured only at question counts already covered by keyed-batching evidence

**Exit criteria:**

- [ ] **The chain case:** with a fake backend answering Dana = Dana Whitfield (0.9), Dana Whitfield = Ms. Whitfield (0.9), Dana vs Ms. Whitfield (0.4), no cross-component pairs in the uncertain band, and a floor of 0.30, the three produce **one** element
- [ ] **The internal-conflict case:** A = B, B = C, A vs C ≤ floor → that component is `Unresolved(entity_conflict)` naming the pairs; other components are emitted
- [ ] **The split case:** under the cross-component variant, two components linked by a pair at 0.40 (above a 0.30 floor) → both are `Unresolved(entity_conflict)`; under the internal-only variant, both are emitted
- [ ] **Pre-merge:** `"Acme Corp"` and `"Acme  Corp"` merge with zero backend questions; `"US"` and `"us"` do **not** merge by default; with casefold opted in they do; identical strings under different entity types never merge
- [ ] Pairwise resolution for n candidates issues n(n−1)/2 keyed questions in one request, split only by the budget
- [ ] A candidate count above the cap yields `Unresolved(too_many_candidates)`
- [ ] **Cap measured:** component outcomes at n ∈ {10, 20, 30} on ≥ 20 real arrays per n (including how many arrays are incomplete only through membership ties), and keyed-batching accuracy at the resulting question count (measured only to 320 so far, on Jev **[P4]**), are written down; the default cap is the largest n meeting the Phase 0 probe 4 go band
- [ ] **Jitter experiment** results are written down; both-orderings asking is adopted only if it at least halves the pair-decision flip rate between identical runs and component accuracy is not lower (point estimates)
- [ ] **Members only:** a rejected candidate linked at 0.9 to two members A and B, with A–B at 0.10 (≤ floor), does not merge them: A and B are emitted as two elements under both variants

### 9.2 Post-v0: source selection (class D), moved out of v0 by Phase 0r **[Q2, Q9]**

Phase 5 is abandoned (its text is kept above as the record), and these items moved out of the phases that would have built them. Their v0 fate is stated so that nothing is silently half-built:

| item | was in | v0 fate |
|---|---|---|
| Candidates, `none_of_these`, the complete-value template, context windows for repeated text, lone candidates and `direct_extraction`, `max_candidates`, the pre-filter | Phase 5 | not built; `x-jevson.source` refuses with `source_selection_dropped` (Phase 2) |
| Extractors: `extract/llm.py`, `extract/patterns.py`, `extract/occurrences.py`; `hostile_extractor.py` | Phase 5 | not built; the `Extractor` protocol and `ExtractorError` are defined (Phase 1) with no v0 implementation, caller, or raise |
| `default_extractor` and `extractors=` | Phase 2 (mapping), Phase 5 (lift) | parameters kept; any field they would source-select refuses with `source_selection_dropped` |
| `unicode/graphemes.py`, its vendored Unicode 17.0 table, `tests/conformance/`, and the graphemes exit criterion | Phase 1 | not built; `Result.versions` has no grapheme-table or `unicodedata` key |
| `extract/spans.py` and the span-verification exit criterion | Phase 1 | not built; the `Span` type and `SOURCE_SPAN` provenance kind (with `source_id`) stay in `types.py`, and v0 constructs neither |
| Class F parsing of a selected span (`assemble/parse.py`), `locale`, decimal-string emission for parsed values | Phase 5 | not built; no v0 value is parsed from the source |
| Abstention, the `DESIGN §5.6` table, object absence | Phase 1 (assembler), Phase 5 | not reachable; `Absent` and `Result.absent` stay in the type and are always empty |
| Decision retry with exclusions and `retry_budget` | Phase 5 | not built; v0 has no decision retries, and `resolve()` takes no `retry_budget` (adding the keyword later is not breaking) |
| The second gate and `Unresolved(verification_failed)` | Phase 5 | not built; the reason is reserved |
| The source screen and `Unresolved(source_flagged)` | Phase 5 | not built (row above); the reason is reserved |
| Source-grounded arrays of spans: membership over candidates, source order (`assemble/ordering.py`), overflow by span | Phase 7 | not built; only multi-label enum arrays ship |
| Hostile spans, hostile extractors, hostile sources against selection | PLAN §4.2 | not built |
| Coverage, retry, calibration, and screen measurements on a fresh labelled corpus | Phase 5 | not run; the corpus is part of reviving class D |

`Unresolved` reasons that only class D can produce (`abstained`, `no_candidates`, `too_many_candidates`, `unparseable`, `verification_failed`, `source_flagged`) stay in the closed set as reserved, so reviving class D does not change `UnresolvedReason` (`DESIGN §6.1`). Multi-source extraction (Phase 9) depends on this work.
