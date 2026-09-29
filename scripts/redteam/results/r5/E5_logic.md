# E5: Logic review, round 5 (Jevson Revision 7)

**Targets:**

- `Jevson/DESIGN.md` (798 lines), `PLAN.md` (910), `README.md` (49), and `docs/REDTEAM.md` (120).
- `Agents/CLAUDE.md`: the Jev and Jevson blocks at :146–167.
- `Admin/README.md`: :22, :43, and :68.

Line numbers refer to the working tree. No design documents were edited.

**Severity** follows the brief:

- **Blocker:** a phase cannot be built, or an exit criterion cannot pass as written.
- **Major:** a contradiction or unowned behaviour that two competent implementers would resolve differently, in a way that changes observable results or safety.
- **Minor:** wording, a cross-link, or an edge case with one obvious resolution.

**Local checks run this round:**

- `scripts/redteam/check_r5_weakkey_clients.py` (httpx 0.28.1, Python 3.11).
- A Pydantic 2.12.5 schema dump of `Optional[Address] = None`, `list[Literal] = []`, and `Field(default_factory=list)`.

**Result: 0 blockers, 2 majors, 12 minors. CONVERGED: no.**

Both majors are narrow and share one root cause: the Revision 7 rules for defaulted fields and for object absence were written for leaves. Each has a short fix.

---

## 0. Round-4 verification (results/r4/E4_logic.md)

**Majors 1–10: all fixed.**

- **1. Array holes.** Fixed at DESIGN.md:478 and :296, with an exit at PLAN.md:595.
- **2. Object absence.** Fixed at DESIGN.md:386, with an exit at PLAN.md:491. See new major 1 and major 2, which are residues of this fix.
- **3. Pre-filter.** Fixed at DESIGN.md:336, with an exit at PLAN.md:489. The residue in the PLAN.md:473 deliverable is m10.
- **4. Occurrence counting.** Fixed at DESIGN.md:318 and :602, with an exit at PLAN.md:488.
- **5. Direct extraction with several candidates.** Fixed at DESIGN.md:334, with an exit at PLAN.md:490. A residue is m9.
- **6. Criterion ties.** Fixed at DESIGN.md:503 and :489, and in PLAN.md:418 and :434. The glossary residue is m10.
- **7. Level state.** Fixed at DESIGN.md:329, with an exit at PLAN.md:433. Residues are m4 and m5.
- **8. Defaulted fields.** Fixed at DESIGN.md:256 and PLAN.md:316, but the fix over-reaches to objects and arrays. See **new major 1**.
- **9. Members-only components.** Fixed at DESIGN.md:395, with an exit at PLAN.md:594. A residue is m7.
- **10. Step timeouts.** Fixed at DESIGN.md:542 and in PLAN.md:118, :370, and :493.

**Minors m1–m16: fixed, except the residues noted.**

- **m1.** R6 (:519), DESIGN.md:40, and PLAN.md:98 are fixed.
- **m2.** DESIGN.md:221 and :436, and PLAN.md:501, are fixed.
- **m3.** DESIGN.md:453 is fixed.
- **m4.** PLAN.md:488 and :495 are fixed.
- **m5.** PLAN.md:744 is fixed.
- **m6.** Fixed at DESIGN.md:259 and :554. Residue: PLAN.md:466 still writes `Jevson(default_extractor=...)` (m10).
- **m7.** Fixed at DESIGN.md:164 and :572, and PLAN.md:434 and :492.
- **m8.** Fixed at DESIGN.md:538–542 and :469. The new text has buildability residues: m1, m2, and m3.
- **m9.** PLAN.md:276, :335, and :593 are fixed. Residue: PLAN.md:315 (m10).
- **m10.** PLAN.md:316 is fixed.
- **m11.** Fixed: the flag is renamed `raise_on_unresolved_required`.
- **m12.** DESIGN.md:71 is fixed.
- **m13.** Fixed at DESIGN.md:619 and PLAN.md:381.
- **m14.** Fixed at PLAN.md:382, :199–200, :497, and :590, and DESIGN.md:492. Residue: the redraft bar at PLAN.md:438 still lacks the paired interval (m10).
- **m15.** All fixed: the executor wording (:606), `usage.input_tokens` in DESIGN §8.2 (:602), the format wording (:257), the malformed-body split (:480 and PLAN.md:369), `known=` (:556), the screen's invalid answers (:480), `RefusalReason` (PLAN.md:53), the REDTEAM order, and the diagram `§` (:121).
- **m16.** README.md:3 and :21 and Admin/README.md:22 and :43 are fixed. A related claim in README.md:20 and Agents/CLAUDE.md is m12.

**Cross-checks that hold:**

- The tie band is stated consistently across DESIGN §4.2, §5.5, §6.2, §6.3, and §11 (apart from the glossary nit in m10) and in the PLAN exits.
- The P22 arithmetic holds: 2 + 38 + 16 = 56 and 490 + 872 + 792 = 2,154.
- The context-window budget agrees: ±40 characters in DESIGN §5.1, 80 characters in DESIGN §8.2, and +2,521 tokens in P22.
- The `UsageError` set is complete: DESIGN.md:469, PLAN.md:54, and PLAN.md:371.

---

## Blockers

None.

---

## Major

### 1. [major] The class A rule for undeclared defaulted fields swallows optional nested objects and defaulted arrays, contradicting DESIGN §5.6 "Objects", DESIGN §4.2 enum arrays, and three PLAN exits

**Where:**

- DESIGN.md:256: "A field with a `default` and no `x-jevson` declaration is **class A**: it is omitted…; it is neither decided nor refused."
- It conflicts with:
  - DESIGN.md:386 ("`Optional[Address] = None` on an invoice with no shipping address is simply absent", which implies it is extracted when present);
  - PLAN.md:491 ("with one field present, its missing required fields are `Unresolved(abstained)`");
  - DESIGN.md:296 and PLAN.md:586 (multi-label enum arrays);
  - PLAN.md:593 ("an array of unbounded items with no `source` refuses").

**Finding.** Pydantic 2.12.5 emits the following (checked this round):

- **`shipping: Optional[Address] = None`** becomes `{"anyOf": [{"$ref": …Address}, {"type": "null"}], "default": null}`. That is a field with a default and no `x-jevson`, because the declarations sit on Address's leaves.
- **`tags: list[Literal["a","b"]] = []`** carries `"default": []`.
- **`Field(default_factory=list)`** emits **no** `default`.

Read literally, DESIGN.md:256 has four consequences:

- The optional sub-object is never extracted, so the Phase 5 exit at PLAN.md:491 cannot pass.
- A defaulted enum array is never decided, while the same array written with `default_factory` is decided.
- `list[str] = []` compiles as class A instead of refusing, as PLAN.md:593 requires.
- `x-jevson.ordinal: true` or `order: source` on a defaulted field may or may not count as a "declaration". The escape list names only `source`, `generate`, and `question`.

An implementer who applies the rule to leaves only gets the intended behaviour. The two readings return different `.value`s on very common schemas.

**Fix text (DESIGN.md:256, replace the first bullet):**

> A **leaf** field (not an object or array) with a `default` and no `x-jevson` key other than `order` is **class A**: it is omitted from `.value` so the default applies (`decided_by: code`); it is neither decided nor refused. To have it decided, declare `source` or `generate`, or add `x-jevson.question` (or `ordinal: true`) to a bool, enum, or integer-range field. An **object or array** field's default does not make it class A: it is compiled from its items' or descendants' declarations, and it is class A only if nothing in it would be decided; its absence then follows DESIGN §5.6.

Add to the Phase 2 exit at PLAN.md:316:

> `Optional[Address] = None` with declared leaves compiles to decision nodes; `list[Literal[...]] = []` and `Field(default_factory=list)` compile identically.

### 2. [major] Object absence: which descendants count as "committed" is undefined when an optional object contains class A, C, or E fields

**Where:**

- DESIGN.md:386: "An object node is abstained when every **source-decided** descendant abstained or had no candidates and **none committed** a value."
- DESIGN.md:413 defines "decided from the source" as classes D and E, and class C decisions whose question reads the source.
- DESIGN.md:454 says schema-derived choices never abstain.

**Finding.** Take `Optional[Contact] = None`, where `Contact = {name: str (source), email: str (source), kind: Literal["work","home"]}`, on a document with no contact.

- **Reading A** (only class D counts): `Contact` is absent, the `kind` decision is discarded, and `complete is True`.
- **Reading B** (the DESIGN §5.8 definition, or "none" meaning any descendant): `kind` always commits, because an enum has no `none_of_these`. The object is therefore never abstained, so `name` becomes `Unresolved(abstained)` and `complete is False` on every document without a contact.

The same split applies to a `generate` descendant (drafted and possibly adjudicated for a non-existent object), a constant or defaulted leaf, and a `known=` value inside the object.

The Phase 5 exit (PLAN.md:491) uses an all-string `Address`, so it does not settle the question. Sub-objects that mix source strings with an enum or a constant are common, so the two readings diverge on the `complete` flag of ordinary documents.

**Fix text (DESIGN.md:386, replace the first sentence):**

> An object node is abstained when it has at least one class D (source-selected) descendant, every class D descendant abstained or had no candidates, and no class D descendant committed. Class A, C, and E descendants do not count: when the object is abstained their decisions are kept in `Result.decisions` but their values are discarded, and a `generate` step under an abstained object is not run (the object's class D decisions are ordered before it). An object with no class D descendant is never abstained. A `known=` value inside an object counts as committed.

Add to PLAN.md:491:

> …including an `Address` with an enum field `kind`, which is discarded when the object is absent.

---

## Minor

### m1. The `WeakKeyDictionary` of per-loop clients does not release clients for dead loops (measured)

- **Where:** DESIGN.md:540 and :554.
- **Finding:** `check_r5_weakkey_clients.py` ran five `asyncio.run()` calls, each making one request through a per-loop `httpx.AsyncClient` held in a `WeakKeyDictionary`.
  - **5 of 5 entries survived `gc.collect()`.** The client's connection pool reaches its transports, and the transports reach the loop, so the value keeps its own key alive.
  - Only an explicit `aclose()` before the loop ended freed them (0 of 5).
- **Effect:** a caller running `asyncio.run(j.aresolve(...))` per task, or pytest-asyncio with per-test loops, leaks one client and its keep-alive sockets per loop. Results are not affected.
- **Fix text:**

  > The library loop keeps one long-lived client. For a caller's loop, `aresolve()` creates the client on first use and closes it (`aclose()`) before returning, unless the caller has entered `async with JevBackend(...)` on that loop, in which case it is closed on exit.

  Add a Phase 3 exit: "20 sequential `asyncio.run(aresolve(...))` calls leave no live client for a dead loop."

### m2. Fork re-creation is under-specified and untested

- **Where:** DESIGN.md:540.
- **Finding:** re-creating the loop is not enough.
  - A `threading.Lock` in the per-key limiter that was held by the library thread at the moment of `fork` is copied in the locked state, so the child hangs on its first request.
  - The child also inherits the parent's library-loop client, whose sockets it must never use.
  - No PLAN exit exercises fork.
- **Fix text:**

  > `os.register_at_fork(after_in_child=…)` replaces the library loop and thread, re-initialises every limiter lock, and drops (without closing) every inherited client.

  Add a Phase 3 exit: "`resolve()` succeeds in a forked child, including when the parent was mid-request."

### m3. What `close()` does from a synchronous thread is unowned

- **Where:** DESIGN.md:540 ("close the client for the current loop").
- **Finding:** after `with Jevson(...) as j: j.resolve(...)`, the exit runs on a thread with no running loop, so "the current loop" is undefined. One implementer closes nothing; another closes the library-loop client.
- **Fix text:**

  > `close()` closes the library-loop client (submitted to that loop); `aclose()` closes the client for the running loop.

### m4. Stale state layout in PLAN, and R3 lacks the per-draft exception

- **PLAN.md:418** still says "state is `{"source": …, "draft": …}`", which contradicts DESIGN.md:329 and the exit at PLAN.md:433.
  - **Fix:** "state follows the keyed level layout of `DESIGN §5.2` (`drafts: {node id: draft}`)".
- **R3 (DESIGN.md:516)** still says "one keyed Jev call per topological level", while DESIGN.md:329 allows one call per draft.
  - **Fix:** append to R3 "…except adjudication's per-draft fallback in DESIGN §5.2".

### m5. The multi-draft injection regression does not test cross-draft steering

- **Where:** PLAN.md:433.
- **Finding:** the P7 set has one draft per source. Running it "under the keyed multi-draft layout" therefore changes only a key name. It never puts an injected draft beside a *second* draft, which is the new risk the layout introduces.
- **Fix text:**

  > …run with each injected draft placed beside a second, clean draft that fails its own criteria; a flip of either draft's verdict counts.

### m6. When candidates appear in state is underdefined

- **Where:** DESIGN.md:329 ("when present"), DESIGN.md:223, :316, and :602.
- **Finding:** three things are unstated:
  - whether candidate texts go in option descriptions only, as P5 and P14 measured, or also in state;
  - whether the `c0…cN` ids are unique across the fields of one level;
  - whether preflight counts state candidates against limit (a).
- **Fix text:**

  > Candidate texts are in option descriptions; state `candidates` is used only when a noul (membership, pair) references a candidate, with ids unique within the level; preflight counts it in the state size.

### m7. The members-only fixture is variant-dependent

- **Where:** PLAN.md:594.
- **Finding:** the fixture does not fix the A–B pair. If A–B lies in (`conflict_floor`, 0.5], the cross-component variant makes A and B `Unresolved(entity_conflict)`, and the expected output differs by variant.
- **Fix:** add "…and A–B at 0.10 (≤ floor): A and B are emitted as two elements under both variants".

### m8. Membership ties at the mention level

- **Where:** DESIGN.md:395, :478, and :489.
- **Finding:** a tied membership noul on a duplicate mention of an accepted entity yields `Unresolved(tie)` at the array pointer (the rules are clear), so the array is incomplete even though the entity is present. With about 30 candidates this will be common.
- **Fix:** state it as a known cost, and have the Phase 7 cap measurement (PLAN.md:590) report "arrays incomplete only through membership ties".

### m9. Direct extraction with one text at several offsets

- **Where:** DESIGN.md:334 ("two or more **distinct** candidates").
- **Finding:** a single text found at two offsets is either "lone", committed with the extractor's offset, or goes through occurrence expansion and is asked.
- **Fix:** "a lone candidate text occurring at several offsets is asked as an ordinary choice over its occurrences (DESIGN §5.1)".

### m10. Residues and wording

- **PLAN.md:466.** Change `Jevson(default_extractor=...)` to `JevsonConfig(default_extractor=...)` (see DESIGN.md:259).
- **PLAN.md:473.** The pre-filter deliverable is unscoped. **Fix:** "for fields whose value is the verbatim span".
- **PLAN.md:315.** "Every class C construct … compiles" conflicts with arrays refusing until Phase 7 (:335). **Fix:** "…except union discrimination and enum arrays".
- **PLAN.md:324.** Which reason does Phase 2 give for an undeclared `format: date` or `Decimal` field? It is not class G under DESIGN.md:257, so it should be `not_yet_supported`, per PLAN.md:466. **Fix:** say so.
- **PLAN.md:438.** The redraft bar lacks the paired difference and 95% interval that PLAN.md:497 now reports (round-4 m14).
- **DESIGN.md:697** (glossary, "tie margin"). **Fix:** "…resolved as `Unresolved(tie)`, or as a failed criterion in adjudication".
- **DESIGN.md:538 and PLAN.md:55.** "All are async", but `Normalizer` and `CostSink` are synchronous (:549–550). **Fix:** "the three I/O protocols are async".
- **DESIGN.md:588.** `versions` omits whether the source screen is on, and its wording version, which are result-affecting settings.
- **PLAN.md:757.** The hostile-extractor row omits "never-returning" (it is listed at :118).

### m11. The built-in extractor defaults can be surprising

- **Where:** DESIGN.md:257.
- **Finding:**
  - Every undeclared `Decimal` gets the *money* extractor, including quantities such as `weight_kg`.
  - A `date-time` field gets the date extractor, whose spans usually lack a time, so it will be `unparseable`.
- **Fix:** "the money extractor applies to a `Decimal` field whose description or name does not … (or only when declared); `date-time` has no built-in extractor". Either rule is fine; state one.

### m12. README and Agents claims beyond DESIGN §6

- **README.md:20** says "Every committed string is a verified span of the source." **Agents/CLAUDE.md:161** says "Every committed string is verifiable by substring match."
  - A parsed decimal (`"1204.50"`) or ISO date is a committed string that is *not* a span. DESIGN.md:446 says values "came from" a verified span.
  - **Fix:** "Every committed value is a verified span of the source, or parsed from exactly one (an amount or a date)."
- **Agents/CLAUDE.md:162** says generative fields are "admitted only after Jev adjudicates them against declared criteria". It lacks README.md:21's qualifier.
  - **Fix:** append "(a field with none is admitted and flagged ungated)".
- **Admin/README.md:22, :43, and :68 are consistent** with DESIGN §6.

---

## Sequencing check of the Revision 7 exits

- **Phase 3, step timeout (PLAN.md:370).** Buildable: the fake step node of :366 exists, and the executor runs hand-built graphs. `wait_for` cancels a cooperative infinite await. A hostile extractor that swallows `CancelledError` is outside the stated definition at PLAN.md:118.
- **Phase 3, lifecycle (PLAN.md:371).** Buildable. Fork and leak are not tested (m1, m2).
- **Phase 4, criterion ties and `@1` (PLAN.md:434).** Buildable with a fake backend.
- **Phase 5, object absence (PLAN.md:491).** Nested objects exist from Phase 2 and candidates from Phase 5. It is blocked only by the literal reading of DESIGN.md:256 (major 1).
- **Phase 5, retry record and timeouts (PLAN.md:492–493).** Buildable.
- **Phase 7, members-only and array holes (PLAN.md:594–595).** Membership and pairs arrive in Phase 7 itself, so both are buildable. The fixture detail is m7.
- **Statistical exits.** No new exit is ill-posed. The only new measured exit (PLAN.md:433) is testable but mis-targeted (m5).
