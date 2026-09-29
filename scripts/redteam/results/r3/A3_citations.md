# A3: Citation audit of Revision 5 (red-team round 3)

**Scope.** Working tree on branch `docs/revision-3-decisions`: `DESIGN.md` (735 lines), `PLAN.md` (883), `README.md` (49), `docs/REDTEAM.md` (108), `Agents/CLAUDE.md`, and `Admin/README.md`. No design doc was edited.

**Method.** Every number attached to a new Revision 5 tag was recomputed from `results/r2/raw/*.json` with independent code (scratchpad `r3/recompute/p10.py` plus inline scripts), not with the probe's own analysis code. I re-ran three scripts with their fixed seeds:
- `check_r3_calibration_bar_empirical.py`: reproduced byte-for-byte.
- `check_r2_sim_bar_uniform2.py`.
- `check_r2_sim_bar_uniform.py`.

Vendor pages were read from `jevdocs/`. The launch blog was fetched live on 2026-09-29.

**Line references.** `D` = DESIGN.md, `P` = PLAN.md, `R` = README.md, `RT` = docs/REDTEAM.md.

## Summary

**Tag instances.** There are 212 bold tags: DESIGN 140, PLAN 72, README 0. Three of them are example tags inside the evidence rule (D9 ×2, P5), which leaves **209 claim tags**.

| verdict | count | where |
|---|---|---|
| **SUPPORTED** | 201 | — |
| **OVERSTATED** | 5 | D70 V-confidence, D100 V-models, D320 P11, D418 L11, D581 L7 |
| **WRONG** | 3 | D285 P12, D326 P11, D480 L13 (first instance) |
| **UNSUPPORTED** | 0 | — |

**Round-2 traceability.**
- E2 blockers and majors (24): 18 addressed, 6 partial.
- E2 minors m1–m14: all addressed.
- a1–a7: 6 addressed, 1 partial (a3: "never a guess").
- A2 non-S tag rows: 21 of 24 fixed; 3 not fixed or partly fixed (rows 19, 40, 80).
- Of A2's round-1 NOT-ADDRESSED items, D-10 (the `format` caveat in the Constraint tier) is still not addressed, and C-5 (missing prior art) is still partial.

**REDTEAM defects.** 15 found (section 4).

---

## 1. Tag verdict table

### 1a. Tags new in Revision 5, and every number attached to them (recomputed)

| # | line | claim | tag | recomputation / evidence | verdict |
|---|---|---|---|---|---|
| 1 | D56 | released September 2026, early access | V-launch | Live fetch of typesafe.ai/blog/introducing-system-one-models-and-jev: "Jev, available today in early access"; "Today, we are opening early access". **The page now shows "Sep 28, 2026"**, whereas round 1 (r1/A row 3) recorded "Sep 15, 2026". Either date is September | S (date drift noted in RT defect 12) |
| 2 | D70 | "The vendor describes its probabilities as calibrated" | V-systemone, V-primer | `concepts__system-one.md:21` "trained for calibrated decisions: their probabilities are optimized against outcomes to reflect uncertainty"; `introduction__machine-learning-primer.md:7` "trains decision models with calibrated probabilities", :37 "returns decisions and calibrated probabilities", :57-61. **Both pages do say it.** Both also say calibration describes groups, not single answers | S |
| 3 | D70 | `confidence` has "a formula that depends on the number of options" | V-confidence | `confidence.md:149` "a statistic computed from the probability distribution"; :138 gives only a *demo approximation* "(3 × largest probability − 1) / 2 … for three options". The option-count dependence is an inference, as A2 row 19 already said. "(some vendor pages also call it calibrated)" is S: `date_extraction_cookbook.md:359`, `how-to-build…:293` | **O** (minor) |
| 4 | D71 | sums 1.00 or 0.99 (4 of 630) | L17 | `check_r2_rounding.txt`: `{'0.99': 4, '1.00': 626}` | S |
| 5 | D88 | ~18 / ~27 / ~80 tokens per option | P14 | raw `r2_source_ceiling.json`: 4,672 / 6,854 / 20,114 over a 2-option baseline, 255 options, giving 18.3 / 26.9 / 78.9. The context format is `PROSE[j:j+70][s]PROSE[j+70:j+140]`, i.e. ±70 (`probe_r2_source_ceiling.py:71`) | S |
| 6 | D88 | ~108,000 chars of prose, ~62,000 of business text, with a realistic 255-option question | P14 | raw: `max_state_chars_accepted` 108,437 (B) and 62,343 (A); first rejected 109,218 and 63,125. The "prose" corpus is DESIGN.md text | S |
| 7 | D92 | range ≤ 0.05 for 90% of 200 contract questions over 10 repeats | P12 | raw `r2_tie_rule.json`: 200 q × 10 obs; range ≤ 0.05 in **184/200 = 92%**; p90 = 0.05 | S (slightly understated) |
| 8 | D92 | pair nouls up to 0.37 (0.22–0.59, sd 0.13) over 12 identical calls; 16/1,824 flipped between runs | P12 | raw `r2_jitter_entity.json`: "M. Castell for the Landlord" / "the agent": 12 obs, min 0.22, max 0.59, pstdev 0.133. The range is 0.37 within the last 10 calls alone. A/B recompute: 1,824 pairs, **16 flips**, max diff 0.26. Caveat: the 6 docs were chosen for high A–B difference (B2) | S |
| 9 | D93 | exact 0.50 once in 2,000; 1.1% within ±0.05; 2/200 flipped, both hedged | P12 | recompute: exact 50 = 1; 45–55 inclusive = 23/2,000 = 1.15%; flips 2 (`cap`, `excl`, both level `amb`) | S |
| 10 | D107 | 10-level: 8 of 12 had no level > 0.5 | P13 | raw `r2_score_decode.json` run 0: 8/12; run 1: 8/12 | S |
| 11 | D68, D287 | round(score) vs argmax disagree 8/60 | P13 | run 0: 8/60 (6 at 10 levels). **Run 1: 5/60** (3 at 10 levels). The docs cite run 0 only | S (add the second run) |
| 12 | **D285** | "the ±0.05 band removed every true↔false flip across 10 identical calls on 200 questions at ~1% of answers" — attached to the rule "true iff p ≥ 0.55; false iff p ≤ 0.45" | P12 | The evidence used **|p − 0.5| ≤ 0.05 as the tie**, so 0.45 and 0.55 are ties (`probe_r2_tie_rule.py:12`). Under the rule as DESIGN writes it (0.45 = false, 0.55 = true; PLAN:273 "p = 0.55 is true"), recomputed on raw: **1/200 true↔false flip remains** (`cap`: 0.45 → false, 0.56 → true). Tie rate 17/2,000 | **W** |
| 13 | D312 | ±40 window: right occurrence 40/40; text alone 22/40; lone wrong-role occurrence committed 48–83% | P15 | recompute from `r2_opaque_ids.json`: F2 40/40, F0 22/40. Absent sets committing the wrong occurrence: F2 22/40 (55%), F3 33/40 (82.5%), F4 19/40 (47.5%). **The adopted ±40 format (F2) gives 55%** | S |
| 14 | **D320** | "Without this wording lone partial spans were committed 32/42 times; with it 0/42, with all 42 correct kept" | P11 | Numbers correct (32/42 base; W1 0/42, a-W1 42/42). But "this wording" is DESIGN's template ("the complete *<field>* as written in the source; a partial value — for example … — is not acceptable"). **The tested wording W1 was different:** "…the {field}, complete and exactly as written in full in the text?", plus a changed `none_of_these` description (B2 lines 173-175). The paired control rerun gave 31/42, not 32/42 | **O** |
| 15 | D322 | hint: abstention 32/36 → 35/36; present 36/36 → 33/36 | P16 | `r2_scoping_hint.json` report: H0 32/36 & 36/36; H1 35/36 & 33/36; McNemar p = 0.25 (B2) | S |
| 16 | D326 | 84/84 wrong-role abstained; 2/42 false abstentions | P11 | report b1 42/42 + b2 42/42 abstain; a S2 abstain 2/42 | S |
| 17 | **D326** | "behaved the same as the candidate among **3–4 competitors**" | P11 | `opts4` has 3 or 4 **candidates in total**: the candidate plus 2–3 competitors (84 cases each, recomputed; script line 16 "3 same-type competitors" at most). S2 and S4 disagreed 1/42 (a), 0/84 (b), 5/42 (c). RT P11's "among 3–4" is correct; DESIGN's wording is not | **W** (count) |
| 18 | D379, D444, D640, D691 | pair jitter up to 0.37 | P12 | as row 8 | S (×4) |
| 19 | D388 | plain CC 12–13%; Rev 3 1.5–3.0%; internal rule 3.8–4.5%, mostly splits; two-directional 0/133, 0/134; correct 113/133, 109/134 vs 117 | P10 | independent recompute: plain 16/133 = 12.0%, 17/134 = 12.7%; rev3 2/133, 4/134; internal @0.30 5/133 (2 merges / 3 splits), 6/134 (1/5); two-directional @0.30 0/133, 0/134 silent, 113/133 and 109/134 correct, 20 and 25 unresolved; plain correct 117 both runs | S. Note: 109/134 = 0.813 is below the ≥ 0.85 go band, which the docs do not mention |
| 20 | D390 | rule selected 0.30 (grid top), 0.20 on a subset | P10 | recompute: ALL A/B → 0.30; old p06 subset → 0.20. Same-pairs ≤ 0.40: 9/488 (A) | S |
| 21 | D392 | consistent-but-wrong partition undetectable | P6, P10 | Okoro merge at 0.82–0.95 in both runs (B2 e.4) | S |
| 22 | D418 | shorthand accepted 63,855–76,510 forbidden boundaries "across 15 of 20 classes" in 316,621 positions | L11 | `check_r2_grapheme_rule.txt`: TOTAL 316,621; FA 76,510 in the (Mn,Me) reading, over **15** classes; FA 63,855 in the (Mn,Mc,Me) reading, over **13** classes (Tamil and Mc-misc drop to 0) | **O** (minor: "13–15 of 20") |
| 23 | D419 | no grapheme API before 3.15 | L11 | The 3.11 output shows "stdlib unicodedata has grapheme API: none". 3.12–3.14 are asserted in D2 (Docker), but **no output file for 3.12–3.14 is committed**. `check_r2_grapheme_py315.txt`: 3.15.0rc2, 0/3000 in every class | S (by report) |
| 24 | D474 | tie band inside which decisions flipped; entity pairs measured with a 0.5 boundary | P12, P10 | as rows 9 and 19 | S (×2) |
| 25 | D480 | empirical: 2,202 top-label p, 49% at 1.00; n = 1,000 calibrated 100%, 5-pt overconfident 0% | L14 | re-run: `n=2202 mean=0.936 share==1.00 0.49`; n = 1000 δ = 0 1.00, δ = 0.05 0.00 (R = 150). Caveats: the pool mixes every choice and score answer in r1/r2 raw, including repeated identical requests and author-written pilot prompts; only condition 1 is simulated | S |
| 26 | **D480** | "on a uniform(0.5, 1) distribution the same bar at n = 1,000 passed a calibrated model **0–50%**" | L13 | re-run of `check_r2_sim_bar_uniform2.py` (seed 11): **U n=1000 → 0.0; Beta(18,2) → 0.5**; n = 3000 U 0.995, B 1.0. `check_r2_sim_bar_uniform.py` (97.5th): U 0.0, Beta 0.257. **Uniform passed 0%.** The 50% belongs to Beta(18,2) | **W** |
| 27 | D480 | τ − 0.02 rule passed an 8-pt-overconfident model 96–100% | L13 | `check_r2_calibration_bar.txt` δ = +0.08: P:tau.8 1.000 (all four cells); P:tau.9 0.994 / 1.000 / 0.964 / 0.990 | S |
| 28 | D581 | "the leanest **measured** template needs ~18k tokens for 435 questions, a verbose one ~58k" | L7 | RT L7: "(cl100k proxy)". These are tokenizer estimates, not Jev `usage` | **O** (minor) |
| 29 | D707–717 changelog | 0/133, 0/134; up to 0.37; partials 32/42 → 0/42; 40/40 vs 22/40; L11; L13/L14; P14; L17 | P10, P12, P11, P15, L11, L13–14, P14, L17 | as above | S (×11). Row D719 "Citations … corrected" is overstated, because rows 3, 30 and 31 below and RT defects 2–6 persist (untagged, see section 2) |
| 30 | PLAN P204 | ±6 points (−6.2/+5.1); correlation ≈ −0.8 | L12 | `check_r2_phase0_oc.txt`: Wilson 5.66 (lower gap 6.21, upper gap 5.11); corr −0.793 | S (×2) |
| 31 | P208, P765, P805 | two-directional rule, in-sample | P10 | as row 19 | S (×3) |
| 32 | P270, P807 | CR\|LF, ZWJ, flags, Hangul, Indic; "wrong in 15 of 20 classes" | L11 | 15 FA classes in the Mn,Me reading, plus 1 false-reject class | S |
| 33 | P300, P312, P772 | normalisation incl. Decimal, single-member Enum | L3, L16 | D2 §7 table: Decimal anyOf; 1-member Enum `$ref` | S (×3) |
| 34 | P470, P477, P480, P804 | Phase 5 aligned with Phase 0; ≤ 6/300; ≤ 7 FP / ≥ 130 TP | L15 | `check_r2_phase5_bars.txt`: N=300 pass iff x ≤ 6; n=300 FP ≤ 7; n=150 TP ≥ 130 | S (×4) |
| 35 | P455, P189, P736, P762, P796 | occurrences + context; repeated-text cases | P15 | as row 13 | S (×5) |
| 36 | P766, P769, P801, P369 | jitter; tie band; hundredths | P12, P1, L17 | as rows 7–9, 4 | S (×4 lines, 6 tags) |
| 37 | P767, P797, P798, P841 | complete-value template; 84/84; lone candidates safer asked | P11 | as rows 14 and 16. P797 has the same wording caveat as D320 | S |
| 38 | P768 | preflight on declared maxima | P14 | — | S |
| 39 | P803 | the bar's power depends on the distribution | L13, L14 | holds even with row 26 corrected | S |
| 40 | P841, D694 | score value = most probable level | P13 | B2 probe 4 CONFIRMED | S (×2) |

### 1b. Tags carried over from Revision 4 (A2 verdicts re-checked)

All carried-over rows that A2 marked S still read the same and remain **S**: X1–X8, V-index, V-api, V-primitives, V-models (limits, price, rate, English), V-jagged, V-advanced, V-fanout, V-preparsed, V-cookbooks, V-consistency, V-sdk, V-sdk-constants, P1–P9, L1–L4, L9, L10. Status of A2's non-S rows:

| A2 row | Rev 5 line | status |
|---|---|---|
| 15 cookbooks "measured on jev-1.12" | D60 "Several vendor cookbooks set `jev-1.12`" | fixed |
| 19 calibration misattributed to V-confidence | D70 now V-systemone / V-primer | fixed; the formula inference remains (row 3) |
| 28, 38 price / rate on V-api | D84, D96 → V-models (`models.md:13-14`) | fixed |
| 39 request-id "every" | D96 "every response whose headers were captured" | fixed |
| **40 images / step-by-step on V-jagged** | **D100 → V-models.** `models.md:16` covers images, but **models.md never mentions reasoning**. The nearest vendor text is `concepts__system-one.md:23` "do not … generate explanations of their reasoning" | **O** (still misattributed; the RT V-models row repeats it) |
| 45 advocacy / injection merged | D103 separated (0.91 / 1.00) | fixed |
| 50 "refuses everything interesting" | D152 lists specific refusals | fixed |
| 59 "identically" | D310 "equivalently" | fixed |
| 62 "under-specified scope" | D340 "superseded due dates" | fixed |
| 68 CO/Co | D381 CAT/cat (`check_span_unicode.txt:48`) | fixed |
| 82, 156 "billed" retries | D533 "may be billed"; P771, P790 | fixed |
| 86 ~2.5k | P14 per-option costs | fixed |
| 87 ~28 tok / pair via P6 | D581 L7 | fixed (row 28 caveat) |
| 90 n³ via P6 | D581 untagged arithmetic | fixed |
| 95 playground "reference implementation" | D608 "community example" | fixed |
| 110 D623 | removed | fixed |
| 119 Phase 4 novelty | P29 "we found in no single existing project" | fixed |
| 124 L5 at n = 150 | P204 L12 | fixed |
| 131 margin 0.10 | P369 0.20 | fixed |
| 32 "110 questions" | D92 "40 … × 25 × 2 sessions" | fixed (count now right) |
| 77 ±0.05 | D444 "usually ≤ 0.05 … up to 0.37" | fixed |
| **80 L6 n = 300 figures** | removed from DESIGN. The **RT L6 row still says "depending on binning"**; A2 asked for "and confidence spread" | partial (RT only) |

---

## 2. Untagged factual claims (DESIGN rule at D9)

| # | where | claim | fix |
|---|---|---|---|
| U1 | D58 | "State is text or JSON. Questions are a map from key to a typed question." | add **[V-api, V-models]** (`models.md:16`) |
| U2 | D332 | "Jev's probabilities are relative to the options it was handed" | add **[V-jagged]** ("the Choice is relative") |
| U3 | D361 | "Jev's distribution is relative to the offered set" | add **[V-jagged]** |
| U4 | D419 | "vendored table (~9 KB)" | **[L11]**; say "~9 KB compressed (32 KB JSON, 2,194 ranges)" (`check_r2_grapheme_rule.txt` "JSON bytes 32192, zlib 9100") |
| U5 | D432 | Constraint tier "holds unconditionally: yes" via `jsonschema` 2020-12 | still no caveat that `format` is unchecked by default **[L10]** (A2 D-10, round 1). Append "(`format` checked only with jsonschema's format extras **[L10]**)" |
| U6 | D638 (§10) | "~62k–108k characters of source" | tag **[P14]**, and add B2's finding that with ±70 context windows state is left with ~12k tokens (~30k–50k chars) |
| U7 | D84 row | rate limits | omits `models.md:24` "can change without notice" (A2 A-19, still partial) |
| U8 | R7, R28, R33 | constrained decoding; vendor pattern and open projects; source steering | README carries **0 tags**, yet **R43 says REDTEAM holds "every factual claim"**. Either tag README or change R43 to "every factual claim in DESIGN and PLAN" (A2 (b)18, not addressed) |
| U9 | D719 | "Citations … corrected" | "mostly corrected; residuals in docs/REDTEAM.md" |
| U10 | D203 | "A typical object resolves in 1–3 Jev calls" | a design estimate; acceptable |

---

## 3. Traceability of round-2 findings

### E2 blockers and majors

| E2 | status | where in Rev 5 |
|---|---|---|
| 1 | addressed | DESIGN §3.5 (D241-255); P301, P413, P452 |
| 2 | addressed (different design) | runtime `Unresolved(too_many_candidates)`; zero candidates → absent, no call (D328, D346-347; P459, P473) |
| 3 | addressed | P311 "except union discrimination" |
| 4 | addressed | D549-555 `decisions` by node id, `decided_by` incl. `llm`, `caller` via `known=` (D508) |
| 5 | **partial** | step execution P346; drafting templates P403; `Cost.llm_*` D561. **Where the draft sits in the adjudication state (which the P7 0/80 depends on) is still unspecified** (grep "draft" in state: none) |
| 6 | addressed | DESIGN §5.2; P184, P303; `Result.versions` |
| 7 | addressed | D465 closed set |
| 8 | **partial** | `PreflightError`, `ExtractorError` added (D453-458). **Residue:** P374 "Cost is populated on … every typed exception", but D458 says only the last four carry `Cost` |
| 9 | **partial** | tie band for choices/scores (D286-287) and sum tolerance (D71) added. **Authority of the vendor `choice` field vs argmax is not stated** |
| 10 | addressed | R3, D7, CLAUDE.md:164 |
| 11 | addressed | R24 scoped to source-selected fields; R33-34 |
| 12 | addressed | P227 (probe 1); P200 (screen rates) |
| 13 | addressed | P470 (Phase 5 uses Phase 0 bands, L15) |
| 14 | **partial** | bar rebuilt and tagged (D475-480). **τ being chosen on the evaluation data is not addressed** (no "fixed before data / held-out half") |
| 15 | addressed | `max_candidates`, `max_candidate_chars`, `max_draft_chars` (D245-247, D577) |
| 16 | **partial** | threshold (bool rule), placement (first decision level), scope (D401). **That the screen noul is itself steerable is not stated** |
| 17 | addressed | D594 (CachingBackend + ReplayLLM, caller directory) |
| 18 | addressed | D523-529 async; per-key limiter D535; P372 |
| 19 | addressed | D290, P553 (enum arrays survive); D237 flat `allOf` |
| 20 | addressed | DESIGN §5.6 |
| 21 | addressed | P424 (human labels, two-sided); the LLM is not named (minor) |
| 22 | addressed | P477 (constructed misses; N ≥ 300) |
| 23 | addressed | P369 (margin ≥ 0.20; fail > 2%) |
| 24 | addressed | P420 (> 3/80); per-variant cap omitted |

### E2 minors and Agents/Admin items

| item | status | where |
|---|---|---|
| m1 | addressed | grep finds no bare § in PLAN |
| m2 | addressed | P62 |
| m3 | addressed | P367 |
| m4 | addressed | P204 |
| m5 | addressed | P479 |
| m6 | addressed | P360 |
| m7 | addressed | P188 |
| m8 | addressed | P208, P220 |
| m9 | addressed | P463 |
| m10 | addressed | D192, P520 |
| m11 | addressed | D203 |
| m12 | addressed | D464 |
| m13 | addressed | P346 |
| m14 | addressed | R28 |
| a1 | addressed | CLAUDE.md:17, :37 |
| a2 | addressed | :159 |
| a3 | **partial** | :164 fixed the "every value" claim but says a value the source does not support comes back "absent or Unresolved, **never a guess**". That contradicts DESIGN §1.1/§6 ("measured, not guaranteed") and P7 (20/20 steered commits) |
| a4 | addressed | :125, :242, :260 |
| a5 | addressed | :150 |
| a6 | addressed | Admin:22 reworded; account row "Enrolled (early access)" |
| a7 | addressed | Admin:42 |

### A2 non-S rows, defects, and round-1 items A2 listed as NOT ADDRESSED or PARTIAL

**Fixed:**
- Tag rows: see 1b.
- Round-1 items:
  - A-6: D587-588, empty key.
  - A-40: D321, P320.
  - A-43: D71.
  - C-1d: D488 uses a one-field tool schema.
  - C-17: P787.
  - D-4: `ordinal: true`.
  - D-6: Brier, D480.
  - E-34: D464.
  - E-40: **the decline is now recorded** at P27 and P789, with the risk row at P759. E-40's alternative (unions right after Phase 3) is still not discussed.
- A2 defects:
  - defects 1–4: V-primer, V-models, V-cookbooks and V-consistency rows.
  - defect 5: P1 count.
  - defect 12: L13 and L14 added.
  - defect 13: L7.
  - defect 14: X2 and X3 now list Reducto, AWS BDA and jod.
  - defect 10: request-id wording.

**Still open:**
- **D-10** (U5): not addressed.
- **A-19** (U7): partial.
- **C-5**: PyPI `jev`, other `jev-extract` repos, and entity_alignment as the §5.7 precedent are still missing from DESIGN §9. Partial.
- **C-10** (ask TypeSafe about the name before release): not addressed.
- **D-2**: P670 says "adjacent to a surrogate pair", not "inside a surrogate pair is rejected". Partial.
- **A-37** date parts: deferred at P883, which counts as declined with a reason.
- **A2 (b)18** (U8): README tagging vs the "every factual claim" wording is not addressed.
- **A2 defects 7, 8, 9, 11**: not addressed (section 4, items 4–7).

### B2 doc changes

| probe | change | status |
|---|---|---|
| 1 | cross-component condition | done (D385) |
| 1 | qualify "absence of evidence" | done (D386) |
| 1 | extend grid | done (to 0.45) |
| 1 | record splits and merges separately | done (P208) |
| 1 | two-sided floor rule | **not done**: the floor rule is still the one-sided same-pair ≤ 2% rule; only the verdict uses silent-wrong |
| 1 | compute the floor on ≥ 2 runs | **partial**: the flip rate is recorded, but the floor is not computed per run |
| 1 | "42% is template-specific" | **not done** (D379: 38–42% on p06 docs vs 8–13% on the new docs) |
| 2 | complete-value wording | done (with the row 14 caveat) |
| 2 | partial stratum | placed in probe 8 (P202), not probe 2; acceptable |
| 3 | band | done, but the boundary is inconsistent (row 12) |
| 3 | cache replay | done (D444) |
| 3 | "rare ties" | done (D93) |
| jitter addendum | — | done |
| 4 | keep argmax | done |
| 4 | `legend` echo | done |
| 4 | no zero-probability claim | done |
| 4 | report `p(argmax)` and flag < 0.5 | **not done** |
| 4 | "≤ 7 levels" | softened to "prefer narrow rubrics" |
| 5 | per-option costs, character ceilings, preflight on descriptions | done |
| 5 | context-window ceiling | **not stated** (U6) |
| 6 | context windows | done (D312) |
| 6 | offer all occurrences | done (D312) |
| 6 | 3× cost | done (D88) |
| 7 | hint not a fix; scope from the caller | done (D322, `x-jevson.source.scope`) |
| 7 | measure H0 vs H1 in Phase 0 | **not done** |

### D2 doc changes

| check | status |
|---|---|
| 1 grapheme | done (D418-419, P270). Missing: "offsets 0 and len are always boundaries" and "a combining mark after `\n` is a valid start" (minor) |
| 2 | done (P204, P227; borderline flag dropped) |
| 3 | done (tie-safe bins, one-sided, Wilson rule; Brier) |
| 4 | done (option a, P470) |
| 5 | done (P477) |
| 6 | done (P480) |
| 7 | done (D229-239, D253). `minLength`, `readOnly`, untyped `enum` are not named (minor) |
| 8 | done (D71, D286, D594). Numeric option-id display order is not stated (minor) |

---

## 4. docs/REDTEAM.md defects

Every tag used in DESIGN and PLAN is defined in REDTEAM. Every script REDTEAM names exists (checked by filename). A key search over the repo (value compared in memory) found 0 hits outside `.env`.

1. **RT57 L13 (WRONG).** "with probabilities uniform on (0.5, 1) … passed a calibrated model 0–50%". Uniform gave 0.00; 0.50 is Beta(18,2). Fix: "uniform(0.5,1): 0% at n = 1,000, 99.5% at n = 3,000; Beta(18,2): 50% and 100%".
2. **RT57 L13 (OVERSTATED).** "the Wilson rule at τ passed calibrated ≥ 0.98, 2-point 0.16–0.55, 5-point 0.00". These are the `P:ALT` columns, which is the **Wilson rule AND debiased ECE ≤ 0.03** (`check_r2_calibration_bar.py` docstring), not the Wilson rule alone and not the adopted bar. Say so. Also, `check_r2_sim_bar_uniform*.py` have **no committed outputs and no docstrings**, and `…uniform.py` uses the 97.5th percentile.
3. **RT73 V-models.** "no images or step-by-step reasoning": `/models` has no reasoning statement. Move it to V-systemone (`concepts__system-one.md:23`).
4. **RT45 L1.** "digest is identical on Python 3.11 and 3.12 (… digest in NOTE)". The NOTE lists a digest for **3.11 only** and *different* dump hashes (9aede147… vs b1646456…). Unsupported (A2 defect 11, not addressed).
5. **RT22 P3.** "~70k rejected", "~34k single question rejected" are still unmarked extrapolations (A2 defect 7).
6. **RT24 P5.** "130 trap … documents" should be 70 docs yielding 60 present + 70 absent cases (A2 defect 8).
7. **RT25 P6.** The lease-template gold caveat is still missing (A2 defect 9).
8. **RT55 L11.** "63,855–76,510 … in 15 of 20 classes" should be "13–15 of 20", depending on the reading.
9. **RT59 L15.** "abandons with P ≈ 0.64 where Phase 0 says conditional" is one point (false abstention 0.15). Across the band the range is 0.26–0.74 (`check_r2_phase5_bars.txt`).
10. **RT58 L14.** Add the caveats: the pool mixes choice and score answers from author-written pilots, including repeated identical requests; R = 150 replicates; only condition 1 is simulated.
11. **RT31 P12.** State that the band evidence treats 0.45 and 0.55 **as ties**. DESIGN's rule does not (row 12).
12. **RT70 V-launch.** The page currently shows "Sep 28, 2026"; round 1 recorded "Sep 15, 2026". Record the retrieval date and the quote.
13. **RT32 P13 and RT30 P11.** Add P13 run 2 (5/60), and P11's W1 wording text with its paired control (31/42).
14. **RT107 round log.** "round 2 found 10 items unaddressed and 7 partly fixed" matches neither A2 (≈ 8 NOT ADDRESSED including the unrecorded E-40, ≈ 19 PARTIAL) nor E2 (3 partly fixed). Cite the counts, or reword to "several items unaddressed or partly fixed".
15. **RT10.** "the snapshot is not committed". `scripts/redteam/jevdocs` is a symlink into `/private/tmp/…/scratchpad/jevdocs` and is **not in `.gitignore`**. `scripts/` is untracked, so committing it would commit a dangling symlink. Add `scripts/redteam/jevdocs` to `.gitignore`.

---

## 5. Agents/CLAUDE.md and Admin/README.md

**Agents/CLAUDE.md** (Jev block :146-155, Jevson block :157-167, :17, :37, :50, :64, :125, :242, :260):
- The following agree with Rev 5 and with the evidence:
  - noul has no confidence;
  - 2–255 options and 2–10 levels;
  - score = most probable level;
  - jitter "usually ≤ 0.05; up to 0.37";
  - 62% vs 0%;
  - limits 32k / 64k;
  - p50 "~0.15–0.3 s" (P8: 0.149–0.223 s small state; 0.28–0.30 s at 20k);
  - $0.042 per M input tokens.
- **:164 "never a guess"** overclaims (see a3). Fix: "…comes back as *absent* or a typed `Unresolved` rather than a guess — measured, not guaranteed; a hostile source can defeat it."
- :149 "`confidence` … depends on the option count" carries the same inference as row 3 (minor).
- **:60 "Secrets live only in Infisical"** contradicts Jevson's practice. The key is in `Jevson/.env` (verified to exist and to hold `TYPESAFE_API_KEY`), and DESIGN §8.3 and RT7 say so. Either say "Infisical, plus a gitignored local `.env` for Jevson probes until PLAN Phase 11", or remove the local copy.

**Admin/README.md:**
- :42 Jevson row is consistent with Rev 5 ("Design — Phase 0 next").
- :22 to-do: reworded ("account and key obtained; build the spike"). Consistent.
- **:67 "TypeSafe / Jev | Enrolled (early access) | API key in Infisical".** Nothing in any repo evidences that the key is in Infisical:
  - Jevson documents only the gitignored `.env` (RT7, D590 "Fetching the key from the team's Infisical project is planned tooling (PLAN Phase 11)").
  - Admin and Agents contain no Infisical secret reference for TypeSafe.
  - The claim is **unverifiable from the repos**. The owner should confirm it, or write "API key in local `.env` (Jevson); Infisical planned".
- Out of scope but inconsistent with Rev 5: `Admin/PROJECT_THESIS_SSOT.md:208` ("calibrated confidence") and `:776` (jevapi.dev as API reference, "released 15 September", "~64k state window").
