# Jevson — design

> **Status:** Design document, Revision 11.5, 2026-10-19 (adjudication asked apart from other questions; 11.4, multi-label enum arrays; 11.3, union discrimination; Revision 11, 2026-10-14, the fallback scope). Pre-implementation. Phase 0 ran on `jev-1.13.0` and Phase 0r on the Decisions API; both gave the pre-registered verdict **drop source selection** **[Z9, Q2, Q9]**. **v0 is the fallback product** (DESIGN §10.1): bounded decisions over declared options, criteria-gated generative fields, union discrimination, and multi-label enum arrays. Class D (source selection) and everything built on it — DESIGN §5.1–§5.6, span verification in §5.9, class F parsing of a selected span, the source screen — is the design of record for deferred work (`PLAN.md` §9.2), not v0 behaviour. The decision model is now the **OpenAI Decisions API** (`gpt-6-luna`), which replaced Jev on 2026-10-14; the decision record is `Agents/docs/decisions/2026-10-14-decisions-api-replaces-jev.md` (Project-Asterion/Agents). The library keeps the name Jevson for now (DESIGN §12).
>
> **This document is the SSOT for Jevson.** It carries everything an agent or contributor needs to work on the project: what the library is, what it guarantees, the architecture, the vocabulary, the constraints of the model it sits on, and the rules that are not open for reinterpretation. The build sequence lives in [`PLAN.md`](PLAN.md).
>
> **One line (the full design):** Jevson is a general-purpose, open-source schema compiler for source-grounded structured extraction. It turns a Pydantic model or JSON Schema into a graph of bounded decisions, has the decision model make them, assembles the result in code, and records for every field how it was decided — with the source span or declared option, and the probability, where the decision model decided it — or a typed reason it could not be resolved.
>
> **One line (v0):** a schema compiler for bounded decisions: every field is a constant, a default, a caller-supplied value, a choice among options the schema declares, or an LLM draft admitted against declared criteria, and records how it was decided, with the declared option and the probability where the decision model decided it, or a typed reason it could not be resolved. No value is selected from the source.
>
> **Evidence.** Every factual claim in this document and `PLAN.md` about the decision model, about other tools, or about measured behaviour carries an evidence tag such as **[P3]**, **[V-models]** or **[D1]**, resolved in [`docs/EVIDENCE.md`](EVIDENCE.md) to the probe script, vendor page, or source that established it. A claim without a tag is a design decision, or arithmetic shown in place.
>
> **Measured on Jev.** Every **P** measurement and every **V** page is about `jev-1.13.0` and TypeSafe's documentation. Phase 0r re-measured the ones that depend on model behaviour on the Decisions API (**Q** tags; DESIGN §2.3 says which held). The rest stand as measurements of Jev and precautions for the Decisions API, never as facts about `gpt-6-luna`. **D** tags are the Decisions API's own documentation and third-party reports about it.

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
- level-batched execution that respects the decision model's context limits;
- source-grounded arrays, with entity resolution that refuses to merge on contradictory evidence planned after v0 (Phase 0 measured it below its bar on real prose on `jev-1.13.0` **[Z4]**; DESIGN §5.7);
- generative fields admitted only after passing declared criteria;
- a typed three-outcome result, proven by an adversarial suite.

That combination is the product. It generalises TypeSafe's "select, don't generate" pattern from a recipe into a library.

### 1.1 The one-line pitch to a pipeline author

> Jevson is the extraction node in your chain that tells you when it doesn't know — and shows you where each value came from.

A LangChain, LlamaIndex, or plain-Python pipeline can branch on Jevson's result: commit, fall back, escalate to review, or abort. **Two honest limits belong in the pitch:** provenance proves where a value came from, not that the source is honest (DESIGN §5.8); and abstention covers source-selected fields and is measured, not guaranteed (DESIGN §6). **In v0 the pitch is narrower:** there are no source-selected fields, so v0 says where each value came from only as a declared option, a draft, a default, or the caller, and has no abstention (DESIGN §10.1).

---

## 2. The decision model — the constraints that shape everything

The decision model is the **OpenAI Decisions API**: `POST https://api.openai.com/v1/decisions`, model `gpt-6-luna` (the only model offered), public beta, with general availability expected "in the coming weeks" **[D1]**. It replaced Jev (TypeSafe's `jev-1.13.0`, early access **[V-launch]**) on 2026-10-14; the decision record, `Agents/docs/decisions/2026-10-14-decisions-api-replaces-jev.md`, lists the documented facts below with their sources. **Official guide: <https://developers.openai.com/api/docs/guides/decisions>** **[D1]**.

**Interface.** `Authorization: Bearer <key>`, body `{model, input, questions, safety_identifier?}` **[D1, D2]**. `input` is a text string, or `user` messages with `input_text` and `input_image` parts **[D2]**. `questions` is a **list** of typed questions, each with optional `name`; answers come back in an `answers` list, one per question in question order, each echoing its `name` **[D1, D2]**. The response also carries `model` and `usage` (`input_tokens`, with cache details; `output_tokens`, with `reasoning_tokens`) **[D2]**. Jevson's word **state** below means the request's shared `input`: Jevson always sends it as one text string.

- **Question names.** `name` is optional in the API **[D2]**; Jevson always sets a unique one. On Jev the question key was not sent to the model **[V-primitives, P1]**; whether the Decisions API shows `name` to the model is undocumented, but Phase 0r found that names, including leading `yes_`/`no_` prefixes, changed no answer **[Q10]**. Jevson still sends opaque, content-free names (`q0…qN`) and maps them to node ids itself, so nothing depends on that finding.
- **Dependent questions** need separate requests **[D1]**, which is how Jevson's levels already work (DESIGN §3.3).

**Model version.** There is **no pinnable snapshot**: the model page lists only the alias `gpt-6-luna` **[D3]**, and behaviour has changed under that name before (an image-encoding fix on 2026-09-25, before this endpoint launched **[D4]**). Each response carries a `model` string **[D2]**; whether it names a version is unknown. Jevson therefore **records** the returned `model` string on every response and in `Result.model`, treats a change in it as a re-baseline, and replays only from records (DESIGN §8.4). The pinning rule of earlier revisions (exact `jev-1.13.0`, aliases rejected **[P9, V-models]**) cannot be applied to this API.

### 2.1 The primitives — as documented

| primitive | request | response | notes |
|---|---|---|---|
| `predicate` | `instructions` | `probability` that the statement is true (0–1) | **no confidence field** **[D1, D2]** |
| `choice` | `instructions`, `choices` [{`value`, `description`?}] | `choice`, `probabilities` [{`value`, `probability`}] per option, `confidence` | 2–255 options, each unique; a value is a string or a boolean, and the two are distinct (`"true"` ≠ `true`) **[D2]** |
| `score` | `instructions`, `levels` [{`label`, `description`?}], lowest first | `score` (the probability-weighted mean of the level indices, which start at 0, so it can fall between levels), `probabilities` [{`value`, `label`, `probability`}] per level, `confidence` | **the maximum number of levels is undocumented** **[D1, D2]** |
| any | — | `refusal`: `{type: "refusal", name}` instead of an answer; the other questions in the request still get answers | **[D1, D2]** |

**From Jev to the Decisions API:**

| Jev | Decisions API | what changed |
|---|---|---|
| `noul` | `predicate` | renamed; still a probability with no confidence |
| `choice` over a key → description map | `choice` over a list of `{value, description}` | lower bound of 2 documented (Jev accepted 1 **[P2]**); values typed string or boolean |
| `score` (2–10 levels **[P2]**, with `legend`) | `score` | maximum levels undocumented; no `legend` field (each level's `label` is in `probabilities`) |
| — | `refusal` | new: a per-question decline (below) |
| `state` + a map of keyed questions | shared `input` + a list of named questions | answers in question order |
| text or JSON state only; no images **[V-models]** | text, or text and up to 128 images | images are **not adopted** (below) |

- **Refusal is a first-class outcome.** Any question may come back as `refusal` **[D2]**. Jevson records it in `Result.decisions` and resolves the node to `Unresolved(refused)` (DESIGN §6.1). It is never mapped to `none_of_these`, to a default option, or to an absent value, and it is never retried unchanged.
- **Typed values.** Jevson's options are opaque string ids (`c0…cN`, DESIGN §5.1), so a boolean `value` never appears in a Jevson request; a bool field is a `predicate` (DESIGN §4.2).
- **Images are readable but not adopted.** The API accepts images (base64 data URLs in the guide; SDK 3.31.0 also accepts public HTTP(S) URLs) **[D1, D2]**. Jevson's sources are text (DESIGN §5.9); image input would need its own design change.
- **Probabilities vs `confidence`.** The guide describes predicate probabilities as "the model's estimate" and choice and score answers as a distribution plus "a separate `confidence` field" **[D1]**; it does not define `confidence` and makes **no calibration claim**, advising thresholds set from your own labelled examples **[D1]**. (On Jev, `confidence` was a statistic of the distribution that changed with the option count **[V-confidence]**.) Jevson reports `confidence` but makes every calibration claim and bar about **probabilities**.
- **Integer hundredths.** On Jev, values were rounded to two decimals and distributions summed to 1.00 or 0.99 **[L17]**; on the Decisions API, values have at most two decimals and every distribution measured summed to exactly 1.00 **[Q14]** (the guide documents neither; its examples show at most two decimals and are labelled illustrative **[D1]**). Jevson **stores** every probability as integer hundredths, but **validates on the raw values the API returns**: the sum check runs before rounding, because rounding full-precision values first would make a large distribution lose mass (200 options at 0.004 each all round to 0). The sum tolerance on Jev was min(⌈K/2⌉, 5) hundredths of a pre-rounded output (at most 1 observed at K ≤ 11 **[L17]**; 0 across 20 easy answers at K = 51 and K = 255 **[P23]**). For the Decisions API, Phase 0r measured no deviation at all **[Q14]**, so an answer is invalid if its raw probabilities sum outside **1 ± 0.01** (one hundredth absorbs two-decimal rounding; anything more means the answer is not what was measured). The selected option is the argmax in hundredths; if the API's `choice` field names a different option and the top-two margin is outside the tie band, the answer is invalid.
- **Lower bounds.** The compiler enforces ≥ 2 options and ≥ 2 levels itself, whatever the API accepts.
- **Errors.** The Decisions API's error codes and bodies are not in the sources above. (Jev returned HTTP 400, not the documented 422, with a JSON `detail` **[P2]**.) Phase 3 maps them from observed responses.

### 2.2 Limits — documented and measured

| limit | Decisions API | on `jev-1.13.0` (measured, not transferable) |
|---|---|---|
| options per `choice` | 2–255, unique **[D2]**; 1 and 256 rejected (HTTP 400 `array_below_min_length` / `array_above_max_length`) **[Q11]** | 255; 1 accepted **[P2]** |
| levels per `score` | 2–10; 1 and 11 rejected (HTTP 400) **[Q11]** | 10; 1 accepted **[P2]** |
| context per request | ~915k input tokens accepted, ~928k rejected (HTTP 400 `invalid_request_error`, code null, "Decision input exceeds the token limit."); no separate per-question limit (one ~257k-token question accepted); no truncation observed from 30k to 915k; input above 272K tokens billed at 2× **[Q11, D3]** | state + longest question ~32,768 tokens; state + all questions ~65,536 tokens; HTTP 400 `max_tokens_exceeded` **[V-models, P3]** |
| questions per request | **200**; 201 rejected (HTTP 400 `array_above_max_length`) **[Q5, Q11]** | no count limit; 2,515 accepted **[P2, P3]** |
| images per request | 128 **[D2]** (not adopted) | none **[V-models]** |
| rate | not measured; four HTTP 429s on 500k–915k-token requests suggest a token-rate limit **[Q11]**; the model page publishes per-tier limits for `gpt-6-luna` (Build tier: 5,000 RPM, 2M TPM **[D3]**), not stated to apply to `/v1/decisions` | ~1,200 requests/min, ~250k tokens/s; "can change without notice" **[V-models]** |
| price | $0.10 per million input tokens; no charge for output, cache reads, or cache writes; regional and long-context multipliers apply **[D1]** | $0.042 per million input tokens, output free **[V-models]** |

Phase 0r (2026-10-14) measured these on `gpt-6-luna`; preflight budgets against them (DESIGN §8.2). They are measured, not documented, so a vendor change can move them: a limit rejection is handled as DESIGN §8.2 says, never retried as is.

**What fits (on the Decisions API).** Each short question costs ~160 input tokens (Jev ~24), and the input is billed once per request (1 question over a 257k input: 257,075 tokens; 200 questions: 288,915). Beside a realistic 255-option question, ~910k tokens of source fit: ~2.88M characters of business text, checked live with one 897k-token request **[Q12]**.

**What fits (on Jev).** Option descriptions dominate a large `choice`: ~18 tokens per option for bare short spans, ~27 for realistic 5–80-character spans, ~80 with a ±70-character context window **[P14]**. With a realistic 255-option question, the largest source accepted was ~108,000 characters of plain English prose or ~62,000 characters of dense business text **[P14]**; with context windows on every option, the state is left ~12k tokens (~30,000–50,000 characters) **[P14]**. The 400 body carried no token counts and no tokenizer is published **[P3]**; **no silent truncation was observed**: every over-limit request was rejected **[P3]**. The Decisions API's behaviour over a limit is unknown.

### 2.3 Behaviour — measured on `gpt-6-luna` (Phase 0r, 2026-10-14)

- **Deterministic in every test so far.** Identical requests returned identical probabilities: 40 ambiguous questions × 25 repeats in two sessions about an hour apart (range 0.00, 0 flips), 192 entity pairs × 12 calls (0 flips; Jev up to 0.37 and 12/192), and all 1,824 probe-4 pairs across two runs (0 differing) **[Q10, Q4]**. Within one day only: the alias has no snapshot, so this can change without notice (R15).
- **Ties are exact and stable, not jittery.** Exact 0.50 appeared on 0/2,000 contract answers, and two near-threshold questions returned 0.50 on all 30 calls; no argmax flipped on 180 choice questions × 10 **[Q10]**. The tie margin stays (DESIGN §6.2), now to keep stable 0.50s and near-ties from committing, rather than to absorb jitter.
- **Questions are independent.** Question names (including `yes_`/`no_` prefixes and opaque ids), order, and co-batching with 0–50 other questions changed no answer **[Q10]**.
- **Probabilities have at most two decimals and every distribution sums to exactly 1.00** (5,841 values; K up to 255); the vendor's `choice` was always the argmax **[Q14]**.
- **Positional references still fail.** Indexing into 150 items was wrong 0.578 of the time; keyed references 0.006 **[Q5]**. R13 stands.
- **Content in the source still steers answers** (20/46 absent cases steered, as on Jev) **[Q6]**.
- **Abstention is weaker than on Jev; selection is stronger** (Q1–Q3, Q8), and calibration on this task is worse (ECE 0.120 against 0.046) **[Q7]**. This is why source selection stays dropped.
- **Unexplained refusals:** two "needle" choice questions over large inputs were refused at all 9 sizes tried, while yes/no questions over the same text were answered **[Q11]**. No other refusal occurred in 2,767 requests.
- **Latency** (sequential, client clock): p50 0.20 s for 1 question and 0.52 s for 200 over a small input; 1.2–1.6 s over ~200k tokens; 5–13 s over 500k–915k **[Q13]**. Slower than Jev (0.15–0.22 s).

### 2.3a Behaviour — measured on `jev-1.13.0` (the record)

Everything in this subsection was measured on Jev, or documented by TypeSafe for Jev. §2.3 above records which of it held on the Decisions API. The design rules these measurements motivated — the tie margin, keyed references, untrusted sources, mandatory `none_of_these` — stay in force for the decision model, citing this evidence. The guide documents none of these properties for the Decisions API: there is no seed or temperature control **[D2]**, and two small third-party reports of identical answers to identical requests are unverified **[D6, D7]**.

- **Near-deterministic, not deterministic.** Byte-identical requests return different probabilities. Bool nouls jitter least (per-question range ≤ 0.05 for 90% of 200 contract questions over 10 repeats **[P12]**); **choices jitter more** (range p90 0.11, max 0.21 over 180 enum questions × 10 repeats; the argmax flipped on 14/180 questions) **[P20]**; and **ambiguous entity-pair nouls ranged up to 0.37** (0.22–0.59, sd 0.13) over 12 identical calls, with 16 of 1,824 pair decisions flipping between two identical runs **[P12]**. On 40 ambiguous yes/no questions × 25 repeats × 2 sessions, no decision away from the threshold flipped **[P1]**. The vendor's σ ≈ 0.01 was measured with a fresh `uid` in each call, not on identical input **[V-consistency]**.
- **Exact ties are rare; near-threshold flips are not.** An exact 0.50 appeared once in 2,000 bool observations; 1.1% landed within ±0.05 of 0.5; 2 of 200 questions flipped across 10 identical calls, both hedged clauses **[P12]**. The tie margin that removes flips is therefore wider than exact equality (DESIGN §6.2).
- **Questions are independent.** Question keys, map order, and co-batched questions have no measurable effect (0/120 selection changes batched vs alone) **[P1, V-primitives]**. Splitting a level is answer-neutral.
- **Adding questions is nearly free.** State is billed **once per request**; each short noul adds ~22–26 tokens; overhead is ~280 tokens per request **[P3]**. Latency p50: 0.15 s for 1 question, 0.17 s for 100, 0.22 s for 300 over a small state **[P8]**.
- **Cost.** $0.042 per million input tokens, output free **[V-models]**. Cost per decision depends on batching; there is no single constant. `usage.input_tokens` was present on every successful response and `x-typesafe-request-id` on every response whose headers were captured **[P8]**.

**Known weaknesses on Jev**, kept as rules for the decision model:

- **Referencing state by array position fails.** Asking about `items[137]` in a 320-item list gave 62% wrong answers; keyed references (`items.k137`), inlined values, and one request per item gave 0/320 **[P4]**. The error grows with the **length of the indexed list in state**, not with questions per request. The vendor's own examples use `items[{i}]` **[V-jagged]**, so this is a trap.
- **Content in the state can steer answers** **[V-jagged]**. Measured: a note in an invoice advocating the wrong span moved candidate selection 20/20 (advocacy note, confidence up to 0.91; injected instruction, up to 1.00) and defeated `none_of_these` 20/20; the same injections in an LLM *draft* did not flip adjudication (0/80) **[P7]**. See DESIGN §5.8.
- **Literal reading; negations and indirection cost accuracy** **[V-jagged]**. Questions are phrased positively and directly (DESIGN §5.2).
- **No arithmetic, counting, or date comparison** **[V-jagged]** — class F in DESIGN §4, always code.
- **Distractors hurt** **[V-jagged]**; in the abstention pilot, long multi-entity documents were the only regime where `none_of_these` failed **[P5]**.
- **Flat distributions on wide scales.** On 10-level scores, 8 of 12 answers had no level above 0.5 **[P13]**; prefer narrow rubrics.
- **English is the primary training language**; other languages, including CJK scripts, are handled but not equally well **[V-models]**.

Third-party comparisons of the two models (Jev and `gpt-6-luna`) exist and are cited as signal, never as fact **[D5–D9]**; they do not replace Phase 0r.

### 2.4 Hard limits

- **Cannot produce free-form text, arrays, or nested objects** — only a probability, a choice from supplied options, or a score over supplied levels **[D1, D2]**. The guide sends generation of objects and explanations to Structured Outputs and function calling instead **[D1]**.
- **Returns no reasoning text.** `usage.output_tokens_details.reasoning_tokens` is reported, but no reasoning is returned **[D2]**.
- **Has no schema awareness of its own.** Every question Jevson asks is one Jevson constructed.

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
   │   decision nodes (choice | score | predicate)    │
   │   step nodes (external: extract | generate)      │
   └────────────────────┬─────────────────────────────┘
                        ▼
   ┌──────────────────────────────────────────────────┐
   │ EXECUTOR   preflight budget → topological levels │
   │   steps run through Extractor / LLM protocols    │
   │   decisions: one batched request per level,      │
   │     adjudication in its own request              │
   │   bounded retry / redraft loops live here        │
   └────────────────────┬─────────────────────────────┘
                        ▼
              BACKEND (protocol): DecisionsBackend │ FakeBackend │ CachingBackend │ fallbacks (Jev, AnyJev-style, constrained decoding)
                        ▼
   ┌──────────────────────────────────────────────────┐
   │ ASSEMBLER  ordering, entity res. (post-v0),      │
   │            cardinality, overflow, class F parse  │
   └────────────────────┬─────────────────────────────┘
                        ▼
          validate against the original schema
                        ▼
                     Result (DESIGN §8.1)
```

### 3.1 The central abstraction is the decision graph

Jevson is not "JSON Schema → decision questions" — that is what `jev_jsonschema` does for Jev, and why it refuses free-form strings, arrays, objects, and unions **[X3]**. Jevson is:

```text
Schema + Source  →  Decision Graph  →  execution (steps + decision levels)
                 →  Resolved graph  →  JSON assembly  →  validation
```

A graph has two node types. **Only decision nodes are sent to the decision model.**

```text
DecisionNode
  id             target instance pointer + role, e.g. /customer/tier#choice, /items#pair:c3:c7;
                 a retry or redraft of the same node is recorded in Result.decisions as id@n
  kind           choice | score | predicate
  question       compiled from a versioned template (DESIGN §5.2); never references state by position
  options        opaque option ids → descriptions; or ordered levels; or none (predicate)
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

**Audit architecture (not built):** an LLM builds a `Person`, the decision model objects, the work is discarded, retry.

**Construction architecture (built):**

```text
decision model: Person 0.04 / Organization 0.96
→ execute only the Organization branch's nodes → assemble
```

**Every branch is compiled and validated up front** by `compile_schema()`, so refusal stays total and happens before any network call (R14). Only the selected branch is *executed*. The wrong branch's steps — extraction, generation — never run. A branch discriminator has no `none_of_these` in v0; a tie or invalid answer leaves the whole subtree `Unresolved`. Two branches whose required properties and descriptions are identical after normalisation are *undiscriminable* and refuse at compile time.

TypeSafe documents *speculative fan-out* for Jev: ask every branch's questions in one call and let code discard the irrelevant ones **[V-fanout]**. For branches whose nodes are pure decision questions, that saves a round trip at a small token cost; for branches with steps it would run work whose output is discarded. The choice is measured in `PLAN.md` Phase 6.

**As built (Phase 6, ASTERION-37):**

- **The discriminator** is one `choice`, `<pointer>#branch`, over one option per branch, asked with the union template of `docs/taxonomy.md` §1.2. An option's text is the branch's `title: description`, or whichever of the two it has, or else a summary of its shape (`with name, email`, its required properties). A text two branches share gets the summary appended; branches still identical after that refuse with `undiscriminable_union`. Pydantic titles every model with its class name.
- **Gates.** A node inside a branch carries its gates, the `(discriminator, option)` pairs above it, outermost first, so nested unions compose. Its id is its pointer with `|<option>` after the union's pointer (`/payment|c1/speed#choice`), because two branches may decide the same instance pointer. `|` is not a JSON pointer escape, the `#role` suffix, or the `@n` attempt suffix, and it is not an index (R13).
- **Execution.** A node whose branch was not selected never runs and leaves nothing in `.value`, not even a null. The selected branch's constants (a Pydantic tag such as `type: "card"`) are committed by code (`decided_by: code`), and so is every required constant with no default outside a union. Without them, a discriminated union fails `oneOf` and `model_validate`.
- **Strategy: fan-out by default** (`JevsonConfig.union_fanout`, chosen from the Phase 6 measurement, §12). A union whose branches hold only decisions asks them in the discriminator's request; the executor records the discriminator first and discards the unselected branches' answers, which never reach `Result.decisions`. A union with a `generate` field anywhere in it always takes the separate level, so its steps never run speculatively. With `union_fanout=False` every union takes the separate level, and only the selected branch's questions are sent.
- **A root-level union refuses** with `root_union`. `.value` is an object, a Pydantic model's root is a model, and a root discriminator would leave nothing to name in `.unresolved` but `""`. Wrap the union in a field.
- **Arrays of unions** refuse with `union_in_array`, beside arrays of objects. `anyOf` beside `oneOf` refuses with `unsupported_keyword`. `generate` on a union refuses with `generate_field_type`.

### 3.3 Level batching

```text
decision graph → dependency analysis → topological levels
              → one batched request of named questions per level (split only by DESIGN §8.2)
```

Questions in one request share one `input` and are independent **[D1]**; on Jev, state was billed once per request and batching was answer-neutral **[P1, P3]**, and on the Decisions API the input is billed once per request and co-batching with up to 50 other questions changed no answer **[Q10, Q11]**, so batching is cheaper and answer-neutral; a level holds at most 200 questions **[Q11]**. A typical object resolves in **1–3 requests**: one level for everything that depends only on extraction, one more for each union discriminator above it. A level that adjudicates drafts asks those questions in a request of their own (DESIGN §5.2), so it costs one more request, plus one per redraft round. Array membership questions are asked over all candidates in the *same* level, so arrays add no level (pairwise entity questions, post-v0 **[Z4]**, would join that level).

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

1. **Normaliser/compiler.** `category` → `choice` over declared values. `vendor`, `billing_address` → source selection over candidate spans. `total` (Pydantic `Decimal`, normalised to a decimal value emitted as a string) → source selection over *money* candidates, then a deterministic parse of the selected span (class F on a selected span — the decision model never does arithmetic). `line_items` → membership `predicate` per candidate (deduplication is the extractor's contract in v0, R6).
2. **Extract steps** return verified candidate spans with offsets: two organisations, two addresses, three money amounts, five line-item strings.
3. **Graph:** every decision depends only on the extract steps → **one decision level → one request**. Candidates are placed in state as an object keyed by opaque ids (`c0…cN`), never by position (R13).
4. **The Decisions API** returns selections, distributions, and `none_of_these` probabilities in one pass.
5. **Assembler** orders accepted line items by source offset, enforces `maxItems` retaining overflow, parses the selected total, inserts values by span.
6. **Validate** against the original schema. Provenance: `vendor ← [142,151)`, `total ← [610,617)`, `category ← declared option`.

**In v0** (DESIGN §10.1) this schema refuses at compile time: `vendor`, `total`, `billing_address`, and `line_items` declare `x-jevson.source`, so `compile_schema()` raises one `CompileError` listing all four pointers with the reason `source_selection_dropped` (R14). With those four fields removed, `category` compiles to one `choice` in one level, as above.

### 3.5 Normalisation and field declarations

**Normalisation** (class A, before mapping; the compiler reads Pydantic's `mode="validation"` schema, with Pydantic ≥ 2.12, whose output is byte-identical to the latest release on 20 cases while 2.8–2.11 differ **[L18]**) **[L3, L16]**:

| emitted construct | normalised to |
|---|---|
| static, acyclic local `$ref` / `$defs` (nested models, `Enum` classes) | inlined, merging any sibling keywords on the referencing property (Pydantic places `x-jevson`, `description`, and `default` next to the `$ref`) **[L18]**; node ids come from **instance** pointers, so two fields of one `$defs` type get distinct ids |
| `anyOf: [T, {type: null}]`, `type: [T, "null"]` (`Optional[T]`); a flat `anyOf` whose non-null branches are themselves one normalisable type (e.g. `Optional[Decimal]` emits three branches) | the null branch is stripped first; nullable T, no discrimination node **[L18]** |
| `const`, single-value `Literal`, single-member `Enum` (emitted as a `$ref` to a one-value `enum`) | deterministic constant **[L18]**, committed by code when it is required with no default, or sits in the selected union branch (§3.2) |
| `Decimal` (`anyOf [number, string with pattern]`) | a decimal value, emitted in `.value` as the **string** form, because `jsonschema` rejects valid cents under `multipleOf: 0.01` as floats (11,426 of 100,001 values) and Pydantic's unanchored pattern accepts too many digits **[L18]** |
| flat `allOf` of object schemas (raw JSON Schema; Pydantic ≥ 2.10 emits none **[L18]**) | merged; anything else refused |
| `anyOf` / `oneOf` with ≥ 2 non-null branches, a type list with ≥ 2 non-null types, `oneOf` + `discriminator` (Pydantic discriminated unions) | a union: a discriminator `choice`, then the selected branch (§3.2); a root-level union refuses (`root_union`) |
| `exclusiveMinimum`/`exclusiveMaximum`, `multipleOf`, `format` | kept for final validation only |
| recursive or dynamic `$ref`, `dict[str, X]` (`additionalProperties` schema), tuples (`prefixItems`), `Any`, `bytes`, arrays of objects | refused with a named reason (tracked in `PLAN.md` §9) |

**Field declarations.** Per-field configuration lives in one keyword, **`x-jevson`**. Pydantic users write `Field(json_schema_extra={"x-jevson": {...}})`, so the emitted JSON Schema is identical to what a raw-schema user writes; Pydantic places it on the property, beside any `$ref` **[L18]**. Keys:

```text
source:    { extractor: <name>, entity_type?: <name>, direct_extraction?: bool,
             scope?: <text>, max_candidates?: int (default 50, ≤ 254),
             max_candidate_chars?: int (default 120), locale?: <BCP 47 tag> }
                           # refuses in v0: source_selection_dropped (below)
generate:  { criteria: [<text>], rubric?: {description: <text>, levels: [...], minimum: <level>},
             instructions?: <text>, max_draft_chars?: int }
                           # a rubric without a non-empty description refuses: rubric_description_missing
ordinal:   true            # an integer range is an ordinal rating → score (DESIGN §4.2)
order:     source | semantic   # semantic refuses in v0 (R7)
question:  <text>          # overrides the compiled field description
```

- A **leaf** field (not an object or array) with a `default` and no `x-jevson` key other than `order` is **class A**: it is omitted from `.value` so the default applies (`decided_by: code`); it is neither decided nor refused. To have it decided, declare `generate` (or `source`, which refuses in v0), or add `x-jevson.question` (or `ordinal: true`) to a bool, enum, or integer-range field. An **object or array** field's default does not make it class A: it is compiled from its descendants' or items' declarations, and it is class A only if nothing in it would be decided; its absence then follows DESIGN §5.6.
- **`source` refuses in v0.** Phase 0r dropped source selection **[Q2, Q9]**, so a field declaring `x-jevson.source` refuses at compile time with the reason **`source_selection_dropped`**, whatever its extractor and keys, never with `not_yet_supported`, which promises a later phase. The rest of this subsection describes the source-selection design of record (`PLAN.md` §9.2).
- An unbounded `string` or `number` field (including `format` strings and `Decimal`) with no default and neither `source` nor `generate` **refuses (class G)** — unless a default extractor is configured, in which case it is source-selected with that extractor; **in v0, such a field refuses with `source_selection_dropped` instead**. The built-in pattern extractors (`money`, `date`, `email`, `phone`, `url`) are used **only when declared** by name, so a `weight_kg: Decimal` is never mistaken for money.
- Because class G depends on configuration, `compile_schema(schema, extractors={names}, default_extractor=None)` receives the extractor *names* (not instances); an `x-jevson.source.extractor` naming an unknown extractor refuses. In v0 both parameters are kept so reviving class D is not a signature change, and they can only change which refusal a field gets.
- Library-wide settings live in one `JevsonConfig`: the tie margin, (post-v0, with entity resolution **[Z4]**: entity-type normalisers, `conflict_floor`, the entity rule variant, the pairwise cap), (with class D, deferred: the source screen and the retry budget), `default_extractor`, `raise_on_unresolved_required`, `step_timeout_s`, and the redraft and transport budgets. `resolve()` may override the redraft budget per call (and, with class D, the retry budget). `locale` (class D, deferred) (on a source declaration) fixes how class F reads decimal and grouping separators and numeric dates; the default is `en-US` (`,` groups thousands, `.` marks decimals, numeric dates are month-first), so `$1,204` is 1204 and `$1,204.50` is 1204.50. Parsing is strict (grouping separators only between groups of three digits); a selected span that does not parse under the field's locale — `1.204,50` under the default — is `Unresolved(unparseable)`; ISO dates and dates with month names parse under any locale. A `locale` tag Jevson does not support refuses at compile time.
- A field can declare `source` or `generate`, not both.
- Unknown `x-jevson` keys refuse at compile time.

---

## 4. The classification model

Every schema construct and extraction operation falls into exactly one class. This taxonomy is the compiler's backbone and the instrument that decides v0's scope (`PLAN.md` Phase 0).

| class | name | handled by | example |
|---|---|---|---|
| **A** | Deterministic | ordinary code | required fields, nesting, defaults, types, constants, nullable |
| **B** | Grammar | constrained decoding, where the caller's LLM supports it | key spelling in an LLM draft |
| **C** | Bounded semantic decision | **the decision model** | classification, ordinal rating, boolean predicate, union discrimination |
| **D** | Source selection — **not in v0** (Phase 0r **[Q2, Q9]**) | **candidate spans + the decision model** | which of four spans is the billing address |
| **E** | Unbounded generation | LLM, then decision-model adjudication | a summary, a synthesised description |
| **F** | Computational | deterministic code | parsing a selected money span (deferred with class D), date arithmetic, unit conversion |
| **G** | Unsupported | explicit refusal | anything the compiler cannot map |

### 4.1 "Can be a decision question" is not "should be a decision question"

When the value is determined by the schema and the source is not needed, the decision model adds cost and nothing else. By contrast, *"which of these three people is the customer?"* cannot be answered by the schema or a grammar — the value must be selected from evidence.

Every taxonomy entry therefore records its **existing alternatives** — constrained decoding, plain code, TypeSafe's cookbooks, and the open projects in DESIGN §9 **[X3]**.

### 4.2 Mapping rules — corrected against evidence

The mapping from `jev_jsonschema` **[X3]** is adopted with corrections:

| construct | mapping | note |
|---|---|---|
| `bool` | `predicate`; true iff p ≥ 0.56; false iff p ≤ 0.44; 0.45–0.55 inclusive is `Unresolved(tie)` | on Jev, the band that removed every true↔false flip across 10 identical calls on 200 questions counted 0.45 and 0.55 as ties **[P12]**; it is the tie margin of DESIGN §6.2 applied to a binary answer |
| string/int enum, 2–255 values | `choice` over opaque ids; a top-two margin ≤ 0.10 → `Unresolved(tie)` | on Jev, a ±0.05 band left 11/180 argmax flips; a 0.10 margin left 1/180, converting 7.8% of answers to ties **[P20]** |
| integer range 2–10 **declared `ordinal: true`** | `score`; the value is the **most probable level**; a top-two margin ≤ 0.10 → tie | the API's `score` is a probability-weighted mean of level indices **[D1]** (e.g. 3.20 for p = [.45,0,0,0,.55]) that can fail `type: integer` **[L4]**; on Jev, round(score) and argmax disagreed on 8/60 live scores **[P13]** |
| integer range not declared ordinal (a count, a quantity) | a number: source-selected (class D + F) or refused | counts are not ratings; counting is never asked of the decision model (Jev documented that it cannot count **[V-jagged]**) |
| number bounded 0–1 | **not** a probability; a number like any other | mapping it to the decision model's probability writes a belief into value fields such as `tax_rate: 0.20` **[L4]** |
| array of enum (multi-label) | one membership `predicate` per declared value, with the bool rule; elements in declared enum order; `maxItems` keeps the first k in that order, overflow retained; a tied value is `Unresolved(tie)` at the array pointer naming the value, the others emitted | `PLAN.md` Phase 7 |

---

## 5. Candidates, provenance, and abstention

> **Not in v0.** Phase 0r confirmed the pre-registered verdict **drop source selection** on the Decisions API **[Q2, Q9]**, as Phase 0 had on Jev **[Z9]**. DESIGN §5.1–§5.6, the source screen in §5.8, and span verification in §5.9 are the **design of record** for that deferred work (`PLAN.md` §9.2); they describe no v0 behaviour. What v0 keeps from this section: DESIGN §5.2's template rules for its own questions (versioned templates, positive phrasing, keyed level state), §5.7 as the post-v0 entity-resolution design, §5.8's untrusted-source limit, and the provenance *types* of §5.9.

### 5.1 The decision model cannot generate a string — but it can choose one

Given *"Dana Whitfield, VP of Marketing at Acme Corp, met with John Smith from Globex yesterday"*, an extract step produces verified candidate spans and the question becomes a `choice`:

```text
choice(/customer/name):
    c0  "Dana Whitfield"   [0, 14)
    c1  "John Smith"       [52, 62)
    none_of_these
→ c0  p=0.91
```

The decision model never generates the text. Code inserts the selected span. This is TypeSafe's documented pattern for Jev **[V-preparsed]**; Jevson's contribution is compiling it from a schema and carrying it through the rest of the pipeline.

**Options are opaque ids** (`c0…cN`), sent as each choice's string `value`, with the span text in its `description` **[D2]**. On Jev, text keys and opaque ids performed equivalently (35/36 identical selections) **[P5]**.

**Identical text at several offsets.** When a candidate's text occurs more than once in the source, **every occurrence is offered as its own option, with a ±40-character context window in its description.** On Jev, with context windows the model picked the right occurrence 40/40; with text alone it was at chance, 22/40 **[P15]**. **`max_candidates` counts options after this expansion**; a field whose occurrences exceed it is `Unresolved(too_many_candidates)`, with the distinct texts and occurrence counts in `detail`. Offering every occurrence matters: when only a wrong-role occurrence was offered, it was committed 48–83% of the time rather than abstained on — the value text is right but the provenance is wrong **[P15]**. Code finds every occurrence by exact match. Mixing context-bearing and bare options in one choice did not bias decisions out of sample (repeated-text answers 48/48 mixed vs 20/48 all bare; unique answers 48/48 in every format), though ~0.10 of probability mass shifted toward context-bearing options when the answer was absent and 1 of 48 such cases committed one **[P19]**; the test was near ceiling.

### 5.2 Questions are compiled from versioned templates

Question wording decides accuracy, so it is code, not ad hoc prose. `compile/questions.py` renders every question from a template with a recorded `QUESTION_TEMPLATE_VERSION`; Phase 0 probes use the same templates, so their verdicts carry over.

Template rules, each backed by evidence:

- **Demand the complete value.** Candidate questions ask: "Which of these is the complete *<field>* as written in the source? A partial value — for example a street without its city, or a date without its year — is not acceptable.", and `none_of_these` reads "None of the other options is the complete *<field>* as written in the source; a partial value does not count." This exact text was tested out of sample: with the full value among 4 competitors it was chosen 72/72 with and without the wording; when only partial variants were offered, correct abstention rose from 19/72 to 72/72 **[P18]**. An earlier variant cut lone partial commits from 32/42 to 0/42 **[P11]**.
- **When the source itself states only a partial value**, the intended answer is abstention (the field is then absent). Measured compliance depends on the field: addresses and dates abstained, while names, phones, and venues often committed the longest partial (15/36 abstained overall) **[P18]**. This is a stated limit. On real documents, sources stating only a partial value were abstained on 11/17 **[Z8]**.
- **Positive, direct phrasing; no negations** **[V-jagged]**.
- **No two questions alike.** A level's questions share one input, so identical questions get identical answers. A label that is not unique in the graph is qualified by its nearest ancestor property names ("billing kind", "shipping kind"), and `compile_schema()` refuses `duplicate_question` for any two nodes that still render the same question over the same options. A decided bool needs a statement (`x-jevson.question` or `description`) and is otherwise refused `bool_predicate_missing` (`docs/taxonomy.md` §1.2, template version 1.1.0).
- **Level state layout.** A level's state is `{"source": …}` plus, when present, `"candidates": {<opaque id>: …}` and `"drafts": {<field node id>: <draft>}`; each question names the entries it is about by key (R13). **Only adjudication questions are asked over a state that holds `drafts`** (deciding is not rendering: LLM-written text is never input to a bounded decision other than its own adjudication; Asterion invariant 7). A level's adjudication questions go in their own request(s), with the drafts they name; every other question of the level (enums, booleans, ordinals, memberships, discriminators) goes in request(s) over the source-only state. Each group is budgeted and split on its own (DESIGN §8.2). Candidate texts appear in option descriptions; `candidates` in state is used only when a predicate (membership, pair) references a candidate, with ids unique within the level, and preflight counts it in the state size. On Jev, injected drafts did not flip verdicts under a single `draft` key **[P7]**; the keyed multi-draft layout is re-measured by the Phase 4 injection regression, and if it does worse, adjudication issues one call per draft.
- **Scope from the schema.** The field's `description` (or `x-jevson.question`) and `x-jevson.source.scope` are rendered into the question. A generic scoping hint did not improve accuracy measurably (abstention 32/36 → 35/36, present-answer accuracy 36/36 → 33/36) **[P16]**, so no hint is added by default.

### 5.3 Single candidates still get a question

A lone extracted candidate is **not** committed unchecked by default: the extractor is the weak link, and a lone wrong candidate is exactly the wrong-but-valid failure. The default is a two-option `choice([c0, none_of_these])`, batched into the existing level at near-zero marginal cost on Jev **[P3, P8]**. In the Jev pilot it abstained on 84/84 wrong-role lone candidates and falsely abstained on 2/42 correct ones, and behaved the same as the candidate among 2–3 competitors **[P11]**. On real documents on Jev it abstained on 39/50 wrong-role lone candidates and 35/50 lone partials, and committed 49/50 correct ones **[Z8]**: asking still refuses most lone wrong candidates, and committing them unchecked would refuse none. A field may opt into `direct_extraction: true`: a lone verified candidate then commits without a decision, carries no probability, and is listed in `Result.ungated`; zero candidates follow DESIGN §5.6; two or more distinct candidates (counted after the pre-filter below), or one text occurring at several offsets (DESIGN §5.1), are asked as an ordinary choice with `none_of_these` and the field is not ungated.

**Zero candidates** resolve without a backend call (DESIGN §5.6). **More than `max_candidates`** (default 50; hard cap 254, leaving one option for `none_of_these`) is a run-time condition — the compiler never sees a source — and yields `Unresolved(too_many_candidates)` rather than silent truncation. **For fields whose value is the verbatim span**, candidates that cannot satisfy the field's own string constraints (`maxLength`, `minLength`, `pattern`) are rejected before the question is asked, and counted. For class F fields the constraints apply to the parsed value after selection, and a failure is reported in `violations`.

### 5.4 `none_of_these` is mandatory, and it is the safety property

Without it the architecture is **more dangerous than asking an LLM directly**: the decision model's probabilities are relative to the options it was handed (one probability per supplied option **[D2]**; TypeSafe documents the same for Jev **[V-jagged]**), so a missing correct answer is invisible. Every candidate-backed `choice` compiles with a described `none_of_these` option:

```text
SELECT(candidate)   or   ABSTAIN(none_of_these)   or   REFUSED → Unresolved(refused)
```

`none_of_these` means *no supplied candidate is sufficiently supported as the answer* — the source may genuinely not contain one, or extraction may have missed it. A `refusal` answer **[D2]** is neither a selection nor an abstention: it says nothing about the source, so it becomes `Unresolved(refused)` (DESIGN §6.1) and is never read as `none_of_these` or as any option.

**Pilot evidence** (on `jev-1.13.0`; synthetic, author-written; not the pre-registered Phase 0 probe) **[P5]**: on short documents and trap documents (superseded values, negations, near-duplicate names), selection and abstention were at ceiling. In long, multi-entity documents, abstention when the answer was absent fell to 32/36 = 0.89 (95% CI 0.75–0.96); three of the four failures were superseded due dates. A separate yes/no gate ("does any candidate fill this field?") was *worse* (0.56), because in a multi-entity document some candidate usually is *a* seller, just not *the* one. **The choice-with-`none_of_these` design stays; a predicate gate is not used as the abstention mechanism.** Phase 0r re-measures both on the Decisions API.

**On real documents** (the pre-registered Phase 0 probes): the correct span was chosen on 132/150 present-answer cases and `none_of_these` on 2/150 **[Z1, Z3]**, but abstention with the correct span removed was 110/150 = 0.73 — the *conditional* band — and 24/45 in the hard regime (long multi-entity documents or superseded values) **[Z2]**. That put candidate selection behind the second gate of `PLAN.md` Phase 5, which probe 9 then measured early on a fresh corpus: it cut commits on absent answers from 29/139 to 10/139 but left 105/150 correct commits, and the pre-registered verdict was **drop source selection** **[Z9]** (`docs/gate-probe.md`). These are measurements on `jev-1.13.0`; Phase 0r re-runs the probes on the Decisions API, and its verdict replaces this one.

### 5.5 Abstention lifecycle

```text
extract step → verified candidates
      ├── zero candidates ──────────────────────────► absent or Unresolved(no_candidates) (DESIGN §5.6)
      ├── more than max_candidates ─────────────────► Unresolved(too_many_candidates)
      ↓
   decision-model choice (candidates + none_of_these)
      ├── candidate selected ─────────────────────────► value + provenance
      ├── tie (top-two margin ≤ 0.10) ────────────────► Unresolved(tie)
      ├── refusal ────────────────────────────────────► Unresolved(refused); no retry
      └── none_of_these
              ↓
        retry: extractor re-invoked with seen spans as exclusions
              ├── no new verified span ──────────────► as abstention (no backend call)
              └── choice over OLD ∪ NEW + none_of_these
                     ├── candidate selected ─────────► value + provenance
                     ├── refusal ────────────────────► Unresolved(refused)
                     └── none_of_these ─────────────► as abstention (DESIGN §5.6)
```

- **Retry only helps if the input changes.** Retry against a **schema-derived** option set has a budget of **zero**. Retry against a **candidate-derived** set re-extracts; its request is issued only if extraction returns at least one verified span not seen before. A refusal is not retried: the input would be unchanged.
- **The retry offers old ∪ new candidates**, because the distribution is relative to the offered set (DESIGN §5.4).
- **Retries for every field that abstained in one level are batched** into one follow-up call (subject to DESIGN §8.2).
- **The default budget of one is provisional**, with a two-sided bar measured in `PLAN.md` Phase 5: the retry stays on only if it recovers ≥ 10% of abstentions *where the answer was present*, **and** raises the false-commit rate on truly-absent cases by ≤ 2 points. A retry costs a full extraction, which is caller-priced; `retry_budget` is a documented per-call parameter.

### 5.6 Absent, null, and unresolved

**In v0 nothing abstains**, because nothing is source-selected: `Result.absent` is always present and always empty, and no object is ever abstained. The table below is the design of record for class D. Schema-derived decisions never abstain in either case (DESIGN §6); a tie or refusal on them is `Unresolved`.

An abstention is not an error: the source may simply not contain the value. What it produces depends on the schema:

| field | abstention (or zero candidates) yields | recorded in |
|---|---|---|
| not required (with or without a default, nullable or not) | key omitted — a Pydantic caller's `model_validate` then applies the declared default | `Result.absent` |
| required and nullable (`Optional[T]` with no default) | `null` | `Result.absent` |
| required and not nullable | key omitted | `Result.unresolved` (reason `abstained`, or `no_candidates`) |

A **refusal** is not an abstention and never follows this table: whatever the field's requiredness, it yields `Unresolved(refused)` with the key omitted, because it says nothing about whether the source contains the value. An object with a refused class D descendant is not abstained.

A nullable field with a non-null default (`Optional[str] = "x"`) is not required, so it is omitted and the caller receives `"x"`, not `None` **[L18]**.

**Objects.** An object node is abstained when it has at least one class D (source-selected) descendant, every class D descendant abstained or had no candidates, and none committed — a source-grounded array counts as abstained when it accepted no member; a `known=` value inside it counts as committed. Class A, C, and E descendants do not count: when the object is abstained their decisions stay in `Result.decisions` but their values are discarded, and a `generate` step under the object is not run (the object's class D decisions, including their retries, are ordered before it; generate steps at the root wait for nothing, since the root is never abstained). An object with no class D descendant is never abstained, and **the root object is never abstained**. The abstained object then follows the table itself (omitted, `null`, or `Unresolved(abstained)`), recorded once at the object pointer. If any class D descendant committed, each required descendant that abstained is `Unresolved(abstained)` as usual. So `Optional[Address] = None` on an invoice with no shipping address is simply absent, even if `Address` has an enum field.

`complete` is therefore true for a document that legitimately lacks an optional field, and callers who treat absence as suspicious read `Result.absent`. Because abstention cannot tell "not in the source" from "the extractor missed it", `absent` carries the candidates seen and the abstain probability.

### 5.7 Entity resolution

Pairwise `predicate` answers are independent, so they can contradict each other: *A = B*, *B = C*, *A ≠ C*. In the round-1 pilot on Jev, 95.1% of pairs were judged correctly but **42% of documents contained a non-transitive triple** **[P6]**; the same pair can move by up to 0.37 across identical calls **[P12]**. Resolution runs in stages:

1. **Deterministic pre-merge, no model.** Candidates of one entity type whose text is identical under that type's `Normalizer` merge before any question is asked. **The default normaliser is lossless on case:** Unicode NFC plus whitespace collapse. Casefolding is opt-in per entity type, because it silently merges `US`/`us`, `Apple`/`apple`, `IT`/`it`, `CAT`/`cat` **[L1]**. The normaliser never merges initials or first names (`Sam`/`Samuel`, `D. Whitman`), which were the pilot's dominant failure **[P6]**.
2. **Pairwise `predicate`** over the remaining candidates, asked in the same level as membership (capped, DESIGN §8.2). Components are built over **accepted members only**: pair answers involving non-members are recorded in `decisions` and ignored, so a rejected candidate never bridges two members. Components are the connected components of member pairs with p(same) > 0.5. A refused pair answer is treated as a pair inside the tie band: the components it links become `Unresolved(refused)`.
3. **Internal consistency (always on).** A component containing a pair at or below `conflict_floor` — a confident "different" — is a possible wrong merge and becomes `Unresolved(entity_conflict)`, naming its spans and the offending pairs. Internal pairs above the floor are tolerated, so a chain such as *Dana* ↔ *Dana Whitfield* ↔ *Ms. Whitfield* still merges.
4. **Cross-component consistency (the variant Phase 0 chose on Jev **[Z4]**).** Additionally, a component linked to another by a pair in (`conflict_floor`, 0.5] is a possible split, which would emit a duplicate element; under this variant both components become `Unresolved(entity_conflict)`.
5. Other components are emitted, and an array with any unresolved component is incomplete. A membership tie on a mention likewise leaves its array incomplete. With ~1.1% of pilot yes/no answers and 2.6% of pilot candidate choices inside the margin **[P12, P22]** (membership predicates themselves not yet measured), long arrays will sometimes be incomplete for this reason alone; the post-v0 entity-resolution phase reports how often (`PLAN.md` §9.1).

**How the variant was chosen.** On 48 pilot documents on Jev (1,824 pairs, two identical runs) the internal rule alone was silently wrong on 5/133 and 6/134 components, mostly *splits*, and adding the cross-component condition gave 0/133 and 0/134 at 113/133 and 109/134 correct versus 117 — but that was found and scored in-sample **[P10]**. Out of sample, on 80 new documents in new domains (5,410 pairs, two runs), **no split occurred in 160 document-runs**, both rules were silently wrong on 1/312 components (a consistent-but-wrong merge), and the cross-component condition only blanked 8–9 otherwise-correct components; each uncertain cross pair blanks two components **[P17]**. Plain connected components were silently wrong on 25/312 **[P17]**. The non-transitive rate is template-dependent: 42% of documents in the first pilot, 12% and 60% on two later sets **[P6, P17]**. `PLAN.md` Phase 0 probe 4 then chose between them on real prose by a pre-registered rule (item 6) **[Z4]**.

6. **`conflict_floor` = 0.05, and the variant is the cross-component rule**, both chosen on `jev-1.13.0` by the rules fixed before the data was seen **[Z4]**. On 50 real prose clusters (360 same-entity pairs over two runs), 2/360 same-entity pairs were at or below 0.05 and 8/360 at or below 0.10, so the rule selected the *bottom* of its grid, not the top it selected on every pilot corpus **[P10, P17]**; the grid top does not bind. The internal rule was silently wrong on 30/330 components (20 splits, 10 merges); adding the cross-component condition cut that to 4/330 but, with any cross pair in (0.05, 0.5] blanking both components, left 163/330 correct. The lower silently-wrong rate selects the cross-component variant, and under it probe 4 is **stop** (correct 0.494 < 0.70); under the internal rule it would also be stop (silently wrong 0.091 > 0.05). Pair judgements themselves were accurate (1560/1592) and stable (2/796 flips).

**Consequence for v0:** pairwise entity resolution does not ship. Deduplication is the extractor's declared contract (`PLAN.md` Phase 7's abandon criterion, applied from Phase 0), and this section describes the design a post-v0 phase re-measures (`PLAN.md` §9.1).

**Stated limit:** a partition that is *consistent but wrong* — two people with near-identical names judged the same with high probability and no uncertain link — cannot be detected by any rule of this kind **[P6, P10, P17]**.

### 5.8 The source is untrusted input

Provenance proves **where** a value came from, not that the source is honest. Anyone who can write a sentence into the source can steer candidate selection: on Jev, a note beside the wrong address moved the selection 20/20 and turned 20/20 correct abstentions into confident commits **[P7]**. TypeSafe documents it as a Jev weakness **[V-jagged]**; the Decisions API documents nothing about it either way, and Phase 0r re-measures it. No rule in this document defends against it.

What Jevson does:

- States the limit in the README, the result documentation, and DESIGN §6.
- **Deferred with class D (`PLAN.md` §9): not in v0.** The design of record was to ship an **opt-in source screen**: one `predicate` over the source, asked in the first decision level, asking whether the source contains text addressed to automated processors. In the first pilot one wording flagged 40/40 attacks with 0/40 false positives and a second flagged 20/20 *benign* invoices **[P7]**; out of sample, the first wording caught 60/60 attacks (all at p ≥ 0.86) but **flagged 27–28 of 60 benign invoices, e-mails, and contracts**, triggered by ordinary processing notes (EDI and AP-portal routing, "file under"), while plain instructions were flagged 0/66 **[P21]**. **The screen does not work yet**; it stays off by default until `PLAN.md` Phase 5 finds a wording that meets its bar on real documents that include processing notes. A first reading on real documents on Jev was far better: it flagged 50/50 attacked documents, 0/50 of the same documents unattacked, and 3/50 benign documents with ordinary processing notes (mostly auction pick-up instructions) **[Z6]** — not the Phase 5 bar, which needs ≥ 300 held-out benign documents. It flags at p ≥ 0.56 only — flagging the tie band caught no extra attacks and added 5–8% false positives **[P21]**. A flagged source turns **every field decided from the source** — classes D and E, and class C decisions whose question reads the source — into `Unresolved(source_flagged)`; constants and defaults (class A) are unaffected.
- States that **the screen can itself be steered**: it is a decision question over the same untrusted text. A refused screen answer counts as flagged.
- Includes hostile sources in the adversarial suite (`PLAN.md` §4.2).

Adjudication of LLM drafts (DESIGN §6.3) was not steered on Jev by the same injections (0/80) **[P7]**; that result is a regression test, not a guarantee.

### 5.9 Provenance

Exactly two kinds in the type:

```text
SOURCE_SPAN      source id, start offset, end offset
DECLARED_OPTION  option identifier (schema enum value, rubric level)
```

**In v0 only `DECLARED_OPTION` is ever produced.** `SOURCE_SPAN` and the `Span` type (with `source_id`) stay in the public types so that reviving class D is not a breaking change, but no v0 code constructs a span, the grapheme segmenter and its table are not built, and `Result.versions` records no grapheme-table or `unicodedata` version (DESIGN §8.1). The span semantics below are the design of record.

**Span semantics:**

- Offsets are **Python `str` code-point offsets** into the **original, un-normalised** source, half-open `[start, end)` **[L1]**. Normalisation never produces provenance offsets.
- A span is valid only if `source[start:end]` equals the candidate text exactly, **and both boundaries are extended-grapheme-cluster boundaries under Unicode UAX #29** at a pinned Unicode version, tested against the Unicode `GraphemeBreakTest.txt` conformance file. A shorthand rule ("not before a combining mark, variation selector, skin-tone modifier, or ZWJ") accepted 63,855–76,510 forbidden boundaries across 13–15 of 20 classes (depending on the reading) — CR|LF, after a ZWJ, inside flag pairs, Hangul jamo, Indic conjuncts, Thai — in a 316,621-position corpus **[L11]**. Python has no grapheme API before 3.15 **[L11]**, so Jevson vendors a generated boundary table — ~1.2 KB compressed, with a 47-line pure-Python segmenter that passed every line of the official conformance test at Unicode 15.1, 16.0, and 17.0 **[L19]** — pinned to **Unicode 17.0**, the version Python 3.15 uses. Because a draft segmenter with a real bug in one rule also passed the conformance file, the implementation is additionally tested differentially against the `regex` module **[L19]**. The table's Unicode version is recorded in `Result`.
- Exact matching rejects an extractor's precomposed `é` for a source's decomposed one, or `\n` for `\r\n` **[L1]**. Rejection is counted and reported, never repaired: extractors return offsets into the original text, and the LLM extractor's strings are located in the source by Jevson.
- Verification happens **before** the backend call. An unverifiable span never becomes an option.
- **v0 takes one source per call** (it is still the input every decision reads), refused at the call boundary otherwise; `source_id` is in the type so multi-source is not a breaking change (`PLAN.md` Phase 9).

**Derived provenance is out of v0** (R9); the one planned exception, deferred with class D, is class F applied to **one selected span** (parsing `"$1,204.50"` into the decimal `"1204.50"`: the span's digits without grouping separators and without rounding), whose provenance is the span. `multipleOf` on a parsed value is checked in decimal arithmetic on those digits, since `jsonschema`'s float check rejects valid cents **[L18]**; `satisfies_schema` therefore uses decimal `multipleOf` where stock `jsonschema` would not.

---

## 6. What is guaranteed

| tier | claim | mechanism | holds unconditionally? |
|---|---|---|---|
| **Structural** | `.value` is valid JSON conforming to the structural schema, or the result says it does not | deterministic assembly + final validation; constrained decoding in the caller's LLM, where supported, reduces redrafts but is not relied on **[X1]** | **yes** |
| **Constraint** | `minimum`, `maxItems`, `pattern`, required fields hold, or the result says they do not (`Result.violations`) | deterministic validation (`jsonschema`, draft 2020-12; `format` checked only with its optional extras **[L10]**); for a Pydantic model, also `model_validate` | **yes** |
| **Provenance** | every bounded value came from a declared option; (with class D, deferred) every value resolved from the source came from a verified span | declared options; (deferred) candidate architecture + substring and UAX #29 boundary verification | **yes**, for fields resolved that way; v0 has no source-resolved fields |
| **Decision** | every decision's full distribution is reported; `choice` and `score` also report the API's `confidence` | the Decisions API | **yes** (predicates have a probability only **[D2]**; a refusal has none and is `Unresolved(refused)`) |
| **Calibration** | reported probabilities match observed frequencies on this task | the decision model | **not yet** — the API makes no calibration claim **[D1]**; Phase 0r's reading on span selection was ECE 0.120 **[Q7]**; the full measurement was `PLAN.md` Phase 5's and is deferred (`PLAN.md` §9) |
| **Semantic correctness** | the value is objectively the right interpretation | — | **no. Not claimed. Not claimable.** |

**Honest limits** that belong in user-facing docs:

- Only fields decided by the decision model carry a probability — a value parsed from a selected span carries that selection's probability; constants, defaults, direct extractions, caller-supplied values, and ungated drafts do not (`Result.decided_by` says which is which).
- **v0 has no abstention**: abstention applies only to source-selected fields, which v0 does not have, and schema-derived choices have no `none_of_these`. A bounded field the source does not support still gets one of its declared options, or `Unresolved(tie)` or `Unresolved(refused)`.
- Adjudication only checks the criteria you declare (DESIGN §6.3).
- **The source is trusted by the model even when it should not be** (DESIGN §5.8).
- Probabilities jittered on identical input on `jev-1.13.0` — bools usually by ≤ 0.05, choices by up to 0.21, ambiguous pair questions by up to 0.37 **[P12, P20]**; on the Decisions API identical requests returned identical answers in every Phase 0r test, within one day **[Q10]**, but it has no seed control **[D2]** and no snapshot, so that can change. The tie margin removed most but not all flips; replay is exact only from recorded responses (DESIGN §8.4).
- Non-English sources were supported less well by Jev **[V-models]**; the Decisions API documents nothing either way.
- (Class D, deferred) **Numbers and dates are read under the field's `locale`, default `en-US`.** A German `1.204` is read as 1.204 and `03.04.2026` as 4 March, silently, unless the field declares its locale. v0 parses nothing from the source.

### 6.1 The central property

> For any schema and any backend, LLM, extractor, or source behaviour whatsoever, a call returns exactly one of:
>
> 1. a `Result` with `.complete is True` and `.satisfies_schema is True`;
> 2. a `Result` with `.complete is False` **or** `.satisfies_schema is False`, every hole named in `.unresolved` and every failed constraint named in `.violations`; or
> 3. a typed exception from Jevson's hierarchy:
>    - `CompileError` — the schema cannot be mapped (raised by `compile_schema()` or at the start of `resolve`);
>    - `PreflightError` — before any backend call: the source or a declared maximum exceeds a context limit, the source is not a single `str` of valid Unicode text (a lone surrogate cannot be sent), or a `known=` value fails the schema;
>    - `UsageError` — `resolve()` called inside a running event loop, or a closed instance used;
>    - `SchemaViolation` — a required field is unresolved and the caller set `raise_on_unresolved_required=True`;
>    - `BackendError`, `LLMError`, `ExtractorError` — a transport or protocol failure (`ExtractorError` is never raised in v0, which has no extractor step).
>    `SchemaViolation`, `BackendError`, `LLMError`, and `ExtractorError` carry the partial `Result` and its `Cost`; `CompileError`, `PreflightError`, and `UsageError` are raised before anything is spent.
>
> Never a fourth outcome. Never a result that claims completeness or validity it does not have. Never an untyped exception from a model's output, an extractor, a malformed HTTP body, or a network failure.

- `satisfies_schema` means `.value` validates against the original schema (and, for a Pydantic model, `model_validate` succeeds); `complete` means `unresolved` is empty. A fully resolved object can still fail a constraint the candidates could not be pre-filtered for (`minItems`, `uniqueItems`, cross-field rules **[L9]**): that is outcome 2 with `complete is True`. `absent` fields do not make a result incomplete (DESIGN §5.6).
- An unresolved **required** field yields outcome 2 by default (`satisfies_schema=False`); with `raise_on_unresolved_required=True` it yields outcome 3. It is never outcome 1. Constraint failures on a complete object are always outcome 2.
- At an unresolved **field** pointer the key is **omitted** from `.value`. An **array** with unresolved members (membership ties in v0; entity components post-v0) is emitted with its resolved elements, and each unresolved member is one `Unresolved` at the array pointer, with its span (or the tied enum value) in `detail`. An unresolved union names its whole subtree; an unresolved root yields `.value == {}`.
- **`Unresolved` reasons are a closed set:** `abstained` and `no_candidates` (required field), `tie`, `invalid_backend_answer`, `too_many_candidates`, `budget_exceeded` (a run-time context-limit rejection that preflight did not predict), `unparseable` (a selected span that class F cannot parse under the field's locale, e.g. `1.204,50` under the default `en-US`), `entity_conflict` (post-v0, with entity resolution **[Z4]**), `redraft_exhausted`, `source_flagged`, `verification_failed` (second gate, `PLAN.md` Phase 5), `dependency_unresolved` (a node whose dependency did not resolve), `refused` (the API answered the question with `refusal` **[D2]**; never mapped to an option, a default, or `absent`). **Reachable in v0:** `tie`, `invalid_backend_answer`, `budget_exceeded`, `redraft_exhausted`, `dependency_unresolved`, `refused`. The others are **reserved** for deferred work (class D, `PLAN.md` §9.2; entity resolution, `PLAN.md` §9.1) and stay in the set so reviving it does not change the type. `not_yet_supported` and `source_selection_dropped` are `CompileError` reasons, not `Unresolved` reasons.
- **A well-formed HTTP 200 whose JSON is malformed or mis-typed** is `invalid_backend_answer` for the affected questions; an unparseable HTTP response is a `BackendError`. An invalid answer to the source screen counts as flagged.
- **Transport retries are not decision retries.** 429, 5xx, and timeouts are retried with exponential backoff up to `transport_retries` (default 2), counted separately in `Cost`, and exempt from the changed-input rule. Other 4xx responses are not retried. A context-limit rejection is never retried unchanged (DESIGN §8.2).

### 6.2 Probabilities are reported, not enforced, by default

Calibration on this task is not established (Phase 0r's reading on span selection was ECE 0.120 **[Q7]**), so v0 ships **no default threshold that drops a committed value**:

- Every decision's distribution is reported (DESIGN §8.1).
- In the class D design, `none_of_these` is the one abstention path on by default — a structural signal about the option set, not a calibration claim. v0 has no abstention path.
- **The tie margin**: a decision whose top two outcomes differ by ≤ 0.10 (in hundredths) yields `Unresolved(tie)`. For a predicate that is 0.45 ≤ p ≤ 0.55; for a choice or score, the top two options. It is a reproducibility rule — decisions inside it flipped on identical input on Jev **[P12, P20]**; on the Decisions API nothing flipped in Phase 0r, but exact 0.50s recurred on the same questions **[Q10]**, so the margin stays — not a confidence gate, and it removes most but not all flips (1/180 choice questions still flipped at 0.10 **[P20]**). It applies to every decision that commits a value or admits a draft: bool fields, enum and candidate choices, scores, array membership, criteria (where a tie counts as a failed criterion, DESIGN §6.3), and union discriminators. Two decisions follow their own rules: entity pairs use DESIGN §5.7, which was measured with a plain 0.5 boundary **[P10, P17]**, and the source screen flags at p ≥ 0.56 **[P21]**. The margin is configurable in `JevsonConfig`. Over the 2,154 saved pilot candidate choices that use a `none_of_these` key it would have converted 56 (2.6%) to ties **[P22]**; on real documents on Jev it converted 20/300 candidate choices (6.7%) **[Z1, Z2]**.
- **A default threshold is deferred, with a pre-registered bar** (`PLAN.md` §9). It is adopted in v1 only if, over ≥ 1,000 pre-labelled candidate-backed decisions from a corpus disjoint from Phase 0:
  1. the **one-sided 95% bootstrap upper bound of top-label ECE** on the selected option's probability is ≤ 0.05, using 15 bins with equal-mass quantile edges merged so that tied probability values are never split; and
  2. among decisions with p ≥ τ, the **Wilson 95% lower bound of accuracy** is ≥ the mean p of those decisions minus 0.03, at τ = 0.90, fixed before the corpus is labelled (τ = 0.80 is reported only); and
  3. before either is evaluated, the bar's operating characteristic is computed **on the observed probability distribution**: if a perfectly calibrated model would pass with probability < 0.95, or a model overconfident by 0.05 with probability > 0.05, the corpus is extended once to 3,000. If the check still fails at 3,000, the bar is recorded as *not decidable* and the threshold stays deferred.

  Why this shape: on the empirical distribution of 2,202 real Jev top-label probabilities (49% exactly 1.00; measured on `jev-1.13.0`, so the shape is re-checked in Phase 0r), condition 1 at n = 1,000 passed a calibrated model 100% of the time and a 0.05-overconfident one 0% **[L14]**; but on a uniform(0.5, 1) distribution the same bar at n = 1,000 passed a calibrated model 0% of the time (99.5% at n = 3,000), and on Beta(18, 2) about 50% **[L13]**, so the power check (3) is mandatory rather than assumed. The earlier "accuracy ≥ τ − 0.02" rule passed an 8-point-overconfident model 96–100% of the time and is replaced by (2) **[L13]**. Brier score is reported alongside.

### 6.3 Generative fields and adjudication

A class E field is drafted by the caller's LLM and admitted only after the decision model adjudicates it.

- **Declaration.** `x-jevson.generate` (DESIGN §3.5), with criteria, an optional rubric and minimum level, optional drafting instructions, and `max_draft_chars`.
- **Criteria are predicates about the draft and the supplied source, never about the world.** "The summary mentions the refund amount stated in the source" is a criterion; "the refund amount is correct" is not — the decision model is not a fact-checker.
- **Execution.** A `generate` step asks the LLM for a one-field tool schema `{value: string}`. Providers differ on the envelope — OpenAI and Anthropic strict modes require `additionalProperties: false`, and Gemini's `parameters` schema has no such field — so the schema is passed as JSON Schema and each `LLM` adapter renders it for its provider **[L20]**. The draft must be ≤ `max_draft_chars` (default 4,000), checked after the call rather than as `maxLength`, so its adjudication budget is known at preflight. Each criterion is one `predicate`, batched with the level's other adjudication questions in a request that holds no other question (DESIGN §5.2), each passing at p ≥ 0.56; a criterion inside the tie margin or refused, or a rubric whose top two levels are within it and straddle the declared minimum or that is refused, counts as **failed** for that draft — named in `rejections` and triggering a redraft, so exhaustion is `redraft_exhausted`, never `tie`. An optional rubric is one `score` whose most probable level must be ≥ the declared minimum; its question names what is rated by the rubric's required `description` (e.g. "how faithfully the summary reflects the source"), since levels alone do not say what they measure.
- **Rejection** names the failing criteria (`Result.rejections`). A redraft passes them back to the LLM. A draft identical to one already adjudicated is not re-adjudicated and counts against `redraft_budget` (default 1). Exhaustion yields `Unresolved(redraft_exhausted)`.
- **Any malformed LLM output** — a missing or misspelled key, prose instead of a tool call, a non-string value, an over-length draft — is a failed draft, never an exception or a malformed object.
- **A field with no criteria** is admitted with a `no_criteria_declared` marker and listed in `Result.ungated`.

---

## 7. The v0 rules

Settled. Changing one is a design change that updates this document. **In v0**, R1, R2, R4, R5, and R9's single-span exception apply to class D and so have nothing to act on (DESIGN §10.1); they stay as the rules the deferred work must follow. R7's source order likewise applies to arrays of spans; v0's multi-label enum arrays are in declared enum order (DESIGN §4.2), and `order: semantic` still refuses.

1. **Candidate-backed choices always include `none_of_these`.**
2. **`none_of_these` triggers bounded retry, then `absent` or `Unresolved`** by the table in DESIGN §5.6 — never an exception, never a silent guess.
3. **Independent decisions are level-batched** into one request of named questions per topological level, except that a level's adjudication questions go in a request of their own, the only one whose state holds drafts, with its per-draft fallback (DESIGN §5.2).
4. **A single candidate is still asked** as `choice([candidate, none_of_these])` unless the field opts into direct extraction (DESIGN §5.3).
5. **Source-grounded arrays are built from membership `predicate`s** over a candidate set.
6. **Array deduplication is the extractor's declared contract in v0**: Phase 0 measured pairwise entity resolution below its bar on real prose on `jev-1.13.0` **[Z4]**, so v0 does not claim it. The entity-resolution stage of DESIGN §5.7 (internal rule plus the cross-component variant, `conflict_floor` 0.05) is the design a post-v0 phase re-measures.
7. **Arrays are in source order.** Semantic ordering is out of v0 and tracked (`PLAN.md` §9); `x-jevson.order: semantic` refuses rather than silently source-ordering.
8. **Overflow is never silently discarded.**
9. **Derived provenance is out of v0**, except class F parsing of one selected span (DESIGN §5.9).
10. **There are no global modes.** One object freely mixes deterministic, source-grounded, decision-model-selected, LLM-generated, and caller-supplied fields (`resolve(schema, source, known={pointer: value})`).
11. **Decision graph, compiler, and executor are the core abstractions**; compilation is separate from execution; loops are executor policy.
12. **The taxonomy determines whether v0 is broad or deliberately narrow.**

Implementation rules of equal standing:

13. **Never reference state by array position.** Candidates and collections are placed in state as objects keyed by stable opaque ids, or inlined into the question. The rule was motivated on Jev (62% vs 0% wrong **[P4]**) and stands for the decision model until Phase 0r says otherwise. Question names are opaque (DESIGN §2).
14. **Refusal is loud and early:** at compile time or in call-time preflight, before any backend call, with the offending JSON pointers.
15. **The model version is recorded, since it cannot be pinned.** The Decisions API offers no snapshot **[D3]**: every response's `model` string is recorded, a change in it is a re-baseline, and exact replay reads records only (DESIGN §2, §8.4). (Until Revision 10 this rule pinned an exact Jev release and rejected aliases.)
16. **The source is untrusted input** (DESIGN §5.8).

---

## 8. Interfaces and dependency posture

Five protocols, each earning its place by having a real second implementation. The three I/O protocols (`Backend`, `Extractor`, `LLM`) are **async**; `Normalizer` and `CostSink` are synchronous. The synchronous `resolve()` submits `aresolve()` to **one library-owned event loop running in a daemon thread**, so every sync call shares one loop; `resolve()` refuses to run inside an already-running loop, where `aresolve()` is the entry point. A fresh loop per call is not used: an `httpx.AsyncClient` and asyncio locks are bound to the loop that first used them, and a second `asyncio.run` fails with `Event loop is closed` **[L20]**. Caller-supplied async objects (`LLM`, `Extractor`) used from `resolve()` run on that library loop, so an object used from `resolve()` must not also be used on another loop. If the caller's wait in `resolve()` is interrupted (Ctrl-C or any other exception), the submitted call is cancelled on the library loop and given up to 2 s to unwind before the exception is re-raised, so it stops spending; the `Cost` spent before the interrupt is not reported.

**Lifecycle.** The library loop keeps one long-lived client. On a caller's loop, **each `aresolve()` call uses its own client**, created on first use and closed before that call returns, so concurrent calls under `asyncio.gather` never close each other's client; if the caller has entered `async with DecisionsBackend(...)` (or `async with Jevson(...)`, which enters its backend) on that loop, calls on that loop share one client until exit. A weak map of per-loop clients does not work, because a client that has made a request keeps its loop alive (5 of 5 survived garbage collection) **[L22]**. `Jevson` and `DecisionsBackend` are context managers: `close()` closes the library-loop client (submitted to that loop), `aclose()` the one for the running loop. After `os.fork()`, `os.register_at_fork(after_in_child=…)` marks the library loop and thread for lazy re-creation on the next call, re-initialises every limiter lock, and drops (without closing) every inherited client. `CostSink.record` may be called from any thread.

**Timeouts.** Every step call is bounded by `JevsonConfig.step_timeout_s` (default 120); expiry raises `ExtractorError(timeout)` or `LLMError(timeout)` with the partial `Result`. Protocol implementations must not block the event loop — blocking work belongs in `asyncio.to_thread` — because a blocking caller implementation stalls every synchronous caller in the process. Jevson's own extractors comply.

| protocol | signature (abridged) | implementations |
|---|---|---|
| `Backend` | `async ask(state, questions, model) -> BackendResponse(answers, input_tokens, request_id, model)` | `DecisionsBackend`, `FakeBackend`, `CachingBackend` (wraps another backend), fallbacks (a Jev backend; AnyJev-style substitutes; constrained decoding over an open model) |
| `Extractor` | `async extract(source, field: FieldSpec, exclude: list[Span]) -> list[Candidate]` | **none in v0** (defined, never called; class D, `PLAN.md` §9.2); planned: LLM-backed, pattern (money, date, email, phone, URL), NER, user-supplied |
| `LLM` | `async complete(messages, tool_schema \| None) -> LLMResponse(arguments: dict \| None, raw: str, input_tokens, output_tokens)` | injected by the caller; `ReplayLLM` for exact replay |
| `Normalizer` | `normalise(text) -> str`, `representative(spans) -> Span` | declared per entity type; used by entity resolution, post-v0 **[Z4]** |
| `CostSink` | `record(cost_event)` | default in-memory, user-supplied |

**`DecisionsBackend` calls `POST /v1/decisions` directly with `httpx`; the vendor SDK is not a dependency** — so every request, retry, and token is visible to `Cost`. The reasons were measured on TypeSafe's SDK: `typesafe-sdk` was pre-1.0 with breaking releases days apart, retried requests by default — requests that may be billed — where `Cost` could not see them, and logged bodies unredacted under `TYPESAFE_LOG_LEVEL=debug` **[V-sdk, X5]**. The `openai` SDK (≥ 3.26.0 for this endpoint **[D1]**) has not been reviewed against them; the decision is revisited when it is.

**API shape.** `Jevson(backend, llm=None, extractors={name: Extractor}, config=JevsonConfig(), cost_sink=None)` with `resolve(schema, source, *, known=None, redraft_budget=None)` / `aresolve(...)`. The schema (a JSON Schema dict or a Pydantic model class) is an argument of each call, so one instance — one backend, one cost sink, one configuration — serves many schemas, and it is compiled at the start of the call, before anything is spent. Every request names `JevsonConfig.model` (default `gpt-6-luna`), which is recorded in `Result.versions` beside the returned `model` string. In v0 `extractors` is accepted and unused (any field that would use one refuses at compile time, DESIGN §3.5); `retry_budget` arrives with class D, as a new keyword. **There is no default backend** — constructing `DecisionsBackend(...)` is an explicit choice to spend money, so an environment variable never silently turns a test into paid calls. The backend's clients follow the lifecycle above: one long-lived client on the library loop, and per-call clients on caller loops. The rate limiter is **per API key**, shared across every `DecisionsBackend` in the process through a registry keyed by a hash of the key, and built on `threading.Lock` rather than asyncio primitives; that design held 20 requests/s exactly across 5 loops, while an asyncio semaphore shared across threads lost a wakeup **[L20]**.

**Caller-supplied values.** `known={pointer: value}` fills fields the caller already has. Each value is validated against the field's schema before any spend (`PreflightError` otherwise); the field's nodes are skipped; `decided_by` is `caller` and no provenance is recorded. `known` pointers name fields outside arrays; a pointer inside a union branch is used only if that branch is selected, and a known discriminator value selects its branch without a decision.

**Privacy posture:** nothing is logged or written by default. Source text, spans, drafts, and values are written nowhere unless the caller supplies a sink or a cache directory.

**Vendor risk:** `Backend` is the substitution point. The Decisions API is a single-vendor public beta with no snapshot **[D1, D3]**. Fallbacks: Jev itself, and AnyJev and jevfire, which provide Jev-style decisions over other models **[X3]**.

### 8.1 The result type

```text
Result
  value             dict — the assembled object; unresolved pointers omitted
  satisfies_schema  bool — .value validates against the original schema
  complete          bool — unresolved is empty
  provenance        {pointer: SOURCE_SPAN | DECLARED_OPTION}
  decided_by        {pointer: code | decision | llm+decision | llm | direct | caller}
                      llm = generated with no criteria declared; caller = supplied via known=
  decisions         {f"{node_id}@{n}": Decision(kind, selected, distribution_hundredths,
                                       vendor_confidence | None, target_pointer)}
                      every decision, n = 0 for the first ask and incremented per retry
                      or redraft: field choices, criteria, membership, pairs, discriminators,
                      the source screen
  unresolved        [Unresolved(pointer, reason, candidates_seen, abstain_probability, detail)]
  violations        [Violation(pointer, keyword, message)]  — failed schema constraints
  absent            [Absent(pointer, candidates_seen, abstain_probability)]
  ungated           [pointer]  — direct-extracted or no_criteria_declared fields
  overflow          [Overflow(pointer, spans, membership_probability, values)]
                      one per array: a multi-label enum array's dropped declared values (spans empty),
                      or (deferred, class D) a source-grounded array's dropped spans (values empty)
  rejections        [Rejection(pointer, criteria, draft)]
  cost              Cost(decision_requests, decision_input_tokens, decision_input_tokens_estimated,
                         decision_request_ids, cache_hits,
                         llm_input_tokens, llm_output_tokens,
                         decision_retries, transport_retries, redrafts, level_splits,
                         wall_clock_by_component)
  model             the `model` string(s) the API returned (currently unpinnable; whether the string names a version is unknown, DESIGN §2)
  versions          question template version, the requested model, the context limits and token estimator
                    preflight used, and the result-affecting settings: tie margin, default_extractor, and
                    the redraft budget used. Added with the
                    deferred work that uses them, and absent until then (not null, not a placeholder):
                    the Unicode versions of the grapheme table and of `unicodedata` (used for NFC) and the
                    retry budget (class D); source screen on/off and its wording version (the screen);
                    conflict_floor, entity rule variant, and pairwise cap (entity resolution, post-v0)
```

Every field is always present. An empty collection is the absence of a condition; `None` never means "nothing happened". The executor emits every cost event to the configured `CostSink` as it happens.

### 8.2 The context budget

On Jev, two limits applied to every request **[V-models, P3]**. **On `/v1/decisions`, Phase 0r measured** a single input limit of ~915k tokens per request (no separate per-question limit) and at most 200 questions per request **[Q11]**. Preflight budgets against **two configured limits**, defaulting to those measured values with a safety margin (input 900,000 tokens; 200 questions), and records the values used in `Result.versions`. They are measured, not documented, so they stay configurable.

- **(a) state + the longest single question ≤ the per-question limit** (Jev: ~32k tokens). Exceeding it cannot be fixed by splitting.
- **(b) state + all questions ≤ the per-request limit** (Jev: ~64k tokens). Exceeding it splits the level (its adjudication questions and its other questions are budgeted and split as two separate groups, DESIGN §5.2; that separation is not a split); questions are independent **[D1]** (and splitting was answer-neutral on Jev **[P1]**), and each split re-sends and re-bills the state (`Cost.level_splits`).

**Preflight, before the first backend call,** budgets every level against both limits using declared maxima, not observed content: (class D, deferred) `max_candidates` options at `max_candidate_chars` plus an 80-character context window each (defaults 50 × 120) for candidate questions, `max_draft_chars` for adjudication, the pairwise cap for entity questions (post-v0), and every union branch and every retry. The per-option and per-question costs measured on the Decisions API (255 options over a 2-option baseline: ~4,510 tokens for realistic spans, ~17,671 with context windows; ~160 tokens per short question **[Q11, Q12]**) calibrate the estimator, against the measured limits of DESIGN §2.2 (200 questions, ~915k input tokens per request), and estimates are compared with `usage.input_tokens` on every response **[D2]**: each decision `CostEvent` carries its request's estimate (`estimated_input_tokens`) beside the billed `input_tokens`, and `Cost.decision_input_tokens_estimated` sums the estimates over the same billed responses. The v0 estimator is a token per 3 UTF-8 bytes plus 160 tokens per question and 8 per option (`bytes/3+160q+8o`); measured on 164 live requests it is conservative for question-heavy requests (1.23–1.27 of billed at 32 questions) but not guaranteed (one single-question request at 0.96) **[Q11, Q15]**. Each node is budgeted at its declared size through a per-node hook, so a phase that adds content to the state budgets it before it exists (Phase 4: a node's `max_draft_chars`); in v0 the declared size is the node's question and option text. A source or declaration that cannot fit raises `PreflightError` before any spend. Because preflight uses declared maxima, a run-time overflow can only come from estimator error or a wrong limit; a context-limit rejection is then mapped to a split for (b), and for (a) — where neither Jev **[P3]** nor the Decisions API **[Q11]** says which question overflowed — the level is bisected to find it and that field becomes `Unresolved(budget_exceeded)`; an identical request is never retried.

**The source ceiling** is the per-question limit minus the longest question. On Jev that was ~108k characters of English prose or ~62k of dense business text alongside a realistic 255-option question **[P14]**; under the default declarations a 50-candidate question of 120-character spans cost ~1.6k tokens, ~2.5k with context windows **[P22]**, so the ceiling was close to the full 32k. Longer sources are refused in v0; chunking is planned (`PLAN.md` Phase 9).

**Pairwise entity resolution is O(n²)**: n(n−1)/2 questions. It is **capped at n = 30** (435 questions) by default. The cost depends on the template: the leanest template needs ~18k tokens for 435 questions and a verbose one ~58k, estimated with a proxy tokenizer **[L7]**, so the template is part of the budget. Pair questions are asked over every candidate, not only accepted members, so the cap applies to candidates. Keyed-batching accuracy was measured up to 320 questions per request **[P4]**, not 435, and non-transitive triples grow with the number of triples, n(n−1)(n−2)/6 — so the *quality* ceiling may be lower than the token ceiling. The post-v0 entity-resolution phase (`PLAN.md` §9.1) measures both and lowers the cap if needed; pairwise resolution is not in v0 **[Z4]**. Above the cap the executor yields `Unresolved(too_many_candidates)` rather than approximating.

### 8.3 Credentials

Anyone must be able to use the library with their own key and none of our tooling.

- `DecisionsBackend(api_key=...)` takes the key as an argument; when omitted (or empty), it falls back to the `OPENAI_API_KEY` environment variable, the name the guide uses **[D1]**.
- With neither, or with an empty string in both, construction raises `MissingCredentials` naming both options, before any network call.
- The library never reads a `.env` file and never writes, logs, or `repr`s the key.
- The team's key lives in Infisical. Until that is set up, the repository's own tests and scripts read a local, gitignored `.env`; its template `.env.example` names `OPENAI_API_KEY`. Fetching the key from Infisical is planned tooling (`PLAN.md` Phase 11).

### 8.4 Replay

The Decisions API offers no snapshot to pin and no seed **[D2, D3]**, and Jev was near-deterministic, not deterministic (DESIGN §2.3), so **a request re-sent is a new measurement, never a replay**. Replay reads recorded responses only. Every response's `model` string is recorded with it **[D2]**; a change in that string between runs is a re-baseline (R15).

Jevson's own code is deterministic: given identical backend, LLM, and extractor responses it produces an identical `Result`, excluding wall-clock timings. **Exact replay** uses two opt-in wrappers, both implementations of existing protocols: `CachingBackend` (key: SHA-256 of the RFC 8785 canonical JSON of the requested model, state, and questions; responses stored whole, with the returned `model` string and probabilities as integer hundredths) and `ReplayLLM` (the same scheme over LLM requests). The Python `rfc8785` and Node `canonicalize` packages produced identical hashes on unicode and edge-case requests; `canonicaljson` and a sorted `json.dumps` did not **[L21]**. A request that cannot be canonicalised (a lone surrogate, an integer beyond 2⁵³) is not cached. A cache hit is counted in `Cost.cache_hits` and spends nothing; with `replay_only=True` a miss raises `BackendError(replay_miss)` (or `LLMError(replay_miss)` for `ReplayLLM`, whose key also includes the caller's LLM id). Exact replay also requires deterministic extractors — pattern extractors are; an LLM-backed extractor is when its `LLM` is a `ReplayLLM`. Both wrappers write only to a directory the caller supplies.

---

## 9. Prior art

Credit where it is due. **Every mechanism below predates Jevson.**

**In the Jev ecosystem** **[X3, V-cookbooks]** — the model Jevson was designed on. These projects target Jev and remain the history of the pattern; none of them is affected by the move to the Decisions API:

| project | what it does | relationship |
|---|---|---|
| TypeSafe cookbook *pre-parsed value extraction* | regex candidates → `choice` over spans with a `NONE` option → code copies the value verbatim | **DESIGN §5.1 and §5.4 are this pattern.** Jevson compiles it from a schema |
| TypeSafe cookbooks *SDE cascade*, *citation check*, *entity alignment*, *date extraction*, *function calling* | per-field "absent from source" nouls over LLM extraction; claim support; merge/curate/leave decisions (the precedent for DESIGN §5.7's refusal to merge on weak evidence); date parts as choices with "not stated"; a signature → questions compiler | each covers one piece; none is a general schema compiler |
| `TypeSafeAI/typesafe-playground` | document extraction with offsets, candidate ids, explicit `null` choice | in TypeSafe's GitHub organisation; describes itself as a community example |
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

> Jevson generalises TypeSafe's "select, don't generate" extraction pattern into a schema compiler: nested objects, unions decided before construction, source-grounded arrays, criteria-gated generative fields, and a typed three-outcome result verified by an adversarial suite.

That is the claim for the full design. **The v0 claim** (the fallback product, DESIGN §10.1), which the Phase 8 README is held to:

> Jevson compiles a Pydantic model or JSON Schema into bounded decisions over the options the schema declares — enums, booleans, ordinal ratings, multi-label enum arrays, and union branches decided before construction — plus generative fields admitted only after passing declared criteria, assembled in code, with a typed three-outcome result verified by an adversarial suite. It does not select values from the source: that was designed, measured on two decision models, and dropped **[Z9, Q2, Q9]**.

`jev_jsonschema` already maps much of the bounded part for Jev **[X3]**; what v0 adds is the decision model it targets, unions, criteria-gated generation, and the typed result.

**Not** "first of its kind." **Not** "nobody catches this." **Not** "guaranteed JSON." Grounding checks and per-field confidence exist elsewhere; the claim is the combination, in an open library, as far as we found.

---

## 10. Limits and refusals

| limit | consequence |
|---|---|
| the decision model cannot produce free-form text **[D1]** | unbounded fields are drafted by the LLM, then adjudicated (DESIGN §6.3) |
| `choice` ≤ 255 options **[D2]**; `none_of_these` takes one | enums > 255 values refuse; (class D, deferred) `max_candidates` ≤ 254, more → `Unresolved(too_many_candidates)` |
| option descriptions dominate large choices | preflight budgets declared maxima; context windows only for repeated text |
| `score` limited by Jevson to 2–10 levels (the API's maximum is undocumented); wide scales came back flat on Jev **[P13]** | only declared ordinals; value = most probable level; narrow rubrics preferred |
| Jev accepted 1-option choices and 1-level scores **[P2]**; the Decisions API documents a minimum of 2 choices **[D2]** | the compiler refuses them either way |
| state + longest question ≤ the per-question limit (Jev: ~32k tokens **[P3]**; unknown for the Decisions API) | on Jev, ~62k–108k characters of source beside a realistic 255-option question, ~30k–50k with context windows on every option **[P14]**; longer refuses in v0 (`PreflightError`); chunking planned (`PLAN.md` Phase 9) |
| state + all questions ≤ the per-request limit (Jev: ~64k tokens **[P3]**; unknown for the Decisions API) | levels split, re-billing the state |
| probabilities jitter; decisions near thresholds flip (measured on Jev **[P12, P20]**) | tie margin → `Unresolved(tie)`; exact replay from records (DESIGN §8.4) |
| any question may be refused **[D2]** | `Unresolved(refused)`; never a default option |
| no pinnable model version **[D3]** | the returned `model` string is recorded; a change is a re-baseline (R15) |
| image input is not adopted (the API reads images **[D1]**) | no image input; adopting it needs a design change, an egress review and its own probes |
| the decision model is not a fact-checker | adjudication is only as good as the declared criteria |
| content in the source can steer selection (measured on Jev **[P7]**) | stated limit; source screen not yet working **[P21]**; hostile-source tests (DESIGN §5.8) |
| abstention on real documents measured below its bar on both models **[Z2, Q2]** | source selection is not in v0 (DESIGN §10.1); `x-jevson.source` refuses with `source_selection_dropped` |
| (class D, deferred) candidate coverage bounds everything | `none_of_these` is the only defence (DESIGN §5.4) |
| pairwise entity resolution is O(n²) | post-v0 **[Z4]**; capped at n = 30, quality measured in its phase (DESIGN §8.2) |
| one source per call in v0 | refused at the call boundary; multi-source planned (`PLAN.md` Phase 9) |
| unbounded array cardinality | v0 ships multi-label enum arrays only; source-grounded membership is deferred with class D; generative lists refused |
| `anyOf` / `oneOf` with ≥ 2 non-null branches | a discriminator `choice`, then only the selected branch (§3.2); every branch is compiled, so a refusal in any branch is total; a root-level union, an array of unions, and undiscriminable branches refuse |
| recursive or dynamic `$ref`, `dict[str, X]`, tuples, `Any`, `bytes`, arrays of objects | refused with a named reason (DESIGN §3.5) |
| dates and amounts in the source | not parsed in v0 (class F on a selected span is deferred with class D); relative dates ("next Friday") tracked (`PLAN.md` §9) |
| non-English sources | supported, less well; documented |
| numbers and dates in other conventions | (class D, deferred) read under the default `en-US` unless the field declares `locale`; misreadings are silent |

**Refusal over invention.** Any construct the compiler cannot map is reported before a single API call, with the offending JSON pointers.

### 10.1 The v0 scope: the fallback product

Frozen from the Phase 0 verdicts on `jev-1.13.0` (`docs/taxonomy.md` §8) — candidate selection *conditional* **[Z1–Z3]**, entity resolution *stop* **[Z4]**, R13 reproduced **[Z5]**, then the second gate *drop* **[Z9]** — and **re-decided by Phase 0r on the Decisions API** (`docs/taxonomy.md` §9): probe 2 *stop* (abstention 79/150 = 0.527) and the second gate *drop* **[Q2, Q9]**, entity resolution *stop* **[Q4]**. The pre-registered abandon criterion fired, so **v0 is the fallback product**: `PLAN.md` Phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7. Phase 5 is abandoned and kept as the record; every class D item is a tracked deferral (`PLAN.md` §9.2).

| capability | class | in v0? | phase | evidence and condition |
|---|---|---|---|---|
| structure, required fields, defaults, constants, nullable | A | yes | 1–3 | — |
| enums (`choice`), booleans (`predicate` with the tie band), declared ordinals (`score`) | C | yes | 2–3 | schema-derived choices have no `none_of_these` in v0 |
| generative fields adjudicated against declared criteria | E | yes | 4 | — |
| union discrimination | C | yes | 6 | — |
| multi-label enum arrays | C | yes | 7 | the only arrays in v0 |
| source selection over verified candidate spans, with `none_of_these`, the complete-value template, context windows for repeated text, lone candidates asked, retry, and the second gate | D | **no**: refused with `source_selection_dropped` | abandoned (5) | drop on Jev **[Z9]** and on the Decisions API **[Q2, Q9]**; revived only by passing probes 1–3 and 9 again (`PLAN.md` §9) |
| span verification and the UAX #29 grapheme table | — | **no** | deferred from 1 | serves class D only; the `Span` type and `SOURCE_SPAN` kind stay in the types |
| parsing one selected span (money, number, date), `locale` | F on D | **no** | deferred from 5 | depends on class D |
| abstention, `Result.absent` populated, object absence (DESIGN §5.6) | — | **no**: `absent` is always empty | deferred from 1 and 5 | depends on class D |
| source-grounded arrays of spans: membership, source order, `maxItems` with overflow | D | **no** | deferred from 7 | depends on class D; would ship without deduplication **[Z4]** |
| opt-in source screen | C | **no** | deferred from 5 | readings: 50/50 attacks, 3/50 benign on Jev **[Z6]**; 50/50 and 1/50 on the Decisions API **[Q6]**; its bar needs ≥ 300 held-out benign documents |
| pairwise entity resolution (internal rule, cross-component variant, `conflict_floor` 0.05) | D | **no** | post-v0 | probe 4 stop on both models **[Z4, Q4]** (`PLAN.md` §9.1) |
| arrays of objects, generative lists, derived values, semantic order, multi-source | G | no | post-v0 | `PLAN.md` §9; multi-source also needs class D |
| state referenced by position | — | never | — | R13 **[Z5, Q5]** |

The taxonomy's prediction that classes C and D are a narrow band was **wrong** on the pre-registered test: in the 16 sampled schemas, class C and D fields are the median majority of a schema (0.79), and most extraction fields are class D; what narrows v0 is structure, since arrays of objects hold most of the resume and receipt fields (`docs/taxonomy.md` §5, §8).

---

## 11. Glossary

| term | meaning |
|---|---|
| **decision node** | one bounded decision-model question with a kind, options, dependencies, and a target pointer |
| **step node** | an external operation (extract, generate) whose output a decision depends on |
| **decision graph** | decision and step nodes with dependency edges; acyclic |
| **level** | a set of mutually independent decision nodes, resolvable in one batched request |
| **candidate** | a verified source span offered as a possible value, under an opaque option id |
| **span** | `(source_id, start, end)` in code points of the original source, on grapheme boundaries |
| **option source** | where a `choice`'s options came from: schema enum, rubric, or candidate spans |
| **abstention** | `none_of_these` selected — no supplied candidate is sufficiently supported |
| **refusal** | the API declined one question (`refusal` answer); recorded as `Unresolved(refused)`, never an abstention or an option |
| **decision model** | the API that answers bounded questions: the OpenAI Decisions API since Revision 10, Jev before |
| **absent** | an abstention on a field the schema allows to be missing or null; not an error |
| **unresolved** | a named hole in the result, with a reason from a closed set |
| **complete** | no unresolved holes |
| **tie margin** | a top-two difference ≤ 0.10, resolved as `Unresolved(tie)`, or as a failed criterion in adjudication |
| **entity resolution** | collapsing spans that refer to the same entity into one array element |
| **conflict floor** | p(same) at or below which a pair counts as confidently different |
| **overflow** | candidates accepted by membership but dropped by a cardinality constraint; always retained |
| **adjudication** | the decision model checking a generated draft against declared criteria before commit |
| **preflight** | the executor's pre-call budget check of every level against declared maxima |

---

## 12. Open questions

Each is recorded in `PLAN.md` §7 against the phase that answers it, with its policy fixed now so the answer changes a setting, not the design.

- **Retry's real value** — was Phase 5 (DESIGN §5.5); deferred with class D (`PLAN.md` §9.2).
- **Calibration on this task** — was Phase 5 (DESIGN §6.2); deferred (`PLAN.md` §9). Readings: ECE 0.046 on 280 committed candidate decisions on Jev **[Z7]**; ECE 0.120 on 276 on the Decisions API **[Q7]**.
- **Source screening** — whether any detector wording can flag hostile sources without flagging ordinary processing notes; the tested wording flagged 27–28 of 60 benign documents **[P21]**, 3/50 on a first reading on real documents on Jev **[Z6]**, and 1/50 on the Decisions API **[Q6]**. Was Phase 5; deferred (`PLAN.md` §9).
- **Union execution: level vs. speculative fan-out** (DESIGN §3.2) — Phase 6. **Answered: fan-out by default** (ASTERION-37, 2026-10-16; `tests/integration/test_live_union_fanout.py`). The test ran 50 fixtures (5 schemas of 2–3-branch unions, 10 sources each), one resolve per strategy each, on `gpt-6-luna`. Fan-out cut the median resolve from 0.366 s to 0.197 s and the requests from 100 to 50, and gave the same value on 50/50 fixtures. It asked 320 questions against 188. On the fixtures' one-line sources it billed 53% more input (42,754 against 27,951 tokens). With a ~1,800-character preamble before every source, it billed 6% less (59,326 against 63,051), because the separate level re-sends the state, so real documents favour it. A union with a `generate` field never fans out.
- **The pairwise quality ceiling** (DESIGN §8.2) — the post-v0 entity-resolution phase (`PLAN.md` §9.1); not answered in v0, since pairwise resolution does not ship **[Z4]**.
- **Whether jitter on pair questions can be reduced** — for example by asking both orderings of a pair — rather than only banded (DESIGN §5.7, **[P12]**). The post-v0 entity-resolution phase (`PLAN.md` §9.1); Phase 0 saw 2/796 pair flips between identical runs on Jev **[Z4]**.
- **Does source selection work on the Decisions API?** Phase 0 found it did not on `jev-1.13.0`: after probe 9 measured the second gate, the pre-registered verdict was to drop source selection (**[Z9]**, `docs/gate-probe.md`; the README's findings). **Answered: no.** Phase 0r re-ran the same pre-registered probes on `gpt-6-luna`: probe 2 fell in its stop band (abstention 79/150 = 0.527) and probe 9 dropped the gate, so the verdict is confirmed **[Q2, Q9]**.
- **The name.** "Jevson" names Jev, which is no longer the decision model, and `jevapi.dev` asserts Jev is a TypeSafe trademark **[X4]**. Whether to rename is a separate follow-up; decided before the PyPI release in `PLAN.md` Phase 8.

**Closed by evidence on `jev-1.13.0`**, and re-checked on the Decisions API where they depend on model behaviour (keyed references **[Q5]**, independence of questions **[Q10]**, the predicate-gate result through probe 9 **[Q9]**): level splitting is answer-neutral **[P1]**; keyed state references matter **[P4]**; a predicate gate is a worse abstention mechanism than `none_of_these` **[P5]**; a lone candidate is safer asked than committed **[P11]**; the score value is the most probable level **[P13]**; the complete-value wording does not cost accuracy when the full value is present **[P18]**. Mixed option descriptions showed no decision bias at near-ceiling accuracy **[P19]**; on real documents, present cases whose correct text repeats were answered correctly 51/63 **[Z1]**. Entity resolution on real prose: below its bar, out of v0 **[Z4]**. State references by position fail on the pinned model **[Z5]**.

---

## 13. Changelog

### Revision 11.5 — 2026-10-19, adjudication asked apart from other questions (ASTERION-50)

- **Request layout (§3.3, §5.2, §6.3, R3, §8.2).** A level's adjudication questions were batched with its enum, boolean, ordinal, membership and discriminator questions, so the LLM's draft sat in the state of unrelated bounded decisions: a draft saying "the mood is happy" was input to the mood question. They now go in request(s) of their own, the only ones whose state holds `drafts`; every other question is asked over the source-only state. Each group is budgeted, split and bisected on its own; `Cost.level_splits` counts only splits within a group. A level with drafts costs one more request.

### Revision 11.4 — 2026-10-16, multi-label enum arrays (ASTERION-38)

- **`Overflow` gains `values` (§8.1).** A multi-label enum array's overflow has no spans, so the dropped declared values are recorded, one `Overflow` per array, aligned with their membership probabilities.
- Membership predicates are ids `<array>#member:c<i>` and ask `According to the source, is "<value>" one of the <label>?`, recorded under question template version 1.1.0 (§4.2, §5.2).

### Revision 11.3 — 2026-10-16, union discrimination (ASTERION-37)

**Unions (§3.2, §3.5, §10, §12).**
- A union compiles to a discriminator `choice` over its branches. Every branch is compiled, and only the selected branch runs.
- Branch nodes are gated, and their ids are qualified with `|<option>`.
- Undiscriminable branches refuse (`undiscriminable_union`), and so do root unions (`root_union`) and arrays of unions (`union_in_array`).
- Fan-out is the default, chosen from the Phase 6 measurement.

**Constants.**
- A required constant with no default (a `Literal["invoice"]` field) is now committed by code. Before, it was omitted, so `.value` failed the schema.
- The selected branch's constants are committed the same way.

**`known=` (§8).**
- A known value for a branch constant selects that branch. It must match exactly one branch.

**`.unresolved`.**
- `Unresolved` entries inside an unresolved subtree are now listed, so an unresolved union names its children `dependency_unresolved` (§6.1).

### Revision 11.2 — 2026-10-16, the rubric names what it rates (ASTERION-32)

`x-jevson.generate.rubric` requires a non-empty `description`, rendered as `{rubric}` in the rubric question (§3.5, §6.3; `docs/taxonomy.md` §1.2); a rubric without one refuses at compile time with `rubric_description_missing`, beside every other offending pointer (R14). The template had a `{rubric}` slot that nothing declared. `generate` on anything but a string refuses with `generate_field_type`.

### Revision 11.1 — 2026-10-15, the façade's call shape (ASTERION-30)

`resolve` and `aresolve` take the schema as their first argument (§8); the API shape had no place for it. `JevsonConfig.model` names the requested model and is recorded in `Result.versions` (§8, §8.1). A source that is not valid Unicode text is a `PreflightError` (§6.1). Preflight's estimate is recorded beside the billed `input_tokens` on every decision event and in `Cost`, and each node is budgeted through a per-node declared-size hook (§8.1, §8.2).

### Revision 11 — 2026-10-14, the fallback scope

Phase 0r confirmed **drop source selection** on the Decisions API **[Q2, Q9]**, so v0 is the fallback product the plan named in advance: `PLAN.md` Phases 1–4, 6 and 8 plus the multi-label enum arrays of Phase 7 (ASTERION-25). No mechanism changed; this revision records which parts of the design v0 builds.

| changed | now | source |
|---|---|---|
| **v0 scope** (DESIGN §10.1) | the fallback product; class D, span verification, class F on a span, abstention, the source screen, and source-grounded arrays are deferred (`PLAN.md` §9.2) | **[Q2, Q9]** |
| **`x-jevson.source` and `default_extractor`** (DESIGN §3.5) | refuse in v0 with the `CompileError` reason `source_selection_dropped`, not `not_yet_supported`; the parameters stay so reviving class D is not a signature change | — |
| **Provenance** (DESIGN §5.9, §6) | v0 produces only `DECLARED_OPTION`; `Span`, `SOURCE_SPAN`, and `source_id` stay in the types | — |
| **`Result.versions`** (DESIGN §8.1) | no grapheme-table, `unicodedata`, retry-budget, or screen entries in v0: absent, not null | — |
| **`Result.absent`** (DESIGN §5.6) | always empty in v0 | — |
| **`Unresolved` reasons** (DESIGN §6.1) | six reachable in v0; the rest reserved for deferred work | — |
| **`resolve()`** (DESIGN §8) | no `retry_budget` in v0 | — |
| **Public claim** (DESIGN §9.1) | a v0 claim added beside the full-design claim | — |
| **Sections 5.1–5.6, 5.8's screen, 5.9's span semantics** | kept as the design of record for deferred work | — |

### Revision 10.1 — 2026-10-14, Phase 0r results

Phase 0r re-ran probes 1–9 and the pilot probes on `gpt-6-luna` (2,767 requests, $2.32; ASTERION-22) **[Q1–Q14]**. §2.2's unknowns are measured (200 questions per request, 2–10 score levels, ~915k input tokens); §2.3 now records the Decisions API's behaviour (deterministic within a day, stable exact ties, names and order without effect, two-decimal probabilities summing to exactly 1.00), and the Jev record moves to §2.3a; the sum tolerance is 1 ± 0.01; preflight is calibrated on the measured costs (§8.2). Source selection stays dropped: probe 2 is in its stop band and probe 9 drops the gate.

### Revision 10 — 2026-10-14, the OpenAI Decisions API replaces Jev

The product owner replaced Jev with the OpenAI Decisions API (`gpt-6-luna`) on 2026-10-14 (`Agents/docs/decisions/2026-10-14-decisions-api-replaces-jev.md`, ticket ASTERION-20). The architecture is unchanged; the backend and every statement about the model are ported. Measurements made on `jev-1.13.0` are kept and labelled as such, not transferred. This revision was merged on 2026-10-14 (ASTERION-23) with Revision 9.2's Phase 0 results, which stay labelled as measurements on `jev-1.13.0`.

| changed | now | source |
|---|---|---|
| **DESIGN §2** | the decision model as documented (primitives, mapping from Jev, limits documented vs unknown); Jev's measured behaviour kept in DESIGN §2.3, to be re-measured | **[D1, D2, D3]** |
| **Primitives** | `noul` → `predicate`; choices are `{value, description}`; `score` maximum levels undocumented (Jevson keeps 2–10) | **[D2]** |
| **Refusal** | new reason `Unresolved(refused)`: never an option, a default, `absent`, or a retry | **[D2]** |
| **Question names** | opaque `q0…qN`, since whether `name` reaches the model is undocumented | **[D2]** |
| **R15, replay** | no snapshot exists: the returned `model` string is recorded; replay from records only | **[D2, D3, D4]** |
| **Context budget** | configured limits, Jev's measured values as placeholders until Phase 0r | **[D3]** |
| **Backend, credentials** | `DecisionsBackend`; `OPENAI_API_KEY`; the `openai` SDK not yet reviewed | **[D1]** |
| **`decided_by` values** | `jev` → `decision`, `llm+jev` → `llm+decision` (a `Result` API change; nothing is released yet) | — |
| **Images** | readable by the API, not adopted | **[D1, D2]** |
| **Open questions** | does source selection work on the Decisions API? (Phase 0r) | — |

### Revision 9.2 — 2026-09-29, Phase 0 results

Phase 0 ran its eight pre-registered probes on real documents (796 requests; `docs/taxonomy.md`). Candidate selection is *conditional* and ships with the second gate **[Z1–Z3]**; pairwise entity resolution is *stop*, so deduplication is the extractor's contract in v0 (R6, DESIGN §5.7: `conflict_floor` 0.05, cross-component variant) **[Z4]**; R13 is reproduced **[Z5]**; first readings of the source screen, calibration, and single candidates **[Z6–Z8]**. The v0 scope is frozen in DESIGN §10.1; it refuses every array of objects in v0 (previously only nested ones were out of scope), since Phase 7 builds arrays of spans only. The taxonomy prediction was wrong.

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
