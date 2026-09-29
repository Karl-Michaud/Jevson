# A4: Citation audit of Revision 6 (red-team round 4)

**Scope.** Working tree on branch `docs/revision-3-decisions`: `DESIGN.md` (766 lines), `PLAN.md` (898), `README.md` (49), `docs/REDTEAM.md` (119), `Agents/CLAUDE.md` (:60, :146–167), `Admin/README.md` (:22, :42, :67). No design doc was edited.

**Method.**
- Every number attached to a new Revision 6 tag (P17–P22, L18–L21) was recomputed from raw data with independent code, not the probes' own analysis functions. Scratch scripts are in the session scratchpad (`r4/p17.py` plus inline scripts).
  - P17: my own connected-components and rule implementation over `r3_entity_{,hard_}run{A,B}.json`.
  - P18 to P21: recomputed from `r3_complete_value.json`, `r3_mixed_desc.json`, `r3_choice_tie.json`, and `r3_source_screen{,_lines}.json`.
  - P22(b): recomputed over every r1, r2 and r3 raw file.
  - P12: the inclusive bool band was recomputed from `r2_tie_rule.json`.
- L18 to L21 were checked line by line against `results/r3/D3_local.md` and `results/r3/outputs/*`, including `cmp` of the Pydantic JSON outputs and `check_r3_grapheme_table.py`.
- Key scan: 218 files, the key found in 0 (compared in memory; only the count was printed).
- Line refs: `D` = DESIGN.md, `P` = PLAN.md, `R` = README.md, `RT` = docs/REDTEAM.md.

## Summary

**Tag instances.**
- DESIGN has 212 bold tag instances and PLAN has 116; README has 0.
- Three are example tags inside the evidence convention (D9 ×2, P5), which leaves **325 claim tags**: DESIGN 210, PLAN 115.
- Every tag used is defined in RT. L5, L6 and L8 are defined but unused, which is harmless.

| verdict | count | instances |
|---|---|---|
| SUPPORTED | 317 | — |
| OVERSTATED | 7 | D70 V-confidence (carried), D399 P10, D410 P21, D428 L19, D707 P19, P274 L19, P856 P19 |
| WRONG | 1 | D325 P18 ("3–5 competitors"; the set had exactly 4) |
| UNSUPPORTED | 0 | — |

All eight are **minor**.

**Blocker/major items in scope: 1 major.** DESIGN R6 (D514) and PLAN's layout (P98) still state the two-directional entity rule as settled. That contradicts the Revision 6 decision in D394–397, D721 and P566 (section 3 below).

---

## 1. Tag verdicts

### 1a. New Revision 6 tags: recomputation

| tag | claim (RT row; DESIGN/PLAN uses) | recomputed | verdict |
|---|---|---|---|
| **P17** | floor 0.45 (grid top) on every corpus and run | MAIN, HARD and ALL × A/B: all 0.45; 1,030 gold-same of 5,410 pairs | S |
| P17 | two-directional 0/224 MAIN, 1/312 overall | A: MAIN 214 ok / 10 U / **0** wrong; HARD 64/23/**1**. B: 216/8/0 and 63/24/1 | S |
| P17 | internal-only 1/312; Rev 3 whole-array 1/312 (0.76 correct); plain components 25/312, all merges | internal@0.45 287/24/1 in both runs; rev3 237 (A) and 240 (B) correct = 0.760 and 0.769, 1 wrong; plain 287 ok, 25 merges, 0 splits | S |
| P17 | **0 splits in 160 doc-runs** | 0 splits under every policy, both runs, 80 docs | S |
| P17 | cross condition blanked 8–9 otherwise-correct components | blanked by the cross condition only, and correct: 9 (A), 8 (B) | S |
| P17 | arrays with ≥ 1 unresolved component 27/80 and 26/80 | 27 (A), 26 (B) | S |
| P17 | non-transitive docs 12% main, 60% split-stress | MAIN 6/50 both runs; HARD 18/30 (A), **17/30 (B)** | S (60% is run A only; nit) |
| P17 | D397 "each uncertain cross pair blanks two components" | B3 cascade table ("always blanks both") | S |
| P17 | D399 "selected the top of its grid on every pilot corpus — 0.30 … 0.45 [P10, P17]" | P10's own row says "0.30 (grid top; **0.20 on the P6 subset**)" | **O** (P10 instance; minor). Fix: "…on every full pilot corpus (0.20 on the round-1 subset)" |
| P17 | P211 role nouns "produced the pilot's only splits [P10, P17]" | P17 had role nouns ("Plaintiff", "the Guarantor", "their captain") and 0 splits | S (reads as "the only splits observed were P10's"); nit |
| P17 | P818 "did nothing out of sample" | prevented 0 errors, but blanked 8–9 correct components | S; nit: "prevented nothing and cost 8–9 components" |
| **P18** | FULL: chosen 72/72 both wordings | 72/72, 72/72 (argmax recomputed) | S |
| P18 | PARTIAL: correct abstention 19/72 → 72/72 | 19 → 72 | S |
| P18 | DOCPARTIAL: 15/36 abstained; addresses and dates abstain, names, phones and venues commit | address 6/6, hearing date 6/6, guest 3/6, supplier 0/6, phone 0/6, venue 0/6 | S |
| P18 | **D325 / RT37 "among 3–5 competitors"** | every FULL case had exactly **5 options = full + 4 competitors** (2 partials, 1 competitor full, 1 competitor partial; `len(F)=5` for 72/72) | **W** (minor). Fix: "among 4 competitors (two partial variants and another entity's value)" |
| P18 | D325 "This exact text was tested" | the probe's W1 is DESIGN's template verbatim, except that it uses an ASCII " - " where DESIGN has an em dash | S |
| P18 | RT37 "≥ 60 documents per condition" | FULL/PARTIAL 72 docs; DOCPARTIAL **36** | RT defect (minor) |
| **P19** | unique 48/48 in every format; repeated-text MIX 48/48, CTX 47/48, BARE 20/48 | reproduced from the report and paired counts | S |
| P19 | RT38 "~0.10 probability shifted … **with no decision changed**" | UA mean p on context options 0.098 (MIX) vs 0.000 (BARE); **MIX vs BARE had 1 discordant UA decision**: MIX committed a context-bearing option where BARE abstained | **O** (RT, minor) |
| P19 | D317 "did not bias decisions out of sample" | OK as worded, with the mass-shift caveat stated | S |
| P19 | **D707 / P856 closed by evidence: "does not bias decisions"** | B3: "at ceiling … these distractors are easy, so a small bias could go undetected"; it recommended a Phase 0 re-test with same-role distractors, which was not added | **O** ×2 (minor). Fix: move to "not detected at ceiling; re-tested in Phase 0" |
| **P20** | argmax flips 14/180; 11/180 at a 0.05 margin; 1/180 at 0.10 | 14 / 11 / 1 | S |
| P20 | 4.4% and 7.8% of answers tied | 80/1,800 and 140/1,800 | S |
| P20 | range p90 0.11, max 0.21; 69% within 0.05 | p50 0.02, p90 0.11, max 0.21; 124/180 = 68.9% | S |
| P20 | D291 "a ±0.05 band left 11/180" | the band tested was **top-two margin ≤ 0.05**. For a noul, "±0.05" means margin ≤ 0.10 (D484), so the label is ambiguous | S; nit: say "a 0.05 margin" |
| **P21** | attacks 60/60, all p ≥ 0.86, none in 0.45–0.55 | 60/60 in both runs; min 0.86; 0 in the band | S |
| P21 | benign 28/60 at p ≥ 0.55 | A 28, B 28 at 0.55. **At the adopted p ≥ 0.56: A 27, B 28** (one A doc sits at exactly 0.55) | S for RT as stated |
| P21 | **D410 "flagged 28/60 benign invoices and e-mails"** | the 60 are 20 invoices, 20 e-mails and 20 contracts; the flags were 14 + 14 + 0 | **O** (minor). Fix: "flagged 27–28/60 benign documents at the adopted threshold (all invoices or e-mails; 0/20 contracts)" |
| P21 | 16/24 arguable single lines; plain 0/66 | 16/24 at both 0.55 and 0.56; 0/66 | S |
| P21 | the tie band added 5–8% FPs and no attacks | benign in band 4/60 and 3/60; plain 4/66; arguable 2/24 (5.0–8.3%); attacks 0 | S |
| **P22** | +1,600 tokens (50 × 120); +2,521 with 80-char context | `r4/outputs/probe_r4_default_budget.txt` matches; r4 request count 3 | S. Nit: `r4/raw/` is empty, so the raw responses were not saved |
| P22 | D484 "On 1,282 pilot candidate choices … 18 (1.4%)" | independent walk: 1,282 / 18 (mixed_desc 432/11, complete_value 360/5, p05* 490/2) | S as a number |
| P22 | RT40 method "**every** saved candidate choice (r1 P5/P9, r3 P18/P19)" | P9's raw holds no per-choice probabilities (it contributes 0). The r2 candidate choices (P11 336, P15 320, P16 216 = 872, 38 at ≤ 0.10) and p05's 120 "none of the above" choices are excluded. Over all 2,154 `none_of_these` choices the rate is **56 = 2.6%** | RT defect (minor). Fix: "1,282 choices from r1 P5 and r3 P18/P19 (2.6% if r2 P11/P15/P16 are included)" |
| **L18** | `x-jevson` beside `$ref`/`anyOf`/`oneOf`, never in `$defs`; `Optional[Decimal]` three-branch; one-member Enum → `$ref` enum; no `allOf` in ≥ 2.10; 11,426/100,001; `"12.345"` accepted; default lost; 2.12.0 ≡ 2.13.5, 2.8–2.11 differ | D3 §4–5, §7; `check_r3_absent_null.txt:20,27,40`; `cmp`: 2.12.0 identical, 2.8.2 / 2.10.6 / 2.11.10 differ; 2.8.2 has 12 `allOf` | S (×15). The allOf claim holds on 20 cases |
| **L19** | 1.1–1.3 KB; 47 lines; 1,187 / 1,093 / 766; Python 3.15 → 17.0; uniseg fails 9, 8.2 MB | `check_r3_grapheme_table_17.0.0.txt:4-8` (1,344 B at 17.0) | S. Nit: D428/P264/P820 "~1.2 KB" is 1.3 KB at the pinned 17.0 |
| L19 | **"a deliberately buggy segmenter also passed"** (D428, P274, RT69) | the bug was accidental in a first draft, then *retained* as `RUNTIME_V1` (`check_r3_grapheme_table.py:146-148`; D3 "my first segmenter…") | **O** ×2 (D428, P274; minor). Fix: "a segmenter with a real GB11 bug also passed" |
| **L20** | `Event loop is closed`; lost wakeup; 4 threads × 3 calls; 20/s across 5 loops; OpenAI/Anthropic `additionalProperties:false`, Gemini lacks it | `check_r3_sync_over_async.txt:5,20-21,31,39-40`; `check_r3_tool_schema_providers.txt:5` | S (×10) |
| **L21** | rfc8785 = jcs = canonicalize = json-canonicalize; canonicaljson and sorted dumps differ; 2⁵³+1; lone surrogates | `check_r3_jcs_crosslang.txt:3-40` | S (×4). Nit: `canonicaljson` emits 2⁵³+1 exactly, so "rounded elsewhere" is jcs and JS only |

### 1b. Carried and reworded tags

- These tags were re-checked against A3 and still read the same, so they remain **S**: X1–X8, V-index, V-api, V-primitives, V-models, V-jagged, V-advanced, V-fanout, V-preparsed, V-cookbooks, V-consistency, V-sdk, V-sdk-constants, V-launch, V-systemone, V-primer, P1–P16, L1–L4, L7, L9–L17.
- Round-3 WRONG and OVERSTATED fixes:
  - D290 P12 bool rule: recomputed as 0 true↔false flips and 23/2,000 ties with 0.45 and 0.55 inclusive as ties.
  - D333 P11 "2–3 competitors".
  - D490 L13 "uniform 0% … Beta(18,2) ~50%".
  - D100 → V-systemone.
  - D428 L11 "13–15 of 20".
  - D594 L7 "proxy tokenizer".
- **Still OVERSTATED: D70 V-confidence.** "The documented formula is written in terms of the number of options." `confidence.md:138` gives only a demo approximation, "(3 × largest − 1)/2 … for three options". RT86 repeats "option-count-dependent formula". This is A3 row 3, not addressed. Minor. Fix: "the docs describe it as a statistic of the distribution's spread and illustrate it with a three-option approximation".

---

## 2. Untagged factual claims

| # | where | claim | status / fix |
|---|---|---|---|
| U1 | D339 | "Jev's probabilities are relative to the options it was handed" | untagged (A3 U2, not addressed). Add **[V-jagged]** |
| U2 | D369 | "Jev's distribution is relative to the offered set" | untagged (A3 U3). Add **[V-jagged]** |
| U3 | D243 | Pydantic `json_schema_extra` yields "identical" JSON Schema to a raw-schema user's | add **[L18]** |
| U4 | P150 | "The red-team pilots … [P1–P16] … used synthetic, author-written cases" | stale range: P17–P22 are the same kind. Fix: "[P1–P22]" |
| U5 | R43 | REDTEAM holds "every factual claim" | RT3 now says the README carries no tags. Fix: "every factual claim in DESIGN and PLAN" (A3 U8, partial) |

**README check.** Each README claim appears in DESIGN:
- R3 = D7.
- R7 ≈ D17.
- R15 = D25.
- R19–22: §3, §5.
- R24: §5.4 and §5.6.
- R28: D36 and §9.1.
- R32–35: §6.
- R42–45: PLAN.

R35 lists fewer no-probability cases than D450 (it omits "parsed values"), so it says less than DESIGN, not more. **README states nothing DESIGN doesn't.**

---

## 3. Traceability of round-3 findings

### 3a. The one major item

**[major] Settled rule R6 and the PLAN layout still prescribe the two-directional rule.**
- D514 (R6, under "Settled. Changing one is a design change that updates this document"): "emitting only components whose evidence is consistent in both directions".
- P98: `entities.py … two-directional component rule (R6)`.
- D40 also promises arrays that "refuse to … split on … unstable evidence", which only the variant does.
- These contradict the Revision 6 entity decision:
  - D394 "a variant, chosen in Phase 0";
  - D397 "Why the variant is not settled";
  - D721 changelog;
  - P566 "plus the cross-component variant if Phase 0 chose it";
  - P818.
- By DESIGN's own precedence (§7 rules are normative), an implementer would build R6's rule. This is the B3 probe-1 / E3 #8 change propagated incompletely.
- **Fix text:**
  - **D514:** "…lossless on case by default, emitting only components with no internal conflict, plus the cross-component condition if Phase 0 selects it (DESIGN §5.7)."
  - **P98:** "pre-merge, pairwise resolution, internal-consistency rule and optional cross-component variant (R6)."
  - **D40:** "…that refuses to merge on contradictory evidence (and, if Phase 0 selects it, to split on uncertain evidence)."

### 3b. E3 (logic review) findings

| E3 | sev | status | where / residue |
|---|---|---|---|
| 1 central property | blocker | **addressed** | D462 outcome 2 "incomplete *or* invalid"; D568 `violations`; D335 pre-filter; P276 |
| 2 Phase 2 exits | blocker | **addressed** | P316 (no undeclared `Optional[str]`); D257 and P310 `compile_schema(extractors=, default_extractor=)`. Residue (minor): P316 "a defaulted field compiles" is unsafe if that field is an unbounded `str` (see #13a) |
| 3 async | major | **addressed** | D533, D545; P355–356, P372 |
| 4 zero candidates | major | **addressed** | D335, D353, D381, D475 `no_candidates`. Residue (minor): P485 still says "zero candidates yield an `absent` entry" unconditionally (P470 is correct). `abstain_probability` when no call was made is untyped |
| 5 reason set | major | **addressed** | `unparseable` and `budget_exceeded` with bisection (D475, D590); Decimal as a string (D237). Residue (minor): D475 "without a declared locale", but `x-jevson` has no locale key (D246–253); D433 still parses to `1204.5` rather than the string form |
| 6 tie band | major | **addressed** | one margin ≤ 0.10 for every committing decision (D484, D290–292; P370, P416). Rubric-tie outcome is implied only |
| 7 tolerance; argmax | major | **partial** | argmax authority is addressed (D71). **The ⌈K/2⌉ tolerance is unchanged, and not declined.** I rate it minor: in Rev 6 an all-zero or double-1.00 distribution falls to margin 0, so `Unresolved(tie)`; only a malformed backend is affected. Fix: "tolerance min(⌈K/2⌉, 5); max p = 0 → `invalid_backend_answer`" |
| 8 entity cascade | major | **mostly addressed** | cascade stated (D397); the variant choice weighs correct components (P211); a 0.05 fallback floor means *stop* (P211). Residue (minor): members-only components are implied only by the P569 order, and recursion is unstated. See 3a for the R6 propagation |
| 9 attempt ids | major | **addressed** | D164, D563 |
| 10 `known=` | major | **mostly addressed** | D547 (validated, `PreflightError`, no provenance). Residue (minor): unknown pointers, array indices, and a known discriminator are unspecified |
| 11 `max_candidate_chars` | major | **addressed** | D248 default 120; D592 [P22]. Residue (minor): whether occurrences count toward `max_candidates` is unstated |
| 12 untyped call-time errors | major | **partial** | multi-source and `known` → `PreflightError` (D465). Residue (minor): `resolve()` inside a running loop "raises" with no named type (D533, P372). Fix: name it, e.g. `PreflightError(running_loop)` |
| 13 defaults | major | **partial** | (b) addressed (D379, D383, [L18]). **(a) is not addressed:** `currency: str = "USD"` with no `x-jevson` refuses under D256, but class A lists "defaults" (D270). Minor, because D256 decides it. Fix: one sentence in D256 |
| 14 config surface | major | **mostly addressed** | `JevsonConfig` (D258). Residue (minor): `default_extractor` is in neither `Jevson(...)` (D545) nor the `JevsonConfig` list, although P463 uses `Jevson(default_extractor=...)`; `retry_budget` is both config (D258) and per-call (D371); `Result.versions` omits settings |
| 15 cap on candidates | major | **addressed** | D594 "the cap applies to candidates". Residue (minor): "the compiler's run-time check" (D594) should be "the executor's" |
| 16 enum arrays | major | **addressed** | D295; P565, P578; the fallback is stated identically at P27, P232, P500 and P878. Residue (minor): P585 "an array with no source grounding refuses" contradicts P578 |
| 17 redraft bar | major | **mostly addressed** | P435 blind post-hoc labels. Residue (minor): point-estimate "2 points"; the LLM is not recorded |
| 18 retry bar | major | **addressed** | P489 unmodified extractor with exclusions |
| 19 τ, extension | major | **addressed** | D487–488 (τ fixed before labelling; "not decidable" at 3,000) |
| 20 both orderings | major | **addressed** | P570, P583 (n ≥ 40 × 2, halving rule, within the evidenced question count) |
| 21 replay | major | **mostly addressed** | D607 (`cache_hits`, `replay_miss`, surrogates, extractor determinism). Residue (minor): P379 "reproduces the original `Result`" while `Cost.cache_hits` differs; the `ReplayLLM` miss is unspecified |
| 22 stability flip definition | minor | **NOT ADDRESSED** | P380 unchanged |
| 23 screen wording | minor | **partial** | steerability (D411) and threshold (D410) are addressed. Not addressed: "class C decisions whose question reads the source" (= all of class C); the screen runs after the extract and draft steps; the P492 counts vs "≥" n |
| 24 adjudication layout | minor | **addressed** | D328 |
| 25 README / Agents / Admin | minor | **partial** | Agents :164 is fixed, and Admin :22 and :67 are fine. **Not addressed:** D7/R3 wording; D450 "parsed values … do not" (R35 changed, DESIGN did not); R24 is still unconditional; **Admin:42** "typed abstention when the source doesn't support an answer" and "values traceable to the source" are unconditional |
| 26 residues | minor | **partial** | P57 bare § is fixed; `dependency_unresolved` is reworded (D475); the flat `allOf` exit was added (P318). **Not addressed:** D619 "§5.4"; D86 cites §8.2 for `usage.input_tokens`, which §8.2 never mentions; D594 "compiler's"; D256 `date` as a type; P368 Phase 3 "declaration maxima"; P482 names 2 of 3 probes; no `RefusalReason`; array-hole pointer |

None of the not-addressed items is recorded as declined (the D713–729 changelog and the RT119 round log list only changes).

### 3c. A3 items

| A3 item | status |
|---|---|
| W D285 P12 | fixed (D290; recomputed: 0 flips) |
| W D326 P11 | fixed (D333) |
| W D480 L13 | fixed (D490, RT63) |
| O D70 V-confidence | **not addressed** (minor; section 1b) |
| O D100 | fixed (V-systemone) |
| O D320 P11 wording | fixed (D325 now cites P18 for the exact text; P11 is "an earlier variant") |
| O D418 L11 | fixed |
| O D581 L7 | fixed |
| U1 D58 | fixed ([V-api]) |
| U2, U3 | **not addressed** (section 2) |
| U4 | superseded by L19 |
| U5 `format` caveat | fixed (D442) |
| U6 | fixed (D651) |
| U7 | fixed (D84) |
| U8 | partial (section 2, U5) |
| U9, U10 | n/a |
| C-5 prior art | fixed in DESIGN (D620, D624). **RT104 X3 omits PyPI `jev`, `finetuningsingh/jev-extract`, and `dangquan1402/jev-extract`**, although r1 C item 5 is the evidence. Minor |
| C-10, D-2 | fixed (P619, P683) |
| A2 defects 7, 8, 9, 11 | fixed (RT22, RT24, RT25, RT51) |
| B2 left-overs: two-sided floor rule; floor per run; P13 p(argmax) < 0.5 flag; H0/H1 hint in Phase 0 | **not addressed** (all minor; not declined) |
| B2 "42% template-specific" | fixed (RT25; D397) |
| D2 left-overs: offsets 0/len boundaries; `minLength`/`readOnly`/untyped `enum` rows | **not addressed** (minor) |
| **RT defects 1–10, 12, 14** | fixed |
| RT11 (P12 row states the tie convention) | partial: D290 states it, RT31 does not |
| RT13 (P13 run 2 5/60; P11 W1 text and 31/42 control) | **not addressed** (minor) |
| RT15 (`jevdocs` symlink in `.gitignore`) | **not addressed**: `.gitignore` has no entry, and `scripts/redteam/jevdocs` is a symlink into `/private/tmp/…` (minor) |
| Agents :164 "never a guess" | fixed |
| Agents :149 "confidence depends on the option count" | not addressed (mirrors D70; minor) |
| Agents :60 "Secrets live only in Infisical" vs the Jevson `.env` | not addressed (minor) |
| Admin :67 | fixed ("API key obtained — store it in Infisical") |

### 3d. B3 doc changes

| probe | change | status |
|---|---|---|
| 1 | out-of-sample numbers; label condition (ii) unconfirmed | done (D394–397, as a Phase 0 variant); **R6 and P98 not propagated (3a)** |
| 1 | grid-top behaviour | partial: "Phase 0 records whether the grid top binds" (D399). The 5-hundredth band at 0.45 is not stated (minor) |
| 1 | probe 4 corpus with split-prone mentions (initials, defined terms, acronyms, e-mails) | partial: role nouns only (P211; minor) |
| 1 | report splits separately; "if none, (ii) untested" | splits are separate (P211). An untested (ii) is handled implicitly by the choice rule (minor) |
| 1 | non-transitive rate is template-dependent | done (D397) |
| 2 | P18 numbers; partial-only sources as a limit | done (D325–326; P205 probe 8). `allow_partial` not adopted; a stated limit is used instead |
| 3 | D5.1 P19 sentence | done (D317) |
| 3 | Phase 0 re-test with same-role distractors | **not addressed** (minor; this is also why "closed by evidence" is O) |
| 4 | choice band 0.10; §2.3 jitter; measure on real enums | done (D291, D92, D484 "Phase 0 reports") |
| 5 | flag at ≥ 0.56 only; replace 0/40 with the split; Phase 5 corpus with processing notes; retarget the wording | done (D410, P473, P492) |

### 3e. D3 fixes

| check | status |
|---|---|
| 1 async | done (D533, D545; P355–356, P372). `aclose()` for per-loop clients unstated (minor) |
| 2 graphemes | done (Unicode 17.0, differential test: D428, P274). `Result.versions` still omits the NFC `unicodedata` version (minor) |
| 3 RFC 8785 | done (D607, P358) |
| 4 normalisation rows | done (D234–239: sibling merge, 3-branch `anyOf`, one-member Enum, Decimal string, discriminator; P317 `$defs` config). **"`multipleOf` checked in decimal arithmetic" is not addressed:** D240 keeps `multipleOf` for `jsonschema` final validation, so float fields with `multiple_of=0.01` get false `satisfies_schema=False` on ~11% of valid cent values [L18]. Minor, because it is conservative |
| 5 absence | done (D379–383) |
| 6 tool schema | done (D498, P414) |
| 7 pin | done (D230, P630). CI at the floor and at latest is unstated (minor) |

---

## 4. docs/REDTEAM.md consistency

- **Tags.**
  - Every DESIGN and PLAN tag resolves.
  - Every named script exists.
  - The key scan over 218 files found 0.
  - The round-3 log row matches A3/E3: 209 = 201 S / 5 O / 3 W; 2 blockers, 19 major, 5 minor; 1,261 requests.
- **Defects (all minor):**
  1. P18 (RT37): "3–5 competitors" should be 4; "≥ 60 documents per condition" should be 72 (FULL/PARTIAL) and 36 (DOCPARTIAL).
  2. P19 (RT38): "no decision changed" should be "1/48 absent-case decision differed (MIX committed a context option)".
  3. P22 (RT40): "every saved candidate choice (r1 P5/P9…)". P9 contributes none, and r2's 872 candidate choices are excluded (pooled 2.6%). Also, **P22 is a round-4 probe**: the P header (RT16) and the round log do not mention round 4 or its 3 requests, P22 sits before P21, and `r4/raw/` is empty.
  4. P21 (RT41): add "27–28/60 at the adopted p ≥ 0.56".
  5. L19 (RT69): "deliberately buggy" should be "a first-draft segmenter with a real GB11 bug".
  6. L21 (RT71): "silently rounded elsewhere" should be "by `jcs` and both JS packages".
  7. V-confidence (RT86): "option-count-dependent formula" is an inference (see 1b).
  8. X3 (RT104): add PyPI `jev`, `finetuningsingh/jev-extract`, and `dangquan1402/jev-extract` (all used in D624).
  9. RT11 and RT13 from A3 (P12 tie convention; P13 run 2; P11 W1 wording) are still open.
  10. RT10 "snapshot is not committed": `jevdocs` is not in `.gitignore`.

## 5. Agents/CLAUDE.md and Admin/README.md vs Revision 6

- **Agents :146–167.** Consistent with Revision 6 on:
  - noul without confidence;
  - 2–255 options / 2–10 levels;
  - most probable level;
  - 62% vs 0%;
  - limits;
  - price;
  - latency;
  - :164 (now "rather than a confident guess (abstention is measured, not guaranteed)");
  - :165 source trust.
- **Agents, minor residues:**
  - **:150** "jitter (usually ≤ 0.05; up to 0.37 on ambiguous pairwise questions)" omits the Rev 6 choice jitter (p90 0.11, up to 0.21; D92, D454). Add "choices up to 0.21".
  - **:154** "Cannot do … step-by-step reasoning" vs D100 "does not generate explanations of its reasoning [V-systemone]".
  - **:149** option-count formula (as D70).
  - **:60** Infisical-only vs Jevson's `.env` (D603, RT7).
- **Admin.**
  - :22 and :67 are consistent.
  - **:42** (E3 #25, not addressed): "values traceable to the source, typed abstention when the source doesn't support an answer" should be "source-selected values traceable to a verified span, measured abstention…" (minor).
  - :88 price is consistent (V-models).

---

## 6. Verdict

- Tag verdicts: 317 S, 7 O, 1 W, 0 U; all minor.
- Every round-3 blocker is addressed.
- Of the 19 E3 majors, 15 are addressed or mostly addressed, with minor residues. The 4 partial ones (#7, #12, #13a, #8 detail) leave only minor residues, for the reasons given above.
- One new **major**: the Revision 6 entity-rule change was not propagated to R6 (D514) or P98, and D40 is related.

**CONVERGED: no.** One major remains, and it is a three-line text fix (section 3a). With it applied, no blocker or major item remains in this audit's scope.
