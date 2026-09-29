# E4: Logic review, round 4 (Jevson Revision 6)

**Targets:**

- `Jevson/DESIGN.md` (766 lines), `PLAN.md` (898), `README.md` (49), and `docs/REDTEAM.md` (119).
- `Agents/CLAUDE.md`: the Jev and Jevson blocks at :146–167.
- `Admin/README.md`: :22, :42, and :67.

Line numbers refer to the working tree. No design documents were edited.

**Severity** follows the brief:

- **Blocker:** a phase cannot be built, or an exit criterion cannot pass as written.
- **Major:** a contradiction or unowned behaviour that two competent implementers would resolve differently, in a way that matters.
- **Minor:** wording, a cross-link, or a nit.

The phase order is the owner's decision, and this review records risk only.

**Result: 0 blockers, 10 majors, 16 minors. CONVERGED: no.**

---

## 0. Round-3 verification (results/r3/E3_logic.md)

**Verified fixed.** Each item gives where the fix now lives, and any residue.

- **#1** Outcome 2 is now "incomplete **or** invalid". `Result.violations` has been added (DESIGN.md:462, :568). Candidates are pre-filtered on string constraints (:335). The Phase 1 exit asserts `complete ∧ ¬satisfies` (PLAN.md:276). Residue: m11.
- **#2** `compile_schema(schema, extractors={names}, default_extractor=None)` (DESIGN.md:257, PLAN.md:310). A `Decimal` field that declares `source` now refuses only with `not_yet_supported`. Residue: m10.
- **#3** The async design is replaced: one library loop thread, a client per loop, and a `threading.Lock` limiter (DESIGN.md:533, :545). The Phase 3 async exit is at PLAN.md:372. Residue: m8 and major 10.
- **#4** `no_candidates` exists, and zero candidates follow the DESIGN §5.6 table (DESIGN.md:353, :381). Residue: m4.
- **#5** `unparseable` has been added. The bisection maps an overflow to `budget_exceeded` (DESIGN.md:475, :590). Decimals use the string form (:237). Residue: m2.
- **#6** One tie margin of ≤ 0.10 now applies everywhere, with the same band for bools, choices, scores, and criteria (DESIGN.md:290–292, :484). Residue: major 6.
- **#7 (part)** The rule for the vendor `choice` field against the argmax is defined (DESIGN.md:71). The tolerance itself is unchanged (m12).
- **#9 (part)** `decisions` is keyed with an attempt (DESIGN.md:164, :563). Residue: m7.
- **#10 (part)** `known=` now has validation, a `PreflightError`, and `decided_by: caller` with no provenance (DESIGN.md:547). The Phase 3 exit is at PLAN.md:373. Residue: m15.
- **#11** `max_candidate_chars` defaults to 120 and `max_candidates` to 50 (DESIGN.md:247–248, :592). Residue: major 4.
- **#12 (part)** `PreflightError` now covers multiple sources and invalid `known=` values (DESIGN.md:465). Residue: m8.
- **#14 (part)** `JevsonConfig` exists (DESIGN.md:258). Residue: m6.
- **#15** The cap is stated to apply to candidates (DESIGN.md:594). Residue: m15.
- **#16** Enum arrays have a rule (DESIGN.md:295) and a Phase 7 exit (PLAN.md:578). The fallback product is stated identically in all four places (PLAN.md:27, :232, :500, :878). Residue: m9.
- **#17** Redrafts are labelled blind to Jev's verdict (PLAN.md:435). Residue: m14.
- **#18** The second pass is the unmodified extractor (PLAN.md:489).
- **#19 (part)** τ is chosen before labelling, and "not decidable" is defined (DESIGN.md:487–488). Residue: m14.
- **#20 (part)** The experiment is sized, and its question count is bounded by existing evidence (PLAN.md:570, :583). Residue: m14.
- **#21 (mostly)** `cache_hits` exists, a miss raises `BackendError(replay_miss)`, the extractor-determinism rule is stated, and a request that cannot be canonicalised is not cached (DESIGN.md:607). Residue: m13.
- **#23 (part)** The screen being steerable is stated. It flags at p ≥ 0.56 only (DESIGN.md:410–411).
- **#24** The adjudication layout is now `{"source", "draft"}` (DESIGN.md:328). This produces a new issue: major 7.
- **#25 (part)** Agents/CLAUDE.md:164 is fixed, and README.md:24 is now scoped. Residue: m16.
- **#26 (part)**
  - Fixed: the bare `§` in PLAN, the flat-`allOf` exit (PLAN.md:318), and the meaning of `dependency_unresolved`.
  - Not fixed: "compiler's run-time check", the missing `usage.input_tokens` in §8.2, the date/money/phone `format` wording, and `RefusalReason` (m15). The array-hole pointer has become major 1.

**Not fixed:**

- **#8(b)**: are components built over members or over all candidates? See major 9.
- **#13(a)**: a defaulted field with no declaration. See major 8.
- **#22**: the live-stability selection run and the definition of a flip. See m14.

**Cross-reference audit.**

- Every `DESIGN §n` in DESIGN, PLAN and README resolves: 2.1, 2.3, 3.2, 3.3, 3.5, 4, 4.2, 5.1–5.9, 6, 6.1–6.3, 7, 8, 8.1–8.4, 9, 9.1, 10, 12, 13.
- Every `PLAN §n` resolves: 1, 3, 4, 4.1, 4.2, 5, 6, 7, 8, 9.
- The rule numbers PLAN uses (R1, R3–R9, R11, R13–R16) exist in DESIGN §7. The content of R6 is stale (m1).

**Checked and consistent:**

- **Tie band.** The tie margin is stated identically in DESIGN §4.2, §5.5, §6.2 and §11, and in PLAN Phase 0 probe 1 and the Phase 1, 3 and 7 exits. For a noul, 0.45–0.55 inclusive is a tie; for other kinds, a top-two margin ≤ 0.10. Screen and pair exemptions are consistent.
- **Unresolved reasons.** The closed set covers every producer except the gaps noted under majors 5 and 1.
- **`cache_hits` and `violations`** are consistent across DESIGN §8.1 and PLAN.
- **The fallback product** is identical everywhere it is stated.

---

## Blockers

None. Every exit criterion can be met under at least one reasonable reading. The majors below are where readings diverge.

---

## Major

### 1. [major] An array with an unresolved component: "key omitted" contradicts "other components are emitted"

- **Where:**
  - DESIGN.md:474 ("At an unresolved pointer the key is **omitted** from `.value`")
  - DESIGN.md:395 ("Other components are emitted, and an array with any unresolved component is incomplete")
  - PLAN.md:576 ("that component is `Unresolved(entity_conflict)` … other components are emitted")
  - PLAN.md:578 (enum arrays: "ties unresolved")
  - DESIGN.md:295
- **Finding:** `Unresolved` must carry a pointer.
  - **If the pointer is the array** (`/line_items`), DESIGN §6.1 omits the whole array, which contradicts §5.7 and the Phase 7 exit.
  - **If it is an element index**, indices are not stable: the unresolved component has no slot, and later elements shift.
  - **A tied label in a multi-label enum array** has the same problem: one tied label either blanks a 20-label array or is dropped silently.
  - **The two readings give callers different shapes**: a partial array plus a hole, or no array at all. A partial array can also pass `minItems` while the result is incomplete.
- **Fix text:**
  - **DESIGN §6.1, replacing :474:** "At an unresolved **field** pointer the key is omitted from `.value`. An **array** with unresolved components is emitted with its resolved elements (in source or declared order), and each unresolved component is one `Unresolved` whose pointer is the **array pointer**, with the component's spans (or the tied enum value) in `detail`. An unresolved union names its whole subtree; an unresolved root yields `{}`."
  - **DESIGN §4.2, enum-array row, append:** "a tied value yields `Unresolved(tie)` at the array pointer, naming the value; the other values are emitted."

### 2. [major] Absence inside an optional nested object is unowned

- **Where:** DESIGN.md:373–385 (the DESIGN §5.6 table is per field); DESIGN.md:474; PLAN.md:275, :487.
- **Finding:** Take `shipping_address: Optional[Address] = None`, where `Address.street` is required.
  - On an invoice with no shipping address, every leaf of `Address` abstains.
  - Read per leaf, DESIGN §5.6 makes `/shipping_address/street` "required and not nullable" → `Unresolved(abstained)` → `complete is False`, and the result is invalid.
  - The intended result is almost certainly that `shipping_address` is *absent*: key omitted, default `None` applies, `complete is True`.
  - Nothing says absence propagates upward. Optional sub-objects are among the most common shapes in extraction schemas, so the two readings differ on most real documents.
- **Fix text (DESIGN §5.6, after the table):**

  > **Objects.** An object node is abstained when every source-decided descendant abstained or had no candidates, and no descendant committed a value. An abstained object then follows the table itself (omitted, `null`, or `Unresolved(abstained)`), recorded once at the object pointer. If any descendant committed, each required descendant that abstained is `Unresolved(abstained)` as usual.

  Add a Phase 5 exit: "an optional nested object whose fields are all missing from the source is omitted and listed once in `absent`; with one field present, the missing required fields are `Unresolved(abstained)`."

### 3. [major] The string-constraint pre-filter rejects every valid candidate for parsed (class F) fields

- **Where:**
  - DESIGN.md:335 (candidates that fail "the field's own string constraints (`maxLength`, `minLength`, `pattern`)" are rejected before the question)
  - DESIGN.md:237 (Pydantic `Decimal` is `anyOf [number, string with pattern]`)
  - DESIGN.md:213, :221 (the worked example's `total` is a money span, then parsed)
  - PLAN.md:470
- **Finding:**
  - The span `"$1,204.50"` fails the Decimal string-branch pattern, so the worked example's `total` gets zero candidates and becomes `Unresolved(no_candidates)`.
  - The same happens to a date-typed string field with a `pattern` or `maxLength`, fed by date spans such as "3 March 2026".
  - One implementer applies the filter to the span; another applies it to the parsed value, or skips `anyOf` fields.
- **Fix text (DESIGN.md:335):**

  > The pre-filter applies only to fields whose value is the verbatim span. For class F fields, constraints are checked on the parsed value after selection; a parsed value that violates them is reported in `violations`, like any other constraint failure.

### 4. [major] Do repeated occurrences count toward `max_candidates` and the 255-option limit?

- **Where:**
  - DESIGN.md:317 (every occurrence is its own option)
  - DESIGN.md:335, :647 (`max_candidates` ≤ 254)
  - DESIGN.md:590, :592 (preflight: "`max_candidates` × `max_candidate_chars` … plus context windows for repeated text"; ~2.5k tokens)
  - PLAN.md:470
- **Finding:** A party name in a long contract can appear 100+ times, and the ceiling allows ~108k characters of source.
  - **If `max_candidates` counts distinct texts**, the choice can exceed 255 options. That is an HTTP 400 that is not `max_tokens_exceeded` (DESIGN.md:81). Under DESIGN.md:476 it is not retried, so the result is `BackendError` or an unspecified outcome for an ordinary document. Preflight also under-budgets by the repeat factor.
  - **If it counts occurrences**, the field returns `Unresolved(too_many_candidates)` instead.
  - This was R3 #11 bullet 3, and it is still unstated.
- **Fix text (DESIGN §5.3):**

  > `max_candidates` counts **options**, after occurrence expansion. When expansion exceeds it, the field is `Unresolved(too_many_candidates)`, with the distinct texts and occurrence counts in `detail`.

  Add to §8.2: "preflight budgets `max_candidates` options at `max_candidate_chars` + 80 context characters each".

### 5. [major] `direct_extraction: true` with two or more candidates is unowned

- **Where:** DESIGN.md:333 ("it commits without Jev, carries no probability"); PLAN.md:486 (tested only with a single candidate); DESIGN.md:475 (the closed reason set).
- **Finding:** The rule is written for a lone candidate, but the extractor may return several. There are three readings:
  - commit the first one: the silent wrong-but-valid failure Jevson exists to prevent;
  - ask Jev anyway: this contradicts "zero backend calls";
  - leave the field unresolved: no reason in the closed set fits.
- **Fix text (DESIGN §5.3):**

  > With `direct_extraction: true`, a lone verified candidate commits without Jev. Zero candidates follow DESIGN §5.6. Two or more distinct candidates are asked as an ordinary choice with `none_of_these`; the field is then not listed in `ungated`.

  Add a Phase 5 exit for the two-candidate case. (Alternative: a new reason `ambiguous_direct`, added to the closed set.)

### 6. [major] A criterion or rubric tie: `Unresolved(tie)` (DESIGN) or a failed criterion that triggers a redraft (PLAN)?

- **Where:**
  - DESIGN.md:484 (the tie margin "yields `Unresolved(tie)`" and applies to "criteria")
  - PLAN.md:416 ("the tie margin yields a tie, counted as a failed criterion for redraft")
  - DESIGN.md:498–499 (exhaustion → `redraft_exhausted`)
  - DESIGN.md:498 (rubric: "most probable level ≥ minimum"; a rubric tie straddling the minimum is not addressed)
- **Finding:** When a criterion lands at p = 0.52:
  - under DESIGN, the field is `Unresolved(tie)` at once, with no redraft;
  - under PLAN, the draft is redrafted and ends as `redraft_exhausted` or an admitted draft.
  - Reason codes are API, and the redraft is paid.
  - With `redraft_budget` = 0 (a possible Phase 4 outcome), the two readings still give different reasons.
- **Fix text (DESIGN §6.3, Execution):**

  > A criterion inside the tie margin, or a rubric whose top two levels are within it and straddle the minimum, counts as **failed** for that draft. It is named in `rejections` and triggers a redraft. Exhaustion is `redraft_exhausted`, never `tie`.

  In DESIGN §6.2, change "admits a draft: … criteria" to "…criteria (where a tie counts as a failed criterion, DESIGN §6.3)".

### 7. [major] The adjudication state layout conflicts with one call per level (R3) when a level holds two drafts

- **Where:**
  - DESIGN.md:328 (state is `{"source": …, "draft": …}`, the **[P7]** layout)
  - DESIGN.md:511 (R3: one keyed call per level)
  - DESIGN.md:223 (candidates placed "in state" keyed by id)
  - PLAN.md:416, :425 (one call per *field*)
  - PLAN.md:365
- **Finding:** A schema with `summary` and `description`, both `generate` fields, produces two drafts whose criteria sit in the same level. A single `draft` key can hold one draft only. The implementations diverge:
  - one request per draft, which breaks R3 and re-bills the source;
  - `{"source", "drafts": {id: …}}`, a layout **[P7]** did not measure;
  - separately, whether candidate choices in the same level share that state, and whether candidates sit in state (DESIGN.md:223) or in option descriptions (DESIGN.md:315).
- **Fix text (DESIGN §5.2 and R3):**

  > A level's state is `{"source": <text>}` plus, when present, `"drafts": {<field node id>: <draft>}` and `"candidates": {<id>: …}` keyed by opaque id. Each criterion question names its draft by key. **[P7]** measured one draft under a single `draft` key; the keyed multi-draft layout is re-measured in the Phase 4 injection regression before it is used.

  Alternatively, make R3 say: "one call per level, **except** that adjudication issues one call per draft."

### 8. [major] A defaulted field with no `x-jevson` declaration: class A constant, class G refusal, or a Jev decision? (R3 #13a, still open)

- **Where:**
  - DESIGN.md:270 (class A lists "defaults")
  - DESIGN.md:256 (an unbounded string with no `source`/`generate` refuses, class G)
  - DESIGN.md:379 (only the *abstention* case is defined)
  - PLAN.md:316 ("a defaulted field compiles without refusal")
- **Finding:**
  - `currency: str = "USD"` either refuses (per :256) or emits `"USD"` (per :270).
  - `tier: Tier = Tier.basic` is either Jev-decided (Jev can never abstain, so the default is never used) or emitted as a constant.
  - The Phase 2 exit passes or fails depending on which field the test picks.
- **Fix text (DESIGN §3.5, bullets):**

  > A field with a `default` and no `x-jevson` declaration is **class A**: it is omitted from `.value` so the default applies (`decided_by: code`); it is not decided and does not refuse. To have it decided, declare `source` or `generate`, or add `x-jevson.question` to an enum or bool field.

  Pin the Phase 2 exit to `str = "USD"` and `Tier = Tier.basic`.

### 9. [major] Entity components over accepted members or over all candidates? (R3 #8b, still open)

- **Where:**
  - DESIGN.md:204 (pairs are asked over all candidates)
  - DESIGN.md:392 ("Pairwise `noul` over the remaining candidates"; components over pairs with p > 0.5)
  - PLAN.md:569 ("membership → pre-merge → pairwise → components")
- **Finding:**
  - **Built over all candidates:** a rejected non-member X with p(same) > 0.5 to members A and B joins A and B into one element. That is a wrong merge caused by a string the membership step already rejected.
  - **Cross-component variant:** a non-member's uncertain pair blanks members.
  - **Built over members only:** neither happens.
  - The Phase 7 exits use fixtures where every candidate is a member, so they do not settle it.
- **Fix text (DESIGN §5.7, step 2):**

  > Components are built over **accepted members only** (membership is decided in the same level). Pair answers involving non-members are recorded in `decisions` and ignored by steps 3–4.

  Add a Phase 7 exit: "a rejected candidate linked at 0.9 to two members does not merge them."

### 10. [major] There is no timeout for caller-supplied steps; a looping or blocking extractor or LLM hangs every synchronous caller

- **Where:**
  - PLAN.md:118 (`hostile_extractor.py`: "raising, **looping**, and lying extractors")
  - PLAN.md:495 (the central property must hold with hostile extractors)
  - DESIGN.md:459 (for any behaviour whatsoever, the call **returns**)
  - DESIGN.md:533 (all synchronous calls share **one** library loop; caller objects run on it)
  - DESIGN.md:476 (timeouts are defined for transport only)
- **Finding:**
  - An extractor or LLM that never returns makes the call return nothing. That is a fourth outcome, and the Phase 5 exit cannot pass without an unspecified timeout.
  - Worse, because every `resolve()` in the process shares one loop, an `async def extract` that does blocking CPU or I/O work, such as a synchronous NER model or `requests`, stalls **every** thread's `resolve()`. `asyncio.wait_for` cannot pre-empt it.
  - One implementer adds step timeouts plus thread offload; another does neither, and the hostile test hangs.
- **Fix text (DESIGN §8, after the loop paragraph):**

  > Every step call is bounded by `JevsonConfig.step_timeout_s` (default 120). Expiry raises `ExtractorError(timeout)` / `LLMError(timeout)` carrying the partial `Result`. Protocol implementations must not block the event loop; blocking work belongs in `asyncio.to_thread`. Jevson's own pattern extractors and its LLM extractor comply. A blocking caller implementation stalls every synchronous caller in the process, and this is documented.

  In PLAN.md:118, define "looping" as a cooperative infinite await, and add it to the Phase 5 exit (→ `ExtractorError(timeout)`).

---

## Minor

### m1. R6 and DESIGN §1 still mandate the two-directional rule

- DESIGN.md:514 (R6: "emitting only components whose evidence is consistent in both directions") and DESIGN.md:40 ("refuses to merge **or split**") contradict DESIGN §5.7, where the cross-component rule is a Phase 0 variant.
- PLAN.md:98 says "two-directional component rule (R6)".
- **Fix, R6:** "…emitting only components that pass the internal-consistency rule, plus the cross-component rule if Phase 0 chose it (DESIGN §5.7)."
- **Fix, PLAN.md:98:** "internal rule plus the Phase 0 variant (R6)."
- **Fix, DESIGN.md:40:** "refuses to merge on contradictory evidence".

### m2. Decimal is still shown as a number in three places

- DESIGN.md:221 ("`Decimal`, normalised to a number"), DESIGN.md:433 (`"$1,204.50"` → `1204.5`), and PLAN.md:493 ("yields the right number") contradict DESIGN.md:237 (string form).
- **Fix:**
  - "normalised to a decimal value emitted as a string";
  - `"$1,204.50"` → `"1204.50"`;
  - "yields the right decimal string (a number for `type: number` fields)".
- Also state the canonical form: "the digits of the span, without grouping separators, and without rounding".

### m3. The probability of parsed values contradicts the worked example; README and DESIGN now differ

- DESIGN.md:450 says "parsed values … do not" carry a probability.
- The worked example's `total` (DESIGN.md:221) is Jev-selected and then parsed.
- README.md:35 dropped "parsed values", so it now disagrees with DESIGN.
- **Fix, DESIGN.md:450:** "constants, direct extractions, caller-supplied values, and ungated drafts do not; a value parsed from a Jev-selected span carries that selection's probability (`decided_by: jev`)."

### m4. Two Phase 5 absence exits are unconditional, while DESIGN §5.6 is conditional

- PLAN.md:485: "zero candidates yield an `absent` entry"; a required field gives `no_candidates`.
- PLAN.md:487: "a nullable field that abstains is `null`"; `Optional[T] = None` is omitted.
- **Fix, :485:** "zero candidates follow the DESIGN §5.6 table with no backend call (an optional field → `absent`; a required field → `Unresolved(no_candidates)`)".
- **Fix, :487:** "a **required** nullable field that abstains is `null`…; a not-required one is omitted…".

### m5. PLAN §4.1 paraphrases the Revision 5 central property

- PLAN.md:734 says "an incomplete `Result` with every hole named". Complete-but-invalid and `violations` are missing.
- **Fix:** "…a `Result` that is incomplete or invalid, with every hole in `unresolved` and every failed constraint in `violations`; or a typed exception…".

### m6. Configuration homes contradict each other

- `retry_budget` is "a documented per-call parameter" (DESIGN.md:371, PLAN.md:472) but lives in `JevsonConfig` (DESIGN.md:258), while `resolve(source, known=None)` (DESIGN.md:545) takes no budget.
- `raise_on_violation` (DESIGN.md:466), `default_extractor` (PLAN.md:463 writes `Jevson(default_extractor=...)`), and the `CostSink` (DESIGN.md:581) have no home in the API shape.
- `Result.versions` (DESIGN.md:578) omits the result-affecting settings.
- **Fix, DESIGN.md:545:** "`Jevson(backend, llm=None, extractors={}, config=JevsonConfig(), cost_sink=None)`; `JevsonConfig` also holds `default_extractor` and `raise_on_violation`; `resolve(source, *, known=None, retry_budget=None, redraft_budget=None)` overrides the config per call. `Result.versions` records the tie margin, `conflict_floor`, the entity rule variant, and the pairwise cap."

### m7. The `decisions` key format is inconsistent, and no test covers attempts

- DESIGN.md:164 writes `id#attempt-n`, while DESIGN.md:563 writes `node_id#attempt`. Node ids already contain `#` (`/customer/tier#choice`).
- **Fix, DESIGN.md:563:** "keyed `f"{node_id}@{n}"`, n = 0 for the first ask, incremented per retry or redraft".
- **Add a Phase 5 exit:** "a field retried once leaves `…@0` and `…@1`".
- **Add a Phase 4 exit:** the same for one redraft.

### m8. The async lifecycle and error types are unowned

- Nothing says who closes the per-loop `AsyncClient`s: there is no `Jevson.close()`, no `JevBackend.aclose()`, and no context manager.
  - Clients for dead caller loops leak unless they are held weakly, and they cannot be `aclose()`d once their loop has closed.
- Behaviour after `os.fork()` is undefined: the child inherits a loop whose thread is gone, so `resolve()` hangs.
- The `CostSink` is called on the library thread.
- A caller's `AsyncOpenAI` used under both `resolve()` and `aresolve()` breaks across loops. It surfaces as `LLMError`, which is typed but surprising.
- The exception raised by "`resolve()` inside a running loop" is unnamed (DESIGN.md:533, PLAN.md:372).
- **Fix, DESIGN §8:**

  > `Jevson` and `JevBackend` are context managers; `close()` / `aclose()` close the client for the current loop; per-loop clients are held in a `WeakKeyDictionary` keyed by loop. The library loop is re-created after `fork` (`os.register_at_fork`). `CostSink.record` may be called from any thread. A caller object used from `resolve()` must not also be used on another loop. `resolve()` inside a running loop raises `UsageError` (a new, pre-spend member of the hierarchy in DESIGN §6.1).

### m9. Arrays before Phase 7

- **Phase 2.** The refusal list (PLAN.md:324–325) does not refuse arrays. Yet PLAN.md:315 requires "every class C construct" in the v0 list to compile, and enum arrays are class C. Phases 1 and 3 list arrays as out of scope.
- **Phase 1.** PLAN.md:276 uses `minItems` although arrays are out of scope for Phase 1 (PLAN.md:288).
- **Phase 7.** PLAN.md:585, "an array with no source grounding refuses", literally refuses enum arrays.
- **Fix:**
  - **PLAN.md:325:** "…and arrays refuse with `not_yet_supported` (lifted in Phase 7)".
  - **PLAN.md:276:** use `maximum` or `maxLength`.
  - **PLAN.md:585:** "an array of unbounded items with no `source` refuses".

### m10. PLAN.md:316: does "declaring a source" modify both Decimals?

- An undeclared `Optional[Decimal]` refuses under class G (unbounded number), not with `not_yet_supported`.
- **Fix:** "an `Optional[Decimal]` and a `Decimal` field, **each declaring a source**, normalise… and then refuse only with `not_yet_supported`."

### m11. `SchemaViolation` is named for violations but fires only on unresolved required fields

- DESIGN.md:466 and :473 are internally consistent, but a caller with `raise_on_violation=True` receives outcome 2 for a `maxLength` failure.
- **Fix:** rename the flag `raise_on_unresolved_required`, or widen it to "`.satisfies_schema is False`". State which.

### m12. The sum tolerance ⌈K/2⌉ is vacuous at large K (R3 #7, carried)

- At K = 255, a distribution summing to 0.30 is accepted and its argmax committed (DESIGN.md:71). It is unchanged and not contradictory.
- **Fix:** tolerance = min(⌈K/2⌉, 5) hundredths, citing **[L17]** (at most 1 hundredth observed).

### m13. Replay details

- PLAN.md:379 says the replay "reproduces the original `Result` with every call counted as a cache hit". Strict equality is impossible because `Cost` differs.
  - **Fix:** "…equal to the original excluding `Cost` and wall clock".
- A `ReplayLLM` miss has no exception; DESIGN.md:607 covers only `BackendError(replay_miss)`.
  - **Fix:** `LLMError(replay_miss)`.
- The caller's model id is not part of the `ReplayLLM` key.
  - **Fix:** add `llm_id`.
- "Replay-only mode" has no switch.
  - **Fix:** name the flag.

### m14. Statistical residues

- **Phase 3 live stability (PLAN.md:380).** The selection run is not separate, and a flip is not defined; R3 #22 is still open.
  - **Fix:** "…margin ≥ 0.20 in a separate selection run; two further runs compared; a flip is any change of committed value or between value and `tie`."
- **DESIGN.md:487.** "τ ∈ {0.80, 0.90} is fixed before … and both values are reported" leaves open whether the bar needs one τ or both.
  - **Fix:** "the bar uses τ = 0.90; τ = 0.80 is reported only".
- **PLAN.md:582.** The cap measurement has no n per cap.
  - **Fix:** "≥ 20 real arrays per n".
- **PLAN.md:435.** The 2-point comparison at n ≈ 100 has a standard error of ~2 points.
  - **Fix:** report the paired difference with its 95% interval beside the point estimate.
- **PLAN.md:199–200.** Probes 2 and 3 do not say how ties count.
  - **Fix:** "a tie counts as not abstaining (probe 2) and as not a false abstention (probe 3); tie rates reported."

### m15. Residues and wording

- **DESIGN.md:594**, "the compiler's run-time check" → "the executor's".
- **DESIGN.md:86** cites DESIGN §8.2 for `usage.input_tokens`, but §8.2 never mentions it.
  - **Fix, §8.2:** add "estimates are compared with `usage.input_tokens` on every response".
- **DESIGN.md:256.** `date` is not a JSON type, and `money` and `phone` are not `format` values.
- **PLAN.md:369 vs :120 and :375.** A "malformed body" is `Unresolved(invalid_backend_answer)` in one place and "malformed HTTP" is `BackendError` in another.
  - **Fix:** "a well-formed HTTP 200 whose JSON is malformed or mis-typed → `invalid_backend_answer` for the affected questions; unparseable HTTP → `BackendError`."
- **`known=` interactions are unstated:** a pointer inside a union branch, a discriminator, or an array element (DESIGN.md:547).
  - **Fix:** "`known` pointers name fields outside arrays; a pointer inside a union branch is valid only if that branch is selected, and a known discriminator value selects its branch without a decision."
- **The screen's own `invalid_backend_answer`** is unowned.
  - **Fix:** "an invalid screen answer counts as flagged".
- **`RefusalReason`** is not in PLAN.md:49–51.
- **REDTEAM.md:40–41** lists P22 before P21.
- **DESIGN.md:121** uses a bare `§3.5` inside the diagram.

### m16. README, Agents, and Admin claims beyond DESIGN §6

- **README.md:3 and DESIGN.md:7.** "with the source span and probability where Jev decided it" implies a span for Jev-decided enums.
  - **Fix:** "with the source span or declared option, and the probability, where Jev decided it".
- **README.md:21.** "admitted only after Jev checks them against criteria you declare" is false for fields with no criteria, which DESIGN.md:501 admits ungated.
  - **Fix:** "…admitted only after Jev checks them against the criteria you declare (a field with none is admitted and flagged `ungated`)".
- **Admin/README.md:22.** It is still an unchecked box that says the key was obtained.
  - **Fix:** "- [x] TypeSafe Jev early access — account and key obtained", plus a separate "- [ ] build the `DecisionModel` interface spike…".
- **Admin/README.md:42.** "values traceable to the source, typed abstention when the source doesn't support an answer" is unconditional.
  - **Fix:** "source-selected values traceable to a verified span, measured (not guaranteed) abstention when no candidate is supported".
- **Agents/CLAUDE.md:157–167** is consistent with DESIGN §6. No change is needed.

---

## Summary

- **Blockers:** none.
- **Majors: 10.**
  - Array holes vs key omission (1).
  - Absence propagation for optional sub-objects (2).
  - The pre-filter on parsed fields (3).
  - Occurrence counting vs the 255-option limit (4).
  - `direct_extraction` with several candidates (5).
  - Criterion ties, DESIGN vs PLAN (6).
  - The multi-draft state layout vs R3 (7).
  - Undeclared defaults (8, carried).
  - Members vs candidates for components (9, carried).
  - No step timeout on the shared loop (10).
- **Every major has a one-paragraph fix text.** None needs new evidence except the keyed multi-draft layout in major 7, which the Phase 4 injection regression can measure.
- **Minors: 16.**

**CONVERGED: no.**
