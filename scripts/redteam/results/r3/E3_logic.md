# E3: Logic review, round 3 (Jevson Revision 5)

Targets: `Jevson/DESIGN.md` (735 lines), `PLAN.md` (883), `README.md` (49), `docs/REDTEAM.md` (108), `Agents/CLAUDE.md` (Jev and Jevson blocks, :146–167), and `Admin/README.md` (:22, :42, :67). Line numbers refer to the working tree. No design documents were edited.

Severity:

- **Blocker:** a phase cannot be built as written, or an exit criterion or the headline property cannot pass as written.
- **Major:** a contradiction or unowned behaviour that two implementers would resolve differently, or a statistically ill-posed bar.
- **Minor:** stale text, wording, or a missing cross-link.

Scope rules followed: the phase order is the owner's decision. Where it matters, the review notes risk only.

---

## 0. Round-2 verification (results/r2/E2_logic.md)

**Verified fixed:**

- **Blockers and majors:** 1 (one `x-jevson` keyword in DESIGN §3.5; Phase 5 lifts the refusal at PLAN.md:452; the Phase 4 exit at :413), 2 (a run-time `too_many_candidates`; zero candidates handled; but see finding 4), 3 (PLAN.md:311), 6 (versioned templates, DESIGN §5.2 / PLAN.md:184, :303), 7 (a closed set at DESIGN.md:465; see finding 5 for gaps), 8 (`PreflightError`, `ExtractorError`), 10 (DESIGN.md:7, README.md:3), 12, 13 (PLAN.md:470), 15 (declared maxima; see finding 11), 19 (enum arrays and flat `allOf`; see finding 16), 20 (DESIGN §5.6), 22 (constructed misses and 300 absent cases; see finding 18), 24 (PLAN.md:420).
- **Minors:** m2–m14.
- **Agents/Admin:** a1, a2, a4, a5, a7.

**Partly fixed:**

- **R2 #4.** `decisions` is now keyed by node id, and `decided_by` has `llm` and `caller`. There is no attempt index, so retries and redrafts collide (finding 9).
- **R2 #5.** The executor now runs steps, and the drafting prompts have an owner. **Where the draft sits in the adjudication request is still unspecified.** The **[P7]** 0/80 result was measured under one layout (finding 24).
- **R2 #9.** The tie band and sum tolerance are defined. Still open: the vendor `choice` field vs argmax, and a tolerance that is vacuous for large K (finding 7).
- **R2 #11.** README.md:34 has the caveat, but README.md:24 is still unconditional (finding 25).
- **R2 #14.** The power check was added. How τ is chosen is still unspecified (finding 19).
- **R2 #16.** Threshold and scope are defined. The screen's own steerability is unstated, and "class C whose question reads the source" is every class C decision (finding 23).
- **R2 #17.** The cache writes to a caller directory, and `ReplayLLM` exists. `Cost` on replay, non-LLM extractors, and replay misses are unspecified (finding 21).
- **R2 #18.** The protocols are async and the limiter is per key. **New defect:** loop binding (finding 3).
- **R2 #21.** The redraft bar is now labelled, but redrafts cannot be *pre*-labelled, and the LLM is unnamed (finding 17).
- **R2 #23.** Now margin ≥ 0.20 and ≤ 2%. "Flip" and the selection run are undefined (finding 22).
- **m1.** The old residue is gone, but a new bare `§` sits at PLAN.md:56 (finding 26).
- **a3.** Agents/CLAUDE.md:164 still says "never a guess" (finding 25).
- **a6.** Admin/README.md:67 is fixed. :22 is still an unchecked box that says the key was obtained (finding 25).

**Cross-reference audit.** Every `DESIGN §n` in DESIGN, PLAN and README resolves to an existing heading after the §5 renumbering: §5.1–§5.9, §6.1–§6.3, §8.1–§8.4, §10, §12 and §13 were each checked against their content. Every `PLAN §n` resolves. The rule numbers R1, R3–R9, R11 and R13–R16 used in PLAN match DESIGN §7. The residues are in finding 26.

---

## Blockers

### 1. [blocker] The central property omits the case `complete=True, satisfies_schema=False`, which the design produces routinely

- **Where:** DESIGN.md:449–460 (outcome 1 needs complete **and** valid; outcome 2 needs `complete is False`); DESIGN.md:462; PLAN.md:744 (§4.3: "a fully resolved graph either validates … or yields `satisfies_schema is False`"); **[L9]** (REDTEAM.md:53: fully resolved graphs fail `maxLength`, `pattern`, `minItems`, `uniqueItems`, `dependentRequired`); DESIGN.md:456 (`SchemaViolation` fires only when "a required field is unresolved").
- **Finding:** Take a selected span that is 15 characters long in a `maxLength: 10` field, a parsed total below `minimum`, or an array with fewer emitted elements than `minItems` and no hole. Each gives `unresolved == []`, so `complete is True`, while `satisfies_schema is False`. That is neither outcome 1 nor outcome 2, so it is the "fourth outcome" DESIGN §6.1 forbids.
  - The Phase 3 and 4 exit criteria assert the property "over generated schemas", and hypothesis will find this case at once.
  - No `Result` field names the violated keyword, although PLAN.md:744 promises one.
  - `raise_on_violation=True` does not fire on these cases.
  - The zero-candidate path (finding 4) is a second route into the same state.
- **Fix text:**
  - **DESIGN §6.1, outcome 2:** "a `Result` with `.complete is False` **or** `.satisfies_schema is False`, every hole named in `.unresolved` and every validation failure named in `.violations`."
  - **DESIGN §8.1:** add `violations [Violation(pointer, keyword, message)] — final-validation failures; empty iff satisfies_schema`.
  - **DESIGN.md:456:** "`SchemaViolation` — `.satisfies_schema is False` and the caller set `raise_on_violation=True`."
  - **DESIGN §5.3, optional:** "Candidates whose text cannot satisfy the field's own `maxLength`/`minLength`/`pattern`/`format` are filtered by code before the choice and counted." This is class A, and it removes most of the cases above before any spend.

### 2. [blocker] Two Phase 2 exit criteria contradict the Phase 2 refusal list

- **Where:** PLAN.md:312 ("a model with … an `Optional[str]` field, … a `Decimal` field declaring a source … compiles without refusal"); PLAN.md:318 ("unbounded strings or numbers with no `source` or `generate` declaration and no default extractor" refuse); PLAN.md:319 ("`x-jevson.source` fields … refuse with `not_yet_supported`"); DESIGN.md:253.
- **Finding:**
  - An undeclared `Optional[str]` is an unbounded string. Under :318 it refuses (class G).
  - A `Decimal` declaring `source` refuses under :319.
  - :312 therefore cannot pass together with :318 and :319.
  - A third problem: `compile_schema()` is "standalone" (PLAN.md:306), but whether a field refuses depends on `Jevson(default_extractor=...)` (DESIGN.md:253), which `compile_schema()` never receives.
- **Fix text:**
  - **PLAN.md:312:** "…a nested submodel, an `Enum` field, a single-member `Enum`, an `Optional[Category]` field, a `Literal` field, and a defaulted field compile without refusal; a `Decimal` field declaring a source **normalises** to a number (no normalisation refusal) and then refuses only with `not_yet_supported`."
  - **DESIGN §3.5 and PLAN.md:306:** "`compile_schema(schema, *, default_extractor: str | None = None, extractors: Collection[str] = ())`; `Jevson.resolve` calls it with its own configuration. An `x-jevson.source.extractor` name not in `extractors` refuses (`unknown_extractor`)."

---

## Major

### 3. [major] Async-only protocols with a "private event loop" plus one `AsyncClient` and a process-wide limiter are not buildable as literally specified

- **Where:** DESIGN.md:523 ("the synchronous `resolve()` runs them on a private event loop"); DESIGN.md:535 ("The backend owns one `httpx.AsyncClient`. The rate limiter is per API key, shared across every `JevBackend` in the process through a registry"); PLAN.md:349, :372.
- **Finding:**
  - An `httpx.AsyncClient` and its connection pool are bound to the loop that first used them. If `resolve()` uses a fresh loop per call (the natural `asyncio.run` reading), the second `resolve()` on the same backend reuses connections from a closed loop and fails with "Event loop is closed" or a `RuntimeError`.
  - `asyncio.Lock`, `Semaphore` and `Condition` bind to their first loop (Python ≥ 3.10). A process-wide limiter built from them raises "bound to a different event loop" when one backend is used from `resolve()` (private loop) and another from `aresolve()` (the caller's loop), or from two threads. The Phase 3 exit at :372 exercises exactly this.
  - Caller-supplied async `LLM` and `Extractor` objects usually hold their own loop-bound clients, for example an OpenAI `AsyncClient` created on the caller's loop. Running them on Jevson's private loop breaks them.
  - The refusal "inside an already-running loop" names no exception type (see finding 12).
- **Fix text (DESIGN §8, replacing the first paragraph's last sentence and the `JevBackend` sentences):**
  - "`resolve()` drives `aresolve()` on **one persistent event loop per `Jevson` instance, running on a dedicated daemon thread**, created lazily and closed by `Jevson.close()` / context manager. Caller protocols passed to a `Jevson` used synchronously must be usable from that loop.
  - `JevBackend` holds one `AsyncClient` **per event loop** (a `WeakKeyDictionary` keyed by the running loop).
  - The per-key limiter is a **loop-agnostic token bucket** (a `threading.Lock` around timestamps; waiting is done with `asyncio.sleep` on the caller's loop), so it may be shared across loops and threads.
  - Calling `resolve()` inside a running loop raises `UsageError`."
- **Fix text (PLAN Phase 3 exit):** "Two successive `resolve()` calls and an `aresolve()` on a caller loop, all on backends sharing one key, succeed and share one budget; a caller-supplied `AsyncClient`-based fake LLM works under `aresolve()`."

### 4. [major] Zero candidates on a required field: PLAN says `absent`, DESIGN §5.6 says `Unresolved(abstained)`

- **Where:**
  - DESIGN.md:328 ("Zero candidates resolve without a Jev call (DESIGN §5.6)") and DESIGN.md:346 (the lifecycle maps "zero candidates → absent");
  - PLAN.md:459 and :473 ("zero candidates yield an `absent` entry and no backend call", unconditionally);
  - DESIGN.md:373 (a required, non-nullable field → `Unresolved(abstained)`).
- **Finding:** Read literally, a required field with no candidates lands in `absent`, so the result reports `complete=True, satisfies_schema=False` (finding 1).
  - `abstained` is also the wrong reason, because nothing abstained.
  - The mirror case: `Absent.abstain_probability` has no value when no Jev call was made. DESIGN.md:568 forbids a `None` that means "nothing happened", but does not type the nested fields.
  - Zero candidates also skip the retry, yet an extractor that returned nothing is exactly the extraction-miss case that retry exists for.
- **Fix text:**
  - **DESIGN.md:346 and PLAN.md:459/:473:** "zero candidates → the DESIGN §5.6 table, applied as if abstained: nullable → `null`, optional → omitted (`absent`), required → `Unresolved(no_candidates)`."
  - Add `no_candidates` to the closed set at DESIGN.md:465.
  - **DESIGN §8.1:** "`abstain_probability: int | None` in hundredths; `None` iff no Jev call was made for the field."
  - **DESIGN §5.5:** state whether zero candidates trigger the re-extraction retry. The recommendation is yes, within `retry_budget`, because it costs no Jev call unless new spans appear.

### 5. [major] The closed reason set has no reason for three reachable outcomes

- **Where:** DESIGN.md:465 (the closed set); DESIGN.md:220, :423 (class F parse of a selected span); PLAN.md:456, :481; DESIGN.md:577 (run-time `max_tokens_exceeded` → "`Unresolved(too_many_candidates)` for the affected field").
- **Finding:**
  - **(a) Class F parse failure.** A selected money span that does not parse (`"see attached"`, `"TBD"`, `"approx. 1.2k"`), or parses ambiguously (`"1.204,50"`: is it 1204.50 or 1.2045?), has no reason. The alternatives are all bad: guess a locale, raise an untyped exception, or omit silently.
  - **(b) A run-time 400 `max_tokens_exceeded` on limit (a).** The 400 body carries no counts (DESIGN.md:86), so Jevson cannot tell which question is "the affected field" in a multi-question request without bisecting. When the offending question is a criterion, a pair, a membership noul, or the screen, `too_many_candidates` is false.
  - **(c) Decimal precision.** `total: Decimal` is normalised to a JSON number, and DESIGN.md:423 parses `"$1,204.50"` into the float `1204.5`. Money that passes through float is lossy for many values.
- **Fix text:**
  - Add `unparseable_span` to the closed set.
  - **DESIGN §5.9:** "Class F parsing is locale-explicit (`x-jevson.source.locale`, default `en`). A selected span that does not parse, or parses to more than one value under the locale, yields `Unresolved(unparseable_span)`, with the span in `detail`. Decimal-typed fields are emitted as JSON strings in canonical decimal form when the original schema accepts strings (Pydantic `Decimal` does), else as numbers."
  - **DESIGN §8.2:** "On `max_tokens_exceeded`, the executor bisects the request. A single question that still fails yields `Unresolved(context_limit)` for its target pointer." Add `context_limit` to the closed set, and keep `too_many_candidates` for count caps only.

### 6. [major] The tie band's width, scope, and boundary differ between bools, choices, criteria, rubrics, and the screen

- **Where:**
  - DESIGN.md:285 (bool tie at 0.46–0.54, so a two-sided margin of |2p − 1| < 0.10);
  - DESIGN.md:286–287 ("top-two within 0.05", so a margin ≤ 0.05);
  - DESIGN.md:474 (the band applies to "bool fields, enum choices, scores, and array membership");
  - DESIGN.md:488 (criteria "pass at p ≥ 0.55 (the bool rule)", so a criterion at 0.50 is a *failure*, not a tie);
  - DESIGN.md:401 (the screen band *flags*);
  - PLAN.md:705 ("the tie band applies wherever a boundary does");
  - PLAN.md:363.
- **Finding:**
  - **(a) Width.** A two-option `choice([c0, none_of_these])` at 0.53/0.47 has a top-two gap of 0.06, which is not a tie. The same belief expressed as a noul (p = 0.53) *is* a tie. The choice band is half the width of the bool band that **[P12]** measured. The single-candidate choice (DESIGN §5.3), the most common source-grounded question, is exactly this binary case.
  - **(b) Scope.** DESIGN.md:474 omits **candidate-backed choices**, union discriminators (which PLAN.md:523 says tie), criteria, and rubrics. PLAN.md:705 includes them all. So the documents do not say whether a candidate at 0.52 vs `none_of_these` at 0.48 is a commit or a tie. For an *optional* field a tie makes `complete=False`, which is a product decision.
  - **(c) Rubric scores.** The band on rubric scores is undefined for adjudication. Flat wide scales tie often **[P13]**, and it is not stated whether a tie means rejection or `Unresolved(tie)`.
  - **(d) The inclusive edge.** It is not stated whether a gap of exactly 5 hundredths is a tie.
- **Fix text (DESIGN §6.2, replacing the tie-band bullet):**
  - "**The tie band** is defined on the margin between the top two probabilities, in hundredths: a margin **< 10** is a tie. For a noul, the margin is |2p − 100|, so 46–54 tie, as before. It applies to every Jev decision that commits a value: bool fields, schema choices, candidate choices (a candidate vs `none_of_these` included), union discriminators, scores, and array membership.
  - For **adjudication**, a criterion or rubric inside the band **fails** (conservative), and a draft never commits on a tie.
  - For the **screen**, the band flags.
  - Entity pairs use DESIGN §5.7."
  - Update DESIGN.md:286–287 and PLAN.md:363 ("a choice whose top two differ by fewer than 10 hundredths").
  - Note: if the owner prefers the current choice width, the bool band must become 48–52 instead, and **[P12]** did not measure that.

### 7. [major] The sum tolerance ⌈K/2⌉ hundredths accepts an all-zero distribution for K ≥ 200, and argmax vs the vendor `choice` field is unresolved

- **Where:** DESIGN.md:71; PLAN.md:273, :362.
- **Finding:**
  - At K = 255 the tolerance is 128 hundredths, so any sum in [−28, 228] passes. That includes all zeros, which gives no argmax, and 1.00 on two options at once, which gives a "tie" at p = 1.00. The worst-case rounding bound is the wrong statistic: it only matters if the vendor rounds each value independently, and **[L17]** saw at most 1 hundredth of drift in 630 answers.
  - It is also unstated which is authoritative, the vendor's `choice` field or the argmax of `probabilities`, when they disagree. That was R2 #9 and is still open.
- **Fix text (DESIGN.md:71):** "…a sum within **min(⌈K/2⌉, 5)** hundredths of 100 is accepted; anything else, or a maximum probability of 0, is `invalid_backend_answer`. Selection is the argmax of `probabilities`; the vendor's `choice`/`score` fields are recorded in `Decision`, and a vendor `choice` that differs from a unique argmax is `invalid_backend_answer`." Add a Phase 3 exit criterion: "an all-zero 255-option distribution and a vendor `choice` disagreeing with the argmax are both `invalid_backend_answer`."

### 8. [major] The two-directional entity rule: one uncertain hub can blank the whole array, non-members can blank members, and the fallback floor maximises both

- **Where:** DESIGN.md:382–386; DESIGN.md:203 and PLAN.md:552 (pairs are asked over **all** candidates, not only members); PLAN.md:557 (membership → pre-merge → pairwise → components); PLAN.md:208 (the floor rule and its 0.05 fallback).
- **Finding:**
  - **(a) Cascade.** Take one generic mention ("the company", "the client") with p(same) in (floor, 0.5] against each other organisation. Under condition 2, **every** component it touches becomes `Unresolved(entity_conflict)`, so one mention can empty the whole array. This is the round-1 #35 "one component poisons the array" failure returning through a different door. **[P10]**'s 0/133 silently wrong came at 16–24 unresolved per ~133 components, in-sample.
  - **(b) Members vs non-members.** Pairs are asked over all candidates in the same level, but the documents do not say whether the component graph is built over **accepted members** or all candidates. If it is built over all candidates, a *rejected* candidate with an uncertain link to a member blanks the member.
  - **(c) The floor.** The floor rule (PLAN.md:208) looks only at *same-entity* pairs at or below the floor, which is the internal-merge side. The **same** floor sets the lower edge of the cross-component band. A lower floor makes the band (floor, 0.5] wider and pushes more arrays to `Unresolved`. The pre-registered fallback, "if no value qualifies, the floor is 0.05", yields the widest band (0.05, 0.5]: almost every multi-entity array would come back unresolved. The rule's choice of floor ignores its main cost.
  - **(d) Recursion.** It is unstated whether a component linked uncertainly to an *already-unresolved* component is itself unresolved. It should be, but say so.
- **Fix text:**
  - **DESIGN §5.7, step 2:** "Components are built over **accepted members only**; pair answers involving non-members are recorded in `decisions` but ignored by the rule."
  - **Step 3, append:** "Condition 2 is evaluated against all other member components, resolved or not. `detail` names the offending pairs, so a caller can see when one mention caused several conflicts."
  - **PLAN.md:208:** "…the rule is scored at the chosen floor **and the unresolved-component rate is reported beside the silently-wrong rate**; the verdict's *go* band additionally requires unresolved components ≤ 0.25. If no floor qualifies, probe 4 is *stop* and **no floor is written** (the 0.05 fallback is removed)."
  - **PLAN Phase 7 exit:** "**The hub case:** one mention uncertain (0.40) against three otherwise clean components → those components are `Unresolved(entity_conflict)` naming the hub; the count of components blanked by a single mention is reported on real prose."

### 9. [major] `Result.decisions` is keyed by node id, but retries, redrafts, and repeated adjudications reuse node ids

- **Where:** DESIGN.md:551–554 ("every Jev decision: … criteria, …, retries"); DESIGN.md:163 (node ids); DESIGN.md:489 (redraft re-adjudicates the same criteria nodes).
- **Finding:**
  - The retry choice for `/customer/name#choice` and the first choice share a key. Redraft *k*'s `#criterion:2` overwrites draft 1's. So "every Jev decision" is not representable.
  - The R2 #4 fix text had an `attempt` field, and it was dropped.
- **Fix text (DESIGN.md:551):** "`decisions {decision_id: Decision(node_id, attempt, kind, selected, distribution_hundredths, vendor_confidence | None, target_pointer)}` where `decision_id = f"{node_id}@{attempt}"` and `attempt` starts at 0 for the first ask, increasing per retry or redraft." Add a PLAN Phase 4/5 exit criterion: "a field retried once and a draft redrafted once each leave two `Decision`s."

### 10. [major] `known=` (caller-supplied values) has no semantics, no exception, no provenance, and no exit criterion

- **Where:** DESIGN.md:508 (R10: `resolve(source, known={pointer: value})`); DESIGN.md:549–550 (`decided_by: caller`); DESIGN.md:408–412 (only two provenance kinds); PLAN.md:352 (the Phase 3 façade signature). No exit criterion in any phase mentions `known`.
- **Finding:** None of these cases is defined:
  - a pointer that does not exist in the schema;
  - a value that violates the field's schema (an enum value not declared, a wrong type);
  - a pointer inside an unselected union branch, or a `known` discriminator value (does it select the branch and skip the decision?);
  - a pointer into an array (`/items/2`);
  - a known value on a field declaring `source`;
  - whether a flagged source (DESIGN §5.8) touches caller values;
  - what `provenance` holds for a caller pointer (neither `SOURCE_SPAN` nor `DECLARED_OPTION`).
  Invalid input also has no typed exception, which breaks "never an untyped exception" (finding 12).
- **Fix text (DESIGN §8, a new paragraph under API shape):** "`known` maps **field** pointers (no array indices) in the normalised schema to values. Each value is validated against its subschema before any call; an unknown pointer or invalid value raises `UsageError` naming every offender. A known field's nodes and steps are removed from the graph, with their dependants resolved against the given value (a known discriminator selects its branch). Known values are unaffected by the source screen, carry `decided_by = caller`, and have provenance `CALLER` (a third kind; DESIGN §5.9 updated)." Add a PLAN Phase 3 exit criterion covering each case.

### 11. [major] `max_candidate_chars` has no default, and the preflight ceiling under default maxima contradicts DESIGN §8.2

- **Where:** DESIGN.md:245 (`max_candidate_chars?: int`, no default); DESIGN.md:328 (`max_candidates` default 254); DESIGN.md:577 (preflight uses "`max_candidates` × `max_candidate_chars` (plus context windows for repeated text)"); DESIGN.md:579 ("~108k … or ~62k … characters alongside a realistic 255-option question").
- **Finding:**
  - With no default, preflight cannot bound a candidate question at all.
  - Preflight cannot know which candidates will repeat, so it must budget context windows on all 254 options: ~80 tokens each **[P14]**, about 20k tokens. That leaves ~12k tokens of source, roughly a third of the stated ~62k–108k-character ceiling, and only because of the defaults.
  - Separately, repeated-text occurrences each become an option (DESIGN §5.1), so the option count can exceed the number of distinct candidates. A value such as "USD" appearing 300 times forces `too_many_candidates`.
- **Fix text:**
  - **DESIGN §3.5:** "`max_candidate_chars` default 200; a longer verified candidate is rejected like an unverifiable span and counted."
  - **DESIGN §8.2:** "Preflight budgets `max_candidates` options at `max_candidate_chars` plus a ±40-character window each (the worst case). **Under the defaults, the source ceiling is ~N characters** (computed and tagged); the ~62k–108k figures apply only when a field declares ≤ M candidates. Occurrences of one text count separately toward `max_candidates`." Tag the computed ceiling with an L-check.

### 12. [major] Several call-time errors are not in the exception hierarchy

- **Where:** DESIGN.md:453–460; DESIGN.md:421 (more than one source "refused at the call boundary"); DESIGN.md:523 (`resolve()` "refuses" inside a running loop); finding 10 (invalid `known`); finding 2 (unknown extractor name, if caught at `resolve`).
- **Finding:** `PreflightError` is defined as "the source or a declared maximum exceeds a context limit", which covers none of these. A `TypeError`, `ValueError` or `RuntimeError` escaping `resolve()` is an untyped exception under DESIGN §6.1.
- **Fix text (DESIGN.md:455):** add "`UsageError` — the call itself is malformed (more than one source, invalid `known`, a sync call inside a running loop, a source that is not valid Unicode text); raised before any backend call, no spend." Add it to PLAN.md:52.

### 13. [major] Defaulted fields: class A constant, or decided?

- **Where:** DESIGN.md:265 (class A covers "defaults"); DESIGN.md:371–372 (a nullable field "with or without a default" → `null`; an optional non-nullable field → key omitted); PLAN.md:702 ("…or a declared default").
- **Finding:** Nothing says what happens in these two cases:
  - **(a)** A field with a default and **no** `x-jevson` declaration, for example `currency: str = "USD"`. Is it class A (the default is emitted, no decision) or class G (an unbounded string refuses)?
  - **(b)** A defaulted field that declares `source` and abstains. Is the default inserted into `.value`, or the key omitted (DESIGN §5.6)?

  If the key is omitted, a caller that `model_validate`s `.value` silently gets the default. If `null` is emitted for `Optional[str] = "x"`, it overrides a non-null default with `null`. Two implementers will diverge.
- **Fix text (DESIGN §5.6, after the table):** "A field with a JSON Schema `default` and no `x-jevson` declaration is class A: the default is emitted, `decided_by = code`. A defaulted field that declares `source` or `generate` is decided; on abstention it follows the table above (the default is **not** inserted), and `Absent` records that a default exists so the caller can apply it knowingly." Add a Phase 2 exit case for (a) and a Phase 5 case for (b).

### 14. [major] The configuration surface for entity resolution, bands, and caps has no API

- **Where:** DESIGN.md:535 (`Jevson(backend=..., llm=..., extractors=..., default_extractor=None)`); DESIGN.md:285 (the tie band is "configurable"); DESIGN.md:381 (casefold is "opt-in per entity type"); DESIGN.md:390 (`conflict_floor` — "tests pass an explicit floor"); DESIGN.md:530 (`Normalizer` "declared per entity type"); DESIGN.md:401 (the screen is opt-in); DESIGN.md:581 (the pairwise cap); DESIGN.md:363, :466, :489, :463 (`retry_budget`, `transport_retries`, `redraft_budget`, `raise_on_violation`).
- **Finding:** None of these has a stated home: `Jevson(...)`, `resolve(...)`, or `x-jevson`.
  - `entity_type` is a free name in `x-jevson` with no registry.
  - The parameters that change results (floor, band, cap, screen) are not listed in `Result.versions`, so a replayed or compared result cannot say which settings produced it.
- **Fix text (DESIGN §8, API shape):** "`Jevson(backend, llm=None, extractors={}, default_extractor=None, entity_types={name: EntityType(normalizer, casefold=False)}, conflict_floor=<Phase 0 value>, tie_band_hundredths=10, pairwise_cap=30, screen=False)`; `resolve(source, *, known={}, retry_budget=1, redraft_budget=1, transport_retries=2, raise_on_violation=False)`. An `x-jevson.source.entity_type` not registered refuses at compile time. `Result.versions` records every result-affecting setting."

### 15. [major] Pairwise questions over all candidates make the n = 30 cap bite on candidates, not members

- **Where:** DESIGN.md:203 ("pairwise entity questions are asked over all candidates in the *same* level, not only over accepted members"); DESIGN.md:581 (the cap is n = 30; above it → `Unresolved(too_many_candidates)`); PLAN.md:568; DESIGN.md:581 ("the compiler's run-time check").
- **Finding:**
  - An invoice whose LLM extractor proposes 40 product-like strings, of which 6 are real line items, yields `Unresolved(too_many_candidates)` for the whole array. The one-level design moves the cap from members to candidates, and the documents do not state that trade-off.
  - "The compiler's run-time check" is a contradiction in terms: the compiler never sees a source.
- **Fix text (DESIGN §8.2):** "The cap applies to **pre-merged candidates**, because pairs are asked before membership is known (DESIGN §3.3). Above it the executor (not the compiler) either (i) yields `Unresolved(too_many_candidates)`, or (ii) with `pairwise_after_membership=True`, asks pairs over accepted members in a second level." PLAN Phase 7 measures how often real arrays exceed 30 candidates, and chooses between the two.

### 16. [major] Multi-label enum arrays have no exit criteria and no ordering or cardinality rule, and the fallback product is stated three ways

- **Where:** PLAN.md:548, :553 (enum arrays "ship regardless"); Phase 7 exits at :562–:573 (none about enum arrays); PLAN.md:229 and :488 (the fallback is "phases 1–4, 6 and 8", and ":488 Phase 7 is cancelled"); PLAN.md:863 ("1–4, 6, 7 (enum arrays only) and 8"); PLAN.md:572 ("an array with no source grounding refuses", which an enum array is).
- **Finding:**
  - The following are all unspecified: the order of an enum array (R7 "source order" is meaningless for declared values); `maxItems` with more labels passing than allowed (which labels are kept, and is the rest overflow?); `minItems`; `uniqueItems`; and ties.
  - The Phase 7 refusal at :572 as written refuses enum arrays.
  - Phase 5 does not say it is **skipped** when Phase 0's abandon fires. PLAN.md:25 says abandoned phases are skipped, but Phase 0's abandon is about candidate selection, not Phase 0 itself.
- **Fix text:**
  - **PLAN Phase 7 exits:** "**Enum arrays:** `list[Category]` compiles to one membership noul per value (tie band applies; a tied value yields `Unresolved(tie)` at the array pointer); values are emitted in **schema declaration order**; `maxItems` keeps the k most probable, the rest recorded in `overflow`; these criteria run and must pass even when Phase 5 abandoned."
  - **PLAN.md:572:** "…an array of unbounded items with no `source` refuses."
  - **PLAN.md:229 and :488:** "phases 1–4, 6, 7 (enum arrays only) and 8".
  - **Phase 5, Depends on:** "Skipped if Phase 0's abandon criterion fired."
  - **Phase 0:** state what probe 4 *stop* does (recommended: Phase 7 ships without deduplication claims, per its abandon criterion).

### 17. [major] The Phase 4 redraft bar needs labels for text that does not exist until the run

- **Where:** PLAN.md:424 ("over ≥ 100 rejected drafts from a **pre-labelled** set, the rate at which a redraft is admitted *and* truly satisfies the criteria"); DESIGN.md:489.
- **Finding:**
  - Redrafts are produced by the caller's LLM during the measurement, so they cannot be pre-labelled. Labels applied afterwards must be blind to Jev's verdict, or the "truly satisfies" side is contaminated.
  - The comparison is between different populations: a redraft false-admission rate (over ≥ 100 rejected drafts) against "the same rate for first drafts" (over all first drafts, of unstated n).
  - At n ≈ 100, "2 points" is 2 cases, which is noise.
  - The LLM is not named, although the result depends on it (R2 #21).
  - Getting ≥ 100 *rejected* first drafts needs roughly 100 / (rejection rate) first drafts. That count is not in the PLAN §1.1 effort note.
- **Fix text (PLAN.md:424):** "…first drafts and their sources are pre-labelled; **redrafts are labelled after generation by a labeller blind to Jev's verdict**. Recovery = (redrafts admitted and labelled satisfying) / (rejected first drafts), n ≥ 100. False admission is compared as a **paired** rate on the same fields: admitted-but-violating redrafts vs admitted-but-violating first drafts, each over its own admitted count, with the difference's 95% interval reported; the default stays 1 only if recovery ≥ 10% and the interval's upper bound is ≤ 5 points. The LLM and its version are recorded." Add the first-draft count to PLAN §1.1.

### 18. [major] The retry bar's construction guarantees the recovery side

- **Where:** PLAN.md:477 ("the correct span withheld from the first extraction pass and **available to the second**"); DESIGN.md:360, :363.
- **Finding:**
  - The real question is whether the extractor, re-invoked with exclusions, finds the missed span. Making the span available by construction removes that question. What remains is whether Jev picks a correct span among old ∪ new, which is probe 1's accuracy (≥ 0.85 at *go*). "Recovery ≥ 10%" therefore passes almost by construction, and only the false-commit side can fail.
  - The denominator is not stated. A constructed case whose first pass commits a wrong candidate never retries. At probe 2's *go* rate of about 0.80, 100 constructed cases give only about 80 retries.
- **Fix text (PLAN.md:477):** "…the correct span is withheld from the first pass by the harness; **the second pass is the real extractor called with the first pass's spans as exclusions** (the correct span is not injected). Recovery = correct commits after retry / first-pass abstentions, with ≥ 100 first-pass abstentions (construct as many cases as that needs). A second, optimistic figure with the span injected is reported separately as an upper bound."

### 19. [major] The calibration bar: τ is unspecified, and nothing says what happens if the power check still fails at 3,000

- **Where:** DESIGN.md:475–480; PLAN.md:478.
- **Finding:**
  - Condition 2 ("among decisions with p ≥ τ") never says how τ is chosen. Choosing τ on the same data as the Wilson test (for example, the τ that passes) is a multiple-comparison search. This was R2 #14 and is still open.
  - Extending the corpus to up to 3,000 is free of optional-stopping bias **only if** the extension decision reads the probabilities and never the labels. That is implied ("on the observed probability distribution") but not stated.
  - The extension decision needs the extra 2,000 cases to be pre-labelled, disjoint, and under the corpus rules, and PLAN §1.1 counts only "up to 3,000".
  - If the check fails at 3,000 (as **[L13]** can for a uniform-like distribution at the overconfident side), the outcome is undefined.
- **Fix text (DESIGN.md:476–478):** "(2) … τ is fixed before any label is read: τ = the smallest candidate threshold in {0.80, 0.85, 0.90, 0.95} whose count of decisions at or above it is ≥ 300 **on the unlabelled probabilities**… (3) … the extension decision reads probabilities only; labels are unsealed once, after n is final. If the power check still fails at 3,000, no default threshold is adopted in v1 and the reason is recorded."

### 20. [major] The Phase 7 both-orderings experiment has no sample size, test, or budget interaction

- **Where:** PLAN.md:558, :570; DESIGN.md:691; DESIGN.md:581 (cap and budget).
- **Finding:**
  - "Adopted only if it lowers the flip rate … without lowering component accuracy" is a comparison of point estimates at an unstated n. Flips are rare (16/1,824 **[P10]**), so a difference of a few flips decides it.
  - Asking both orderings doubles the pair questions: 870 at n = 30. That exceeds both the lean-template budget **[L7]** and the 320-question keyed-batching evidence **[P4]**. Yet the cap is measured at :569 without saying under which strategy.
- **Fix text (PLAN.md:570):** "…on ≥ 50 real clusters × 2 identical runs per strategy, pre-registered: adopted only if the paired flip count falls by ≥ 50% (with the exact McNemar p < 0.05) and component accuracy is not lower by more than 2 points (paired). **If adopted, the cap criterion at :569 is re-run with doubled pair questions**, and the budget is re-derived."

### 21. [major] Exact replay: `Cost` on replay, extractor replay, and replay misses are undefined

- **Where:** DESIGN.md:594; PLAN.md:368 ("a run replayed through `CachingBackend` reproduces the original `Result`"); DESIGN.md:560–563 (`Cost` includes `jev_requests`, `jev_request_ids`, `jev_input_tokens`); DESIGN.md:444.
- **Finding:**
  - A cache hit issues no request. If `Cost` counts the hits as real calls, it lies about spend. If it does not, the replayed `Result` differs from the original, and the PLAN.md:368 criterion fails.
  - Caller-supplied non-LLM extractors, such as a remote NER service, have no replay wrapper, so "exact replay" is not exact for them.
  - A `ReplayLLM` miss (a key not recorded) has no defined behaviour.
  - The same LLM request can be recorded twice with different responses (two recordings into one directory).
  - The caller's model and sampling parameters are not part of the `LLM` request, so a recording made with one model silently replays for another.
  - The justification "probabilities stored as integer hundredths, so the key is reproducible" confuses stored values with keys: probabilities are not in the key.
  - RFC 8785 requires valid Unicode (I-JSON). A Python `str` with lone surrogates cannot be canonicalised, which gives an untyped exception.
- **Fix text (DESIGN §8.4):** "The cache stores the full `BackendResponse` (answers, `input_tokens`, `request_id`, `model`). On replay, `Cost` reproduces the recorded usage and adds `cache_hits`; the equality in PLAN Phase 3 excludes `cache_hits` and wall clock. `ReplayLLM` and a new `ReplayExtractor` (an `Extractor` wrapper, not a new protocol) raise `LLMError` / `ExtractorError(replay_miss)` on a miss, store one response per key (a second recording with a different response is an error), and include a caller-supplied `llm_id` in the key. Sources with lone surrogates are refused (`UsageError`)."

---

## Minor

### 22. [minor] Phase 3 live stability: "flip" and the selection run are undefined

- **Where:** PLAN.md:369.
- **Finding:** It is not stated whether a decision moving into the tie band (value → `Unresolved(tie)`) is a flip. It is also not stated in which run the "margin ≥ 0.20" is measured. Selecting on the compared runs biases the rate downward, and selecting on one run and comparing it against the next regresses.
- **Fix text:** "…margin ≥ 0.20 in a **separate selection run**; two further runs are compared; a flip is any change of committed value **or** a change between committed and `tie`; the fixture set is drawn from the Phase 0 corpus's schema-derived questions and checked in."

### 23. [minor] Source-screen wording

- **Where:** DESIGN.md:401; PLAN.md:461, :480.
- **Finding:**
  - "Class C decisions whose question reads the source" covers **every** class C decision, because state always contains the source. The phrase should say so.
  - "p ≥ 0.55 flags; the tie band flags too" is simply p ≥ 0.46.
  - The screen is itself a noul over hostile text, and an injection can target it. This is not stated (R2 #16).
  - "First decision level" means the screen runs *after* the extraction and drafting steps. So on a hostile source the caller's LLM has already read the injection and been paid. This is acceptable as a design choice, but should be stated.
  - The screen bar at :480 is stated in counts ("≤ 7 FP, ≥ 130 TP") but the sample sizes are minimums ("≥ 300", "≥ 150"). State the rates, or fix n at exactly 300 and 150.
- **Fix text:**
  - **DESIGN.md:401:** "…flags at p ≥ 0.46 (the bool threshold with the tie band counted as flagged). A flagged source turns every Jev- or LLM-decided field into `Unresolved(source_flagged)`; class A values and `known` values are unaffected. The screen runs after extraction and drafting steps, and is itself steerable; its measured rates are the only claim."
  - **PLAN.md:480:** "…on exactly 300 benign and 150 attacked…".

### 24. [minor] The adjudication request layout is unowned (R2 #5 residue)

- **Where:** DESIGN.md:486–491; PLAN.md:403–405.
- **Finding:** Nothing says whether the draft sits in state beside the source (keyed, R13) or is inlined into each criterion question. The **[P7]** 0/80 regression result applies only to the layout it used.
- **Fix text (DESIGN §6.3, Execution):** "Adjudication state is `{source: <text>, drafts: {<node id>: <draft>}}`; each criterion question references its draft by key — the layout of **[P7]**."

### 25. [minor] README, Agents, and Admin claims beyond DESIGN §6

- **README.md:3 and DESIGN.md:7.** "…with the source span and probability where Jev decided it" implies a span for Jev-decided enum values. **Fix:** "…with the source span or declared option, and the probability, where Jev decided it".
- **README.md:24.** This sentence remains unconditional. **Fix:** "…you get an explicit *absent* or *unresolved* entry rather than a guess — that is the design; how often it happens is measured, and a hostile source can defeat it."
- **README.md:35 and DESIGN.md:440.** "Parsed values … do not [carry a probability]" contradicts the worked example (DESIGN.md:220, `total`), where the span is Jev-selected and then parsed, so the value has the selection's probability. **Fix:** "constants, direct extractions, caller values, and ungated drafts do not; a parsed value carries the probability of the span selection it was parsed from." Also add a `decided_by` note: `jev` for a parsed selection.
- **Agents/CLAUDE.md:164.** "A value the source does not support comes back as *absent* or a typed `Unresolved`, **never a guess**" exceeds DESIGN §6. Abstention is measured (0.89 in long documents **[P5]**; 0/20 under injection **[P7]**), and schema-derived choices have no abstention at all (DESIGN.md:441). **Fix:** "…is built to come back as *absent* or a typed `Unresolved` rather than a guess (measured, not guaranteed; fields chosen from declared options have no abstention in v0)."
- **Admin/README.md:22.** An unchecked box says "account and key obtained", so the box state and the text disagree. **Fix:** "- [x] TypeSafe Jev early access — account and key obtained" plus a separate "- [ ] build the `DecisionModel` interface spike…".
- **Admin/README.md:42.** "Typed abstention when the source doesn't support an answer" is unconditional, and "values traceable to the source" covers only source-selected fields. **Fix:** "…source-selected values traceable to a verified span, measured abstention when no candidate is supported…".

### 26. [minor] Cross-reference and wording residues

- **PLAN.md:56.** "(DESIGN §2.1, §6.2)" is a bare `§`, which PLAN.md:5 says never appears. Change it to "(DESIGN §2.1, DESIGN §6.2)".
- **DESIGN.md:606.** "DESIGN §5.1 and §5.4" is harmless in DESIGN, but make it consistent: "DESIGN §5.1 and DESIGN §5.4".
- **DESIGN.md:86.** This line cites DESIGN §8.2 for checking against `usage.input_tokens`, but §8.2 never mentions `usage.input_tokens`. Add to §8.2: "estimates are compared with `usage.input_tokens` on every response and the ratio recorded".
- **DESIGN.md:581.** "The compiler's run-time check" should be "the executor's run-time check" (finding 15).
- **DESIGN.md:253.** "An unbounded `string`, `number`, `date` …": `date` is not a JSON type, and `money` and `phone` are not JSON Schema `format` values. Say: "…or a string whose `format` is `date`, `email`, or `uri`, or which declares `x-jevson.source.extractor` of a built-in pattern (money, phone)".
- **PLAN.md:361.** In Phase 3, source and generate declarations still refuse at compile time, so "a declaration whose maxima exceed the per-question limit" can only be a large enum with long descriptions, or a hand-built graph. Say which.
- **PLAN.md:470.** "Coverage and false abstention" names two metrics, but Phase 0 has three probes (1 accuracy, 2 abstention, 3 false abstention). Name all three, mirroring probes 1–3, and do the same in the abandon criterion at :488.
- **PLAN.md:50–53.** There is no `RefusalReason` type, but PLAN.md:318 requires "a distinct named reason" for each refusal and `not_yet_supported` is one. Add `RefusalReason` (closed set) to `types.py`, carried by `CompileError`.
- **PLAN.md:300–321.** Flat `allOf` merging (DESIGN.md:237) has no exit criterion. Add: "a flat `allOf` of two object schemas merges; an `allOf` with a non-object member or conflicting property types refuses".
- **DESIGN.md:465.** The meaning of `dependency_unresolved` "…including an unselected-branch failure" is unclear, because unselected branches never execute. Say "including every node under an unresolved union discriminator".
- **Array holes.** DESIGN §6.1 and §5.7 never say which pointer an unresolved array component or tied membership uses: element indices are not stable. State: "array holes use the array pointer, with the component's spans in `detail`".
