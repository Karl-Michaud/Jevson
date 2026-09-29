# E2: Logic review, round 2 (Jevson Revision 4)

Targets: `Jevson/DESIGN.md` (646 lines), `PLAN.md` (854), `README.md` (48), `docs/REDTEAM.md` (94), `Agents/CLAUDE.md` §5, `Admin/README.md`. Line numbers refer to the working tree. No files were edited.

Severity: **blocker** means a phase cannot be built as written, or one of its exit criteria cannot pass as written. **major** means a contradiction or unowned behaviour that two implementers would resolve differently, or a statistically ill-posed bar. **minor** means stale text, wording, or a missing cross-link.

## 0. Round-1 verification (E_logic_review.md)

Findings **fixed**: 2, 3, 4, 5, 6, 7, 8, 9 (partly, see 15), 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 21 (sync only, see 18), 22 (one residue, see m1), 23–30, 31 (partly, see 2), 32, 33 (partly, see 4), 35, 36, 37, 39, 41, 42 (bar now mis-powered, see 14), 43, 44, 45.

Findings **only partly fixed**:

- **R1 #1 (generative blocker).** The compiler and graph are now planned, but *executing* step nodes still belongs to no phase (finding 5 below).
- **R1 #20.** No module drafts through the `LLM` protocol (finding 5).
- **R1 #34.** The root-level unresolved `.value` case is not covered (m14).

**Rule numbers.** Every R-number used in PLAN matches `DESIGN §7`: R1, R3–R9, R11, R13–R16. Every `DESIGN §n` and `PLAN §n` reference resolves. There is one bare-`§` residue (m1) and one weak target (m2).

---

## Blockers

### 1. [blocker] What a plain `str`/`number` field compiles to is contradictory, and the per-field configuration surface does not exist

- **Where:**
  - DESIGN.md:400 says "An undeclared unbounded string is refused (class G)".
  - DESIGN.md:206 (worked example) routes `vendor: str`, `billing_address: str`, and `total: number` to source selection with no declaration.
  - PLAN.md:300 has Phase 2 refuse "unbounded numerics … undeclared unbounded strings".
  - PLAN.md:393 has the Phase 4 exit "an undeclared unbounded string still refuses".
  - PLAN.md:433 says Phase 5 adds "Compiler support for `option_source = candidate_spans`", but no declaration syntax and no statement of which Phase 2 refusal it lifts. Phases 4 and 6 do say what they lift, at PLAN.md:382 and 488.
- **Finding:** After Phase 5, is `vendor: str` class D (source-selected), or class G (refused unless declared)? The documents say both. Several things Phase 5 needs have no syntax:
  - binding a field to an extractor: `total` → money pattern, `vendor` → LLM extractor (`Jevson(extractors=...)` at DESIGN.md:462 has no field mapping);
  - opting a field into `direct_extraction=True` (DESIGN.md:268);
  - declaring an entity type for a `Normalizer` (DESIGN.md:330, 444; PLAN.md:543 "different entity types");
  - overriding the scoping hint (finding 6).

  The prefix is also inconsistent: `x-jevson-order` and `x-jevson-generate` versus `json_schema_extra={"jevson": {...}}`.
- **Fix text:**
  - DESIGN §6.3, replacing the first bullet, and a new DESIGN §3.5 "Field declarations": "Per-field configuration lives in one keyword, `x-jevson`. Pydantic uses `Field(json_schema_extra={"x-jevson": {...}})`, so the emitted JSON Schema is identical. The keys are `source: {extractor: <name>, entity_type?: <name>, direct_extraction?: bool, scope?: <text>}`, `generate: {criteria: [<text>], rubric?: {levels: [...], minimum: <level>}, instructions?: <text>}`, `order: source|semantic`, and `question?: <text>`. An unbounded `string`/`number`/`date` field with neither `source` nor `generate` refuses (class G). With `Jevson(default_extractor=...)` set, such a field is class D."
  - PLAN Phase 5 deliverables: "Lifts the Phase 2 refusal of unbounded strings and numerics for fields declaring `x-jevson.source` (or under a default extractor)."
  - PLAN.md:393: "…an unbounded string with no `source` or `generate` declaration still refuses."

### 2. [blocker] "More than 254 candidates refuse at compile time" cannot be tested, and zero candidates is undefined

- **Where:** PLAN.md:450; DESIGN.md:553 ("larger sets are narrowed by code first, or refused"); DESIGN.md:72 and 555 (the compiler refuses one-option choices); DESIGN.md:284–296 (the lifecycle starts from "verified candidates").
- **Finding:** `compile_schema()` never sees a source (DESIGN.md:320, PLAN.md:299), so the candidate count cannot be known at compile time. A runtime refusal after LLM extraction has been paid for also contradicts "Refusal … before a single API call" (DESIGN.md:570).

  The mirror case is undefined too. If the extractor returns **zero** verified spans (or every span fails verification), the choice would be `[none_of_these]` alone: a one-option choice that the compiler "refuses". The executor has no rule for this case, and no rule for whether it triggers a retry.
- **Fix text:**
  - DESIGN §5.4, a new first bullet: "Zero verified candidates → no Jev call; the retry re-extracts once if the budget allows; otherwise `Unresolved(reason=no_candidates)`."
  - DESIGN §10 row: "More than 254 verified candidates at run time → the set is truncated to the 254 earliest by source offset; the dropped candidates are recorded in `Decision.dropped` (see finding 4) and never silently discarded."
  - PLAN.md:450: "More than 254 verified candidates at run time are truncated per DESIGN §10 and recorded; zero candidates yields `Unresolved(no_candidates)` with no Jev call."

### 3. [blocker] The Phase 2 class C exit criterion cannot pass while unions are refused

- **Where:** PLAN.md:293 ("Every class C construct in the Phase 0 v0 list compiles"); DESIGN.md:223 (class C includes **union discrimination**); PLAN.md:301 (unions refuse with `not_yet_supported` until Phase 6).
- **Finding:** If Phase 0 puts union discrimination on the v0 list, and it is a headline feature (DESIGN.md:38, 542), Phase 2 cannot merge.
- **Fix text (PLAN.md:293):** "Every class C construct in the Phase 0 v0 list **except union discrimination (Phase 6)** compiles to the primitive the taxonomy specifies."

---

## Major: contradictions and unowned semantics

### 4. [major] `Result.probability` and `decided_by` cannot represent what later phases produce

- **Where:** DESIGN.md:474–477, 487; PLAN.md:499; DESIGN.md:142–143.
- **Finding:** `probability` is `{pointer: Decision}`, one decision per pointer. But:
  - a generative field has N criterion nouls plus a rubric score;
  - a retried field has two choices;
  - an array element has one membership noul per merged span plus pairwise merges;
  - a union discriminator shares its pointer with the branch object it selects.

  Beyond the single-decision problem:
  - `decided_by` has no value for a generative field admitted with `no_criteria_declared` (DESIGN.md:405). That field is LLM-only, not `llm+jev`.
  - `caller` (DESIGN.md:474, R10) has no API anywhere: `resolve()` takes no pre-filled values.
  - The architecture diagram (DESIGN.md:142–143) omits `decided_by`, `ungated`, and `model`.
  - The field is named `probability` but holds a `Decision` object.
- **Fix text (DESIGN §8.1):**
  - `decisions {node_id: Decision(kind, selected, distribution, vendor_confidence | None, attempt, dropped)}` — keyed by node id (`/customer/tier#choice`, `/summary#criterion:2`), which is already unique (DESIGN.md:159).
  - `decided_by {pointer: code | jev | llm+jev | llm | direct | caller}`, with `llm` = generative with no criteria.
  - Add `resolve(..., given={pointer: value})` for `caller`, or delete `caller`.
  - Update the diagram at DESIGN.md:142 to list every §8.1 field.

### 5. [major] Executing step nodes belongs to no phase

- **Where:**
  - DESIGN.md:127–128 ("steps run through Extractor / LLM protocols").
  - PLAN.md:362: Phase 3 out of scope "Generative fields".
  - PLAN.md:382–390: Phase 4 lists compile, redraft policy, and adjudicate modules, but no executor change and no drafting module.
  - PLAN.md:88–91: the layout has no `generate`/drafting module.
- **Finding:** Nothing owns any of these:
  - running a `StepNode` before its dependent level;
  - the drafting prompt (field description, source, failing criteria on redraft);
  - where the draft sits in the adjudication request (in state beside the source, or inlined in the question). The P7 0/20 result was measured under one specific layout.
  - `Cost.llm_*` accounting.
- **Fix text (PLAN Phase 4 deliverables):** "`execute/executor.py` runs step nodes through their protocol before the dependent level and records `Cost.llm_input_tokens/llm_output_tokens`. `adjudicate/draft.py` builds the drafting and redraft prompts. State for adjudication is `{source, drafts: {<node id>: text}}`, keyed (R13), matching the **[P7]** layout." Add `adjudicate/draft.py` to the PLAN §2 layout.

### 6. [major] Question wording and the scoping hint are owned by no phase, and the Phase 0 verdict depends on them

- **Where:** DESIGN.md:280 ("Field questions carry a scoping hint ('of *this* invoice, the one being issued')"); DESIGN.md:98 ("All question design is ours"); PLAN.md:434 (the Phase 5 deliverable names the hint but not its source); PLAN.md:166–193 (the probes use unspecified wording).
- **Finding:** The hint needs domain knowledge that a schema does not carry, and no rule says where it comes from: root `title`/`description`, field `description`, or a declaration. The same applies to every Phase 2 enum question.

  Probe results measure *a wording*. P7 showed that one detector wording gave 0/40 false positives while another gave 20/20. So a Phase 0 "go" does not transfer to Phase 5 unless the template does.
- **Fix text:**
  - DESIGN §3.1, after the node definitions: "Question text is `template(field title/description, ancestor titles, root title/description)`; `x-jevson.scope` and `x-jevson.question` override it. Templates are versioned and recorded in `Result.model` metadata."
  - PLAN Phase 2 deliverable: "`compile/questions.py`, the templates."
  - PLAN Phase 0, 0b: "The probes use a written template, checked into `docs/taxonomy.md`; Phase 5 ships that template unchanged, or re-runs probes 1–3."

### 7. [major] `Unresolved` reasons are not enumerated; several paths have no reason at all

- **Where:**
  - Reasons named in the text: `tie` (DESIGN.md:241, 393), `invalid_backend_answer` (PLAN.md:342), `source_flagged` (DESIGN.md:344), `verification_failed` (PLAN.md:439).
  - Paths with no named reason:
    - `none_of_these` after retry (DESIGN.md:295);
    - no new span on retry (DESIGN.md:292);
    - redraft exhaustion (DESIGN.md:403);
    - entity conflict (DESIGN.md:332);
    - nodes left unexecuted when `BackendError` carries a partial Result (DESIGN.md:378);
    - zero candidates (finding 2).
  - PLAN.md:51 has `RefusalReason`, a compile-time enum, but no runtime enum.
  - `not_yet_supported` is a `RefusalReason`, not an `Unresolved` reason. Keep them separate.
- **Fix text (DESIGN §8.1, after the Result block):** "`UnresolvedReason` is closed: `abstained`, `no_candidates`, `no_new_candidates`, `tie`, `invalid_backend_answer`, `source_flagged`, `verification_failed`, `drafts_rejected`, `entity_conflict`, `not_executed`. `abstain_probability` is `float | None` (None unless reason ∈ {abstained, no_new_candidates})." Add `UnresolvedReason` to `types.py` in Phase 1 (PLAN.md:236).

### 8. [major] Call-time refusals and extractor failures have no exception in the three-outcome property

- **Where:** DESIGN.md:374–380 (outcome 3 lists `CompileError`, `SchemaViolation`, `BackendError`/`LLMError`); DESIGN.md:320 (more than one source refused at the call boundary); DESIGN.md:493, 498 (per-question overflow and an overlong source refuse at preflight); PLAN.md:354 ("Cost is populated on every result and every typed exception"), where DESIGN only says "the latter two" carry Result and Cost.
- **Finding:** A preflight refusal is not a `CompileError`, because the schema is fine. None of these has a named type:
  - a preflight refusal;
  - an exception raised by a caller-supplied `Extractor` or `Normalizer`;
  - an LLM draft too large for limit (a), which is post-spend (finding 15).

  The property, which says "never a fourth outcome", therefore cannot be written. DESIGN and PLAN also disagree on which exceptions carry `Cost`.
- **Fix text (DESIGN.md:378):** "…`CompileError` (schema cannot be mapped), `PreflightRefusal` (source, source count, or budget cannot be served; raised before any call), `SchemaViolation`, or `BackendError` / `LLMError` / `ExtractorError` (failure in, or exception from, a backend or a caller-supplied protocol). `SchemaViolation` and the last three carry the partial `Result` and its `Cost`; `CompileError` and `PreflightRefusal` carry no spend." Update PLAN.md:51 and 354 to match.

### 9. [major] Tie and selection rules for `choice` and `score` are undefined; the "do not sum" check will reject real answers

- **Where:** DESIGN.md:241, 393 (ties are defined only for binary decisions); DESIGN.md:71 (values are rounded to 2 dp); PLAN.md:499 (a union "tie" is assumed to exist); PLAN.md:707 ("distributions that do not sum" is an invalid value).
- **Finding:** Several selection cases have no rule:
  - a choice returning 0.45/0.45/0.10;
  - a candidate tied with `none_of_these`;
  - a score with two equal most-probable levels (DESIGN.md:243);
  - whether the vendor's `choice` field or the argmax of `probabilities` is authoritative, and what happens when they disagree.

  Separately, with 2-dp rounding a legitimate 3-option answer can sum to 0.99, and a 255-option answer can be off by much more. An exact-sum check turns real answers into `invalid_backend_answer`.
- **Fix text (DESIGN §6.2, new bullet):** "Selection for `choice` and `score` is the argmax of the returned `probabilities`. Two or more options sharing the maximum → `Unresolved(tie)`. The vendor's `choice`/`score` fields are recorded; if the vendor's `choice` differs from a unique argmax → `invalid_backend_answer`. Distributions must sum to 1 within `0.005 × option count`." Add a Phase 3 exit criterion: "a choice with tied top probabilities yields `Unresolved(tie)`; a 3-option distribution summing to 0.99 is accepted."

### 10. [major] README, DESIGN one-liner and CLAUDE.md claim every value has provenance and a probability

- **Where:** DESIGN.md:7; README.md:3; Agents/CLAUDE.md:164 ("Every value carries its provenance and Jev's probability"); DESIGN.md:309–312 (provenance has only SOURCE_SPAN and DECLARED_OPTION); DESIGN.md:268, 405, 487.
- **Finding:** The following have neither kind of provenance: class A code values and defaults, LLM-drafted generative values, and `caller` values. Direct-extracted fields and `no_criteria_declared` fields have no probability. The claim exceeds the DESIGN §6 Provenance tier, which says "for fields resolved that way".
- **Fix text:**
  - README.md:3 and DESIGN.md:7: "…and returns each value with how it was decided — a source span, a declared option, or a criteria-checked draft — and the probability of every Jev decision behind it, or a typed reason it could not be resolved."
  - CLAUDE.md:164: "Every value records how it was decided (`decided_by`). Values selected from the source carry a verified span, and Jev decisions carry probabilities (calibration measured, not assumed). A field the source does not support comes back as a typed `Unresolved`; a schema construct Jevson cannot map is refused before any call."

### 11. [major] README states abstention unconditionally, and it applies only to candidate fields

- **Where:** README.md:24 ("When the source does not support any candidate, you get a typed `Unresolved` instead of a confident guess"); README.md:19; DESIGN.md:392, 280 (0.89 in long documents), 339 (a hostile source defeated abstention 20/20 at confidence up to 1.0); PLAN.md:854 (schema enums have no abstention path in v0).
- **Finding:** Abstention has no tier in DESIGN §6; it is measured, not guaranteed. Bounded fields always commit a declared option, including when the source is silent. The line-34 caveat does not undo the unconditional sentence at line 24.
- **Fix text (README.md:24):** "When no candidate is supported by the source, the field is built to come back as a typed `Unresolved` rather than a guess — how often it does is measured, not guaranteed, and a hostile source can defeat it. Fields chosen from declared options have no such escape in v0."

### 12. [major] Probe 1 "stop" has no consequence, and probe 6 does not measure the source screen it is credited with

- **Where:** PLAN.md:179 (probe 1 has a stop band, < 0.70); PLAN.md:210 (the abandon criterion names only probes 2 and 3); PLAN.md:184 (probe 6 measures steering and collapse, with no screen); PLAN.md:224 and 804 (probe 6 is listed as answering "source screening").
- **Fix text:**
  - PLAN.md:210: "Probe 1 below 0.70, probe 2 below 0.60, or probe 3 above 0.20 stops candidate selection as designed."
  - PLAN.md:184, append: "; and the true- and false-positive rates of detector wording d1 **[P7]** on these 50 attacked documents and their 50 unattacked originals (reading only)."

### 13. [major] Phase 0 bands use the point estimate while Phase 5 uses CI bounds, so a Phase 0 "conditional" almost guarantees that Phase 5 abandons

- **Where:** PLAN.md:187 (the verdict is the band containing the point estimate); PLAN.md:446–447 (Phase 5 requires the lower bound ≥ 0.60 and the upper bound ≤ 0.20).
- **Finding:** At n = 150 the Wilson half-width is about 7–8 points near p = 0.65. A true abstention rate of 0.60–0.68 is "conditional" in Phase 0, so the plan proceeds and builds Phases 1–4 plus the second gate. Phase 5 then fails its lower-bound test with high probability. The owner's order is kept, but this risk is not written down anywhere.
- **Fix text:**
  - PLAN.md:193, append: "A conditional probe 2 below 0.70, or probe 3 above 0.13, is recorded as **likely to fail Phase 5's CI criteria** (at n = 150 the bounds sit about 7 points from the point estimate); the operating characteristic of the Phase 5 criteria at those rates is computed alongside Phase 0's."
  - Add the same as a PLAN §5 risk row.

### 14. [major] The DESIGN §6.2 calibration bar fails a perfectly calibrated model at n = 1,000, and τ is chosen on the test data

- **Where:** DESIGN.md:394; PLAN.md:454, 775, 845; REDTEAM.md:41 (L6 checked **plain** ECE, not the bootstrap upper bound).
- **Finding:** I ran a simulation: 15 equal-mass bins, percentile bootstrap (B = 200), 150 trials.

  | selected-probability distribution | model | passes plain ECE ≤ 0.05 | passes 95% bootstrap UB ≤ 0.05 |
  |---|---|---|---|
  | Beta(8,2) | perfectly calibrated | 97% | **0%** |
  | Beta(5,1) | perfectly calibrated | 99% | 1% |
  | Beta(20,1) (mass near 1) | perfectly calibrated | — | 100% |

  The binned-ECE bootstrap is biased upward, so the bar mostly measures how spread out the probabilities are. It is also not established by any tag.

  Separately, "accuracy at or above the proposed threshold τ" is computed on the same Phase 5 data that is used to propose τ.
- **Fix text (DESIGN.md:394):** "…the **debiased** top-label ECE (equal-mass bins, with the expected ECE of a perfectly calibrated model at the same n and probability distribution subtracted, obtained by resampling labels as Bernoulli(p)) has a 95% upper bound ≤ 0.05, **and** accuracy at or above τ is ≥ τ − 0.02, where τ is fixed before the data are seen, or chosen on a held-out half. The power of this bar is simulated and tagged in `docs/REDTEAM.md` before it is used." Add an L-check for it.

### 15. [major] Preflight "maximum candidate count" is undefined, and drafts can exceed limit (a) after spend

- **Where:** DESIGN.md:499 ("every retry at its maximum candidate count"); DESIGN.md:498; PLAN.md:341; PLAN.md:398 ("enormous strings").
- **Finding:** The candidate count, candidate text length, membership-noul count, and draft length are unknown until LLM steps run. That applies to the first pass as well as retries. Preflight "before any backend call" cannot budget them without declared maxima.

  With a maximum of 254 candidates and long spans (contract clauses), the preflight would refuse nearly every source. If span length is unbounded, the preflight is not conservative at all. An enormous draft breaks limit (a) at adjudication time, after the LLM has been paid.
- **Fix text (DESIGN §8.2, replacing the preflight bullet):** "Each candidate field declares or inherits `max_candidates` (default 32) and `max_span_tokens` (default 64); generative fields have `max_draft_tokens` (default 1,024). Preflight budgets those maxima. At run time, excess candidates are truncated by source order and recorded (`Decision.dropped`); an over-long span is rejected like an unverifiable one and counted; an over-long draft is a failed draft." Add a PLAN Phase 4 exit criterion: "a draft above `max_draft_tokens` is a failed draft, never a 400."

### 16. [major] The source screen's semantics are unspecified

- **Where:** DESIGN.md:344; PLAN.md:437, 456.
- **Finding:** Several things are undefined:
  - **Threshold and tie:** p > 0.5, and what happens at 0.50?
  - **Placement:** does the screen run as its own level *before* extraction and drafting (one extra call, no wasted LLM spend), or batched into level 0 (LLM steps spent on a document that is then discarded)?
  - **Scope:** "routes every field to `Unresolved`" catches class A constants and defaults that never read the source, and schema-enum choices. Every required `const` field then reads as unresolved.
  - **Self-attack:** the screen is itself a noul over hostile text, and an injection can target it. This is not stated.
- **Fix text (DESIGN.md:344):** "…The screen runs as the first level, before any extraction or drafting; it flags when p > 0.5, and a tie is treated as flagged. A flagged source makes every **source-dependent** pointer (`decided_by` ∈ {jev, llm+jev, direct}) `Unresolved(source_flagged)`; class A values are still emitted. The screen's own question is subject to the same steering; its measured rates are the only claim."

### 17. [major] The response cache neither replays exactly nor respects the privacy posture as written

- **Where:** DESIGN.md:514 (keyed on the Jev request only); DESIGN.md:369 ("Replay is exact only through the response cache"); DESIGN.md:460 (source text is "written nowhere unless the caller supplies a sink"); DESIGN.md:437 ("Five protocols"); PLAN.md:330.
- **Finding:** Once Phase 4 or 5 is active, the Jev request contains LLM-drafted text and LLM-extracted candidates. A non-deterministic LLM changes the request, so the cache misses, and replay of a whole `Result` is not exact.

  The cache stores source text and responses, but nothing says where. If it is on disk by default, it breaks the privacy posture. A pluggable cache store would be a sixth protocol, which the Phase 1 exit criterion (PLAN.md:254) forbids without a DESIGN amendment.
- **Fix text (DESIGN §8.4):** "The cache records **every protocol call** — Backend, LLM, Extractor — keyed by a canonical hash of that call's input. It is off by default and in memory when enabled; persistence requires a caller-supplied `ResponseStore` (a sixth protocol, listed in §8). Exact replay of a `Result` needs every call served from the store." Also DESIGN.md:460: "…unless the caller supplies a `CostSink` or a `ResponseStore`."

### 18. [major] The async and concurrency posture cannot be built as pinned

- **Where:** DESIGN.md:450–453 (the `LLM` protocol is sync only; the Extractor signature is not pinned); DESIGN.md:462 ("the backend owns one HTTP client and one rate limiter"; `resolve()` and `aresolve()`); DESIGN.md:84 (the rate limit is per key).
- **Finding:** There are four problems:
  - An `aresolve()` over a sync `complete()` blocks the event loop.
  - One `httpx` client cannot serve both sync and async paths, because `Client` and `AsyncClient` are separate classes and an `AsyncClient` is bound to its event loop.
  - Two backends, or two processes, on one key each get their own limiter. The resulting 429s exhaust `transport_retries=2` and surface as `BackendError` under load.
  - No exit criterion covers any of this.

  The Extractor signature (exclusions on retry, DESIGN.md:291) has the same sequencing hazard the LLM signature had in round 1.
- **Fix text:**
  - DESIGN §8: pin `LLM.complete` / `LLM.acomplete` (sync callers get a thread-offload adapter) and `Extractor.extract(source, field_spec, exclude: list[Span]) -> list[str | Span]` plus `aextract`. State: "`JevBackend` lazily holds one sync and one async client; the limiter is per backend instance, and callers sharing a key across instances pass a shared `RateLimiter`."
  - PLAN Phase 3 exit: "`aresolve()` over 50 concurrent calls against the fake backend issues no more than the limiter allows and gives results identical to `resolve()`."

### 19. [major] Enum arrays and flat `allOf` have no owner

- **Where:**
  - PLAN.md:310 (arrays are Phase 7);
  - PLAN.md:548 and DESIGN.md:565 (an array with no source grounding refuses);
  - PLAN.md:508 ("`allOf` beyond flat merging") and PLAN.md:852, which imply that flat `allOf` is supported, yet no phase delivers it.
- **Finding:**
  - `tags: list[Category]` (multi-label classification, class C: one noul per enum value) is the most common array in the non-extraction sample (PLAN.md:145). It is refused in every phase and is not in the PLAN §9 deferrals.
  - It is cancelled with Phase 7 if Phase 5 abandons.
  - Flat `allOf` is claimed but built nowhere.
- **Fix text:**
  - PLAN Phase 2 (or 3), new deliverable: "an array of a 2–255-value enum → one membership noul per value (class C), `uniqueItems` respected, schema order."
  - Or add a PLAN §9 row: "Arrays of enums (multi-label) | …".
  - PLAN Phase 2 normalise: "flat `allOf` of object schemas with disjoint properties merges; anything else refuses."

### 20. [major] An optional field that is truly absent is always `Unresolved`, so `complete` is almost never true

- **Where:** DESIGN.md:278 (`none_of_these` conflates "the source lacks it" with "the extractor missed it"); DESIGN.md:382 and 472; PLAN.md:677.
- **Finding:** `middle_name: Optional[str]`, correctly absent from a document, yields `Unresolved` and `complete=False`. On real documents with many optional fields, `complete` is then false nearly always, and it stops working as the branch signal the library sells (DESIGN.md:50).
- **Fix text (DESIGN §5.4):** "A field may declare `x-jevson.source.absent_ok: true` (optional fields only). For it, a terminal `none_of_these` omits the key, records `decided_by=jev` with its probability, and does not count against `complete`; it is listed in `Result.absent`." Alternatively, state explicitly that `complete=False` is expected for optional absences, and give callers `Result.unresolved_required`.

### 21. [major] Redraft recovery is a one-sided bar, measured against Jev rather than the truth

- **Where:** PLAN.md:402; compare the two-sided retry bar at PLAN.md:453.
- **Finding:** "Pass on redraft" is judged by Jev, the component under test. There is no false-admission side: a redraft that passes Jev but actually violates the criteria. The result also depends on the one LLM used to measure it.
- **Fix text (PLAN.md:402):** "…recovery = redrafts that pass Jev **and** are human-labelled as meeting the criteria; false admissions (pass Jev, labelled failing) are recorded; the default stays 1 only if recovery ≥ 10% and false admissions ≤ 2 points above first-draft false admissions. The LLM used is named."

### 22. [major] The retry-bar corpus cannot be built as sized

- **Where:** PLAN.md:36 and 453 (≥ 100 present-answer abstentions); PLAN.md:447 (false abstention ≤ 0.20 over ≥ 150 present cases).
- **Finding:** At most 30 abstentions can come from 150 present cases. At the Phase 0 go rate (≤ 0.10) there are about 15. Getting 100 needs about 1,000 present cases, or a stated construction. The "≤ 2 points" false-commit increase is 3 cases out of 150, which is within noise.
- **Fix text (PLAN.md:453):** "…over ≥ 100 present-answer cases where the correct span is **withheld from the first candidate set** (a simulated extraction miss) and ≥ 150 absent cases; the paired difference in false commits is reported with its 95% interval; the budget stays 1 only if recovery ≥ 10% and the interval's upper bound of the false-commit increase is ≤ 5 points."

---

## Major: statistically ill-posed exit criteria

### 23. [major] Phase 3 "live stability" asserts zero flips on a stochastic quantity

- **Where:** PLAN.md:349; DESIGN.md:90 (per-question SD up to 0.022; range up to 0.10); PLAN.md:726 (§4.4: "measure").
- **Finding:** For a noul, the margin is 2p − 1, so its SD is up to 0.044. A 0.10 margin is then about 2.3 SD from zero, roughly a 1% flip chance per decision in the worst-jitter regime. Over 100 decisions at that SD, P(≥ 1 flip) is roughly 60–70%. Fixtures picked by their margin on a single run also regress toward zero. The criterion is flaky exactly where it matters.
- **Fix text (PLAN.md:349):** "…over ≥ 100 decisions whose top-two margin is ≥ 0.20 in **each of three** calibration runs, two further runs are compared; the flip count is recorded, and the criterion fails if it exceeds 1."

### 24. [major] The Phase 4 injection-regression threshold is the per-variant bound, applied to n = 80

- **Where:** PLAN.md:399.
- **Finding:** 0.16 is the Wilson upper bound for 0/**20**. The pilot was 0/80 in total, which gives an upper bound of about 0.046. As written, up to 12/80 flips passes, so the "regression" almost never fires.
- **Fix text:** "…the suite fails if more than 3 of the 80 failing drafts are judged passing (the pilot's 0/80 has a Wilson upper bound of 0.046), or if any variant has more than 2 of its 20."

---

## Minor

- **m1.** PLAN.md:73 has "`(DESIGN §5.4, §6.1, §6.3)`", which breaks the rule at PLAN.md:5 that a bare `§` never appears. Change it to "DESIGN §5.4, DESIGN §6.1, DESIGN §6.3".
- **m2.** PLAN.md:57 points normalisation to "DESIGN §3", which has only a diagram label. Change it to "DESIGN §3, §10 (anyOf/`$ref` rows)", or add a normalisation paragraph to DESIGN §3.1.
- **m3.** PLAN.md:347 says "No default confidence threshold"; make it "No default probability threshold", matching DESIGN §6.2.
- **m4.** PLAN.md:187 cites **[L5]** for "n = 150 … ±6 points", but L5 was computed at n = 100 (REDTEAM.md:40). Either re-run L5 at n = 150 or drop the tag and label the figure as arithmetic.
- **m5.** PLAN.md:455, "suite fails if they worsen between releases". This is vacuous at the pilot's 20/20 ceiling and undefined otherwise. Change to: "fails if a rate's point estimate exceeds the previous release's Wilson upper bound."
- **m6.** PLAN.md:339. The `[<digits>]` test will false-positive on interpolated text, such as enum descriptions or source spans containing "[1]". Restrict it to template text and state paths.
- **m7.** PLAN.md:170–172. The corpus rules apply to probe 6, but its injected notes must be written by the team. Add: "the injected note is team-written; the documents are not."
- **m8.** DESIGN.md:333. `conflict_floor`'s rule (PLAN.md:191) can select nothing if more than 2% of same-entity pairs are ≤ 0.05. Add: "if no value qualifies, the floor is 0.05 and probe 4 is recorded *stop*." Add to the Phase 0 exit criteria: "`conflict_floor` written into DESIGN §5.6."
- **m9.** PLAN.md:439 and 446. It is not stated whether the coverage and false-abstention measurements run with the conditional second gate on. They must, because the gate changes the commit rate.
- **m10.** PLAN.md:497, "An undiscriminable union" is undefined. Define it as: "branches whose descriptions and required properties are identical after normalisation." Also state that the discriminator has no `none_of_these` in v0 (consistent with PLAN.md:854).
- **m11.** DESIGN.md:331 and PLAN.md:535. It is not stated whether pairwise nouls run over all pre-merged candidates, which lets them share the membership level, or only over accepted members, which adds a level. This changes the "1–3 calls" claim at DESIGN.md:199. State it.
- **m12.** DESIGN.md:384. "At an unresolved pointer the key is omitted" does not cover an unresolved **root** (a root union). Add: "an unresolved root yields `.value == {}`."
- **m13.** DESIGN.md:462 and PLAN.md:577. `CostSink` is defined in Phase 1, but no phase wires it until Phase 8. State in Phase 3 that the executor emits to it.
- **m14.** README.md:28. The present tense ("Jevson generalises…", "verified by an adversarial suite") describes unbuilt features. Change to "Jevson is designed to generalise it…".

## Agents / Admin

- **a1 (minor).** Agents/CLAUDE.md:17 ("the structured-output library") and :37 ("Jev-adjudicated structured output") use the framing DESIGN §1 rejects. Change them to "the source-grounded extraction library" and "Source-grounded structured extraction (Jevson)".
- **a2 (minor).** Agents/CLAUDE.md:159, "Grammar-constrained decoding already makes invalid JSON unreachable", contradicts DESIGN.md:17 ("not unconditional" **[X1]**). Change to "…makes invalid JSON rare; Jevson still validates everything it assembles."
- **a3 (major, same as finding 10).** Agents/CLAUDE.md:164 has the "every value" overclaim, and it says "an unsupported field comes back as Unresolved", but unsupported constructs are refused. Use the fix text in finding 10.
- **a4 (major).** Agents/CLAUDE.md:125 ("validated by Jevson against the trial schema") and :260 ("generative model drafts → Jevson admits") describe adjudicating an externally produced draft. DESIGN §8 exposes only `resolve`/`aresolve`, where Jevson drafts through the injected `LLM`. Change :260 to "execution bus: `Jevson.resolve` with the generative model injected as its `LLM` → draft admitted by declared criteria → payload_ref (labelled generated)", and :125 to "drafted and admitted through Jevson (criteria-gated)".
- **a5 (minor).** Agents/CLAUDE.md:150, "decisions within ~0.05 of a threshold can flip", is not a measured band. Change to "identical requests jitter (range up to 0.10, SD ≤ 0.022); decisions near a threshold can flip, and exact 0.50 ties occur".
- **a6 (minor).** Admin/README.md:22 (the to-do "get an account and key" is still unchecked) and :67 ("Not yet enrolled") are stale: REDTEAM.md:7 reports 1,555 live requests on the team key, and PLAN.md:131 says "live key (available)". Tick the to-do or reword it to the remaining `DecisionModel` spike, and set the account row to "Enrolled (early access) · key in Infisical / local `.env`".
- **a7 (minor).** Admin/README.md:42. The repo row omits criteria-gated generative fields, which is the one capability that survives either abandon criterion. Append: "…; LLM-drafted fields admitted only after passing declared criteria." A suggested status is "Design (Rev 4) — Phase 0 next".
