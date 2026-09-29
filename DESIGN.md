# Jevson — design

> **Status:** Design document, Revision 2, 2026-09-28. Pre-implementation.
>
> **This document is the SSOT for Jevson.** It carries everything an agent or contributor needs to work on the project: what the library is, what it guarantees, the architecture, the vocabulary, the constraints of the model it sits on, and the rules that are not open for reinterpretation. The build sequence lives in [`PLAN.md`](PLAN.md).
>
> **One line:** Jevson is a source-grounded structured extraction library — values are traceable to source evidence or declared options, bounded semantic choices are made by a calibrated decision model, and structure is enforced deterministically.

---

## 1. The problem — stated correctly

The obvious framing of this library is *"guarantee that an LLM's JSON output matches the schema."* **That framing is wrong, and building against it would be building something that already exists.**

Grammar-constrained decoding already solves it. When a sampler is masked against a compiled grammar, an out-of-enum value, a misspelled key, a missing brace, or a wrong nesting depth is not *unlikely* — it is **unreachable**. The illegal token is removed from the distribution before the model chooses. That is the same modality of guarantee Jev offers, and it ships today in OpenAI Structured Outputs, Anthropic strict tool schemas, vLLM, Outlines, XGrammar, and llama.cpp GBNF.

Nothing outside the model can beat that, because everything outside the model happens *after* the tokens have been chosen. A library that inspects finished output can only detect, never prevent.

So shape is table stakes. **The real failure is different and nobody addresses it:**

```json
{ "first_name": "Whitfield", "last_name": "Dana" }
```

Perfectly schema-valid. Completely wrong. A grammar cannot see it. `jsonschema` cannot see it. The pipeline downstream cannot see it, and the bad row lands in the database with no signal attached.

That is the class of failure Jevson exists for:

| failure | example | who catches it today |
|---|---|---|
| invalid syntax | missing brace | constrained decoding |
| invalid shape | key at wrong depth | constrained decoding |
| out-of-enum value | `"urgent"` where the enum has three options | constrained decoding |
| constraint violation | `maxItems: 5`, six items | `jsonschema` |
| **wrong entity chosen** | the vendor's address extracted as the billing address | **nobody** |
| **wrong branch taken** | a `Person` object built where the source described an `Organization` | **nobody** |
| **value absent from source** | a plausible name that appears nowhere in the document | **nobody** |
| **silent confidence** | any of the above, with no signal that anything is wrong | **nobody** |

The gap is **semantic selection**: which interpretation of the source belongs in this field. The schema does not answer it. A grammar cannot reach it. It is a bounded decision, and bounded decisions are exactly what Jev is for.

### 1.1 The one-line pitch to a pipeline author

> Jevson is the node in your chain that knows when it doesn't know.

In a LangChain or LlamaIndex pipeline today, if step 3 extracts the wrong address, nothing tells you. The output was valid. Everything downstream is confidently wrong. Jevson returns a calibrated confidence per field and an explicit abstention when the source does not support any candidate — a signal you can branch on: fall back, escalate to human review, abort the chain.

---

## 2. Jev — the constraints that shape everything

Jev is TypeSafe's constrained "System One" model, released 2026-09-15. Docs: <https://jevapi.dev/>. It is non-autoregressive: it does not generate tokens at all.

**Interface.** `POST https://api.typesafe.ai/v1/systemone` with a `state` (text or JSON) and a `questions` map.

**Three primitives, and only three:**

| primitive | input | output |
|---|---|---|
| `noul` | a predicate | boolean probability + confidence |
| `choice` | declared options (≤ 255) with criteria | selection + probability distribution + confidence |
| `score` | an ordered rubric (2–10 levels) | level + per-level probabilities + confidence + machine-readable legend |

**Operational facts, all load-bearing:**

- **All questions on a state are evaluated in one parallel forward pass.** Adding questions costs almost no latency. This is the single most important performance property in the system and the architecture is built around exploiting it.
- **Deterministic.** Same input produces the same answer run to run; vendor-stated σ = 0.01 over 15 repeats. Answers are therefore cacheable, and replay is nearly free.
- **Confidence is an explicit training objective** (RLCD), so thresholds behave like thresholds. Across many predictions at confidence 0.8, outcomes should occur about 80% of the time — this describes group behaviour, not a guarantee about any single answer.
- Context ~64k tokens for state plus questions. Latency 70–500 ms.
- Rate limits ~250k tokens/s, 1200 req/min.
- $0.042 per million input tokens; **output free.** ~$0.068 per 1000 decisions.

**Hard limits — these are why the architecture looks the way it does:**

- Cannot produce free-form text.
- Cannot produce arrays or nested objects.
- Cannot read images or files.
- Does not reason step by step.
- **Has no concept of a schema.** Every question Jevson asks is one Jevson constructed. Jev supplies judgement; all structure and all question design is ours.

### 2.1 The keyed-batching requirement

When batching many questions over a collection, **key them as object properties, never by array index.**

```text
GOOD:  candidates.k137   candidates.k138
BAD:   candidates[137]   candidates[138]
```

Measured: 320 items with one yes/no question each.

| batching style | items per request | wrong answers |
|---|---|---|
| `candidates[i]` | 150 | 86 / 320 (27%) |
| `candidates[i]` | 25 | 29 / 320 (9%) |
| `candidates.k137` | 320 | **0 / 320** |
| one item per question | 320 | **0 / 320**, 0.4 s |

Source: [measured writeup](https://gist.github.com/pedramamini/014676fa8684d91bf7000f4623701ada). The vendor's own examples use `items[i]`, so this is a trap, not a nicety. **It is a hard implementation requirement, not a tuning detail.**

---

## 3. Architecture

```text
      SCHEMA                                    SOURCE
   (Pydantic or                            (document / text)
    JSON Schema)                                   │
         │                                         │
         ▼                                         ▼
   ┌───────────┐                            ┌─────────────┐
   │ COMPILER  │                            │  EXTRACTOR  │ ← pluggable:
   │ schema →  │                            │  source →   │   LLM / regex /
   │ decision  │                            │  candidate  │   NER / user
   │ points    │                            │  spans      │
   └─────┬─────┘                            └──────┬──────┘
         └────────────────┬───────────────────────┘
                          ▼
                 ┌──────────────────┐
                 │  DECISION GRAPH  │  nodes: kind, question, options,
                 │  + dependencies  │  option-source, deps, provenance
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │    EXECUTOR      │  topological levels
                 │  level batching  │  one keyed Jev call per level
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │  BACKEND (proto) │  Jev │ AnyJev │ Fake
                 └────────┬─────────┘
                          ▼
                 ┌──────────────────┐
                 │    ASSEMBLER     │  entity resolution, ordering,
                 │                  │  cardinality, overflow capture
                 └────────┬─────────┘
                          ▼
                 validate against original schema
                          ▼
     Result(value, provenance, confidence, unresolved, cost)
```

### 3.1 The central abstraction is the decision graph

Jevson is **not** "JSON Schema → Jev questions." That is what the prior art does, and it is why the prior art refuses everything interesting.

Jevson is:

```text
Schema + Source + Evidence  →  Decision Graph  →  Jev execution
                            →  Resolved graph  →  JSON assembly
```

A **decision node** carries:

```text
id            stable identifier, used as the Jev question key
kind          choice | score | noul
question      the natural-language predicate or prompt
options       declared options, or a rubric, or none (noul)
option_source schema_enum | schema_rubric | candidate_spans | predicate
dependencies  node ids that must resolve before this node compiles or runs
provenance    what kind of provenance a resolved value will carry
target        JSON pointer into the object under construction
```

**Compilation and execution are separate concerns.**

- The **compiler** answers: *what decisions are necessary?*
- The **executor** answers: *what can run in parallel, and in what order?*

This split is what makes level batching fall out naturally, and it is what lets new decision kinds be added without touching execution.

### 3.2 Decide-then-construct, not generate-then-check

The distinction matters and it is the reason Jev is load-bearing rather than decorative.

**Audit architecture (what we are not building):**

```text
LLM picks Person → LLM builds a Person object → Jev says "actually Organization"
→ discard → retry
```

Jev is an auditor. Work is wasted. The wrong branch was constructed before anyone objected.

**Construction architecture (what we are building):**

```text
Jev: Person 0.04 / Organization 0.96
→ traverse the Organization branch
→ compile only that branch's decision nodes
→ resolve them → assemble
```

Jev is a controller. Its answer **determines what gets built**. The wrong branch is never constructed.

### 3.3 Level batching

Most decision nodes are independent — `category` does not depend on `vendor`. Serialising them throws away the one property that makes Jev nearly free.

```text
decision graph → dependency analysis → topological levels
              → one batched, keyed Jev call per level
```

A typical object resolves in **1–3 Jev calls**, not one per field. A new level is required only where a genuine dependency exists — in practice, union discrimination that gates which nodes exist at all.

### 3.4 Worked example

Schema: `vendor: str`, `total: number`, `billing_address: str`, `line_items: [str]`, `category: enum[software|hardware|services]`.
Source: an invoice naming two companies and two addresses.

1. **Compiler** classifies each field. `total` → deterministic parse, no model. `category` → `choice`, options from the schema. `vendor`, `billing_address` → source selection, options from extracted spans. `line_items` → membership `noul` per candidate.
2. **Extractor** returns candidate spans with offsets: two organisations, two addresses, five line-item strings.
3. **Graph**: every node independent → **one level → one Jev call**, questions keyed as objects (`q.vendor`, `q.addr`, `q.item_0` …).
4. **Jev** returns selections, distributions, confidences, and `none_of_these` probabilities — all in one parallel pass.
5. **Assembler** deduplicates line items via pairwise `noul` batched into the same call, orders by source offset, enforces `maxItems` retaining any overflow, inserts values by span.
6. **Validate** against the original schema. Emit provenance: `vendor ← [142,151]`, `category ← declared option`.

---

## 4. The classification model

Every schema construct and extraction operation falls into exactly one class. This taxonomy is the backbone of the compiler and the instrument that decides v0's scope (see `PLAN.md` Phase 0).

| class | name | handled by | example |
|---|---|---|---|
| **A** | Deterministic | ordinary code | required fields, nesting, defaults, types |
| **B** | Grammar | constrained decoding | key spelling, enum membership at the token level |
| **C** | Bounded semantic decision | **Jev** | classification, ordinal rating, boolean predicate, union discrimination |
| **D** | Source selection | **candidate spans + Jev** | which of four spans is the billing address |
| **E** | Unbounded generation | LLM | a summary, a synthesised description |
| **F** | Computational | deterministic code | date arithmetic, currency parsing, unit conversion |
| **G** | Unsupported | explicit refusal | anything the compiler cannot map |

### 4.1 "Can be a Jev question" is not "should be a Jev question"

This is the discriminator that decides whether Jevson is a broad library or a sharp one, and it must be applied honestly.

An enum can trivially be expressed as a `choice`. But if constrained decoding already guarantees the enum and there is no semantic ambiguity, **Jev adds nothing** and routing it through Jev is cost and latency for no benefit.

By contrast:

> *Which of these three people is the customer?*

The schema does not contain the answer. A grammar cannot reach it. The value must be selected from evidence, and the selection is the hard part. **That is the semantic gap Jevson exists to fill.**

Every entry in the taxonomy must therefore record its **existing alternatives** — if constrained decoding or plain code already solves it, it is not a Jevson differentiator, however neatly it maps to a primitive.

---

## 5. Candidates, provenance, and abstention

### 5.1 Jev cannot generate a string — but it can choose one

Jev cannot be asked *"what is the customer's name?"* It has nothing to select from. But given:

> "Dana Whitfield, VP of Marketing at Acme Corp, met with John Smith from Globex yesterday."

an extraction step can produce candidate spans, and the question becomes an ordinary `choice`:

```text
choice(customer.name):
    "Dana Whitfield"   [0, 14]
    "John Smith"       [52, 62]
    none_of_these
→ "Dana Whitfield"  p=0.91  confidence=0.94
```

**Jev never generates the text. It chooses which source-grounded text belongs there.** Deterministic code then inserts the selected span.

### 5.2 Candidates are for disambiguation, not extraction

If the source says *"The customer's name is Dana Whitfield"* and there is one obvious span, forcing an LLM to produce a candidate list so Jev can pick the only element is pointless — and *harder* than asking for the value, because producing a list reintroduces formatting fragility.

The rule:

```text
one obvious source span     → direct extraction
multiple plausible spans    → Jev candidate choice + none_of_these
no suitable source span     → generation, computation, or refusal
```

Candidate mode with a single candidate remains *available* where provenance is valuable enough to justify it, but it is never mandatory.

### 5.3 `none_of_these` is mandatory, and it is the safety property

Without it, the architecture is **strictly more dangerous than asking the LLM directly**, because it launders a wrong answer through a calibrated-looking number.

```text
real answer:  Dana
candidates:   John, Acme

Jev:  John 0.08   Acme 0.92
```

That 0.92 is calibrated **over the option set it was handed**, not over reality. Nothing in the response reveals that the correct answer was never offered.

Therefore: **every candidate-backed `choice` compiles with an explicit `none_of_these` option.** The contract becomes:

```text
SELECT(candidate)   or   ABSTAIN(none_of_these)
```

Note the precise meaning: `none_of_these` does **not** prove the extractor failed. It means *no supplied candidate is sufficiently supported as the answer* — the source may genuinely not contain one.

### 5.4 Abstention lifecycle

```text
candidate extraction
      ↓
   Jev choice
      ├── candidate selected ───────────────► value + provenance
      └── none_of_these
              ↓
        bounded retry (default 1 expanded extraction)
              ├── candidate selected ───────► value + provenance
              └── budget exhausted ────────► Unresolved(...)
```

**Retry only helps if the input changes.** Jev is deterministic (§2) — re-asking the same question over the same state returns the same answer. A retry that does not expand the candidate set, change the state, or alter the question is guaranteed to be wasted spend. Therefore:

- Retry against a **schema-derived** option set (enum, rubric) has a default budget of **zero**. There is nothing to expand.
- Retry against a **candidate-derived** option set re-runs extraction with a widened brief, producing a genuinely different option set. Default budget **one**.

The terminal outcome is a **typed value, never an exception**:

```text
Unresolved(field, reason, candidates_seen, abstain_probability)
```

**Optional vs required:**

| field | unresolved | outcome |
|---|---|---|
| optional | yes | partial result, hole flagged — an honest representation of uncertainty |
| required | yes | strict schema failure — the object cannot claim schema satisfaction |

Strictness is configurable for optional fields. **Required-field failure remains objectively detectable regardless of caller preference** — a caller may choose to receive it rather than raise, but the result must report that the object does not satisfy the schema.

### 5.5 Provenance is a first-class output

Exactly two kinds in v0, deliberately boring:

```text
SOURCE_SPAN      source id, start offset, end offset
DECLARED_OPTION  option identifier (schema enum value, rubric level)
```

**Span semantics, pinned so implementations cannot disagree:**

- Offsets are **Python `str` character offsets**, not bytes. The hostile suite includes unicode confusables and multi-byte content; byte offsets would make verification wrong in exactly those cases.
- Half-open interval `[start, end)`, matching Python slicing.
- **v0 supports one source per call.** `source_id` exists in the type so multi-source is not a breaking change later, but supplying more than one source refuses at compile time.
- A span is valid only if `source[start:end]` equals the candidate text exactly. Verification happens **before** the Jev call, not after — an unverifiable span never becomes an option.

Which supports two clean guarantees:

> This value came from this exact source span — verifiable by substring match.

> This value was selected from this declared option set.

**Derived provenance is out of v0.** A field like `age_at_signing ← birth_date, signing_date, date arithmetic` requires an expression layer and turns the flat provenance map into a graph. That is a feature in its own right. Computed fields are the caller's responsibility until v1.

---

## 6. What is guaranteed

Guarantees are tiered. Conflating them is how the README would become false.

| tier | claim | mechanism | holds unconditionally? |
|---|---|---|---|
| **Structural** | output is valid JSON conforming to the structural schema | constrained decoding + deterministic assembly | **yes** |
| **Constraint** | `minimum`, `maxItems`, `pattern`, required fields, cross-field rules | deterministic validation | **yes** |
| **Provenance** | every value came from a named source span or a declared option set | candidate architecture + substring verification | **yes**, for fields resolved that way |
| **Decision** | a calibrated probability distribution and confidence accompany every bounded decision | Jev | **yes**, as a group property |
| **Semantic correctness** | the value is objectively the right interpretation | — | **no. Not claimed. Not claimable.** |

**Never claim the last row.** Jev is not an oracle and not a fact-checker. What Jevson provides is that when the source does not support an answer, you get an abstention instead of a confident wrong value — and when a value is committed, you can point at where it came from.

Two further honest limits that belong in user-facing docs:

- **Adjudication only checks the criteria you declare.** Criteria quality is the library's real interface for generative fields.
- **Jev's confidence is calibrated over the options it was given.** `none_of_these` is what makes a bad option set visible; nothing else does.

### 6.1 The central property, stated precisely

The library's headline claim is that the result survives arbitrary model behaviour. Stated as a binary — *"a valid object or a refusal"* — it is **wrong**, because an abstained optional field is a legitimate third outcome that satisfies neither.

The correct statement, and the one the adversarial suite asserts:

> For any schema and any backend or LLM behaviour whatsoever, a call returns exactly one of:
>
> 1. a `Result` whose `.value` validates against the original schema, and `.satisfies_schema is True`;
> 2. a `Result` carrying one or more `Unresolved` fields, with `.satisfies_schema is False` and every hole named; or
> 3. a typed refusal (`CompileError` or `SchemaViolation`) naming the reason.
>
> Never a fourth outcome. Never a partial object that claims to satisfy the schema. Never an untyped exception from a model's output.

`satisfies_schema` is a required field on `Result` precisely so outcome 2 cannot be mistaken for outcome 1 by a caller who forgets to check.

### 6.2 Confidence is reported, not enforced, by default

Whether Jev's calibration transfers to source-span disambiguation is an **open question** (§12), not an established fact. Shipping a default confidence threshold that silently drops values would be asserting an answer we do not have.

Therefore in v0:

- Confidence and the full distribution are **always reported** per decision.
- **No default threshold gates a commit.** A caller who wants gating sets one explicitly.
- `none_of_these` is the one abstention path that is on by default, because it is a *structural* signal about the option set rather than a *calibration* claim about the model.

If Phase 0's spike and Phase 4's measurements show calibration holds on this task, a default threshold becomes defensible in v1 — with the evidence cited.

---

## 7. The twelve v0 rules

Settled. These are not open for reinterpretation during implementation; changing one is a design change that updates this document.

1. **Candidate-backed choices always include `none_of_these`.**
2. **`none_of_these` triggers bounded retry, then a typed `Unresolved`** — never an exception, never a silent null.
3. **Independent decisions are level-batched** into one keyed Jev call per topological level.
4. **Candidates are primarily for source-span disambiguation**, not universal extraction.
5. **Source-grounded arrays are supported through membership `noul`s** over a candidate set.
6. **Array deduplication is an explicit entity-resolution stage**, scoped to an entity type — never generic string equality.
7. **Array ordering defaults to source order**; semantic ordering is a separate, declared decision problem.
8. **Overflow is never silently discarded** — hard schema constraints must not cause evidence to disappear.
9. **Derived and computed provenance is out of v0.**
10. **There are no global modes.** A single object freely mixes deterministic, source-grounded, Jev-selected, LLM-generated, and computed fields.
11. **Decision graph, compiler, and executor are the core abstractions**, and compilation is separate from execution.
12. **The taxonomy determines whether v0 is broad or deliberately narrow** — the evidence decides the scope, not the ambition.

Plus two implementation rules of equal standing:

13. **Questions are keyed as object properties, never by array index** (§2.1).
14. **Refusal is loud and happens at compile time**, before any API call, with the offending JSON pointers.

---

## 8. Interfaces and dependency posture

Five protocols, each earning its place by having a real second implementation. **An interface with exactly one implementation and no prospect of a second is not created.**

| protocol | implementations | why it exists |
|---|---|---|
| `Backend` | `JevBackend`, `FakeBackend`, (`AnyJev`) | vendor containment; testing without spend |
| `Extractor` | LLM-backed, regex, NER, user-supplied | candidate generation is domain-specific |
| `LLM` | injected by the caller | we do not assume a provider |
| `Normalizer` | declared per entity type | canonical-representative policy is a user decision |
| `CostSink` | default, user-supplied | cost accounting is observable, not buried |

**SOLID, concretely:**

- **S** — compiler, extractor, executor, backend, assembler each own one transformation; the seams are where the data changes form.
- **O** — new decision kinds and new extractors plug in without the executor changing.
- **L** — every `Backend` and `Extractor` is substitutable; this is what makes the fake backend and an `AnyJev` swap real rather than aspirational.
- **I** — narrow separate protocols rather than one fat interface.
- **D** — everything depends on protocols. **The Jev SDK is reachable only through `Backend`**, so no consumer of Jevson imports a vendor SDK.

**Privacy posture:** nothing is logged by default. Source text, candidate spans, and resolved values are never written anywhere by the library unless the caller supplies a sink.

**Vendor risk:** Jev is a single-vendor, early-access dependency. `nokia-applied-research/AnyJev` and `kikoncuo/jevfire` provide Jev-style constrained decisions over other models and are the identified substitution path. The `Backend` protocol exists so that substitution never touches the compiler, the graph, or the assembler.

### 8.1 The result type

Pinned here because it is the library's primary interface and every phase touches it.

```text
Result
  value             dict — the assembled object
  satisfies_schema  bool — False whenever any Unresolved is present (§6.1)
  provenance        {json_pointer: SOURCE_SPAN | DECLARED_OPTION}
  confidence        {json_pointer: Confidence(value, distribution)}
  unresolved        [Unresolved(pointer, reason, candidates_seen, abstain_probability)]
  overflow          [Overflow(pointer, candidate, probability)]   — R8
  rejections        [Rejection(pointer, criterion, draft)]        — adjudication history
  cost              Cost(jev_questions, jev_input_tokens, llm_input_tokens,
                         llm_output_tokens, retries, wall_clock_by_component)
```

Every field is always present. An empty list is the absence of a condition; `None` is never used to mean "nothing happened."

### 8.2 The context budget

State and questions **share a ~64k token window** (§2). This is a hard constraint that a long source document plus a large candidate set will hit, and nothing in the architecture prevents it implicitly.

The executor therefore budgets before every call:

- Estimate tokens for the state plus the level's question map.
- If a level exceeds the window, **split the level** — the questions are independent by construction, so splitting is always safe and costs one extra round trip.
- If a *single* question plus its state exceeds the window, **refuse loudly** with the offending pointer. Silently truncating the state would change the answer without telling anyone.

This also caps pairwise entity resolution (§5, R6), which is O(n²): resolving n candidates costs n(n−1)/2 questions. **Pairwise resolution is capped at n = 30** (435 questions) by default. Above the cap the compiler refuses and directs the caller to narrow candidates upstream — approximating with a cheaper clustering heuristic would make deduplication silently unreliable, which is worse than refusing.

---

## 9. Prior art

All early-stage. **Every one of them runs schema → Jev and drops the generative model.**

| project | what it does | relationship |
|---|---|---|
| [`Kiln-AI/jev_jsonschema`](https://github.com/Kiln-AI/jev_jsonschema) | JSON Schema → Jev questions → JSON. Refuses free-form strings, arrays, objects, `anyOf`/`oneOf`/`allOf`/`$ref`, `const`, `not`, unbounded numbers. No LLM. | Closest existing work. Its mapping table is precedent we credit. It refuses precisely the cases Jevson exists to handle. |
| [`doronp/jevc`](https://github.com/doronp/jevc) | Transpiles prompts and schemas into Jev decision programs | Replaces the prompt; keeps no generative model |
| [`alexwestco/llm-to-jev`](https://github.com/alexwestco/llm-to-jev) | Classifies prompt convertibility | Analysis step, not a runtime |
| [`eortizs/jev-json-builder`](https://github.com/eortizs/jev-json-builder) | Express middleware, typed payloads from natural language | Same schema-first shape, JS |
| [`0xjba/jev-swap`](https://github.com/0xjba/jev-swap) | Finds LLM calls that are really decisions | Adoption tooling |
| [`nokia-applied-research/AnyJev`](https://github.com/nokia-applied-research/AnyJev), [`kikoncuo/jevfire`](https://github.com/kikoncuo/jevfire) | Jev-style constrained decisions over other models | Candidate backends |

Also relevant: 12+ Jev agent skills exist for Claude Code ([madewithjev.com/skills](https://madewithjev.com/skills)). All are routing, ranking, judging, or gating. **None does schema conformance or source-grounded extraction.**

**Mapping precedent** adopted from `jev_jsonschema`: bool → `noul` at 0.5; number bounded 0–1 → raw probability; string/int enum ≤ 255 → `choice`; integer range of 2–10 levels → `score`.

### 9.1 The defensible public claim

> Handles the semantic selection that schema-first converters refuse and constrained decoding structurally cannot reach.

**Not** "first of its kind." **Not** "guaranteed JSON" — structured outputs already deliver that, and claiming it invites the correct response *"why not just use structured outputs?"*

---

## 10. Limits and refusals

| limit | consequence |
|---|---|
| Jev cannot produce free-form text | unbounded fields go to the LLM under a provider tool schema, then adjudication |
| `choice` caps at 255 options | larger candidate sets must be narrowed by code first, or the field is refused |
| `score` caps at 2–10 levels | wider ranges are re-modelled as an ordinal rubric or bucketed |
| Jev has no vision | image-derived fields are generative and adjudicated only against declared criteria |
| Jev is not a fact-checker | adjudication is only as good as the declared criteria |
| Jev has no schema awareness | all question design is Jevson's; the compiler is the product |
| Candidate coverage bounds everything | Jev can only select from the set it is given — §5.3 is the only defence |
| ~64k shared state + question window | levels split automatically; a single oversized question refuses (§8.2) |
| Pairwise entity resolution is O(n²) | capped at n = 30 candidates; above it, refuse rather than approximate (§8.2) |
| Retry is useless against identical input | Jev is deterministic; retry budgets default to zero unless extraction can widen (§5.4) |
| One source per call in v0 | `source_id` reserved in the type; multiple sources refuse at compile time (§5.5) |
| Unbounded array cardinality | not a bounded decision; source-grounded membership only, generative lists refused in v0 |
| `anyOf` / `oneOf` / `$ref` | resolved where the branch is a bounded decision (§3.2); refused loudly where not |

**Refusal over invention.** Any construct the compiler cannot map is reported before a single API call, with the offending JSON pointers. A library whose value proposition is that the output cannot be wrong must fail at compile time or it is worthless.

---

## 11. Glossary

| term | meaning |
|---|---|
| **decision node** | one bounded question with a kind, options, dependencies, and a target JSON pointer |
| **decision graph** | the full set of decision nodes for a schema + source, with dependency edges |
| **level** | a set of mutually independent nodes, resolvable in one batched Jev call |
| **candidate** | a source span offered as a possible value for a field |
| **span** | `(source_id, start, end)` — verifiable against the source by substring match |
| **option source** | where a `choice`'s options came from: schema enum, rubric, or candidate spans |
| **abstention** | `none_of_these` selected — no supplied candidate is sufficiently supported |
| **unresolved** | terminal outcome after retry budget exhaustion; a typed value, not an error |
| **entity resolution** | collapsing multiple spans referring to the same entity into one array element |
| **overflow** | candidates accepted by membership but dropped by a cardinality constraint; always retained in the result |
| **adjudication** | Jev checking a generated string against declared criteria before commit |

---

## 12. Open questions

Left open deliberately. Each is recorded in `PLAN.md` against the phase that will answer it.

- **Global ranking coherence.** Independent per-item `score` may not produce a coherent global ordering — it admits ties and encodes no pairwise preference. Semantic array ordering stays marked *unproven* until tested.
- **Entity-resolution quality.** Pairwise `noul` is the right shape and fits the batch budget (n=20 → 190 questions, one call). Whether Jev is *good* at it on real prose is untested.
- **Retry budget's real value.** Whether a second extraction pass after `none_of_these` actually recovers answers, or merely costs a round trip.
- **Calibration on this task specifically.** Jev's published calibration is not a claim about source-span disambiguation. Must be measured.
- **Criteria authoring.** Adjudication is only as good as user-written criteria. Whether we ship templates, a dry-run tool, or documentation is unsettled; the dry-run tool is the current favourite.
- **Default confidence thresholds.** Deliberately absent in v0 (§6.2). Whether a default gate becomes defensible depends on Phase 0 and Phase 4 calibration evidence.
- **Level splitting under the context budget.** Splitting a level is safe for correctness (§8.2), but Jev evaluates a state's questions jointly. Whether splitting measurably changes answers is untested.
- **Multi-source extraction.** One source per call in v0. Whether cross-document candidate selection is a real need or a distraction is unanswered.
- **Pairwise cap of 30.** Chosen against the context budget, not against measured degradation. The real ceiling may be lower.
- **JS port.** Deferred to v1. The population exists; splitting v0 across two languages does not.
- **The name.** "Jevson" couples us to a vendor whose replaceability is an explicit design goal. Kept for now, revisited at v1.

---

## 13. Changelog

### Revision 2.1 — 2026-09-28, review pass

Adversarial review of Revision 2 and the build plan. No architectural reversals; six gaps closed where the design was underspecified enough that two implementers would have disagreed.

| added | why it was missing |
|---|---|
| **The central property stated as three outcomes** (§6.1) | It was written as a binary — "valid object or refusal" — which silently excluded the legitimate abstained-optional-field case. The headline claim was imprecise. |
| **Confidence reported, not enforced** (§6.2) | A default threshold would assert calibration on this task, which is an open question, not a finding. |
| **Retry is useless against identical input** (§5.4) | Jev is deterministic, so retrying an unchanged question is guaranteed waste. Budgets now default to zero unless extraction can genuinely widen. |
| **Span semantics pinned** (§5.5) | Character vs byte offsets, interval convention, and single-source scope were all unstated; byte offsets would break verification on exactly the unicode cases the hostile suite covers. |
| **The result type pinned** (§8.1) | Referenced by every phase, defined nowhere. |
| **Context budget and the O(n²) cap** (§8.2) | The 64k shared window appeared nowhere in the architecture, and pairwise entity resolution had no ceiling — 255 candidates would have been 32,385 questions in one call. |

### Revision 2 — 2026-09-28

Revision 1 was built on a premise that did not survive scrutiny. What changed and why:

| reversed | was | now | why |
|---|---|---|---|
| **The problem statement** | "LLMs cannot be *made* to emit valid JSON; providers only narrow the failure rate" | Grammar-constrained decoding closes it structurally; shape is table stakes | The claim was false for grammar-based sampling. Building against it would have duplicated shipping technology. |
| **The headline** | "Guaranteed schema-valid JSON" | "Source-grounded structured extraction" | The old headline is satisfied by structured outputs. It invites *"why not just use those?"* and has no good answer. |
| **Mode A / Mode B** | two global modes, split on whether a schema had generative fields | removed entirely | A false dichotomy. The decision graph is compositional; a single object freely mixes all field classes. |
| **Per-field evidence commits** | LLM passes `evidence` per field, Jev decides, one field at a time | compiled decision graph, level-batched | Serialising threw away Jev's parallel-question property. Also, LLM-authored `evidence` is an unbounded influence channel over a bounded output — persuasive-but-wrong evidence yields *high* confidence. |
| **Jev's role** | gate on the commit path, auditing values | controller determining what gets constructed | Decide-then-construct is materially different from generate-then-check: the wrong branch is never built. |
| **Free-form fields** | "Jev cannot fill these, full stop" | candidate spans turn many of them into bounded choices | The largest missed idea in Revision 1. Jev never generates text; it selects among source-grounded spans. |
| **Arrays** | declared max cardinality, one `noul` per slot | membership `noul` over candidates + entity resolution + source ordering | Per-slot questions are evaluated in parallel and so cannot be coherent — slot 3 cannot know whether slot 2 was filled. |
| **Determinism** | assumed Jev values were not stable across calls | Jev is deterministic, σ = 0.01 | Factual error, corrected against measurement. Replay is consequently near-free. |
| **`anyOf` / `oneOf`** | refused | branch discrimination is a `choice` at level 0 | It is the cleanest decide-then-construct case, and the closest prior art refuses it — a free differentiator. |

Also added in Revision 2: the keyed-batching requirement (§2.1), the mandatory `none_of_these` rule (§5.3), tiered guarantees (§6), the classification model (§4), the provenance model (§5.5), and the "can be" versus "should be" discriminator (§4.1).
