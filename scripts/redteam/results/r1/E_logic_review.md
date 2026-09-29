# E — Internal logic review of Jevson DESIGN.md / PLAN.md Revision 3

Scope: internal soundness only. Line numbers are against the working tree on branch `docs/revision-3-decisions` (DESIGN.md 645 lines, PLAN.md 807 lines, README.md 44 lines). No docs were edited.

Severity key: **blocker** = a phase cannot be built or its exit criterion cannot pass as written; **major** = contradiction or unowned behaviour that two implementers would resolve differently; **minor** = stale text, wording, or a missing cross-link.

---

## A. Blockers

### 1. [blocker] Phase 4 has no compiler, graph, or executor support for generative fields
- **Location:** PLAN.md:288 (Phase 2 out of scope: "Generative fields (Phase 4)"), PLAN.md:355-363 (Phase 4 deliverables), DESIGN.md:157-165 (node `kind` is `choice | score | noul`; `option_source` has no generative value), DESIGN.md:172, 204, 466-467 ("new decision kinds plug in without the executor changing"; "one Jev call per level").
- **Finding:** Phase 5 explicitly lists "Compiler support for `option_source = candidate_spans`" (PLAN.md:406). Phase 4 has no equivalent. Nothing plans:
  - how the compiler recognises a class E field. Phase 2 must refuse an unconstrained `string` field, because it is not in the bounded subset, so after Phase 2 every generative field is a `CompileError`. Nothing says how the field is marked generative, or how criteria and rubrics are declared on it (a Pydantic `Field(json_schema_extra=...)`? a config map keyed by pointer?).
  - a graph representation for "LLM drafts, then Jev adjudicates." That is a dependency (the draft must exist before the `noul` batch runs) with a non-Jev step inside it. The executor as specified only makes Jev calls per level.
  - the redraft loop. Rejection → redraft → re-adjudicate is a dynamic cycle, and a DAG leveller cannot express it. The retry machinery in `execute/policy.py` is specified only for none_of_these (Phase 3) and candidates (Phase 5).
- **Fix text (PLAN Phase 4 deliverables):** "`compile/mapping.py` gains class E routing: a string field declared generative in config (`generative={pointer: Criteria(...)}`) compiles to a `GENERATE` step plus one `noul` node per criterion, with the criterion nodes depending on the step. `DecisionKind` gains no new Jev primitive. Instead `DecisionGraph` gains a non-Jev `Step` node type that the executor runs through the `LLM` protocol before the dependent level. Redraft is an executor-level loop bounded by `redraft_budget` and implemented in `execute/policy.py`. It is not expressed as graph edges." Also add to DESIGN §3.1: "Nodes are either Jev decisions (`choice|score|noul`) or external steps (`generate`, `extract`). Only decisions are batched into Jev calls."

### 2. [blocker] Pydantic nested models and `Optional[...]` fields cannot compile until Phase 6
- **Location:** PLAN.md:264-265, 274, 279 (Phase 2 nested objects plus "a Pydantic model and its emitted JSON Schema compile to identical graphs"), PLAN.md:455 (`$ref` resolution is a Phase 6 deliverable), PLAN.md:446-452 (anyOf is Phase 6).
- **Finding:** Pydantic v2 emits nested models as `$defs` + `$ref`, and it emits `x: T | None = None` as `anyOf: [T, {type: null}]`. Read literally, Phases 2–5 refuse:
  - every nested Pydantic model, which undercuts the Phase 2 three-level-nesting criterion when the input is Pydantic;
  - every nullable optional field. That is the field shape the Phase 3 criterion "an unresolved **optional** field…" (PLAN.md:322) is most likely to use.

  A library whose schema surface is "Pydantic or JSON Schema" (PLAN.md:723) would be unusable with idiomatic Pydantic for five phases, including the "working library" Phase 3. If Phase 6 abandons, it stays unusable permanently.
- **Fix text (PLAN Phase 2 deliverables):** "Class A normalisation before mapping: static, acyclic local `$ref`/`$defs` are inlined; `anyOf: [T, {type: null}]` (and `type: [T, "null"]`) is normalised to *nullable T*, with no discrimination node. Recursive refs refuse (named reason). Phase 6 covers only unions with two or more non-null branches." Also move PLAN.md:455 and PLAN.md:462 out of Phase 6, and add a Phase 2 exit criterion: "A Pydantic model with a nested model and an `Optional[str]` field compiles without refusal."

### 3. [blocker] The Phase 7 flagship dedup test is likely to fail under the Phase 7 conflict rule
- **Location:** PLAN.md:501 (`"Dana"` / `"Dana Whitfield"` / `"Ms. Whitfield"` → one element), PLAN.md:492 and 507, DESIGN.md:373.
- **Finding:** All n(n−1)/2 pairs are asked. So any component of three or more that survives must be a clique in which every pair is judged "same". "Dana" vs "Ms. Whitfield" share no token, and an honest pairwise `noul` on that pair can reasonably come back below 0.5. If it does, the component {Dana, Dana Whitfield, Ms. Whitfield} contains a "different" pair and becomes `Unresolved`, so the flagship criterion fails by the rule written six lines below it. In general, the rule makes transitive coreference chains (short name ↔ full name ↔ title + surname) unresolvable. That is the most common real-prose pattern.
- **Fix text (DESIGN §5.6 step 2):** "Classes are connected components of pairs with p(same) ≥ 0.5. A component is merged unless some pair inside it is judged *confidently different* (p(same) ≤ `conflict_floor`, default 0.2). Pairs between the floor and 0.5 are treated as not-evidence rather than conflict. A component with a confident conflict is reported as a per-component `Unresolved`, and the other components of the array are still emitted (see finding 12)." Alternatively, keep the strict rule and change the PLAN.md:501 fixture to one the strict rule can pass. Either way, Phase 0 probe 4 should measure the clique-completeness rate so the choice is made on evidence.

### 4. [blocker] Phase 6 "only the selected branch is ever compiled" contradicts R14 and compile-time refusal
- **Location:** PLAN.md:453, 459 ("only the selected branch's nodes are ever compiled or executed — asserted by counting compiled nodes"), PLAN.md:461 ("undiscriminable union refuses at compile time"), DESIGN.md:192, 448 (R14: refusal at compile time, before any API call), DESIGN.md:561, PLAN.md:280 (`compile_schema()` returns a graph or raises; network-free).
- **Finding:** If branch nodes compile only after level 0 runs, an unmappable construct inside branch B is discovered after a Jev call, and only when B is selected. That breaks R14 and makes `compile_schema()` non-total over the schema. It also breaks context-budget preflight (finding 9).
- **Fix text:** "All branches are compiled and validated statically by `compile_schema()`, so refusal stays total and pre-network. Only the selected branch's nodes are *executed*. The exit criterion counts executed nodes and backend questions, not compiled nodes." Edit DESIGN §3.2 line 192 from "compile only that branch's decision nodes" to "execute only that branch's decision nodes".

---

## B. Contradictions

### 5. [major] "Multiple sources" refusal: compile time, call boundary, or runtime?
- **Location:** DESIGN.md:357 ("refuses at compile time"), DESIGN.md:557 ("refuse at the call boundary (§5.5)"), PLAN.md:317 ("runtime concern… does not belong in the compiler").
- **Finding:** §5.5 contradicts §10 and PLAN. `compile_schema()` never sees a source, so "compile time" is impossible as written.
- **Fix text (DESIGN.md:357):** "…but supplying more than one source refuses at the call boundary, before any backend call, with a named reason."

### 6. [major] `satisfies_schema` is ill-defined for unresolved optional fields
- **Location:** DESIGN.md:337-342 (optional unresolved → "partial result… honest"; "strictness is configurable for optional fields"), DESIGN.md:406-407, 483 ("False whenever any Unresolved is present"), PLAN.md:322.
- **Finding:** An object that omits an optional field *does* validate against the schema. Forcing `satisfies_schema=False` makes the name false, which is exactly the misreading the field exists to prevent. It also makes "strictness is configurable for optional fields" meaningless, because nothing is left to configure. And outcome 2's `.value` may validate while outcome 1 requires validation, so the two outcomes are not disjoint on `.value`.
- **Fix text (DESIGN §8.1):** Split the field into two. `satisfies_schema: bool` means `.value` validates against the original schema. `complete: bool` means no `Unresolved` is present. Outcome 1 is `satisfies_schema and complete`. Outcome 2 is `not complete`, with `satisfies_schema` reported truthfully. The optional-field strictness setting then decides whether an optional hole is omitted from `.value` (validates) or fails validation.

### 7. [major] An unresolved required field is outcome 2 or outcome 3, but it cannot be both
- **Location:** PLAN.md:322 ("additionally reported as a schema violation regardless of caller strictness"), DESIGN.md:340-342 ("a caller may choose to receive it rather than raise"), DESIGN.md:408 (`SchemaViolation` is a refusal, outcome 3).
- **Finding:** The central-property test (PLAN §4.1) cannot be written until one mapping is chosen. "Reported as a schema violation" can mean a raised `SchemaViolation` (outcome 3) or a Result with `satisfies_schema=False` (outcome 2).
- **Fix text:** "An unresolved required field yields outcome 2 by default (`satisfies_schema=False`, the `Unresolved` names the pointer). With `raise_on_violation=True` it yields outcome 3 (`SchemaViolation` carrying the partial `Result` and its `Cost`). It is never outcome 1."

### 8. [major] The determinism rule is unachievable once an LLM is in the loop
- **Location:** PLAN.md:639 ("Same schema, source, and backend produce the same result… anything non-deterministic in our own code is a bug"), PLAN.md:326 ("Same input resolves to the same output across runs against the live API"), PLAN.md:423 ("resolve identically through the LLM extractor and a hand-supplied one"), PLAN.md:580 ("byte-identically"), DESIGN.md:67 (σ = 0.01, not 0).
- **Finding:**
  - LLM extraction (Phase 5) and drafting (Phase 4) are nondeterministic in general, so the rule is false from Phase 4 onward.
  - σ = 0.01 means probabilities are not bit-stable. Near p = 0.5 (bool `noul`, the entity-merge threshold) or on near-tied choices, the selection itself can flip.
  - Vendor model updates make "across runs" a moving target.
  - PLAN.md:423 is ill-posed: two extractors resolve identically only if they emit identical candidate sets.
- **Fix text (PLAN §3):** "Determinism: given identical Jev responses and identical LLM/extractor outputs, Jevson's own code produces an identical `Result`. This is asserted with the fake backend and recorded LLM outputs. Against the live API, Phase 3 asserts identical *selections* (not probabilities) over a fixture set with no near-ties (margin ≥ 0.1), records the Jev model version in `Result.cost` or metadata, and treats a version change as a re-baseline, not a failure." Rewrite PLAN.md:423 as "…resolve identically when the hand-supplied extractor returns the same candidate set the LLM extractor returned (recorded)."

### 9. [major] Execution-time budget refusal contradicts R14 "before any API call"
- **Location:** DESIGN.md:448 (R14), DESIGN.md:503 ("If a single question plus its state exceeds the window, refuse loudly"), PLAN.md:319.
- **Finding:** Oversize depends on the source, which is known only at call time. With retries (new candidates) and union branches (finding 4), a later level can exceed the window after earlier levels have already spent money. R14 as written ("at compile time, before any API call") cannot cover this.
- **Fix text (DESIGN §8.2):** "Before the first backend call, the executor preflights every level, including every union branch and a retry at its maximum candidate count, against the window. Any single-question overflow refuses then, pre-spend. Overflow that arises only from retry-returned candidates truncates the *candidate set* (never the state), logs the dropped candidates in `Unresolved.candidates_seen`, and does not refuse." Amend R14 to "…at compile time or call-time preflight, before any API call."

### 10. [major] The structural tier claims "constrained decoding" and "unconditionally", but Jevson controls no decoder
- **Location:** DESIGN.md:385, PLAN.md:357, 367 ("the key cannot be missing or misspelled"), DESIGN.md:460 (LLM "injected by the caller — we do not assume a provider"), PLAN.md:671 (hostile LLM returns "wrong field names, missing fields").
- **Finding:** The LLM is caller-injected and may not support strict tool schemas. The hostile LLM double deliberately violates them. So the Phase 4 criterion "key cannot be missing" is not a property the library can assert, and the structural tier's unconditional status must rest on deterministic assembly plus final validation alone.
- **Fix text:** In DESIGN.md:385, change the mechanism to "deterministic assembly + final `jsonschema` validation; constrained decoding, where the injected LLM supports it, reduces redraft rate but is not relied on." Rewrite PLAN.md:367 as: "A generative field is requested under a tool schema when the `LLM` supports it. A missing or misspelled key from any LLM is treated as a failed draft (consumes redraft budget → `Unresolved`), never as an exception or a malformed object — asserted against the hostile LLM."

### 11. [major] README contradicts DESIGN on generative fields, calibration, and "shape that cannot be wrong"
- **Location:** README.md:17 ("never asks a model to conjure a value"), README.md:20 ("Free-form fields are chosen from candidate spans"), README.md:23 ("Every value arrives with a calibrated confidence"), README.md:40 ("shape that cannot be wrong", "a calibrated number on every decision"), README.md:32 ("nine phases"). Compare DESIGN.md:395, 547 (LLM-drafted generative fields), DESIGN.md:416 (calibration on this task is an open question), DESIGN.md:539.
- **Finding:** Phase 4, now the first capability after the core, is exactly "asking a model to conjure a value." Class A/F fields carry no confidence at all. "Calibrated" is asserted where DESIGN says it is unmeasured. PLAN.md:538 says the headline must be rewritten by Phase 8, but the README is live now and contradicts the SSOT.
- **Fix text:** README.md:17-20: "It asks a model to conjure a value only where nothing else can: bounded fields are chosen from declared options; free-form fields are selected from verified source spans where the source contains them; truly generative fields are drafted by an LLM and admitted only after passing declared criteria." README.md:23: "Every model decision arrives with Jev's confidence (whether it is calibrated for span selection is measured in Phase 5) and a pointer to its origin." README.md:32: "phases 0–8 to v0, plus planned post-v0 phases 9–11."

### 12. [major] The entity merge threshold p ≥ 0.5 is a default confidence gate on a commit
- **Location:** DESIGN.md:373 (merge at p ≥ 0.5), DESIGN.md:421 ("No default threshold gates a commit"), DESIGN.md:533 (bool → `noul` at 0.5).
- **Finding:** Merging two spans into one array element is a commit, and 0.5 is a default threshold on it. Bool fields have the same issue. §6.2 needs an explicit carve-out, or the rule is violated by Phase 2 (bool) and Phase 7 (merge).
- **Fix text (DESIGN §6.2):** "Exception: where a `noul` must be turned into a structural decision (bool field, entity merge), the decision boundary is 0.5 and the probability is always reported. This is argmax over a binary distribution, not a confidence gate."

### 13. [minor] R10 "computed fields" versus "computed fields are the caller's responsibility until v1"
- **Location:** DESIGN.md:441 vs DESIGN.md:366, and DESIGN.md:214 (`total` → "deterministic parse").
- **Fix text:** R10: "…source-grounded, Jev-selected, LLM-generated, and caller-supplied fields." See finding 16 for class F.

### 14. [minor] "Splitting is always safe" is stated as fact but listed as an open question
- **Location:** DESIGN.md:502 vs DESIGN.md:590.
- **Fix text (DESIGN.md:502):** "…the questions are independent in the graph, so splitting is safe *structurally*; whether it changes Jev's answers is open (§12)."

### 15. [minor] Strict order contradicts Phase 11 "may be pulled earlier"
- **Location:** PLAN.md:33 ("Phases run strictly in order. Each phase depends on the one before it") vs PLAN.md:613.
- **Fix text (PLAN.md:33):** add "Exceptions are stated in the phase itself (Phase 11)."

---

## C. Sequencing bugs

### 16. [major] The worked example (and the Phase 8 quickstart) needs class F, which no phase plans
- **Location:** DESIGN.md:211-214 (`total: number` → "deterministic parse, no model"), PLAN.md:278 ("unbounded numerics each refuse"), PLAN.md:539 (Phase 8 quickstart uses §3.4), DESIGN.md:234 (class F).
- **Finding:** `total: number` is an unbounded numeric, so Phase 2 refuses it. Locating the total in the source is really class D (the invoice has subtotal, tax, and total). Only `extract/patterns.py` (Phase 5, money) touches it. No phase plans a class F "parse" path, and if Phase 5 abandons, the Phase 8 quickstart example is uncompilable.
- **Fix text:** Either change §3.4 to "`total` → candidate spans from the money pattern extractor, `choice` + `none_of_these`, then deterministic parse of the selected span (class F applied to a selected span)", and add "parse selected span to the schema type (number, date)" to Phase 5 deliverables, or add a class F deliverable to Phase 2. Also add to Phase 8: "Quickstart uses only capabilities that shipped."

### 17. [major] Phase 3 tests `none_of_these → Unresolved` before anything produces `none_of_these`
- **Location:** PLAN.md:321, DESIGN.md:300 and 432 (R1: `none_of_these` only on *candidate-backed* choices), PLAN.md:25 ("Phase 3 is a working library… provenance, and typed abstention").
- **Finding:** In Phase 3 every choice is schema-derived and, per R1, has no `none_of_these` option. The criterion can only be exercised by a fake backend returning an option that was never offered, which is a hostile-backend behaviour, not abstention. So the Phase 3 "working library" has no typed abstention path in production. Its provenance is DECLARED_OPTION only.
- **Fix text:** Rewrite PLAN.md:321 as "A backend answer outside the offered option set (including an unoffered `none_of_these`) resolves to `Unresolved(reason=invalid_backend_answer)`, never an exception." Rewrite PLAN.md:25 as "…resolves bounded schemas with confidence reporting, declared-option provenance, and typed `Unresolved` on invalid answers. Abstention over candidates arrives in Phase 5." Optionally decide in DESIGN whether schema enums may opt into `none_of_these` (e.g. "category not determinable from source"), which is a real need for classification over thin sources.

### 18. [major] No phase owns the adversarial suite or the central property
- **Location:** PLAN.md:647-675 (§4), PLAN.md:372 (Phase 4 references "the hostile LLM in §4"), PLAN.md:90-91.
- **Finding:** `hostile_backend.py` and `hostile_llm.py` are deliverables of no phase, and no exit criterion before Phase 10 (PLAN.md:605) asserts the §4.1 central property. The library's headline claim has no merge gate.
- **Fix text:** Phase 3 deliverable: "`tests/adversarial/hostile_backend.py` covering every §4.2 backend row; exit criterion: the §4.1 property holds over generated schemas × every hostile backend behaviour." Phase 4 deliverable: "`tests/adversarial/hostile_llm.py`"; exit: "§4.1 holds with the hostile LLM." Phase 5 exit: "§4.1 holds with hostile spans."

### 19. [major] The Phase 0 conditional band's "mandatory second gate" is planned nowhere
- **Location:** PLAN.md:176, PLAN.md:757.
- **Finding:** If probes 1–3 land in the conditional band, the candidate architecture "ships with a mandatory second gate". Phase 5 has no deliverable or criterion for it, and no cost bar for "cost is re-evaluated".
- **Fix text (Phase 5):** "If Phase 0 returned *conditional* on probes 1–3: each committed candidate span gets an independent verification `noul` ('the span X is the <field description> in the source'), batched into the same call; a failed verification yields `Unresolved(reason=verification_failed)`. The cost delta is recorded."

### 20. [minor] `Rejection` type and generative-drafting module are missing from Phase 1 and layout
- **Location:** PLAN.md:44-45, 218 (types list lacks `Rejection`, `Cost`), DESIGN.md:488 (Result has `rejections` from Phase 1), PLAN.md:79-81 (no module owns LLM drafting; `extract/llm.py` is Phase 5).
- **Fix text:** Add `Rejection` and `Cost` to `types.py` in Phase 1. Add `adjudicate/generate.py — draft generative fields through the LLM protocol under a tool schema` to the layout and to Phase 4.

### 21. [minor] The `LLM` protocol is designed in Phase 1 with no consumer until Phase 4
- **Location:** PLAN.md:108, 219, 235.
- **Finding:** Phase 4 needs the protocol to express "call with a tool schema, get validated arguments back, report tokens". If Phase 1 guesses wrong, Phase 4 must "amend DESIGN §8", which the Phase 1 exit criterion discourages.
- **Fix text:** Pin the `LLM` protocol signature in DESIGN §8 now: `complete(messages, tool_schema) -> LLMResponse(arguments: dict | None, raw: str, input_tokens, output_tokens)`.

---

## D. Stale cross-references after the reorder

### 22. [major] PLAN's bare `§` references resolve to the wrong DESIGN sections
- **Location:** PLAN.md:5 declares "section references below (§3, §5, §8 …) point [to DESIGN]". Under that rule, the following resolve incorrectly:
  - PLAN.md:372 "hostile LLM in §4" → DESIGN §4 is the classification model (means PLAN §4.2)
  - PLAN.md:422 "default-threshold decision (§9)" → DESIGN §9 is prior art (means PLAN §9)
  - PLAN.md:494 "tracked in §9" → same
  - PLAN.md:554 "recorded as a decision in §6" → DESIGN §6 is guarantees (means PLAN §6)
  - PLAN.md:605 "adversarial suite (§4.1)" → DESIGN §4.1 is "can be vs should be" (means PLAN §4.1)
  - PLAN.md:720, 737 "(§9)" → prior art (means PLAN §9)
- **Fix text:** Write internal references as "PLAN §9" / "this plan §4.2", or amend line 5 to "bare § references point to DESIGN.md unless prefixed 'PLAN'", and prefix the seven above.

### 23. [minor] DESIGN.md:505 "(§5, R6)" should be "(§5.6, R6)".

### 24. [minor] The layout still lists semantic ordering
- **Location:** PLAN.md:76 `ordering.py  source order, semantic order (R7)`. R7 now puts semantic order out of v0 (DESIGN.md:438).
- **Fix text:** "`ordering.py  source order (R7); semantic order deferred, PLAN §9`".

### 25. [minor] "Answers" sections point at questions DESIGN §12 no longer lists as open
- **Location:** PLAN.md:387 (Phase 4 "Answers: criteria authoring") vs DESIGN.md:594 ("Settled… criteria authoring"). PLAN.md:762 also keeps a settled item in the *open questions* table.
- **Fix text:** Change Phase 4 Answers to "None open. Implements the settled criteria policy (DESIGN §6, §12 'settled')". Move PLAN.md:762 into §6 Decisions. Also add a PLAN §7 row for the one genuinely new Phase 4 question: "Do redrafts pass criteria they failed? → if recovery is below X%, the default redraft budget becomes 0."

### 26. [major] Answers and open-question rows claim measurements no exit criterion takes
- **Location:**
  - PLAN.md:206 (Phase 0 answers "calibration on this task (first reading)") and DESIGN.md:424 ("If Phase 0's spike… show calibration holds"): none of probes 1–5 measures calibration.
  - PLAN.md:341 and 760 (Phase 3 closes "does splitting a level change answers"): no Phase 3 exit criterion compares split and unsplit answers.
  - PLAN.md:521 and 761 (Phase 7 closes "real pairwise ceiling"): no criterion measures accuracy against n.
- **Fix text:**
  - Phase 0: add "Probe 6: reliability of Jev's `confidence` over probe-1/3 outcomes (ECE, 10 bins, CI reported; reading only, no band)". Otherwise remove "calibration" from Phase 0 Answers and from DESIGN.md:424.
  - Phase 3 exit: "Splitting is measured: the same level resolved unsplit and forcibly split into k∈{2,4} calls, over ≥ 100 questions; selection agreement is written to `docs/taxonomy.md`. If agreement < 0.98, the budget refuses instead of splitting (DESIGN §12)."
  - Phase 7 exit: "Pairwise accuracy is measured at n ∈ {10, 20, 30}; the cap is set to the largest n with accuracy within the probe-4 go band."

### 27. [minor] Sequencing summary and effort note are stale or argue from Asterion
- **Location:**
  - PLAN.md:35 "Phase 4… is what the first user needs": this scopes from Asterion, contrary to PLAN.md:720.
  - PLAN.md:31 "nine of them before release, plus the planned post-v0 phases" is out of date: the post-v0 set now includes a full second-language implementation (Phase 10).
  - PLAN.md:29 "Phase 0 … roughly a day": 150 fields × 11 columns, 100 hand-labelled cases, 50 hand-labelled entity clusters, and 300 probe-5 items is not a day.
  - Phase 5 adds ≥ 300 labelled calibration decisions plus a retry-recovery corpus, and the effort note never mentions that labelling cost.
- **Fix text (PLAN.md:29-31):** "Phase 0 is several days, dominated by labelling (100 probe cases + 50 clusters). Phase 5 adds a second labelled corpus of ≥ 300 decisions, disjoint from Phase 0's. Phase 10 is a second implementation of the library, not a port script." PLAN.md:35: delete "and is what the first user needs"; the independence-from-Phase-5 argument stands on its own.

### 28. [minor] Risk and open-question tables miss the new Phase 4 position
- **Location:** PLAN.md:697-712.
- **Fix text:** Add "Adjudication admits bad drafts (criteria too weak) | Phase 4 | `no_criteria_declared` marker; dry-run tool; rejections recorded" and "Pydantic `$ref`/nullable refused before Phase 6 | Phase 2 | normalise in Phase 2 (finding 2)".

---

## E. Untestable or moving-target exit criteria

### 29. [major] Phase 5 coverage test compares against a spike point estimate on a different corpus
- **Location:** PLAN.md:415-416, 428.
- **Finding:**
  - The Phase 0 rate is a point estimate with ±8–10 points of CI (PLAN.md:170). The library rate adds extraction noise and runs on a different corpus.
  - "No worse than" a noisy point estimate fails about half the time by chance even with identical machinery.
  - "Cannot be *made* to pass" invites tuning until it passes, which is exactly what Phase 0 forbids (PLAN.md:158, 192).
  - It also conflicts with §4.4 (PLAN.md:689: integration tests *measure* rather than assert).
- **Fix text:** "Measured on a held-out corpus of ≥ 100 absent-answer and ≥ 100 present-answer cases, disjoint from Phase 0's and labelled before any run. Pass = abstention sensitivity's 95% CI lower bound ≥ 0.60 and false-abstention's upper bound ≤ 0.20 (the Phase 0 stop bands). No parameter may change between the first measurement and the verdict except bug fixes, and every run is recorded."

### 30. [minor] Phase 4 "the second draft differs" is not a sufficient condition and is not controllable
- **Location:** PLAN.md:371.
- **Finding:** The LLM may return an identical draft. The criterion should specify what the library *does*, not what the LLM does. It should mirror the §5.4 rule.
- **Fix text:** "Redraft passes the failing criteria back to the LLM. If the new draft is identical to one already adjudicated, it is not re-adjudicated (no Jev call) and counts against the budget. Asserted with a fake LLM that repeats itself."

---

## F. Gaps with no owner

### 31. [major] Transport and provider failures fit none of the three outcomes
- **Location:** DESIGN.md:404-410, PLAN.md:327, 638.
- **Finding:** Jev 4xx/5xx/429, timeouts, and LLM provider errors have no mapping. "Never an untyped exception *from a model's output*" leaves network errors unaddressed. Nothing covers what happens to cost already spent when level 3 fails after levels 1–2, whether 429 is retried with backoff (and whether that violates "retries must change the input", PLAN.md:640), or how a 1200 req/min limit interacts with level splitting.
- **Fix text (DESIGN §6.1, new paragraph):** "Transport failures are a typed `BackendError` / `LLMError` (outcome 3b), carrying the partial `Result` (`cost` populated, `unresolved` naming unexecuted nodes). Transport retries (429/5xx/timeout, exponential backoff, bounded by `transport_retries`, default 2) are not decision retries and are exempt from the changed-input rule; they are counted separately in `Cost.transport_retries`. 4xx other than 429 is not retried." Add a Phase 3 exit criterion: "Every hostile transport behaviour (timeout, 429, 500, malformed HTTP body) yields `BackendError` with partial cost, never an untyped exception."

### 32. [major] Single-candidate direct extraction skips the safety property
- **Location:** DESIGN.md:280, 285, PLAN.md:419 (zero backend calls for an unambiguous field), DESIGN.md:289, README.md:23.
- **Finding:** "One obvious span" is decided by the extractor, which is the component the risk table calls the weak link (PLAN.md:704). A single wrong candidate, where the extractor missed the right entity, is committed with no Jev call, no `none_of_these`, and no confidence. That is the wrong-but-valid failure, laundered through "provenance verified". Nothing defines "obvious".
- **Fix text:** "A single verified candidate commits without Jev only if the field sets `direct_extraction=True`. The default is `choice([candidate, none_of_these])`, one question batched into the existing level at ~zero marginal latency (§2), so abstention covers it. `Result.confidence` for a direct-extracted field is absent and the pointer is listed in `Result.ungated`." Rewrite the PLAN.md:419 test accordingly.

### 33. [minor] `Result.confidence` for fields with no decision is undefined
- **Location:** DESIGN.md:485, 493.
- **Fix text:** "`confidence` has an entry only for pointers resolved by a Jev decision. Deterministic, direct-extracted, and caller-supplied pointers are absent from it, and `Result.decided_by[pointer] ∈ {code, jev, llm+jev, llm, direct}` states why."

### 34. [minor] What `.value` holds at an unresolved pointer or union subtree is undefined
- **Location:** PLAN.md:463, 465, 635 ("no silent nulls").
- **Fix text:** "At an unresolved pointer the key is omitted from `.value` (never `null`); if the pointer is the root, `.value` is `{}`. The `Unresolved` entry names the pointer, and for a union it names the whole subtree."

### 35. [major] One conflicting component poisons the whole array
- **Location:** DESIGN.md:373, PLAN.md:492.
- **Finding:** "`Unresolved` for that array" discards every clean component because one component conflicts. With n = 30 and independent pairwise error ε, P(at least one conflicting triangle) rises steeply with n, so large arrays would almost always be wholly unresolved.
- **Fix text:** "A conflicting component yields an `Unresolved` for that component (listing its spans and conflicting pairs); other components are emitted normally; the array is marked incomplete (`complete=False`). Under `maxItems`, unresolved components count toward overflow decisions as unknown and are never silently dropped."

### 36. [minor] `maxItems` × entity resolution × overflow ordering is unspecified
- **Location:** PLAN.md:495, 505, DESIGN.md:487.
- **Fix text:** "Order: membership → pre-merge → pairwise → components ordered by earliest span → `maxItems` truncation keeps the first k in source order; each overflowed element records all its merged spans and the minimum membership probability among them."

### 37. [major] Retry is underspecified: which option set, and does it cause harm?
- **Location:** DESIGN.md:326, PLAN.md:408, 421.
- **Finding:**
  - It is undefined whether the retry `choice` offers *new spans only* or *old ∪ new*. Because Jev's distribution is relative to the offered set, the two give different answers.
  - The 10% bar measures only benefit. Retry also raises false commits when the answer is truly absent: a second, wider extraction produces more plausible distractors.
  - The recovery-rate denominator ("abstentions") mixes truly-absent cases, where recovery must be 0, with extraction-missed cases, so the rate depends on the corpus mix.
- **Fix text:**
  - "The retry choice offers old ∪ new candidates plus `none_of_these`; this is stated so both implementers build the same question."
  - "The bar is two-sided and computed only over abstentions where the answer *was* present in the source: keep the retry budget at 1 iff recovery ≥ 10% **and** the false-commit rate on truly-absent cases increases by ≤ 2 points. Corpus ≥ 100 abstentions, labelled beforehand."

### 38. [minor] No async API and no concurrency posture
- **Location:** DESIGN §8 and the PLAN §2 layout.
- **Finding:** Pipeline authors (LangChain/LlamaIndex, the target user, PLAN.md:721) run async. Nothing states whether `Jevson` is sync-only, thread-safe, or shares a rate limiter across calls.
- **Fix text (Phase 3):** "`Jevson.resolve` and `Jevson.aresolve`; the backend owns an httpx client and a shared token-bucket limiter; instances are safe to share across threads/tasks." Or record the sync-only decision in PLAN §6.

### 39. [minor] Interplay between level splitting and retry is unspecified
- **Fix text (DESIGN §5.4):** "Retries for all fields that abstained in a level are batched into one follow-up call per level (subject to §8.2 splitting)."

---

## G. The Revision 3 decisions, argued against

### 40. [major] Phase 4 before Phase 5 is the wrong default when Phase 0 says "go"
- **Location:** PLAN.md:35, 353, DESIGN.md:606.
- **Argument:**
  - The reason given ("survives Phase 5's abandon criterion") argues that Phase 4 should *exist* in the fallback, not that it should come *first*.
  - Phase 5's abandon criterion is the only remaining existential test. It decides the README positioning, whether Phase 7 exists, and whether the library differs from `jev_jsonschema` (PLAN.md:35). Running it later means building ~450 lines of Phase 4 before knowing what the product is.
  - Phase 4 is also the phase with the largest unplanned design surface (finding 1). Phase 5 has a concrete design and a test corpus from Phase 0.
  - Scenario: Phase 0 is *go* at 0.81 abstention. Phase 4 is built, and then Phase 5 on a real corpus measures 0.62. The team now has an adjudication-first library whose README and quickstart were written around a capability that failed.
- **Change:** "If Phase 0 returns *go* on probes 1–3, run 5 before 4; if *conditional* or *stop*, run 4 first." If that is judged too complex, keep 4 → 5 but put unions (Phase 6, ~250 lines, needs only Phase 3, and fixes the Pydantic-union gap) right after Phase 3.

### 41. [minor] Casefold pre-merge is lossy for case-meaningful entity types
- **Location:** DESIGN.md:372, PLAN.md:491, 508.
- **Argument:** Pre-merge happens *before* any question, so a wrong merge is silent. That is the failure §5.6 exists to prevent. Case-meaningful examples inside one entity type:
  - chemical formulas and substances ("Co" cobalt vs "CO" carbon monoxide)
  - gene and protein names (human "BRCA1" vs mouse "Brca1")
  - tickers and acronyms vs words ("US" vs "us", "IT" vs "it", "AND" as a gate vs "and")
  - product SKUs

  In each case "different entity" is the correct answer and casefold never lets Jev see it.
- **Change:** Default normaliser is NFC + whitespace collapse (lossless on case). Casefold is opt-in per entity type (`Normalizer(casefold=True)`), and the "Acme Corp"/"ACME CORP" exit criterion declares it. Alternatively keep casefold but send case-only-differing pairs to the pairwise stage instead of merging them silently. They are cheap because they are few.

### 42. [major] The ECE ≤ 0.05 over ≥ 300 bar is statistically underpowered and underspecified
- **Location:** DESIGN.md:424, PLAN.md:422, 739, 800.
- **Argument:**
  - Binned ECE at n = 300 with 10–15 bins has sampling noise of roughly 0.02–0.04 and a positive bias, so a perfectly calibrated model can fail the bar and a miscalibrated one can pass.
  - The bar does not say which number is evaluated: Jev's `confidence` field, the selected option's probability, or the `none_of_these` probability.
  - It does not say which bins, or whether the bar applies to the point estimate or to a CI bound.
  - A default threshold only needs calibration *near the threshold*, not global ECE.
- **Change:** "Metric: top-label ECE of Jev's reported `confidence` for the selected option (15 equal-mass bins), plus the reliability at the proposed threshold τ. Bar: the 95% bootstrap upper bound of ECE ≤ 0.05 **and** the empirical accuracy of decisions with confidence ≥ τ is ≥ τ − 0.02, over ≥ 1000 decisions from a corpus disjoint from Phase 0 and pre-labelled."

### 43. [minor] The 10% retry bar is not cost-weighted
- **Location:** DESIGN.md:327, PLAN.md:421.
- **Argument:** A retry costs a full LLM extraction, which is orders of magnitude more expensive than a Jev question (DESIGN.md:71). "10% of abstentions recovered" can be worth it or not depending on the LLM price, which is caller-specific.
- **Change:** Combine with finding 37. Also expose the retry default as a documented per-call parameter and publish recovery and cost-per-recovered-value, so callers set it on their own price.

### 44. [minor] The credentials environment fallback is consistent but has two sharp edges
- **Location:** DESIGN.md:511-514, PLAN.md:328, 599.
- **Argument:**
  1. If `Jevson()` defaults to `JevBackend()` when no backend is passed, a developer with `TYPESAFE_API_KEY` in their shell silently hits the paid API in "unit" tests. Nothing makes the choice of live over fake explicit.
  2. The JS port "falls back to `TYPESAFE_API_KEY`", but in browsers and edge runtimes there is no `process.env`.
- **Change:** "`Jevson` requires an explicit `backend=`; there is no default backend." For JS: "Environment fallback in Node only; elsewhere `apiKey` is required."

### 45. [minor] Semantic-ordering deferral silently produces wrong-but-valid output for ranked arrays
- **Location:** DESIGN.md:438.
- **Argument:** For a schema like `top_priorities: [str]` (descriptions say "ranked"), source order is a wrong-but-valid value, the failure class the library exists to surface.
- **Change:** "Arrays are emitted in source order and `Result` records `ordering: source` per array pointer; a schema whose array declares `x-jevson-order: semantic` refuses in v0 rather than silently source-ordering."
