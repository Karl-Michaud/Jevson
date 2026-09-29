# E6: Logic review, round 6 (Jevson Revision 8)

**Targets:** `Jevson/DESIGN.md` (813 lines), `PLAN.md` (911), `README.md` (49), `docs/REDTEAM.md` (123); `Agents/CLAUDE.md` :146–167; `Admin/README.md` :22, :43, :68, :89. Line numbers are the working tree. No design document was edited.

**Severity** (per brief): blocker = a phase cannot be built or an exit cannot pass as written; major = a contradiction or unowned behaviour two competent implementers would resolve differently with an observable or safety effect; minor = wording, cross-link, or an edge case with one obvious resolution.

**Result: 1 blocker, 3 majors, 9 minors. CONVERGED: no.**

The blocker is a one-clause wording error in a new Phase 2 exit. The three majors are all in Revision 8 text: the new `locale` rule contradicts its own example, per-call client scoping is undefined for concurrent `aresolve()` calls on one loop, and the new object-absence rule does not say whether it applies to the root.

---

## 0. Round-5 verification (results/r5/E5_logic.md)

**Majors**

| r5 | status | where |
|---|---|---|
| 1. Class A over-reach to objects/arrays | **fixed** | DESIGN.md:256; PLAN.md:316 (but see **B1**, a new wording error in the added exit) |
| 2. Object absence: which descendants count | **fixed** | DESIGN.md:386; PLAN.md:492 (residue: root object, **M3**) |

**Minors**

| r5 | status | where |
|---|---|---|
| m1 weak-map leak | fixed | DESIGN.md:540, PLAN.md:374 (new gap: concurrency, **M2**) |
| m2 fork | fixed | DESIGN.md:540, PLAN.md:374 |
| m3 `close()` from sync thread | fixed | DESIGN.md:540 |
| m4 stale state layout; R3 | fixed | PLAN.md:419; DESIGN.md:516 |
| m5 cross-draft injection | fixed | PLAN.md:434 |
| m6 candidates in state | fixed | DESIGN.md:329 |
| m7 members-only fixture | fixed | PLAN.md:595 |
| m8 membership ties | fixed | DESIGN.md:398; PLAN.md:591 |
| m9 lone text at several offsets | fixed | DESIGN.md:334 |
| m10 residues | fixed except one | PLAN.md:467, :474, :315, :324, :439; DESIGN.md:698, :538, :588; PLAN.md:758 all fixed. **Residue:** PLAN.md:55 and :257 still say all five protocols are async (**m1** below) |
| m11 built-in extractor defaults | fixed | DESIGN.md:257 |
| m12 README/Agents claims | fixed | README.md:20–21; Agents/CLAUDE.md:161–162. A related Admin row is **m8** below |

The evidence tags are consistent: [L22] is at REDTEAM.md:72 and DESIGN.md:540, and [P23] is at REDTEAM.md:41 and DESIGN.md:71.

---

## Blocker

### B1. [blocker] The Phase 2 exit requires a source-declaring object to compile, but Phase 2 refuses every source field

- **Where:** PLAN.md:316: "an `Optional[Address] = None` whose leaves declare sources compiles to decision nodes (not class A)". This conflicts with PLAN.md:325 ("`x-jevson.source` fields … refuse with `not_yet_supported` (lifted in Phases 5…)") and with PLAN.md:322 and :327 (refusal is total; never a partial graph). The same bullet already applies the correct logic to `Decimal` ("each declaring a source, normalise correctly and then refuse only with `not_yet_supported`").
- **Effect:** the exit cannot pass as written. The intent is plain, so the fix is one clause.
- **Fix text (PLAN.md:316):**

  > …an `Optional[Address] = None` whose leaves are enums or bools compiles to decision nodes (not class A), and one whose leaves declare sources refuses with `not_yet_supported` rather than compiling as class A; `list[Literal[...]] = []` and `Field(default_factory=list)` produce the identical result (both `not_yet_supported` until Phase 7)…

---

## Major

### M1. [major] The `locale` rule contradicts its own example and the Phase 5 exit

- **Where:**
  - DESIGN.md:259: "without it, a span that **parses more than one way** is `Unresolved(unparseable)`."
  - DESIGN.md:479: "`unparseable` (… e.g. `1.204,50` without a declared locale)".
  - PLAN.md:502: "an ambiguous span such as `1.204,50` without a declared locale is `Unresolved(unparseable)`".
- **Finding:** `1.204,50` parses exactly one way: `.` as grouping and `,` as decimal gives 1204.50, and the other convention is invalid because a comma cannot follow a decimal point. Under the §3.5 rule it therefore parses, and the PLAN exit fails. The spans that really are ambiguous are `1,204`, `1.204`, and `03/04/2026`. Two readings follow:
  - **Reading A** (try both conventions): `1.204,50` becomes 1204.50, and `$1,204` becomes `unparseable`.
  - **Reading B** (English default, as the example implies): `1.204,50` becomes `unparseable`, and `$1,204` becomes 1204.
- **Effect:** the readings disagree on whole-dollar amounts, which are very common. The result is either a committed value or a required field left `Unresolved`.
- **Fix text (DESIGN.md:259, replace the `locale` sentence):**

  > `locale` (on a source declaration) fixes the decimal and grouping separators and the date order for class F. Without it, a number is parsed under both conventions (`,` grouping with `.` decimal, and the reverse, grouping in threes) and accepted only if exactly one yields a value. A date is accepted only if it is ISO 8601, has a textual month, or has a day > 12. Otherwise the span is `Unresolved(unparseable)`: `1,204`, `1.204`, and `03/04/2026` are ambiguous, while `1,204.50` and `1.204,50` parse.

  Replace the example at DESIGN.md:479 and PLAN.md:502 with `1,204`. Add to PLAN.md:502: "`1.204,50` parses to `"1204.50"`; with `locale: en-US`, `1,204` parses to `"1204"`."

### M2. Per-call clients on a caller's loop are undefined for concurrent `aresolve()` calls

- **Where:**
  - DESIGN.md:540: "On a caller's loop, `aresolve()` creates a client on first use and **closes it before returning**."
  - DESIGN.md:554 and PLAN.md:357 (unchanged): "The backend keeps **one `httpx.AsyncClient` per running event loop**."
- **Finding:** `await asyncio.gather(j.aresolve(a), j.aresolve(b))` is the normal way an async pipeline batches work. If the client is per loop (as :554 says), the first call to return closes it while the second is mid-request, and the second fails with a closed-client error (either a `BackendError` or an untyped one). The text allows three implementations, which behave differently:
  - one client per call;
  - a reference-counted client per loop;
  - a shared client closed on return, which is a bug.
  
  No exit covers this case: PLAN.md:374 tests only sequential `asyncio.run` calls.
- **Fix text (DESIGN.md:540, replace the second sentence):**

  > On a caller's loop with no entered `async with`, each `aresolve()` call owns its own client, created at its first request and closed in a `finally` before it returns, so concurrent calls on one loop never share or close each other's client. When `async with JevBackend(...)` (or `async with Jevson(...)`) has been entered on that loop, every call on that loop uses that one client, which is closed on exit.

  At DESIGN.md:554 and PLAN.md:357, change "one `httpx.AsyncClient` per running event loop" to "one long-lived client on the library loop, and per-call or context-scoped clients on caller loops (DESIGN §8)".

  Add to PLAN.md:374: "`asyncio.gather` of 10 `aresolve()` calls on one caller loop all succeed, and afterwards no client is open."

### M3. The object-absence rule does not say whether it applies to the root

- **Where:** DESIGN.md:386 ("An object node is abstained when it has at least one class D descendant, every class D descendant abstained … The abstained object then follows the table itself (omitted, `null`, or `Unresolved(abstained)`)"). Related: DESIGN.md:478 ("an unresolved root yields `.value == {}`").
- **Finding:** the root is an object node. Take `Ticket {customer_name: str (source), category: Literal[...], summary: str (generate)}`, where the customer's name does not appear in the source:
  - **Reading A** (the literal text): the root is abstained. `.value == {}`, `category` is discarded, `summary` is never drafted, and one `Unresolved(abstained)` sits at `""`.
  - **Reading B** (the rule is meant for nested optional objects): `customer_name` is `Unresolved(abstained)`, and `category` and `summary` are emitted.

  Schemas with a single source field are common, so the two readings differ on ordinary inputs. Reading A also suppresses generation for the whole document. The Phase 5 exit (PLAN.md:492) tests only a nested object.
- **Fix text (DESIGN.md:386, append):**

  > The rule applies to object nodes below the root. The root is never abstained; its fields follow the table individually.

  Add to PLAN.md:492: "…and a root with one source field that abstains still emits its enum and generated fields."

---

## Minor

### m1. PLAN still says all five protocols are async (residue of r5 m10)

- **Where:** PLAN.md:55 ("`protocols.py` Backend, Extractor, LLM, Normalizer, CostSink (async; DESIGN §8)") and PLAN.md:257 ("all five protocols, async"). These contradict DESIGN.md:538.
- **Fix:** "the three I/O protocols async, `Normalizer` and `CostSink` synchronous (DESIGN §8)".

### m2. The PLAN decisions table lacks the leaf qualifier

- **Where:** PLAN.md:835: "**Undeclared defaulted fields** | Class A: omitted so the default applies".
- **Fix:** "Undeclared defaulted **leaf** fields | Class A …; objects and arrays compile from their contents (DESIGN §3.5)".

### m3. The fork handler is buildable, but it should create the loop lazily and pin the test

- **Where:** DESIGN.md:540 and PLAN.md:374.
- **Finding:** starting a thread inside `after_in_child` works, but it is fragile. It spawns a thread in every forked child, including children that never call Jevson, such as multiprocessing workers. Once the daemon thread exists, Python ≥ 3.12 emits a `DeprecationWarning` on every `fork()`, so the test fails under `-W error`. "Mid-request" is also not reproducible without a hook.
- **Fix:**

  > `after_in_child` marks the library loop, limiter locks, and clients stale; the next `resolve()` in the child re-creates them.

  For the exit, state:

  > …using `JevBackend` over an `httpx.MockTransport` that blocks until the fork has happened, with the fork warning filtered.

### m4. The generate step's wait on class D decisions must include retries

- **Where:** DESIGN.md:386 ("the object's class D decisions are ordered before it").
- **Finding:** retry is executor policy, not a graph edge (DESIGN.md:180). The edge "class D decision → generate step" is therefore satisfied after the first ask, before any retry has recovered a value. An implementer will almost certainly wait for the retry, but the text does not say so.
- **Fix:** "…ordered before it, and a decision counts as resolved for this purpose only after its retries (DESIGN §5.5)".

### m5. Decimal `multipleOf` changes what `satisfies_schema` means

- **Where:** DESIGN.md:436, DESIGN.md:476, and PLAN.md:502 (a number for `type: number` fields).
- **Finding:** `satisfies_schema` is computed by a validator whose `multipleOf` is decimal. A caller who re-validates `.value` with stock `jsonschema` will reject about 11% of valid cents on `type: number` fields [L18].
- **Fix:** add to DESIGN.md:476: "Jevson's validator overrides `multipleOf` with a decimal check on every number; a stock float validator may reject `.value` that Jevson reports as satisfying."

### m6. `versions` omits other settings that affect results

- **Where:** DESIGN.md:588–591.
- **Finding:** the effective `retry_budget` and `redraft_budget` (which can be set per call), `default_extractor`, and `transport_retries` all change `.value` or `unresolved`, but none is recorded.
- **Fix:** "…and the effective retry and redraft budgets and `default_extractor`".

### m7. How the pre-filter and direct extraction interact is implied, not stated

- **Where:** DESIGN.md:334 and :336.
- **Finding:** three candidates, two of which fail `maxLength`, leave one, which then commits unchecked. That is the obvious reading. It also means a pattern-extractor field with `direct_extraction` can commit a lone survivor that the question would have rejected.
- **Fix:** "'lone' is counted after the pre-filter".

### m8. The Admin row lacks the ungated qualifier

- **Where:** Admin/README.md:43 ("LLM-drafted fields admitted only after passing declared criteria").
- **Finding:** DESIGN.md:506 admits a field with no criteria as ungated. README.md:21 and Agents/CLAUDE.md:162 now carry the qualifier; Admin does not.
- **Fix:** append "(a field with none declared is admitted and flagged ungated)".

### m9. "Always with a none of these option" overstates

- **Where:** README.md:20 and Agents/CLAUDE.md:161 ("always with a *none of these* option").
- **Finding:** under `direct_extraction: true`, a lone candidate commits with no question (DESIGN.md:334). README.md:35 lists "direct extractions" as carrying no probability but omits "ungated drafts" (DESIGN.md:453).
- **Fix:**
  - README.md:20 and Agents:161: "always with a *none of these* option, unless a field opts into direct extraction".
  - README.md:35: "…constants, defaults, direct extractions, ungated drafts, and values you supply do not."

---

## Checks that hold

**Sequencing of the new exits**

| exit | where | status |
|---|---|---|
| Phase 2, defaulted leaves | PLAN.md:316 | holds, apart from B1 |
| Phase 3, lifecycle and fork | PLAN.md:374 | buildable in Phase 3 |
| Phase 4, cross-draft injection and `@1` | PLAN.md:434–435 | buildable with the Phase 4 layout |
| Phase 5, direct extraction, object absence with an enum and a `generate` field, timeouts | PLAN.md:491–494 | buildable in Phase 5, since `generate` exists from Phase 4 and enums from Phase 2 |
| Phase 7, members-only at A–B = 0.10 and tie reporting | PLAN.md:591, :595 | correct under both variants |

No new exit is statistically ill-posed.

**Buildability**

- **Class-D-first ordering:** it is an ordinary dependency edge from the object's class D decision nodes to its `generate` steps. It adds one level of latency, and there is no cycle. See m4 on retries.
- **The leaf/object rule (DESIGN.md:256)** matches the Pydantic 2.12.5 emissions measured in round 5.
- **The object rule (DESIGN.md:386)** resolves the round-5 enum, `generate`, and `known=` cases.

**README, Agents, and Admin against DESIGN §6**

- README.md:20–24 and :32–35 and Agents/CLAUDE.md:159–165 stay within the §6 tiers, apart from m9.
- Admin/README.md:22, :68, and :89 are consistent. Admin/README.md:43 is m8.
