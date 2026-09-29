# E7: Logic review, round 7 (Jevson Revision 9), convergence check

**Targets:** `Jevson/DESIGN.md` (825 lines), `PLAN.md` (911), `README.md` (49), `docs/REDTEAM.md` (124); `Agents/CLAUDE.md` :146–167; `Admin/README.md` :22, :43, :68, :89. Line numbers are the working tree. No design document was edited.

**Severity** (per brief): blocker = a phase cannot be built or an exit cannot pass as written; major = a contradiction or unowned behaviour two competent implementers would resolve differently with an observable or safety effect; minor = wording, cross-link, or an edge case with one obvious resolution.

**Result: 0 blockers, 0 majors, 9 minors. CONVERGED: yes.**

Every round-6 blocker and major is fixed in text that is internally consistent and buildable. The whole-document pass found no remaining blocker or major. The minors below are residues and edge cases, and none changes a safety property.

---

## 0. Round-6 verification (results/r6/E6_logic.md)

| r6 | status | where |
|---|---|---|
| **B1** Phase 2 exit compiled source-declaring objects | **fixed** | PLAN.md:316 ("refuses only with `not_yet_supported` (not class A)"); consistent with :325 and :327 |
| **M1** `locale` contradicted its example | **fixed** (by a deterministic `en-US` default rather than the proposed both-conventions rule) | DESIGN.md:259, :479; PLAN.md:475, :502. `1.204,50` does not parse under en-US; `$1,204` → 1204; `de-DE` → 1204.50. Rule, example and exit now agree. See minors 1–2 |
| **M2** concurrent `aresolve()` shared a client | **fixed** | DESIGN.md:540 (a client per call; shared only under `async with JevBackend`), :554; PLAN.md:357, :374 (the `gather` exit). Residues in PLAN §5 and §6 are minor 5 |
| **M3** root object abstention | **fixed** | DESIGN.md:386 ("the root object is never abstained"). No Phase 5 exit was added (minor 6) |
| m1 protocols wording | fixed | PLAN.md:55, :257 (residue at :819, minor 5) |
| m2 leaf qualifier in decisions table | fixed | PLAN.md:835 |
| m3 fork lazy re-creation | fixed | DESIGN.md:540 |
| m4 generate step waits for retries | fixed | DESIGN.md:386 |
| m5 decimal `multipleOf` noted | fixed | DESIGN.md:436 |
| m6 `versions` | fixed | DESIGN.md:588–591 |
| m7 lone candidate counted after pre-filter | fixed | DESIGN.md:334 (placement nit, minor 8) |
| m8 Admin ungated qualifier | fixed | Admin/README.md:43 |
| m9 "always none of these" / README:35 | fixed | README.md:20, :35; Agents/CLAUDE.md:161 |

**Evidence tags in changed text.** All resolve and are used accurately:

- [P12] (REDTEAM.md:31: "1.1% within ±0.05") and [P22] (:41: "56/2,154 … 2.6%") in DESIGN.md:398;
- [L22] (:73: "5/5 survived garbage collection") in DESIGN.md:540;
- [L20] and [L18] are unchanged.

One claim in the new text has no tag (minor 9).

---

## Blockers

None.

## Majors

None.

The whole-document pass checked the following, and all hold:

- the class A leaf/object rule against the Phase 2 exits;
- object absence (non-root) against the Phase 5 exits;
- the tie margin across every committing decision;
- the §5.6 table against the closed `Unresolved` set;
- `known=` inside abstained objects;
- the union subtree and `.value == {}` (a root can now be unresolved only as a union);
- per-call clients against the rate limiter, `close`/`aclose`, and fork;
- preflight against declared maxima;
- the Phase 4/5 order against the object-level generate wait. Class D exists only from Phase 5, so Phase 4 is unaffected.

---

## Minors

### 1. [minor] The locale grammar and the set of supported tags are unspecified

- **Where:**
  - DESIGN.md:248 (`locale?: <BCP 47 tag>`), :259;
  - PLAN.md:475, :641 (the dependencies are `jsonschema`, `pydantic`, `httpx`, with no CLDR/Babel).
- **Finding:** "does not parse under the field's locale" does not say how strict parsing is. Babel's lenient `parse_decimal('1.204,50', 'en_US')` returns `1.20450`. The Phase 5 exit (`1.204,50` → unparseable) forces strictness for that one case, but `1,20` or `12,34,567` under en-US remain open. The text also does not say which BCP 47 tags are accepted, or what an unsupported one does. A competent implementer will parse strictly and refuse unknown tags (R14), so this is minor.
- **Fix text (DESIGN.md:259, append):**

  > Parsing is strict: grouping separators appear only left of the decimal separator, in groups of three; anything else is `unparseable`. `locale` accepts the tags in the table in `assemble/parse.py` (each naming its decimal and grouping separators and numeric date order); any other tag refuses at compile time.

### 2. [minor] Under the default, some non-US spans commit a wrong value silently, and this limit is unstated

- **Where:** DESIGN.md:259; the honest limits at DESIGN.md:451–458; §10 at :655–677.
- **Finding:** under `en-US`, a German `1.204 €` parses as 1.204, and `03.04.2026` or `03/04/2026` parses as 4 March. Both are committed with provenance and a probability. This is an owned, deterministic rule (the owner chose it over the round-6 ambiguity rule), so it is not a contradiction. It is still a wrong-but-valid output, which callers should be told about.
- **Fix text (add to DESIGN.md:458 and a §10 row):**

  > Class F reads numbers and numeric dates as `en-US` unless a field declares `locale`; a non-US source without it can yield a wrong but schema-valid amount or date (e.g. `1.204` read as 1.204).

### 3. [minor] Object absence does not say how a source-grounded array descendant counts

- **Where:** DESIGN.md:386.
- **Finding:** "every class D descendant abstained or had no candidates" covers choices. An array inside an optional object whose candidates were all rejected by membership has neither "abstained" nor "no candidates". Read literally, `Optional[Shipment] = None` with `tracking_numbers: list[str]` (source) and a required `carrier` (source) turns an ordinary "no shipment" document into `Unresolved(abstained)` on `carrier`. The obvious intent is that an array with no accepted member counts as abstained.
- **Fix text (DESIGN.md:386, after "…or had no candidates"):**

  > (a source-grounded array counts as abstained when no candidate was accepted as a member, and as committed when at least one was)

  Add a case to the Phase 7 exits.

### 4. [minor] Whether a root-level `generate` step waits for class D decisions

- **Where:** DESIGN.md:386 ("the object's class D decisions, including their retries, are ordered before it").
- **Finding:** the root is an object but is never abstained, so a root-level `generate` step has no reason to wait. Read literally, it waits anyway. The difference is latency only.
- **Fix text:**

  > …ordered before it; this applies to objects below the root.

### 5. [minor] PLAN §5 and §6 still describe "a client per loop" and "async" protocols

- **Where:**
  - PLAN.md:793 ("library loop thread; a client per loop; thread-lock limiter");
  - PLAN.md:819 ("**Protocols** | Async … a client per loop").
- **Finding:** both contradict DESIGN.md:538 (the sync `Normalizer`/`CostSink`) and :540 (per-call clients on caller loops).
- **Fix text (PLAN.md:819):**

  > The three I/O protocols async, `Normalizer` and `CostSink` sync; sync `resolve()` on one library loop thread with one long-lived client; per-call clients on caller loops (shared under `async with`); per-key limiter on `threading.Lock`

  Make the same client wording change at PLAN.md:793.

### 6. [minor] Three rules added in Revision 9 have no exit test

- **Where:**
  - PLAN.md:492 (the root never abstained);
  - PLAN.md:374 (the `async with JevBackend` shared client, and no client left open after `gather`);
  - DESIGN.md:540 (whether `async with Jevson(...)` enters its backend's context).
- **Fix text:**
  - PLAN.md:492, append: "…and a root with one source field that abstains still emits its enum and generated fields."
  - PLAN.md:374, append: "…after `gather` no client is open; inside `async with JevBackend(...)` both calls use one client, closed on exit."
  - DESIGN.md:540: "`async with Jevson(...)` enters its backend's context."

### 7. [minor] "Compile identically" for enum arrays reads as if they compile

- **Where:** PLAN.md:316: "`list[Literal[...]] = []` and `Field(default_factory=list)` compile identically". Per :315, both refuse until Phase 7.
- **Fix text:**

  > …produce the identical result (both `not_yet_supported` until Phase 7).

### 8. [minor] The pre-filter counting parenthetical is attached to "zero candidates" only

- **Where:** DESIGN.md:334.
- **Finding:** "(candidates are counted after the pre-filter below)" sits inside the zero clause. It also governs "lone" and "two or more".
- **Fix text:** move the parenthetical to the start of the sentence:

  > A field may opt into `direct_extraction: true` (candidates counted after the pre-filter below): …

### 9. [minor] A factual claim about Python in the new text carries no evidence tag

- **Where:** DESIGN.md:540: "(Python 3.12+ warns when a process with threads forks …)".
- **Finding:** this is a claim about another tool, which the §0 evidence rule requires to be tagged.
- **Fix text:** add a REDTEAM `V-` or `L-` entry (the CPython 3.12 `os.fork` DeprecationWarning), or drop the parenthetical.

---

## README, Agents, and Admin against DESIGN §6

| file | lines | status |
|---|---|---|
| README.md | :17–24, :30–35 | Within the §6 tiers. Round-6 m9 is fixed. |
| Agents/CLAUDE.md, Jevson paragraph | :157–167 | Within the §6 tiers. Round-6 m9 is fixed. |
| Agents/CLAUDE.md, Jev block | :146–155 | Consistent with DESIGN §2. The p50 "~0.15–0.3 s" is a loose superset of [P8] (0.15–0.22 s); acceptable. |
| Admin/README.md | :22, :43, :68, :89 | Consistent. Round-6 m8 is fixed. |

README.md:20 ("parsed from exactly one (an amount or a date)") remains true under minor 2, since the value is still parsed from one span.

**CONVERGED: yes**: no blocker or major remains; nine minors, none affecting a safety property or an exit's passability.
