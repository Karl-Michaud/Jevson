# Jevson — design

> **Status:** Design document, Revision 9.1, 2026-09-29. Pre-implementation.
>
> **This document is the SSOT for Jevson.** It carries everything an agent or contributor needs to work on the project: what the library is, what it guarantees, the architecture, the vocabulary, the constraints of the model it sits on, and the rules that are not open for reinterpretation. The build sequence lives in [`PLAN.md`](PLAN.md).
>
> **One line:** Jevson is a general-purpose, open-source schema compiler for source-grounded structured extraction. It turns a Pydantic model or JSON Schema into a graph of bounded decisions, has Jev make them, assembles the result in code, and records for every field how it was decided — with the source span or declared option, and the probability, where Jev decided it — or a typed reason it could not be resolved.
>
> **Evidence.** Every factual claim in this document and `PLAN.md` about Jev, about other tools, or about measured behaviour carries an evidence tag such as **[P3]** or **[V-models]**, resolved in [`docs/EVIDENCE.md`](EVIDENCE.md) to the probe script, vendor page, or source that established it. A claim without a tag is a design decision, or arithmetic shown in place.

---

## 1. The problem — stated correctly

The obvious framing of this library is *"guarantee that an LLM's JSON output matches the schema."* **That framing is wrong, and building against it would be building something that already exists.**

Grammar-constrained decoding already makes an out-of-enum value, a misspelled key, or a wrong nesting depth very hard to produce *while the model is sampling*. It ships in OpenAI Structured Outputs, Anthropic strict tool schemas, vLLM, Outlines, XGrammar, and llama.cpp GBNF **[X1]**. It is not unconditional — refusals, `max_tokens` truncation, silently skipped unsupported keywords, and (for Anthropic) enum values differing only in capitalisation can still produce non-conforming output **[X1]** — which is why Jevson validates everything it assembles (DESIGN §6). But shape is not the unsolved problem.

The unsolved problem is this:

```json
{ "first_name": "Whitfield", "last_name": "Dana" }
```

Perfectly schema-valid. Completely wrong. A grammar cannot see it, and `jsonschema` cannot see it.

| failure | example | what exists today |
|---|---|---|
| invalid syntax / shape / out-of-enum | missing brace, key at wrong depth | constrained decoding **[X1]**, plus a final validation pass |
| constraint violation | `maxItems: 5`, six items | `jsonschema` |
| **value absent from source** | a plausible name that appears nowhere in the document | grounding checks: LangExtract character alignment, Instructor quote validation **[X2]**; TypeSafe's own candidate-plus-`none` cookbook **[V-preparsed]** |
| **wrong entity chosen** | the vendor's address extracted as the billing address | commercial ambiguity flags (Sensible, Extend) **[X2]**; TypeSafe's candidate cookbook **[V-preparsed]** |
| **silent confidence** | any of the above, with no signal | per-field scores in Cleanlab TLM, LlamaExtract, Azure Document Intelligence, Reducto, AWS Bedrock Data Automation **[X2]** — mostly proprietary, none deterministic |
| **wrong branch taken** | a `Person` object built where the source described an `Organization` | no tool found **[X2]** |

**Every mechanism Jevson uses already exists somewhere.** Selecting among pre-extracted candidates with a `none` escape hatch is TypeSafe's documented extraction pattern **[V-preparsed]**, and several open projects implement it for single fields or fixed record types **[X3]**. What we did not find is the combination as a **general schema compiler** **[X3]**:

- arbitrary Pydantic / JSON Schema compiled to a decision graph — nested objects, arrays, and unions decided *before* construction;
- level-batched execution that respects Jev's two context limits;
- source-grounded arrays with entity resolution that refuses to merge on contradictory evidence;
- generative fields admitted only after passing declared criteria;
- a typed three-outcome result, proven by an adversarial suite.

That combination is the product. It generalises the vendor's "select, don't generate" pattern from a recipe into a library.

### 1.1 The one-line pitch to a pipeline author

> Jevson is the extraction node in your chain that tells you when it doesn't know — and shows you where each value came from.

A LangChain, LlamaIndex, or plain-Python pipeline can branch on Jevson's result: commit, fall back, escalate to review, or abort. **Two honest limits belong in the pitch:** provenance proves where a value came from, not that the source is honest (DESIGN §5.8); and abstention covers source-selected fields and is measured, not guaranteed (DESIGN §6).

---

## 2. Jev — the constraints that shape everything

Jev is TypeSafe's constrained "System One" model, released in September 2026 in early access **[V-launch]**. **Official documentation: <https://docs.typesafe.ai/>** **[V-index]**. (The site `jevapi.dev` is a third-party summary that states it is not affiliated with TypeSafe **[X4]**; do not cite it.)

**Interface.** `POST https://api.typesafe.ai/v1/systemone`, `Authorization: Bearer <key>`, body `{model, state, questions}` **[V-api]**. State is text or JSON. Questions are a map from key to a typed question **[V-api]**. **The question key is not sent to the model** **[V-primitives, P1]**.

**Model version.** Jevson always pins an exact version. `jev-1.13.0` is accepted; `jev-1.13` is rejected; `jev-latest` is an alias that moves when new releases ship **[P9, V-models]**. Every measurement in this repository is against `jev-1.13.0`. Several vendor cookbooks set `jev-1.12` **[V-cookbooks]**; nothing from them transfers to 1.13 without re-measurement.

### 2.1 The three primitives — as measured

| primitive | request | response | notes |
|---|---|---|---|
| `noul` | `instructions` | `noul`: probability of yes | **no confidence field** **[V-confidence, P2]** |
| `choice` | `instructions`, `criteria` {option: description} | `choice`, `probabilities` per option, `confidence` | 2–255 options in practice; the API accepts 1 **[P2]** |
| `score` | `instructions`, `criteria` (ordered levels) | `score` (a probability-weighted **float**, not a level), `probabilities`, `confidence`, `legend` (echoes the level texts) | 2–10 levels in practice; the API accepts 1 **[P2, L4, P13]** |

- **Probabilities vs `confidence`.** The vendor describes its probabilities as calibrated **[V-systemone, V-primer]**. `confidence` is a statistic computed from the distribution; the vendor's documented approximation (shown for three options) is written in terms of the number of options **[V-confidence]** (some vendor pages also call it calibrated). Because it changes with the option count — adding `none_of_these` changes it — Jevson reports it but makes every calibration claim and bar about **probabilities**.
- **Values are rounded to two decimals.** Jevson handles them as **integer hundredths**. Distributions sum to 1.00 or 0.99 (4 of 630 observed at 0.99) **[L17]**. Rounding K values can move the sum by at most ⌈K/2⌉ hundredths; the tolerance is min(⌈K/2⌉, 5) hundredths, since at most 1 was observed at K ≤ 11 **[L17]** and 0 across 20 easy, single-correct-option answers at K = 51 and K = 255 **[P23]**, and outside it the answer is invalid. The selected option is the argmax in hundredths; if the vendor's `choice` field names a different option and the top-two margin is outside the tie band, the answer is invalid.
- **Lower bounds are not enforced by the API.** A one-option choice returns p = 1.0; a one-level score is accepted **[P2]**. The compiler enforces ≥ 2 options and ≥ 2 levels itself.
- **Validation errors are HTTP 400**, not the documented 422, with a JSON `detail` naming the problem **[P2]**.

### 2.2 Limits

| limit | value | behaviour when exceeded | evidence |
|---|---|---|---|
| state + **longest single question** | ~32,768 tokens | HTTP 400 `max_tokens_exceeded`; splitting cannot help | **[V-models, P3]** |
| state + **all questions** | ~65,536 tokens | HTTP 400 `max_tokens_exceeded`; splitting the level helps | **[V-models, P3]** |
| options per `choice` | 255 | HTTP 400 | **[P2]** |
| levels per `score` | 10 | HTTP 400 | **[P2]** |
| questions per request | no count limit; token budget only (2,515 accepted) | — | **[P2, P3]** |
| rate | ~1,200 requests/min, ~250k tokens/s; "can change without notice" | 429 | **[V-models]** |

The 400 body carries no token counts and no tokenizer is published **[P3]**, so Jevson's estimator is conservative and is checked against `usage.input_tokens` (DESIGN §8.2). **No silent truncation was observed**: every over-limit request was rejected **[P3]**.

**What fits.** Option descriptions dominate a large `choice`: ~18 tokens per option for bare short spans, ~27 for realistic 5–80-character spans, ~80 with a ±70-character context window **[P14]**. With a realistic 255-option question, the largest source accepted was ~108,000 characters of plain English prose or ~62,000 characters of dense business text **[P14]**; with context windows on every option, the state is left ~12k tokens (~30,000–50,000 characters) **[P14]**. Default declarations are far smaller (DESIGN §8.2).

### 2.3 Behaviour — as measured

- **Near-deterministic, not deterministic.** Byte-identical requests return different probabilities. Bool nouls jitter least (per-question range ≤ 0.05 for 90% of 200 contract questions over 10 repeats **[P12]**); **choices jitter more** (range p90 0.11, max 0.21 over 180 enum questions × 10 repeats; the argmax flipped on 14/180 questions) **[P20]**; and **ambiguous entity-pair nouls ranged up to 0.37** (0.22–0.59, sd 0.13) over 12 identical calls, with 16 of 1,824 pair decisions flipping between two identical runs **[P12]**. On 40 ambiguous yes/no questions × 25 repeats × 2 sessions, no decision away from the threshold flipped **[P1]**. The vendor's σ ≈ 0.01 was measured with a fresh `uid` in each call, not on identical input **[V-consistency]**.
- **Exact ties are rare; near-threshold flips are not.** An exact 0.50 appeared once in 2,000 bool observations; 1.1% landed within ±0.05 of 0.5; 2 of 200 questions flipped across 10 identical calls, both hedged clauses **[P12]**. The tie margin that removes flips is therefore wider than exact equality (DESIGN §6.2).
- **Questions are independent.** Question keys, map order, and co-batched questions have no measurable effect (0/120 selection changes batched vs alone) **[P1, V-primitives]**. Splitting a level is answer-neutral.
- **Adding questions is nearly free.** State is billed **once per request**; each short noul adds ~22–26 tokens; overhead is ~280 tokens per request **[P3]**. Latency p50: 0.15 s for 1 question, 0.17 s for 100, 0.22 s for 300 over a small state **[P8]**.
- **Cost.** $0.042 per million input tokens, output free **[V-models]**. Cost per decision depends on batching; there is no single constant. `usage.input_tokens` was present on every successful response and `x-typesafe-request-id` on every response whose headers were captured **[P8]**.

### 2.4 Hard limits and known weaknesses

- Cannot produce free-form text, arrays, or nested objects; does not generate **[V-jagged]**. Cannot read images **[V-models]**; does not generate explanations of its reasoning **[V-systemone]**.
- **Has no schema awareness of its own.** It reads structure in state and instructions well **[V-advanced]**, but every question Jevson asks is one Jevson constructed.
- **Referencing state by array position fails.** Asking about `items[137]` in a 320-item list gave 62% wrong answers; keyed references (`items.k137`), inlined values, and one request per item gave 0/320 **[P4]**. The error grows with the **length of the indexed list in state**, not with questions per request. The vendor's own examples use `items[{i}]` **[V-jagged]**, so this is a trap.
- **Content in the state can steer answers** **[V-jagged]**. Measured: a note in an invoice advocating the wrong span moved candidate selection 20/20 (advocacy note, confidence up to 0.91; injected instruction, up to 1.00) and defeated `none_of_these` 20/20; the same injections in an LLM *draft* did not flip adjudication (0/80) **[P7]**. See DESIGN §5.8.
- **Literal reading; negations and indirection cost accuracy** **[V-jagged]**. Questions are phrased positively and directly (DESIGN §5.2).
- **No arithmetic, counting, or date comparison** **[V-jagged]** — class F in DESIGN §4, always code.
- **Distractors hurt** **[V-jagged]**; in the abstention pilot, long multi-entity documents were the only regime where `none_of_these` failed **[P5]**.
- **Flat distributions on wide scales.** On 10-level scores, 8 of 12 answers had no level above 0.5 **[P13]**; prefer narrow rubrics.
- **English is the primary training language**; other languages, including CJK scripts, are handled but not equally well **[V-models]**.

---

## 3. Architecture

```text
      SCHEMA                                    SOURCE
   (Pydantic or                            (document / text)
    JSON Schema)                                   │
         │                                         │
         ▼                                         │
   ┌─────────────┐                                 │
   │ NORMALISER  │ DESIGN §3.5: $ref, nullable,    │
   │  + COMPILER │ const, Decimal, x-jevson        │
   └──────┬──────┘                                 │
          ▼                                        ▼
   ┌──────────────────────────────────────────────────┐
   │ DECISION GRAPH                                   │
   │   decision nodes (Jev: choice | score | noul)    │
   │   step nodes (external: extract | generate)      │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │ EXECUTOR   preflight budget → topological levels │
   │   steps run through Extractor / LLM protocols    │
   │   decisions: one keyed Jev call per level        │
   │   bounded retry / redraft loops live here        │
   └────────────────────┬─────────────────────────────┘
                        ▼
              BACKEND (protocol): JevBackend │ FakeBackend │ CachingBackend │ AnyJev-style
                        ▼
   ┌──────────────────────────────────────────────────┐
   │ ASSEMBLER  entity resolution, ordering,          │
   │            cardinality, overflow, class F parse  │
   └────────────────────┬─────────────────────────────┘
                        ▼
          validate against the original schema
                        ▼
                     Result (DESIGN §8.1)
```

### 3.1 The central abstraction is the decision graph

Jevson is not "JSON Schema → Jev questions" — that is what `jev_jsonschema` does, and why it refuses free-form strings, arrays, objects, and unions **[X3]**. Jevson is:

```text
Schema + Source  →  Decision Graph  →  execution (steps + Jev levels)
                 →  Resolved graph  →  JSON assembly  →  validation
```

A graph has two node types. **Only decision nodes are sent to Jev.**

```text
DecisionNode
  id             target instance pointer + role, e.g. /customer/tier#choice, /items#pair:c3:c7;
                 a retry or redraft of the same node is recorded in Result.decisions as id@n
  kind           choice | score | noul
  question       compiled from a versioned template (DESIGN §5.2); never references state by position
  options        opaque option ids → descriptions; or ordered levels; or none (noul)
  option_source  schema_enum | schema_rubric | candidate_spans | predicate
  dependencies   node ids that must resolve first
  provenance     kind of provenance a resolved value carries
  target         JSON pointer into the object under construction

StepNode
  id, kind       extract | generate
  protocol       Extractor | LLM
  dependencies   as above
  produces       candidate set (extract) or draft (generate) consumed by dependent decisions
```

**Compilation and execution are separate.** The compiler answers *what decisions are necessary*; the executor answers *what can run together, and in what order*, and it runs step nodes through their protocols. Loops that depend on answers — retry after abstention (DESIGN §5.5), redraft after rejection (DESIGN §6.3) — are executor policies, not graph edges, so the graph stays acyclic.

### 3.2 Decide-then-construct, not generate-then-check

**Audit architecture (not built):** an LLM builds a `Person`, Jev objects, the work is discarded, retry.

**Construction architecture (built):**

```text
Jev: Person 0.04 / Organization 0.96
→ execute only the Organization branch's nodes → assemble
```

**Every branch is compiled and validated up front** by `compile_schema()`, so refusal stays total and happens before any network call (R14). Only the selected branch is *executed*. The wrong branch's steps — extraction, generation — never run. A branch discriminator has no `none_of_these` in v0; a tie or invalid answer leaves the whole subtree `Unresolved`. Two branches whose required properties and descriptions are identical after normalisation are *undiscriminable* and refuse at compile time.

The vendor also documents *speculative fan-out*: ask every branch's questions in one call and let code discard the irrelevant ones **[V-fanout]**. For branches whose nodes are pure Jev questions, that saves a round trip at a small token cost; for branches with steps it would run work whose output is discarded. The choice is measured in `PLAN.md` Phase 6.

### 3.3 Level batching

```text
decision graph → dependency analysis → topological levels
              → one batched, keyed Jev call per level (split only by DESIGN §8.2)
```

Because state is billed once per request and questions are independent **[P1, P3]**, batching is both cheaper and answer-neutral. A typical object resolves in **1–3 Jev calls**: one level for everything that depends only on extraction, one more for each union discriminator above it. Array membership and pairwise entity questions are asked over all candidates in the *same* level, not only over accepted members, so arrays add no level.

### 3.4 Worked example

Schema (Pydantic, abbreviated):

```python
class Invoice(BaseModel):
    vendor: str = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "llm", "entity_type": "organization"}}})
    total: Decimal = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "money"}}})
    billing_address: str = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "llm"}}})
    line_items: list[str] = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "llm", "entity_type": "product"}}})
    category: Literal["software", "hardware", "services"]
```

Source: an invoice naming two companies, two addresses, and a subtotal, tax, and total.

1. **Normaliser/compiler.** `category` → `choice` over declared values. `vendor`, `billing_address` → source selection over candidate spans. `total` (Pydantic `Decimal`, normalised to a decimal value emitted as a string) → source selection over *money* candidates, then a deterministic parse of the selected span (class F on a selected span — Jev never does arithmetic). `line_items` → membership `noul` per candidate plus entity resolution.
2. **Extract steps** return verified candidate spans with offsets: two organisations, two addresses, three money amounts, five line-item strings.
3. **Graph:** every decision depends only on the extract steps → **one decision level → one Jev call**. Candidates are placed in state as an object keyed by opaque ids (`c0…cN`), never by position (R13).
4. **Jev** returns selections, distributions, and `none_of_these` probabilities in one pass.
5. **Assembler** resolves line-item entities (DESIGN §5.7), orders them by source offset, enforces `maxItems` retaining overflow, parses the selected total, inserts values by span.
6. **Validate** against the original schema. Provenance: `vendor ← [142,151)`, `total ← [610,617)`, `category ← declared option`.

### 3.5 Normalisation and field declarations

**Normalisation** (class A, before mapping; the compiler reads Pydantic's `mode="validation"` schema, with Pydantic ≥ 2.12, whose output is byte-identical to the latest release on 20 cases while 2.8–2.11 differ **[L18]**) **[L3, L16]**:

| emitted construct | normalised to |
|---|---|
| static, acyclic local `$ref` / `$defs` (nested models, `Enum` classes) | inlined, merging any sibling keywords on the referencing property (Pydantic places `x-jevson`, `description`, and `default` next to the `$ref`) **[L18]**; node ids come from **instance** pointers, so two fields of one `$defs` type get distinct ids |
| `anyOf: [T, {type: null}]`, `type: [T, "null"]` (`Optional[T]`); a flat `anyOf` whose non-null branches are themselves one normalisable type (e.g. `Optional[Decimal]` emits three branches) | the null branch is stripped first; nullable T, no discrimination node **[L18]** |
| `const`, single-value `Literal`, single-member `Enum` (emitted as a `$ref` to a one-value `enum`) | deterministic constant **[L18]** |
| `Decimal` (`anyOf [number, string with pattern]`) | a decimal value, emitted in `.value` as the **string** form, because `jsonschema` rejects valid cents under `multipleOf: 0.01` as floats (11,426 of 100,001 values) and Pydantic's unanchored pattern accepts too many digits **[L18]** |
| flat `allOf` of object schemas (raw JSON Schema; Pydantic ≥ 2.10 emits none **[L18]**) | merged; anything else refused |
| `oneOf` + `discriminator` (Pydantic discriminated unions) | a union, resolved by `PLAN.md` Phase 6 |
| `exclusiveMinimum`/`exclusiveMaximum`, `multipleOf`, `format` | kept for final validation only |
| recursive or dynamic `$ref`, `dict[str, X]` (`additionalProperties` schema), tuples (`prefixItems`), `Any`, `bytes` | refused with a named reason (tracked in `PLAN.md` §9) |

**Field declarations.** Per-field configuration lives in one keyword, **`x-jevson`**. Pydantic users write `Field(json_schema_extra={"x-jevson": {...}})`, so the emitted JSON Schema is identical to what a raw-schema user writes; Pydantic places it on the property, beside any `$ref` **[L18]**. Keys:

```text
source:    { extractor: <name>, entity_type?: <name>, direct_extraction?: bool,
             scope?: <text>, max_candidates?: int (default 50, ≤ 254),
             max_candidate_chars?: int (default 120), locale?: <BCP 47 tag> }
generate:  { criteria: [<text>], rubric?: {levels: [...], minimum: <level>},
             instructions?: <text>, max_draft_chars?: int }
ordinal:   true            # an integer range is an ordinal rating → score (DESIGN §4.2)
order:     source | semantic   # semantic refuses in v0 (R7)
question:  <text>          # overrides the compiled field description
```

- A **leaf** field (not an object or array) with a `default` and no `x-jevson` key other than `order` is **class A**: it is omitted from `.value` so the default applies (`decided_by: code`); it is neither decided nor refused. To have it decided, declare `source` or `generate`, or add `x-jevson.question` (or `ordinal: true`) to a bool, enum, or integer-range field. An **object or array** field's default does not make it class A: it is compiled from its descendants' or items' declarations, and it is class A only if nothing in it would be decided; its absence then follows DESIGN §5.6.
- An unbounded `string` or `number` field (including `format` strings and `Decimal`) with no default and neither `source` nor `generate` **refuses (class G)** — unless a default extractor is configured, in which case it is source-selected with that extractor. The built-in pattern extractors (`money`, `date`, `email`, `phone`, `url`) are used **only when declared** by name, so a `weight_kg: Decimal` is never mistaken for money.
- Because class G depends on configuration, `compile_schema(schema, extractors={names}, default_extractor=None)` receives the extractor *names* (not instances); an `x-jevson.source.extractor` naming an unknown extractor refuses.
- Library-wide settings live in one `JevsonConfig`: the tie margin, `conflict_floor`, the entity rule variant, the pairwise cap, entity-type normalisers, the source screen, `default_extractor`, `raise_on_unresolved_required`, `step_timeout_s`, and the retry, redraft, and transport budgets. `resolve()` may override the retry and redraft budgets per call. `locale` (on a source declaration) fixes how class F reads decimal and grouping separators and numeric dates; the default is `en-US` (`,` groups thousands, `.` marks decimals, numeric dates are month-first), so `$1,204` is 1204 and `$1,204.50` is 1204.50. Parsing is strict (grouping separators only between groups of three digits); a selected span that does not parse under the field's locale — `1.204,50` under the default — is `Unresolved(unparseable)`; ISO dates and dates with month names parse under any locale. A `locale` tag Jevson does not support refuses at compile time.
- A field can declare `source` or `generate`, not both.
- Unknown `x-jevson` keys refuse at compile time.

---

## 4. The classification model

Every schema construct and extraction operation falls into exactly one class. This taxonomy is the compiler's backbone and the instrument that decides v0's scope (`PLAN.md` Phase 0).

| class | name | handled by | example |
|---|---|---|---|
| **A** | Deterministic | ordinary code | required fields, nesting, defaults, types, constants, nullable |
| **B** | Grammar | constrained decoding, where the caller's LLM supports it | key spelling in an LLM draft |
| **C** | Bounded semantic decision | **Jev** | classification, ordinal rating, boolean predicate, union discrimination |
| **D** | Source selection | **candidate spans + Jev** | which of four spans is the billing address |
| **E** | Unbounded generation | LLM, then Jev adjudication | a summary, a synthesised description |
| **F** | Computational | deterministic code | parsing a selected money span, date arithmetic, unit conversion |
| **G** | Unsupported | explicit refusal | anything the compiler cannot map |

### 4.1 "Can be a Jev question" is not "should be a Jev question"

When the value is determined by the schema and the source is not needed, Jev adds cost and nothing else. By contrast, *"which of these three people is the customer?"* cannot be answered by the schema or a grammar — the value must be selected from evidence.

Every taxonomy entry therefore records its **existing alternatives** — constrained decoding, plain code, the vendor's cookbooks, and the open projects in DESIGN §9 **[X3]**.

### 4.2 Mapping rules — corrected against evidence

The mapping from `jev_jsonschema` **[X3]** is adopted with corrections:

| construct | mapping | note |
|---|---|---|
| `bool` | `noul`; true iff p ≥ 0.56; false iff p ≤ 0.44; 0.45–0.55 inclusive is `Unresolved(tie)` | the band that removed every true↔false flip across 10 identical calls on 200 questions counted 0.45 and 0.55 as ties **[P12]**; it is the tie margin of DESIGN §6.2 applied to a binary answer |
| string/int enum, 2–255 values | `choice` over opaque ids; a top-two margin ≤ 0.10 → `Unresolved(tie)` | a ±0.05 band left 11/180 argmax flips; a 0.10 margin left 1/180, converting 7.8% of answers to ties **[P20]** |
| integer range 2–10 **declared `ordinal: true`** | `score`; the value is the **most probable level**; a top-two margin ≤ 0.10 → tie | the vendor `score` is a probability-weighted float (e.g. 3.20 for p = [.45,0,0,0,.55]) that can fail `type: integer` **[L4]**; round(score) and argmax disagreed on 8/60 live scores **[P13]** |
| integer range not declared ordinal (a count, a quantity) | a number: source-selected (class D + F) or refused | counts are not ratings; Jev does not count **[V-jagged]** |
| number bounded 0–1 | **not** a probability; a number like any other | mapping it to Jev's probability writes a belief into value fields such as `tax_rate: 0.20` **[L4]** |
| array of enum (multi-label) | one membership `noul` per declared value, with the bool rule; elements in declared enum order; `maxItems` keeps the first k in that order, overflow retained; a tied value is `Unresolved(tie)` at the array pointer naming the value, the others emitted | `PLAN.md` Phase 7 |

---

## 5. Candidates, provenance, and abstention

### 5.1 Jev cannot generate a string — but it can choose one

Given *"Dana Whitfield, VP of Marketing at Acme Corp, met with John Smith from Globex yesterday"*, an extract step produces verified candidate spans and the question becomes a `choice`:

```text
choice(/customer/name):
    c0  "Dana Whitfield"   [0, 14)
    c1  "John Smith"       [52, 62)
    none_of_these
→ c0  p=0.91
```

Jev never generates the text. Code inserts the selected span. This is the vendor's documented pattern **[V-preparsed]**; Jevson's contribution is compiling it from a schema and carrying it through the rest of the pipeline.

**Options are opaque ids** (`c0…cN`), with the span text in the option description. Text keys and opaque ids performed equivalently (35/36 identical selections) **[P5]**.

**Identical text at several offsets.** When a candidate's text occurs more than once in the source, **every occurrence is offered as its own option, with a ±40-character context window in its description.** With context windows Jev picked the right occurrence 40/40; with text alone it was at chance, 22/40 **[P15]**. **`max_candidates` counts options after this expansion**; a field whose occurrences exceed it is `Unresolved(too_many_candidates)`, with the distinct texts and occurrence counts in `detail`. Offering every occurrence matters: when only a wrong-role occurrence was offered, it was committed 48–83% of the time rather than abstained on — the value text is right but the provenance is wrong **[P15]**. Code finds every occurrence by exact match. Mixing context-bearing and bare options in one choice did not bias decisions out of sample (repeated-text answers 48/48 mixed vs 20/48 all bare; unique answers 48/48 in every format), though ~0.10 of probability mass shifted toward context-bearing options when the answer was absent and 1 of 48 such cases committed one **[P19]**; the test was near ceiling.

### 5.2 Questions are compiled from versioned templates

Question wording decides accuracy, so it is code, not ad hoc prose. `compile/questions.py` renders every question from a template with a recorded `QUESTION_TEMPLATE_VERSION`; Phase 0 probes use the same templates, so their verdicts carry over.

Template rules, each backed by evidence:

- **Demand the complete value.** Candidate questions ask: "Which of these is the complete *<field>* as written in the source? A partial value — for example a street without its city, or a date without its year — is not acceptable.", and `none_of_these` reads "None of the other options is the complete *<field>* as written in the source; a partial value does not count." This exact text was tested out of sample: with the full value among 4 competitors it was chosen 72/72 with and without the wording; when only partial variants were offered, correct abstention rose from 19/72 to 72/72 **[P18]**. An earlier variant cut lone partial commits from 32/42 to 0/42 **[P11]**.
- **When the source itself states only a partial value**, the intended answer is abstention (the field is then absent). Measured compliance depends on the field: addresses and dates abstained, while names, phones, and venues often committed the longest partial (15/36 abstained overall) **[P18]**. This is a stated limit, re-measured in Phase 0.
- **Positive, direct phrasing; no negations** **[V-jagged]**.
- **Level state layout.** A level's state is `{"source": …}` plus, when present, `"candidates": {<opaque id>: …}` and `"drafts": {<field node id>: <draft>}`; each question names the entries it is about by key (R13). Candidate texts appear in option descriptions; `candidates` in state is used only when a noul (membership, pair) references a candidate, with ids unique within the level, and preflight counts it in the state size. Injected drafts did not flip verdicts under a single `draft` key **[P7]**; the keyed multi-draft layout is re-measured by the Phase 4 injection regression, and if it does worse, adjudication issues one call per draft.
- **Scope from the schema.** The field's `description` (or `x-jevson.question`) and `x-jevson.source.scope` are rendered into the question. A generic scoping hint did not improve accuracy measurably (abstention 32/36 → 35/36, present-answer accuracy 36/36 → 33/36) **[P16]**, so no hint is added by default.

### 5.3 Single candidates still get a question

A lone extracted candidate is **not** committed unchecked by default: the extractor is the weak link, and a lone wrong candidate is exactly the wrong-but-valid failure. The default is a two-option `choice([c0, none_of_these])`, batched into the existing level at near-zero marginal cost **[P3, P8]**. In the pilot it abstained on 84/84 wrong-role lone candidates and falsely abstained on 2/42 correct ones, and behaved the same as the candidate among 2–3 competitors **[P11]**. A field may opt into `direct_extraction: true`: a lone verified candidate then commits without Jev, carries no probability, and is listed in `Result.ungated`; zero candidates follow DESIGN §5.6; two or more distinct candidates (counted after the pre-filter below), or one text occurring at several offsets (DESIGN §5.1), are asked as an ordinary choice with `none_of_these` and the field is not ungated.

**Zero candidates** resolve without a Jev call (DESIGN §5.6). **More than `max_candidates`** (default 50; hard cap 254, leaving one option for `none_of_these`) is a run-time condition — the compiler never sees a source — and yields `Unresolved(too_many_candidates)` rather than silent truncation. **For fields whose value is the verbatim span**, candidates that cannot satisfy the field's own string constraints (`maxLength`, `minLength`, `pattern`) are rejected before the question is asked, and counted. For class F fields the constraints apply to the parsed value after selection, and a failure is reported in `violations`.

### 5.4 `none_of_these` is mandatory, and it is the safety property

Without it the architecture is **more dangerous than asking an LLM directly**: Jev's probabilities are relative to the options it was handed **[V-jagged]**, so a missing correct answer is invisible. Every candidate-backed `choice` compiles with a described `none_of_these` option:

```text
SELECT(candidate)   or   ABSTAIN(none_of_these)
```

`none_of_these` means *no supplied candidate is sufficiently supported as the answer* — the source may genuinely not contain one, or extraction may have missed it.

**Pilot evidence** (synthetic, author-written; not the pre-registered Phase 0 probe) **[P5]**: on short documents and trap documents (superseded values, negations, near-duplicate names), selection and abstention were at ceiling. In long, multi-entity documents, abstention when the answer was absent fell to 32/36 = 0.89 (95% CI 0.75–0.96); three of the four failures were superseded due dates. A separate yes/no gate ("does any candidate fill this field?") was *worse* (0.56), because in a multi-entity document some candidate usually is *a* seller, just not *the* one. **The choice-with-`none_of_these` design stays; a noul gate is not used as the abstention mechanism.**

### 5.5 Abstention lifecycle

```text
extract step → verified candidates
      ├── zero candidates ──────────────────────────► absent or Unresolved(no_candidates) (DESIGN §5.6)
      ├── more than max_candidates ─────────────────► Unresolved(too_many_candidates)
      ↓
   Jev choice (candidates + none_of_these)
      ├── candidate selected ─────────────────────────► value + provenance
      ├── tie (top-two margin ≤ 0.10) ────────────────► Unresolved(tie)
      └── none_of_these
              ↓
        retry: extractor re-invoked with seen spans as exclusions
              ├── no new verified span ──────────────► as abstention (no Jev call)
              └── choice over OLD ∪ NEW + none_of_these
                     ├── candidate selected ─────────► value + provenance
                     └── none_of_these ─────────────► as abstention (DESIGN §5.6)
```

- **Retry only helps if the input changes.** Retry against a **schema-derived** option set has a budget of **zero**. Retry against a **candidate-derived** set re-extracts; its Jev call is issued only if extraction returns at least one verified span not seen before.
- **The retry offers old ∪ new candidates**, because Jev's distribution is relative to the offered set **[V-jagged]**.
- **Retries for every field that abstained in one level are batched** into one follow-up call (subject to DESIGN §8.2).
- **The default budget of one is provisional**, with a two-sided bar measured in `PLAN.md` Phase 5: the retry stays on only if it recovers ≥ 10% of abstentions *where the answer was present*, **and** raises the false-commit rate on truly-absent cases by ≤ 2 points. A retry costs a full extraction, which is caller-priced; `retry_budget` is a documented per-call parameter.

### 5.6 Absent, null, and unresolved

An abstention is not an error: the source may simply not contain the value. What it produces depends on the schema:

| field | abstention (or zero candidates) yields | recorded in |
|---|---|---|
| not required (with or without a default, nullable or not) | key omitted — a Pydantic caller's `model_validate` then applies the declared default | `Result.absent` |
| required and nullable (`Optional[T]` with no default) | `null` | `Result.absent` |
| required and not nullable | key omitted | `Result.unresolved` (reason `abstained`, or `no_candidates`) |

A nullable field with a non-null default (`Optional[str] = "x"`) is not required, so it is omitted and the caller receives `"x"`, not `None` **[L18]**.

**Objects.** An object node is abstained when it has at least one class D (source-selected) descendant, every class D descendant abstained or had no candidates, and none committed — a source-grounded array counts as abstained when it accepted no member; a `known=` value inside it counts as committed. Class A, C, and E descendants do not count: when the object is abstained their decisions stay in `Result.decisions` but their values are discarded, and a `generate` step under the object is not run (the object's class D decisions, including their retries, are ordered before it; generate steps at the root wait for nothing, since the root is never abstained). An object with no class D descendant is never abstained, and **the root object is never abstained**. The abstained object then follows the table itself (omitted, `null`, or `Unresolved(abstained)`), recorded once at the object pointer. If any class D descendant committed, each required descendant that abstained is `Unresolved(abstained)` as usual. So `Optional[Address] = None` on an invoice with no shipping address is simply absent, even if `Address` has an enum field.

`complete` is therefore true for a document that legitimately lacks an optional field, and callers who treat absence as suspicious read `Result.absent`. Because abstention cannot tell "not in the source" from "the extractor missed it", `absent` carries the candidates seen and the abstain probability.

### 5.7 Entity resolution

Pairwise `noul` answers are independent, so they can contradict each other: *A = B*, *B = C*, *A ≠ C*. In the round-1 pilot, 95.1% of pairs were judged correctly but **42% of documents contained a non-transitive triple** **[P6]**; the same pair can move by up to 0.37 across identical calls **[P12]**. Resolution runs in stages:

1. **Deterministic pre-merge, no model.** Candidates of one entity type whose text is identical under that type's `Normalizer` merge before any question is asked. **The default normaliser is lossless on case:** Unicode NFC plus whitespace collapse. Casefolding is opt-in per entity type, because it silently merges `US`/`us`, `Apple`/`apple`, `IT`/`it`, `CAT`/`cat` **[L1]**. The normaliser never merges initials or first names (`Sam`/`Samuel`, `D. Whitman`), which were the pilot's dominant failure **[P6]**.
2. **Pairwise `noul`** over the remaining candidates, asked in the same level as membership (capped, DESIGN §8.2). Components are built over **accepted members only**: pair answers involving non-members are recorded in `decisions` and ignored, so a rejected candidate never bridges two members. Components are the connected components of member pairs with p(same) > 0.5.
3. **Internal consistency (always on).** A component containing a pair at or below `conflict_floor` — a confident "different" — is a possible wrong merge and becomes `Unresolved(entity_conflict)`, naming its spans and the offending pairs. Internal pairs above the floor are tolerated, so a chain such as *Dana* ↔ *Dana Whitfield* ↔ *Ms. Whitfield* still merges.
4. **Cross-component consistency (a variant, chosen in Phase 0).** Additionally, a component linked to another by a pair in (`conflict_floor`, 0.5] is a possible split, which would emit a duplicate element; under this variant both components become `Unresolved(entity_conflict)`.
5. Other components are emitted, and an array with any unresolved component is incomplete. A membership tie on a mention likewise leaves its array incomplete. With ~1.1% of pilot yes/no answers and 2.6% of pilot candidate choices inside the margin **[P12, P22]** (membership nouls themselves not yet measured), long arrays will sometimes be incomplete for this reason alone; Phase 7 reports how often.

**Why the variant is not settled.** On 48 pilot documents (1,824 pairs, two identical runs) the internal rule alone was silently wrong on 5/133 and 6/134 components, mostly *splits*, and adding the cross-component condition gave 0/133 and 0/134 at 113/133 and 109/134 correct versus 117 — but that was found and scored in-sample **[P10]**. Out of sample, on 80 new documents in new domains (5,410 pairs, two runs), **no split occurred in 160 document-runs**, both rules were silently wrong on 1/312 components (a consistent-but-wrong merge), and the cross-component condition only blanked 8–9 otherwise-correct components; each uncertain cross pair blanks two components **[P17]**. Plain connected components were silently wrong on 25/312 **[P17]**. The non-transitive rate is template-dependent: 42% of documents in the first pilot, 12% and 60% on two later sets **[P6, P17]**. `PLAN.md` Phase 0 probe 4 chooses between the internal rule and the two-directional variant on real prose by a pre-registered rule.

6. **`conflict_floor` has no default until Phase 0 measures it**, by a rule fixed before the data is seen. The rule selected the top of its grid on every full pilot corpus — 0.30 when the grid ended there (0.20 on one subset), 0.45 when it was extended **[P10, P17]** — so in practice it may mean "any internal pair at or below 0.45 is a conflict". Phase 0 records whether the grid top binds. Until Phase 0 sets it, tests pass an explicit floor.

**Stated limit:** a partition that is *consistent but wrong* — two people with near-identical names judged the same with high probability and no uncertain link — cannot be detected by any rule of this kind **[P6, P10, P17]**.

### 5.8 The source is untrusted input

Provenance proves **where** a value came from, not that the source is honest. Anyone who can write a sentence into the source can steer candidate selection: a note beside the wrong address moved the selection 20/20 and turned 20/20 correct abstentions into confident commits **[P7]**. This is a documented Jev weakness **[V-jagged]**, and no rule in this document defends against it.

What Jevson does:

- States the limit in the README, the result documentation, and DESIGN §6.
- Ships an **opt-in source screen**: one `noul` over the source, asked in the first decision level, asking whether the source contains text addressed to automated processors. In the first pilot one wording flagged 40/40 attacks with 0/40 false positives and a second flagged 20/20 *benign* invoices **[P7]**; out of sample, the first wording caught 60/60 attacks (all at p ≥ 0.86) but **flagged 27–28 of 60 benign invoices, e-mails, and contracts**, triggered by ordinary processing notes (EDI and AP-portal routing, "file under"), while plain instructions were flagged 0/66 **[P21]**. **The screen does not work yet**; it stays off by default until `PLAN.md` Phase 5 finds a wording that meets its bar on real documents that include processing notes. It flags at p ≥ 0.56 only — flagging the tie band caught no extra attacks and added 5–8% false positives **[P21]**. A flagged source turns **every field decided from the source** — classes D and E, and class C decisions whose question reads the source — into `Unresolved(source_flagged)`; constants and defaults (class A) are unaffected.
- States that **the screen can itself be steered**: it is a Jev question over the same untrusted text.
- Includes hostile sources in the adversarial suite (`PLAN.md` §4.2).

Adjudication of LLM drafts (DESIGN §6.3) was not steered by the same injections (0/80) **[P7]**; that result is a regression test, not a guarantee.

### 5.9 Provenance

Exactly two kinds in v0:

```text
SOURCE_SPAN      source id, start offset, end offset
DECLARED_OPTION  option identifier (schema enum value, rubric level)
```

**Span semantics:**

- Offsets are **Python `str` code-point offsets** into the **original, un-normalised** source, half-open `[start, end)` **[L1]**. Normalisation never produces provenance offsets.
- A span is valid only if `source[start:end]` equals the candidate text exactly, **and both boundaries are extended-grapheme-cluster boundaries under Unicode UAX #29** at a pinned Unicode version, tested against the Unicode `GraphemeBreakTest.txt` conformance file. A shorthand rule ("not before a combining mark, variation selector, skin-tone modifier, or ZWJ") accepted 63,855–76,510 forbidden boundaries across 13–15 of 20 classes (depending on the reading) — CR|LF, after a ZWJ, inside flag pairs, Hangul jamo, Indic conjuncts, Thai — in a 316,621-position corpus **[L11]**. Python has no grapheme API before 3.15 **[L11]**, so Jevson vendors a generated boundary table — ~1.2 KB compressed, with a 47-line pure-Python segmenter that passed every line of the official conformance test at Unicode 15.1, 16.0, and 17.0 **[L19]** — pinned to **Unicode 17.0**, the version Python 3.15 uses. Because a draft segmenter with a real bug in one rule also passed the conformance file, the implementation is additionally tested differentially against the `regex` module **[L19]**. The table's Unicode version is recorded in `Result`.
- Exact matching rejects an extractor's precomposed `é` for a source's decomposed one, or `\n` for `\r\n` **[L1]**. Rejection is counted and reported, never repaired: extractors return offsets into the original text, and the LLM extractor's strings are located in the source by Jevson.
- Verification happens **before** the Jev call. An unverifiable span never becomes an option.
- **v0 takes one source per call**, refused at the call boundary otherwise; `source_id` is in the type so multi-source is not a breaking change (`PLAN.md` Phase 9).

**Derived provenance is out of v0** (R9), except class F applied to **one selected span** (parsing `"$1,204.50"` into the decimal `"1204.50"`: the span's digits without grouping separators and without rounding), whose provenance is the span. `multipleOf` on a parsed value is checked in decimal arithmetic on those digits, since `jsonschema`'s float check rejects valid cents **[L18]**; `satisfies_schema` therefore uses decimal `multipleOf` where stock `jsonschema` would not.

---

## 6. What is guaranteed

| tier | claim | mechanism | holds unconditionally? |
|---|---|---|---|
| **Structural** | `.value` is valid JSON conforming to the structural schema, or the result says it does not | deterministic assembly + final validation; constrained decoding in the caller's LLM, where supported, reduces redrafts but is not relied on **[X1]** | **yes** |
| **Constraint** | `minimum`, `maxItems`, `pattern`, required fields hold, or the result says they do not (`Result.violations`) | deterministic validation (`jsonschema`, draft 2020-12; `format` checked only with its optional extras **[L10]**); for a Pydantic model, also `model_validate` | **yes** |
| **Provenance** | every value resolved from the source came from a verified span; every bounded value from a declared option | candidate architecture + substring and UAX #29 boundary verification | **yes**, for fields resolved that way |
| **Decision** | every Jev decision's full distribution is reported; `choice` and `score` also report the vendor's `confidence` | Jev | **yes** (nouls have a probability only **[V-confidence]**) |
| **Calibration** | reported probabilities match observed frequencies on this task | Jev | **not yet** — measured in `PLAN.md` Phase 5 |
| **Semantic correctness** | the value is objectively the right interpretation | — | **no. Not claimed. Not claimable.** |

**Honest limits** that belong in user-facing docs:

- Only fields decided by Jev carry a probability — a value parsed from a Jev-selected span carries that selection's probability; constants, defaults, direct extractions, caller-supplied values, and ungated drafts do not (`Result.decided_by` says which is which).
- Abstention applies to source-selected fields; schema-derived choices have no `none_of_these` in v0.
- Adjudication only checks the criteria you declare (DESIGN §6.3).
- **The source is trusted by the model even when it should not be** (DESIGN §5.8).
- Probabilities jitter on identical input — bools usually by ≤ 0.05, choices by up to 0.21, ambiguous pair questions by up to 0.37 **[P12, P20]**. The tie margin removes most but not all flips; replay is exact only through the response cache (DESIGN §8.4).
- Non-English sources are supported less well **[V-models]**.
- **Numbers and dates are read under the field's `locale`, default `en-US`.** A German `1.204` is read as 1.204 and `03.04.2026` as 4 March, silently, unless the field declares its locale.

### 6.1 The central property

> For any schema and any backend, LLM, extractor, or source behaviour whatsoever, a call returns exactly one of:
>
> 1. a `Result` with `.complete is True` and `.satisfies_schema is True`;
> 2. a `Result` with `.complete is False` **or** `.satisfies_schema is False`, every hole named in `.unresolved` and every failed constraint named in `.violations`; or
> 3. a typed exception from Jevson's hierarchy:
>    - `CompileError` — the schema cannot be mapped (raised by `compile_schema()` or at the start of `resolve`);
>    - `PreflightError` — before any backend call: the source or a declared maximum exceeds a context limit, more than one source is supplied, or a `known=` value fails the schema;
>    - `UsageError` — `resolve()` called inside a running event loop, or a closed instance used;
>    - `SchemaViolation` — a required field is unresolved and the caller set `raise_on_unresolved_required=True`;
>    - `BackendError`, `LLMError`, `ExtractorError` — a transport or protocol failure.
>    `SchemaViolation`, `BackendError`, `LLMError`, and `ExtractorError` carry the partial `Result` and its `Cost`; `CompileError`, `PreflightError`, and `UsageError` are raised before anything is spent.
>
> Never a fourth outcome. Never a result that claims completeness or validity it does not have. Never an untyped exception from a model's output, an extractor, a malformed HTTP body, or a network failure.

- `satisfies_schema` means `.value` validates against the original schema (and, for a Pydantic model, `model_validate` succeeds); `complete` means `unresolved` is empty. A fully resolved object can still fail a constraint the candidates could not be pre-filtered for (`minItems`, `uniqueItems`, cross-field rules **[L9]**): that is outcome 2 with `complete is True`. `absent` fields do not make a result incomplete (DESIGN §5.6).
- An unresolved **required** field yields outcome 2 by default (`satisfies_schema=False`); with `raise_on_unresolved_required=True` it yields outcome 3. It is never outcome 1. Constraint failures on a complete object are always outcome 2.
- At an unresolved **field** pointer the key is **omitted** from `.value`. An **array** with unresolved components is emitted with its resolved elements, and each unresolved component is one `Unresolved` at the array pointer, with the component's spans (or the tied enum value) in `detail`. An unresolved union names its whole subtree; an unresolved root yields `.value == {}`.
- **`Unresolved` reasons are a closed set:** `abstained` and `no_candidates` (required field), `tie`, `invalid_backend_answer`, `too_many_candidates`, `budget_exceeded` (a run-time `max_tokens_exceeded` that preflight did not predict), `unparseable` (a selected span that class F cannot parse under the field's locale, e.g. `1.204,50` under the default `en-US`), `entity_conflict`, `redraft_exhausted`, `source_flagged`, `verification_failed` (second gate, `PLAN.md` Phase 5), `dependency_unresolved` (a node whose dependency did not resolve). `not_yet_supported` is a `CompileError` reason, not an `Unresolved` reason.
- **A well-formed HTTP 200 whose JSON is malformed or mis-typed** is `invalid_backend_answer` for the affected questions; an unparseable HTTP response is a `BackendError`. An invalid answer to the source screen counts as flagged.
- **Transport retries are not decision retries.** 429, 5xx, and timeouts are retried with exponential backoff up to `transport_retries` (default 2), counted separately in `Cost`, and exempt from the changed-input rule. Other 4xx responses are not retried. `max_tokens_exceeded` is never retried unchanged (DESIGN §8.2).

### 6.2 Probabilities are reported, not enforced, by default

Calibration on source-span disambiguation is unmeasured, so v0 ships **no default threshold that drops a committed value**:

- Every Jev decision's distribution is reported (DESIGN §8.1).
- `none_of_these` is the one abstention path on by default — a structural signal about the option set, not a calibration claim.
- **The tie margin**: a decision whose top two outcomes differ by ≤ 0.10 (in hundredths) yields `Unresolved(tie)`. For a noul that is 0.45 ≤ p ≤ 0.55; for a choice or score, the top two options. It is a reproducibility rule — decisions inside it flipped on identical input **[P12, P20]** — not a confidence gate, and it removes most but not all flips (1/180 choice questions still flipped at 0.10 **[P20]**). It applies to every Jev decision that commits a value or admits a draft: bool fields, enum and candidate choices, scores, array membership, criteria (where a tie counts as a failed criterion, DESIGN §6.3), and union discriminators. Two decisions follow their own rules: entity pairs use DESIGN §5.7, which was measured with a plain 0.5 boundary **[P10, P17]**, and the source screen flags at p ≥ 0.56 **[P21]**. The margin is configurable in `JevsonConfig`. Over the 2,154 saved pilot candidate choices that use a `none_of_these` key it would have converted 56 (2.6%) to ties **[P22]**; Phase 0 reports the rate on real documents.
- **A default threshold is deferred, with a pre-registered bar** (`PLAN.md` §9). It is adopted in v1 only if, over ≥ 1,000 pre-labelled candidate-backed decisions from a corpus disjoint from Phase 0:
  1. the **one-sided 95% bootstrap upper bound of top-label ECE** on the selected option's probability is ≤ 0.05, using 15 bins with equal-mass quantile edges merged so that tied probability values are never split; and
  2. among decisions with p ≥ τ, the **Wilson 95% lower bound of accuracy** is ≥ the mean p of those decisions minus 0.03, at τ = 0.90, fixed before the corpus is labelled (τ = 0.80 is reported only); and
  3. before either is evaluated, the bar's operating characteristic is computed **on the observed probability distribution**: if a perfectly calibrated model would pass with probability < 0.95, or a model overconfident by 0.05 with probability > 0.05, the corpus is extended once to 3,000. If the check still fails at 3,000, the bar is recorded as *not decidable* and the threshold stays deferred.

  Why this shape: on the empirical distribution of 2,202 real Jev top-label probabilities (49% exactly 1.00), condition 1 at n = 1,000 passed a calibrated model 100% of the time and a 0.05-overconfident one 0% **[L14]**; but on a uniform(0.5, 1) distribution the same bar at n = 1,000 passed a calibrated model 0% of the time (99.5% at n = 3,000), and on Beta(18, 2) about 50% **[L13]**, so the power check (3) is mandatory rather than assumed. The earlier "accuracy ≥ τ − 0.02" rule passed an 8-point-overconfident model 96–100% of the time and is replaced by (2) **[L13]**. Brier score is reported alongside.

### 6.3 Generative fields and adjudication

A class E field is drafted by the caller's LLM and admitted only after Jev adjudicates it.

- **Declaration.** `x-jevson.generate` (DESIGN §3.5), with criteria, an optional rubric and minimum level, optional drafting instructions, and `max_draft_chars`.
- **Criteria are predicates about the draft and the supplied source, never about the world.** "The summary mentions the refund amount stated in the source" is a criterion; "the refund amount is correct" is not — Jev is not a fact-checker.
- **Execution.** A `generate` step asks the LLM for a one-field tool schema `{value: string}`. Providers differ on the envelope — OpenAI and Anthropic strict modes require `additionalProperties: false`, and Gemini's `parameters` schema has no such field — so the schema is passed as JSON Schema and each `LLM` adapter renders it for its provider **[L20]**. The draft must be ≤ `max_draft_chars` (default 4,000), checked after the call rather than as `maxLength`, so its adjudication budget is known at preflight. Each criterion is one `noul`, all batched in one call, each passing at p ≥ 0.56; a criterion inside the tie margin, or a rubric whose top two levels are within it and straddle the declared minimum, counts as **failed** for that draft — named in `rejections` and triggering a redraft, so exhaustion is `redraft_exhausted`, never `tie`. An optional rubric is one `score` whose most probable level must be ≥ the declared minimum.
- **Rejection** names the failing criteria (`Result.rejections`). A redraft passes them back to the LLM. A draft identical to one already adjudicated is not re-adjudicated and counts against `redraft_budget` (default 1). Exhaustion yields `Unresolved(redraft_exhausted)`.
- **Any malformed LLM output** — a missing or misspelled key, prose instead of a tool call, a non-string value, an over-length draft — is a failed draft, never an exception or a malformed object.
- **A field with no criteria** is admitted with a `no_criteria_declared` marker and listed in `Result.ungated`.

---

## 7. The v0 rules

Settled. Changing one is a design change that updates this document.

1. **Candidate-backed choices always include `none_of_these`.**
2. **`none_of_these` triggers bounded retry, then `absent` or `Unresolved`** by the table in DESIGN §5.6 — never an exception, never a silent guess.
3. **Independent decisions are level-batched** into one keyed Jev call per topological level, except adjudication's per-draft fallback (DESIGN §5.2).
4. **A single candidate is still asked** as `choice([candidate, none_of_these])` unless the field opts into direct extraction (DESIGN §5.3).
5. **Source-grounded arrays are built from membership `noul`s** over a candidate set.
6. **Array deduplication is an explicit entity-resolution stage**, scoped to an entity type, lossless on case by default, emitting only components with no internal conflict, plus the cross-component condition if Phase 0 selects it (DESIGN §5.7).
7. **Arrays are in source order.** Semantic ordering is out of v0 and tracked (`PLAN.md` §9); `x-jevson.order: semantic` refuses rather than silently source-ordering.
8. **Overflow is never silently discarded.**
9. **Derived provenance is out of v0**, except class F parsing of one selected span (DESIGN §5.9).
10. **There are no global modes.** One object freely mixes deterministic, source-grounded, Jev-selected, LLM-generated, and caller-supplied fields (`resolve(source, known={pointer: value})`).
11. **Decision graph, compiler, and executor are the core abstractions**; compilation is separate from execution; loops are executor policy.
12. **The taxonomy determines whether v0 is broad or deliberately narrow.**

Implementation rules of equal standing:

13. **Never reference state by array position.** Candidates and collections are placed in state as objects keyed by stable opaque ids, or inlined into the question **[P4]**. (The question-map key is not sent to the model **[P1]**.)
14. **Refusal is loud and early:** at compile time or in call-time preflight, before any backend call, with the offending JSON pointers.
15. **The model version is pinned** to an exact release; aliases are rejected by `JevBackend`.
16. **The source is untrusted input** (DESIGN §5.8).

---

## 8. Interfaces and dependency posture

Five protocols, each earning its place by having a real second implementation. The three I/O protocols (`Backend`, `Extractor`, `LLM`) are **async**; `Normalizer` and `CostSink` are synchronous. The synchronous `resolve()` submits `aresolve()` to **one library-owned event loop running in a daemon thread**, so every sync call shares one loop; `resolve()` refuses to run inside an already-running loop, where `aresolve()` is the entry point. A fresh loop per call is not used: an `httpx.AsyncClient` and asyncio locks are bound to the loop that first used them, and a second `asyncio.run` fails with `Event loop is closed` **[L20]**. Caller-supplied async objects (`LLM`, `Extractor`) used from `resolve()` run on that library loop, so an object used from `resolve()` must not also be used on another loop.

**Lifecycle.** The library loop keeps one long-lived client. On a caller's loop, **each `aresolve()` call uses its own client**, created on first use and closed before that call returns, so concurrent calls under `asyncio.gather` never close each other's client; if the caller has entered `async with JevBackend(...)` (or `async with Jevson(...)`, which enters its backend) on that loop, calls on that loop share one client until exit. A weak map of per-loop clients does not work, because a client that has made a request keeps its loop alive (5 of 5 survived garbage collection) **[L22]**. `Jevson` and `JevBackend` are context managers: `close()` closes the library-loop client (submitted to that loop), `aclose()` the one for the running loop. After `os.fork()`, `os.register_at_fork(after_in_child=…)` marks the library loop and thread for lazy re-creation on the next call, re-initialises every limiter lock, and drops (without closing) every inherited client. `CostSink.record` may be called from any thread.

**Timeouts.** Every step call is bounded by `JevsonConfig.step_timeout_s` (default 120); expiry raises `ExtractorError(timeout)` or `LLMError(timeout)` with the partial `Result`. Protocol implementations must not block the event loop — blocking work belongs in `asyncio.to_thread` — because a blocking caller implementation stalls every synchronous caller in the process. Jevson's own extractors comply.

| protocol | signature (abridged) | implementations |
|---|---|---|
| `Backend` | `async ask(state, questions, model) -> BackendResponse(answers, input_tokens, request_id, model)` | `JevBackend`, `FakeBackend`, `CachingBackend` (wraps another backend), AnyJev-style substitutes |
| `Extractor` | `async extract(source, field: FieldSpec, exclude: list[Span]) -> list[Candidate]` | LLM-backed, pattern (money, date, email, phone, URL), NER, user-supplied |
| `LLM` | `async complete(messages, tool_schema \| None) -> LLMResponse(arguments: dict \| None, raw: str, input_tokens, output_tokens)` | injected by the caller; `ReplayLLM` for exact replay |
| `Normalizer` | `normalise(text) -> str`, `representative(spans) -> Span` | declared per entity type |
| `CostSink` | `record(cost_event)` | default in-memory, user-supplied |

**`JevBackend` calls the HTTP API directly with `httpx`; the vendor SDK is not a dependency.** `typesafe-sdk` is pre-1.0 with breaking releases days apart, depends on `httpx2` and `tenacity`, retries requests by default — requests that may be billed — where `Cost` cannot see them, and logs full request and response bodies unredacted when `TYPESAFE_LOG_LEVEL=debug` is set in the environment **[V-sdk, X5]**. Revisit when the SDK reaches 1.0.

**API shape.** `Jevson(backend, llm=None, extractors={name: Extractor}, config=JevsonConfig(), cost_sink=None)` with `resolve(source, *, known=None, retry_budget=None, redraft_budget=None)` / `aresolve(...)`. **There is no default backend** — constructing `JevBackend(...)` is an explicit choice to spend money, so an environment variable never silently turns a test into paid calls. The backend's clients follow the lifecycle above: one long-lived client on the library loop, and per-call clients on caller loops. The rate limiter is **per API key**, shared across every `JevBackend` in the process through a registry keyed by a hash of the key, and built on `threading.Lock` rather than asyncio primitives; that design held 20 requests/s exactly across 5 loops, while an asyncio semaphore shared across threads lost a wakeup **[L20]**.

**Caller-supplied values.** `known={pointer: value}` fills fields the caller already has. Each value is validated against the field's schema before any spend (`PreflightError` otherwise); the field's nodes are skipped; `decided_by` is `caller` and no provenance is recorded. `known` pointers name fields outside arrays; a pointer inside a union branch is used only if that branch is selected, and a known discriminator value selects its branch without a decision.

**Privacy posture:** nothing is logged or written by default. Source text, spans, drafts, and values are written nowhere unless the caller supplies a sink or a cache directory.

**Vendor risk:** `Backend` is the substitution point. AnyJev and jevfire provide Jev-style decisions over other models **[X3]**.

### 8.1 The result type

```text
Result
  value             dict — the assembled object; unresolved pointers omitted
  satisfies_schema  bool — .value validates against the original schema
  complete          bool — unresolved is empty
  provenance        {pointer: SOURCE_SPAN | DECLARED_OPTION}
  decided_by        {pointer: code | jev | llm+jev | llm | direct | caller}
                      llm = generated with no criteria declared; caller = supplied via known=
  decisions         {f"{node_id}@{n}": Decision(kind, selected, distribution_hundredths,
                                       vendor_confidence | None, target_pointer)}
                      every Jev decision, n = 0 for the first ask and incremented per retry
                      or redraft: field choices, criteria, membership, pairs, discriminators,
                      the source screen
  unresolved        [Unresolved(pointer, reason, candidates_seen, abstain_probability, detail)]
  violations        [Violation(pointer, keyword, message)]  — failed schema constraints
  absent            [Absent(pointer, candidates_seen, abstain_probability)]
  ungated           [pointer]  — direct-extracted or no_criteria_declared fields
  overflow          [Overflow(pointer, spans, membership_probability)]
  rejections        [Rejection(pointer, criteria, draft)]
  cost              Cost(jev_requests, jev_input_tokens, jev_request_ids, cache_hits,
                         llm_input_tokens, llm_output_tokens,
                         decision_retries, transport_retries, redrafts, level_splits,
                         wall_clock_by_component)
  model             exact Jev model id reported by the API
  versions          question template version, Unicode versions of the grapheme table and of
                    `unicodedata` (used for NFC), and the result-affecting settings: tie margin,
                    conflict_floor, entity rule variant, pairwise cap, source screen on/off and
                    its wording version, default_extractor, and the retry and redraft budgets used
```

Every field is always present. An empty collection is the absence of a condition; `None` never means "nothing happened". The executor emits every cost event to the configured `CostSink` as it happens.

### 8.2 The context budget

Two limits apply to every request **[V-models, P3]**:

- **(a) state + the longest single question ≤ ~32k tokens.** Exceeding it cannot be fixed by splitting.
- **(b) state + all questions ≤ ~64k tokens.** Exceeding it splits the level; questions are independent **[P1]**, so splitting is answer-neutral, and each split re-sends and re-bills the state (`Cost.level_splits`).

**Preflight, before the first backend call,** budgets every level against both limits using declared maxima, not observed content: `max_candidates` options at `max_candidate_chars` plus an 80-character context window each (defaults 50 × 120) for candidate questions, `max_draft_chars` for adjudication, the pairwise cap for entity questions, and every union branch and every retry. The measured per-option costs (~27 tokens for realistic spans, ~80 with context windows **[P14]**) calibrate the estimator, and estimates are compared with `usage.input_tokens` on every response. A source or declaration that cannot fit raises `PreflightError` before any spend. Because preflight uses declared maxima, a run-time overflow can only come from estimator error; a `max_tokens_exceeded` 400 is then mapped to a split for (b), and for (a) — where the 400 does not say which question overflowed — the level is bisected to find it and that field becomes `Unresolved(budget_exceeded)`; an identical request is never retried.

**The source ceiling** is 32k tokens minus the longest question: ~108k characters of English prose or ~62k of dense business text alongside a realistic 255-option question **[P14]**. Under the default declarations a 50-candidate question of 120-character spans costs ~1.6k tokens, ~2.5k with context windows **[P22]**, so the ceiling is close to the full 32k. Longer sources are refused in v0; chunking is planned (`PLAN.md` Phase 9).

**Pairwise entity resolution is O(n²)**: n(n−1)/2 questions. It is **capped at n = 30** (435 questions) by default. The cost depends on the template: the leanest template needs ~18k tokens for 435 questions and a verbose one ~58k, estimated with a proxy tokenizer **[L7]**, so the template is part of the budget. Pair questions are asked over every candidate, not only accepted members, so the cap applies to candidates. Keyed-batching accuracy was measured up to 320 questions per request **[P4]**, not 435, and non-transitive triples grow with the number of triples, n(n−1)(n−2)/6 — so the *quality* ceiling may be lower than the token ceiling. `PLAN.md` Phase 7 measures both and lowers the cap if needed. Above the cap the executor yields `Unresolved(too_many_candidates)` rather than approximating.

### 8.3 Credentials

Anyone must be able to use the library with their own key and none of our tooling.

- `JevBackend(api_key=...)` takes the key as an argument; when omitted (or empty), it falls back to the `TYPESAFE_API_KEY` environment variable, the name the vendor uses **[V-sdk-constants]**.
- With neither, or with an empty string in both, construction raises `MissingCredentials` naming both options, before any network call.
- The library never reads a `.env` file and never writes, logs, or `repr`s the key.
- The repository's own tests and scripts read a gitignored `.env` (template `.env.example`). Fetching the key from the team's Infisical project is planned tooling (`PLAN.md` Phase 11).

### 8.4 Replay

Jev is near-deterministic, not deterministic (DESIGN §2.3). Jevson's own code is deterministic: given identical backend, LLM, and extractor responses it produces an identical `Result`, excluding wall-clock timings. **Exact replay** uses two opt-in wrappers, both implementations of existing protocols: `CachingBackend` (key: SHA-256 of the RFC 8785 canonical JSON of model id, state, and questions; responses stored with probabilities as integer hundredths) and `ReplayLLM` (the same scheme over LLM requests). The Python `rfc8785` and Node `canonicalize` packages produced identical hashes on unicode and edge-case requests; `canonicaljson` and a sorted `json.dumps` did not **[L21]**. A request that cannot be canonicalised (a lone surrogate, an integer beyond 2⁵³) is not cached. A cache hit is counted in `Cost.cache_hits` and spends nothing; with `replay_only=True` a miss raises `BackendError(replay_miss)` (or `LLMError(replay_miss)` for `ReplayLLM`, whose key also includes the caller's LLM id). Exact replay also requires deterministic extractors — pattern extractors are; an LLM-backed extractor is when its `LLM` is a `ReplayLLM`. Both wrappers write only to a directory the caller supplies.

---

## 9. Prior art

Credit where it is due. **Every mechanism below predates Jevson.**

**In the Jev ecosystem** **[X3, V-cookbooks]**:

| project | what it does | relationship |
|---|---|---|
| TypeSafe cookbook *pre-parsed value extraction* | regex candidates → `choice` over spans with a `NONE` option → code copies the value verbatim | **DESIGN §5.1 and §5.4 are this pattern.** Jevson compiles it from a schema |
| TypeSafe cookbooks *SDE cascade*, *citation check*, *entity alignment*, *date extraction*, *function calling* | per-field "absent from source" nouls over LLM extraction; claim support; merge/curate/leave decisions (the precedent for DESIGN §5.7's refusal to merge on weak evidence); date parts as choices with "not stated"; a signature → questions compiler | each covers one piece; none is a general schema compiler |
| `TypeSafeAI/typesafe-playground` | document extraction with offsets, candidate ids, explicit `null` choice | in the vendor's GitHub organisation; describes itself as a community example |
| `gbesse/jev-extract` | typed records, candidate/absent fields, per-field provenance, request packing, chunk aggregation | closest open project; fixed record types rather than schema compilation |
| `choxos/jev-reviewer` | "which line answers q? (+ none)" with verbatim quotes, across multiple files | multi-source candidate selection already exists (cf. `PLAN.md` Phase 9) |
| `lzq-0529/jev-span`, `jb2197/pydantic-jev`, PyPI `jev`, `finetuningsingh/jev-extract`, `dangquan1402/jev-extract` | span NER over Jev; a Pydantic–Jev shim; a Pydantic → Jev decorator; extraction and extractive QA over Jev | adjacent |
| `mateonunez/jod` | semantic schemas over Jev (npm) | listed in `hellogumbo/awesome-jev`; not reviewed in depth |
| `Kiln-AI/jev_jsonschema` | JSON Schema → Jev questions → JSON, no LLM; refuses free-form strings, arrays, objects, `anyOf`/`oneOf`/`allOf`/`$ref`, `const`, `not`, unbounded numbers | closest schema-first work; its mapping table is adopted with the corrections in DESIGN §4.2 |
| `doronp/jevc` | compiles policy prose into Jev questions plus a residual generative prompt | not purely schema → Jev |
| `alexwestco/llm-to-jev`, `0xjba/jev-swap` | classify prompt convertibility; find LLM calls that are really decisions | analysis and adoption tooling |
| `nokia-applied-research/AnyJev`, `kikoncuo/jevfire` | Jev-style constrained decisions over other models | candidate backends |
| `eortizs/jev-json-builder` | Express middleware: regex candidate spans plus presence gates, TypeScript | JS precedent for candidate selection |

**Outside Jev** **[X2]**: Google LangExtract (character-interval grounding, `None` when unlocatable; no confidence or abstention); Instructor (`CitationMixin`, quote validation, `Maybe`); Cleanlab TLM (`per_field_score`); LlamaExtract (citations and confidence); Azure Document Intelligence (field confidence as a probability); Reducto, Extend, Sensible, AWS Bedrock Data Automation (commercial per-field signals); Unstract LLMChallenge; GLiNER (span + score).

### 9.1 The defensible public claim

> Jevson generalises TypeSafe's "select, don't generate" extraction pattern into a schema compiler: nested objects, unions decided before construction, source-grounded arrays with entity resolution, criteria-gated generative fields, and a typed three-outcome result verified by an adversarial suite.

**Not** "first of its kind." **Not** "nobody catches this." **Not** "guaranteed JSON." Grounding checks and per-field confidence exist elsewhere; the claim is the combination, in an open library, as far as we found.

---

## 10. Limits and refusals

| limit | consequence |
|---|---|
| Jev cannot produce free-form text | unbounded fields are drafted by the LLM, then adjudicated (DESIGN §6.3) |
| `choice` ≤ 255 options; `none_of_these` takes one | `max_candidates` ≤ 254; more → `Unresolved(too_many_candidates)` |
| option descriptions dominate large choices | preflight budgets declared maxima; context windows only for repeated text |
| `score` 2–10 levels; wide scales come back flat **[P13]** | only declared ordinals; value = most probable level; narrow rubrics preferred |
| API accepts 1-option choices and 1-level scores | the compiler refuses them |
| state + longest question ≤ ~32k tokens | ~62k–108k characters of source beside a realistic 255-option question, ~30k–50k with context windows on every option **[P14]**; longer refuses in v0 (`PreflightError`); chunking planned (`PLAN.md` Phase 9) |
| state + all questions ≤ ~64k tokens | levels split, re-billing the state |
| probabilities jitter; decisions near thresholds flip **[P12, P20]** | tie margin → `Unresolved(tie)`; exact replay via cache (DESIGN §8.4) |
| Jev has no vision | image-derived fields are generative and adjudicated against declared criteria only |
| Jev is not a fact-checker | adjudication is only as good as the declared criteria |
| content in the source can steer selection | stated limit; source screen not yet working **[P21]**; hostile-source tests (DESIGN §5.8) |
| candidate coverage bounds everything | `none_of_these` is the only defence (DESIGN §5.4) |
| pairwise entity resolution is O(n²) | capped at n = 30; quality measured (DESIGN §8.2) |
| one source per call in v0 | refused at the call boundary; multi-source planned (`PLAN.md` Phase 9) |
| unbounded array cardinality | source-grounded membership only; generative lists refused in v0 |
| `anyOf` / `oneOf` with ≥ 2 non-null branches | resolved where the branch is a bounded decision (`PLAN.md` Phase 6), refused loudly otherwise |
| recursive or dynamic `$ref`, `dict[str, X]`, tuples, `Any`, `bytes` | refused with a named reason (DESIGN §3.5) |
| relative dates ("next Friday") | not resolved in v0; tracked (`PLAN.md` §9) |
| non-English sources | supported, less well; documented |
| numbers and dates in other conventions | read under the default `en-US` unless the field declares `locale`; misreadings are silent |

**Refusal over invention.** Any construct the compiler cannot map is reported before a single API call, with the offending JSON pointers.

---

## 11. Glossary

| term | meaning |
|---|---|
| **decision node** | one bounded Jev question with a kind, options, dependencies, and a target pointer |
| **step node** | an external operation (extract, generate) whose output a decision depends on |
| **decision graph** | decision and step nodes with dependency edges; acyclic |
| **level** | a set of mutually independent decision nodes, resolvable in one batched Jev call |
| **candidate** | a verified source span offered as a possible value, under an opaque option id |
| **span** | `(source_id, start, end)` in code points of the original source, on grapheme boundaries |
| **option source** | where a `choice`'s options came from: schema enum, rubric, or candidate spans |
| **abstention** | `none_of_these` selected — no supplied candidate is sufficiently supported |
| **absent** | an abstention on a field the schema allows to be missing or null; not an error |
| **unresolved** | a named hole in the result, with a reason from a closed set |
| **complete** | no unresolved holes |
| **tie margin** | a top-two difference ≤ 0.10, resolved as `Unresolved(tie)`, or as a failed criterion in adjudication |
| **entity resolution** | collapsing spans that refer to the same entity into one array element |
| **conflict floor** | p(same) at or below which a pair counts as confidently different |
| **overflow** | candidates accepted by membership but dropped by a cardinality constraint; always retained |
| **adjudication** | Jev checking a generated draft against declared criteria before commit |
| **preflight** | the executor's pre-call budget check of every level against declared maxima |

---

## 12. Open questions

Each is recorded in `PLAN.md` §7 against the phase that answers it, with its policy fixed now so the answer changes a setting, not the design.

- **Entity resolution on real prose, `conflict_floor`, and which rule variant** (DESIGN §5.7) — Phase 0 probe 4.
- **Retry's real value** — Phase 5 (DESIGN §5.5).
- **Calibration on this task** — Phase 5 (DESIGN §6.2).
- **Source screening** — whether any detector wording can flag hostile sources without flagging ordinary processing notes; the tested wording flagged 27–28 of 60 benign documents **[P21]**. Phase 0 probe 6, Phase 5.
- **Union execution: level vs. speculative fan-out** (DESIGN §3.2) — Phase 6.
- **The pairwise quality ceiling** (DESIGN §8.2) — Phase 7.
- **Whether jitter on pair questions can be reduced** — for example by asking both orderings of a pair — rather than only banded (DESIGN §5.7, **[P12]**). Phase 7.
- **The name.** "Jevson" couples us to a vendor whose replaceability is a design goal, and `jevapi.dev` asserts Jev is a TypeSafe trademark **[X4]**; no TypeSafe naming policy was found. Decided before the PyPI release in `PLAN.md` Phase 8, after asking TypeSafe.

**Closed by evidence:** level splitting is answer-neutral **[P1]**; keyed state references matter **[P4]**; a noul gate is a worse abstention mechanism than `none_of_these` **[P5]**; a lone candidate is safer asked than committed **[P11]**; the score value is the most probable level **[P13]**; the complete-value wording does not cost accuracy when the full value is present **[P18]**. Mixed option descriptions showed no decision bias at near-ceiling accuracy **[P19]**; Phase 0's repeated-text cases re-check it.

---

## 13. Changelog

### Revision 9.1 — 2026-09-29, red-team round 7 (converged)

Round 7's logic review found **no blocker and no major** and verified every round-6 finding fixed; with the citation audits of rounds 5 and 6, both review tracks have converged. Its 9 minors are applied here: strict locale parsing and unknown-tag refusal; the silent `en-US` misreading stated as a limit; arrays inside optional objects; root generate steps not waiting; the `async with Jevson` backend; exit tests for the root rule, shared clients, and `gather`; enum-array wording; an unsupported fork remark removed.

### Revision 9 — 2026-09-29, red-team round 6

Round 6: the citation spot-check **converged** again (337 tags: 336 supported, 1 overstated). The logic review found 1 blocker and 3 majors, all in text written for Revision 8, each fixed here in a clause.

| changed | now | source |
|---|---|---|
| **Phase 2 exit** (blocker) | an optional object with source-declared leaves refuses `not_yet_supported` in Phase 2, rather than compiling | logic review |
| **Locale** | a deterministic default (`en-US`); unparseable means "does not parse under the field's locale" | logic review |
| **Caller-loop clients** | one client per `aresolve()` call unless a context manager is entered; safe under `gather` | logic review |
| **Object absence** | the root is never abstained | logic review |
| **Minors** | fork lazily re-created; generate waits for retries; decimal `multipleOf` noted; versions; lone-candidate counting; membership-tie evidence; wording | both reviews |

### Revision 8 — 2026-09-29, red-team round 5

Round 5: the citation audit **converged** (329 tagged claims: 324 supported, 5 overstated, 0 wrong, 0 unsupported; no blocker or major). The logic review found no blocker and 2 majors, both introduced by Revision 7 rules written for leaf fields and applied to objects, plus 12 minors.

| changed | now | source |
|---|---|---|
| **Defaulted fields** | the class A rule applies to leaf fields only; objects and arrays compile from their contents | logic review |
| **Object absence** | only class D descendants count; C, A, E values are discarded and generation is skipped under an absent object | logic review |
| **Per-loop clients** | scoped to each `aresolve()` on a caller's loop; a weak map leaked 5/5 | **[L22]** |
| **Fork, close** | fork handler replaces loop, locks, and clients; `close()` / `aclose()` defined | logic review |
| **Built-in extractors** | only when declared by name | logic review |
| **Sum tolerance** | 0 deviation on 20 easy answers at K = 51 and 255 | **[P23]** |
| **Minors** | R3 per-draft exception; candidate state; membership ties; direct extraction over repeated text; `locale`; decimal `multipleOf`; versions; protocol sync/async split; wording | both reviews |

### Revision 7 — 2026-09-29, red-team round 4

Two reviews of Revision 6: a citation audit (325 tagged claims: 317 supported, 7 overstated, 1 wrong; one major: R6 still prescribed the superseded entity rule) and a fresh logic review (no blockers, 10 majors, 16 minors). Both reported **not converged**.

| changed | now | source |
|---|---|---|
| **R6, DESIGN §1** | internal rule plus the Phase 0 variant | citation audit |
| **Array holes** | unresolved components reported at the array pointer; the array is still emitted | logic review |
| **Object absence** | an optional object whose fields are all missing is absent once | logic review |
| **Pre-filter** | verbatim fields only; parsed fields validate after parsing | logic review |
| **Repeated text** | `max_candidates` counts options after expansion | logic review |
| **Direct extraction** | two or more candidates are asked | logic review |
| **Criterion ties** | count as failed criteria → redraft | logic review |
| **Level state** | keyed `candidates` and `drafts`; multi-draft layout re-measured in Phase 4 | logic review |
| **Defaulted fields** | class A, default applies | logic review |
| **Entity components** | over accepted members only | logic review |
| **Timeouts and lifecycle** | `step_timeout_s`; context managers; per-loop clients held weakly; fork-safe; `UsageError` | logic review |
| **Tie-margin rate** | 2.6% over the 2,154 pilot candidate choices with a `none_of_these` key (was 1.4% over a subset) | **[P22]** |
| **Minors** | sum tolerance cap; decimal canonical form; `decisions` key `id@n`; config homes; replay flags; `known=` scope; screen invalid answers | both reviews |

### Revision 6 — 2026-09-29, red-team round 3

Four reviews of Revision 5: a citation audit (209 tagged claims: 201 supported, 5 overstated, 3 wrong), 1,261 live requests testing the new rules out of sample, local buildability checks, and a fresh logic review (2 blockers).

| changed | was | now | evidence |
|---|---|---|---|
| **Central property** | outcome 2 required `complete is False` | outcome 2 is incomplete *or* invalid; `Result.violations` | logic review, **[L9]** |
| **Tie rule** | bool ±0.05 with 0.45/0.55 decided; choices ±0.05 | one tie margin ≤ 0.10 for every committing decision | **[P12, P20]** |
| **Entity rule** | two-directional rule adopted | internal rule always; cross-component rule a variant chosen in Phase 0 (no splits out of sample) | **[P17]** |
| **Source screen** | opt-in, measured later | does not work yet: 27–28/60 benign flagged; flags at ≥ 0.56 only | **[P21]** |
| **Async** | a private loop per call, one client | one library loop thread; a client per loop; thread-lock limiter | **[L20]** |
| **Absence** | nullable → null | not required → omitted, so defaults apply; required nullable → null | **[L18]** |
| **Normalisation** | Decimal as number; no discriminator row | Decimal as string; `x-jevson` merged beside `$ref`; discriminated unions; Pydantic ≥ 2.12 | **[L18]** |
| **Grapheme table** | ~9 KB, unversioned | ~1.2 KB, Unicode 17.0, conformance plus differential tests | **[L19]** |
| **Defaults** | `max_candidates` 254; no default characters | 50 × 120 | logic review |
| **Replay** | keys only | RFC 8785 libraries named; cache hits, misses, and extractor determinism defined | **[L21]** |
| **Complete-value template** | tested only with lone candidates | tested with competitors; partial-only sources a stated limit | **[P18]** |

### Revision 5 — 2026-09-29, red-team round 2

Four reviews of Revision 4: a citation audit (166 tagged claims, 142 supported), 941 live requests testing the new rules, local statistics and Unicode checks, and a fresh logic review (3 blockers). Evidence in `docs/EVIDENCE.md`.

| changed | was | now | evidence |
|---|---|---|---|
| **Field declarations** | undeclared strings both refused and source-selected; no syntax for extractors | one `x-jevson` keyword; normalisation table (DESIGN §3.5) | logic review |
| **Entity resolution** | internal conflicts only (3.8–4.5% silently wrong, mostly splits) | components must be consistent in both directions (0/133, 0/134 in-sample); floor grid to 0.45 | **[P10]** |
| **Jitter** | "up to 0.10, ±0.05" | typically ≤ 0.05; up to 0.37 on ambiguous pair nouls | **[P12]** |
| **Ties** | exact 0.5 only | ±0.05 band for bools, choices, scores | **[P12]** |
| **Question templates** | unowned | versioned templates; complete-value wording (partials 32/42 → 0/42) | **[P11]** |
| **Repeated text** | "ids can represent it" | every occurrence offered with a context window (40/40 vs 22/40) | **[P15]** |
| **Absence** | every abstention `Unresolved`; `complete` rarely true | `absent` vs `unresolved` by nullability and requiredness | logic review |
| **Grapheme rule** | shorthand list | UAX #29 at a pinned Unicode version, vendored table | **[L11]** |
| **Calibration bar** | bootstrap ECE at n ≥ 1,000; τ − 0.02 rule | tie-safe bins; Wilson rule at τ; mandatory power check on the observed distribution | **[L13, L14]** |
| **Source budget** | "~2.5k tokens for 255 options" | per-option costs; character ceilings; preflight on declared maxima | **[P14]** |
| **Exceptions** | preflight and extractor failures untyped | `PreflightError`, `ExtractorError`; closed set of `Unresolved` reasons | logic review |
| **Rounding** | floats | integer hundredths; sum tolerance; RFC 8785 cache keys | **[L17]** |
| **Protocols** | sync `LLM`; per-instance limiter | async protocols; per-key limiter; pinned `Extractor` signature | logic review |
| **Citations** | 18 overstated, 2 wrong, 4 unsupported | corrected | citation audit |

### Revision 4 — 2026-09-29, red-team round 1

Five independent reviews of Revision 3 (vendor documentation, 1,555 live requests, external claims, local checks, internal logic). Repositioned from "nobody does this" to crediting every predecessor; corrected the Jev facts (noul confidence, calibrated quantity, near-determinism, two context limits, question independence); rewrote R13 around state references; declared the source untrusted; asked single candidates; resolved entity conflicts per component; corrected the mapping table; split `satisfies_schema` from `complete`; normalised Pydantic `$ref`, nullable, and `const`; compiled all union branches; dropped the vendor SDK; raised the calibration bar; gave generative fields a compiler, graph, and executor path.

### Revision 3 — 2026-09-29, open questions settled

Phases made strictly sequential with adjudication ahead of candidate selection; credentials pinned; entity-resolution conflicts handled; retry brief pinned; calibration bar pre-registered; criteria rule; semantic ordering out of v0; multi-source, JS port, and Infisical planned.

### Revision 2.1 — 2026-09-28, review pass

The central property as three outcomes; confidence reported, not enforced; retry useless against identical input; span semantics; the result type; the context budget and the pairwise cap.

### Revision 2 — 2026-09-28

Reversed Revision 1's premise ("LLMs cannot be made to emit valid JSON"), its headline ("guaranteed schema-valid JSON"), its two global modes, its per-field LLM-supplied evidence (an unbounded influence channel over a bounded output), and its per-slot arrays. Introduced the decision graph, decide-then-construct, candidate spans, `none_of_these`, tiered guarantees, the classification model, and provenance.
