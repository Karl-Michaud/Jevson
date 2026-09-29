# A5: Citation audit of Revision 7 (red-team round 5)

**Scope.** Working tree on branch `docs/revision-3-decisions`: `DESIGN.md` (798 lines), `PLAN.md` (910), `README.md` (49), `docs/REDTEAM.md` (120), `Agents/CLAUDE.md` (:60, :146–167), `Admin/README.md` (:22–23, :43, :68, :89). No design doc was edited.

**Method.**
- No Revision 6 snapshot exists: `git diff main` compares against Revision 2.1, and the file history holds only Revision 3. Changed sentences were therefore identified from the DESIGN §13 "Revision 7" table (D725–743) and from each A4/E4 fix text, then re-read in place.
- Every number in the P11, P12, P13, P18, P21, P22, L17 and L19 rows was recomputed from raw JSON or outputs with independent code (scratch scripts in the session scratchpad `r5/`). Integer hundredths were taken via `Decimal(repr(v))`, not float arithmetic.
- Key scan: 223 files, the key found in 0 (compared in memory; only the count was printed).
- Line refs: `D` = DESIGN.md, `P` = PLAN.md, `R` = README.md, `RT` = docs/REDTEAM.md.

## Summary

**Tag instances.**
- DESIGN has 216 bold tag instances and PLAN has 116; README has 0.
- Three are example tags inside the evidence convention (D9 ×2, P5), which leaves **329 claim tags**: DESIGN 214, PLAN 115.
- All 64 tags used are defined in RT. L5, L6 and L8 are defined but unused, which is harmless.
- Every script RT names exists.

| verdict | count | instances |
|---|---|---|
| SUPPORTED | 324 | — |
| OVERSTATED | 5 | D71 L17 (new in Rev 7), D489 P22, D742 P22, P274 L19 (carried), P868 P19 (carried) |
| WRONG | 0 | — |
| UNSUPPORTED | 0 | — |

**All five are minor.**
- No blocker or major item remains in this audit's scope.
- Every A4 item and every E4 major is addressed in DESIGN. The residues are minor, and none is recorded as declined (section 3).

**CONVERGED: yes** (0 blockers, 0 majors).

---

## 1. Tag verdicts

### 1a. Recomputed rows

| tag | claim | recomputed | verdict |
|---|---|---|---|
| **P11** | wrong-role abstained 84/84; correct falsely abstained 2/42; partials 32/42 → 0/42 with W1; paired control 31/42; correct kept 42/42; 2-option ≈ 3–4 options | `r2_single_candidate.json` report: b1 0/42 and b2 0/42 committed (84/84 abstained); a S2 abstain 2/42; c S2 commit 32/42. `r2_single_candidate_completeness.json`: c S2W0 31/42, S2W1 0/42; a S2W1 42/42 | S (RT30, D326, D334, P821–822) |
| **P12** | exact 0.50 1/2,000; 1.1% within ±0.05; 2/200 flipped; 0.45/0.55-as-ties band removed every flip; range p90 0.05 | `r2_tie_rule.json`: 1/2,000; 23/2,000 = 1.15% (inclusive); 2/200 flip on p > 0.5; 0 true↔false flips under the ≥0.56 / ≤0.44 rule; p90 0.05 (92% ≤ 0.05) | S |
| P12 | entity pairs up to 0.37 (0.22–0.59, sd 0.13); 12/192 flipped; 16/1,824 between P10 runs | `r2_jitter_entity.json`: max range 0.37 (0.22–0.59), population sd 0.133, 12/192 flips. P10 run A vs B: 1,824 pairs, 16 flips (max |Δ| 0.26) | S (D92, D291, D392, D457) |
| **P13** | round(score) ≠ argmax 8/60 (run 1), 5/60 (run 2); no zero-probability level; 8/12 ten-level answers max p < 0.5 | run 1: 8; run 2: 5 with Python `round` (half-even), 6 with half-up; zero-p level picked 0 in both runs; ten-level max p < 0.5 8/12 in both | S. Nit: run 2 depends on the rounding convention; state "Python `round`" |
| **P18** | full among 4 competitors 72/72 both wordings; partial-only 19/72 → 72/72; doc-partial 15/36; addresses and dates abstain | F_W0 and F_W1 72/72; P_W0 19/72, P_W1 72/72; DOCPARTIAL_W1 15/36 (address 6/6, hearing 6/6, guest 3/6, supplier, phone, venue 0/6); 72 main + 36 doc-partial cases | S (D326–327, RT37). A4's W at D325 is **fixed** |
| **P21** | attacks 60/60, all ≥ 0.86, none in 0.45–0.55; benign 28/60 at ≥ 0.55, 27–28 at ≥ 0.56; 16/24 lines; plain 0/66; tie band +5–8% FP, no attacks | pA/pB: attacks 60/60, min 0.86, 0 in band; benign ≥ 0.55 28/28, ≥ 0.56 **27/28** (invoice 14 + e-mail 13/14, contracts 0); arguable 16/24; plain 0/66; band: benign 4/60 and 3/60, plain 4/66, arguable 2/24 (5.0–8.3%) | S (D413, D668, D713, RT40). P203, P476 and P832 say "28/60", which is exact at the tested 0.55; nit: "27–28/60 at the adopted 0.56" |
| **P22** | +1,600 / +2,521 tokens | `r4/outputs/probe_r4_default_budget.txt`: `{"baseline_tokens": 377, "50x120": 1600, "50x120+ctx80": 2521}` | S (D604, P833) |
| P22 | 56/2,154 candidate choices (2.6%) at margin ≤ 0.10: r1 2/490, r2 38/872, r3 16/792 | Independent walk over all `results/r*/raw/*.json` for `none_of_these` distributions: r1 490/2 (p05 240/0, p05b 130/0, p05c 120/2), r2 872/38 (opaque_ids 320/22, scoping_hint 216/3, single_candidate 336/13), r3 792/16 (complete_value 360/5, mixed_desc 432/11). **Reproduced exactly** | Numbers S. **"All/every saved candidate choice" is O** (D489, D742, RT41): the 120 P5 choices whose abstain key is `"none of the above"` (`p05_abstention.json`) are excluded, with 0 at ≤ 0.10 (56/2,274 = 2.5%). The P11-W1 choices are saved without full distributions. Minor. Fix: "over 2,154 saved pilot candidate choices that use a `none_of_these` key" |
| **L17** | 626/630 sum to 1.00, 4 to 0.99; float margins miss 56/91 | `r2/outputs/check_r2_rounding.txt`: `{'0.99': 4, '1.00': 626}`; "56/91" | S (RT67) |
| L17 | **D71 (Rev 7): "the tolerance is min(⌈K/2⌉, 5) hundredths, since at most 1 was observed [L17]"** | L17's 630 answers have **option counts 1–11 only** (`check_r2_rounding.txt`: `{1:1, 2:7, 3:112, 4:263, 5:152, 6:22, 10:37, 11:36}`). A walk of all raw files finds **0 saved distributions with K > 11** (4,794 at K ≤ 11: 4,769 sum to 100 and 25 to 99). The cap is applied up to K = 255, including the default 51-option candidate choice. The same sentence notes that rounding can legitimately move the sum by up to ⌈K/2⌉ | **O (minor)**. The observed sums are far tighter than naive rounding: L17's own simulation gives P(sum ≠ 1) of 0.29–0.59 at K = 11 against ~0.6% observed. So the vendor very likely normalises, and the cap is probably harmless. Untested at K > 11. Fix: "…since at most 1 was observed at K ≤ 11 [L17]; Phase 3 integration checks the sum on a 51- and a 255-option answer before the cap is relied on" (add to P277 or P382) |
| **L19** | 1.1–1.3 KB; 47 lines; 1,187 / 1,093 / 766; 3.15 → 17.0; uniseg fails 9, 8.2 MB; draft GB11 bug passed | zlib −9 table 1,228 / 1,136 / **1,344 B**; 47 non-blank lines; v1 and final pass 1,187 / 1,093 / 766; `3.15.0rc2 unidata 17.0.0`; uniseg 757/766 (9 failed), wheel 8,179,942 B | S (D431, RT69). Nit: "~1.2 KB" (D431, P264, P830) is 1.3 KB at the pinned 17.0. **P274 still says "missed a deliberate bug"** (the bug was accidental; A4 O, fixed in D431 but not in PLAN): **O, minor**. Fix: "the conformance file alone missed a real GB11 bug in a first draft" |

### 1b. Other changed or reworded tagged sentences (re-read against evidence)

| where | tag | verdict |
|---|---|---|
| D70 | V-confidence | **S** (A3/A4 O fixed). `confidence.md:138`: "This demo uses (3 × largest probability − 1) / 2 to approximate confidence for three options". The aside "(some vendor pages also call it calibrated)" is true (`cookbooks__date_extraction_cookbook.md:359`), but that page is V-cookbooks, not V-confidence (nit) |
| D230, D237, D384 | L18 | S. D237 "unanchored pattern": `D3_local.md:144`; 11,426/100,001: `check_r3_absent_null.txt:40`. Nit: "the latest release" in D230 means 2.13.5 (RT68) |
| D318 | P15, P19 | S. The 1/48 committed case is now stated (A4 O fixed) |
| D326 | P18 | S ("4 competitors", A4 W fixed) |
| D329 | P7 | S. `probe_07_adversarial.py:5,56`: state `{"source", "draft"}` |
| D340, D370 | V-jagged | S. The tags were added (A3/A4 U1, U2 fixed) |
| D402 | P10, P17 | S ("every full pilot corpus … (0.20 on one subset)"; A4 O fixed) |
| D413 | P7, P21 | S ("27–28 of 60 benign invoices, e-mails, and contracts"; A4 O fixed) |
| D431 | L11, L19 | S ("a draft segmenter with a real bug"; A4 O fixed) |
| D489 | P12, P20, P10, P17, P21 | S. P22 as in 1a |
| D538, D554 | L20 | S (unchanged evidence) |
| D602 | P14 | S |
| D719 | P19 | S. "showed no decision bias at near-ceiling accuracy" plus the Phase 0 re-check (A4 O fixed in DESIGN) |
| P150 | P1–P22 (plain text) | range fixed (A4 U4) |
| P433 | P7 | S. The Wilson upper bound for 0/80 is 3.8416/83.8416 = 0.0458 |
| P828 | P10, P17 | S. Nit carried: "did nothing" also cost 8–9 correct components |
| **P868** | **P19** | **O (carried, minor)**: "mixed option descriptions do not bias decisions" was fixed in D719 but not here. Fix: copy D719's wording |

### 1c. Unchanged tags

X1–X8, all V tags, P1–P10, P14–P17, P20, L1–L4, L7, L9–L16, L18, L20 and L21 read as they did in round 4, where A4 marked them S. Sample re-checks: P20 (D92, D292), P17 (D400), P14 (D88, D604, D663), L12 (P207), L15 (P497, P500). All S.

---

## 2. Untagged factual claims; README

| # | where | claim | status / fix (all minor) |
|---|---|---|---|
| U1 | D243 | the Pydantic `json_schema_extra` output is "identical to what a raw-schema user writes" | still untagged (A4 U3, carried). Add **[L18]** |
| U2 | D71 | "since at most 1 was observed" | tagged, but the evidence covers K ≤ 11 only (see 1a) |

No other new untagged factual claim was found. The Revision 7 additions (lifecycle, timeouts, object absence, array holes, `max_candidates` counting, direct extraction, criterion ties, member-only components) are design decisions, or they carry tags.

**README check.** Each README claim appears in DESIGN:
- R3 = D7.
- R7 ≈ D17.
- R15 = D25.
- R19–22 = D269–276 and D503–506 (R21's "a field with none is admitted and flagged as ungated" = D506).
- R24 = D454 and §5.6.
- R28 = D36 and §9.1.
- R33–34 = D408 and D448–454.
- R35 ⊂ D453.
- R43 now reads "every factual claim in DESIGN and PLAN" (A4 U5 fixed).

**README states nothing DESIGN doesn't.**

---

## 3. Traceability of round-4 findings

### 3a. A4

| A4 item | status | where |
|---|---|---|
| **Major: R6 / P98 / D40 stale entity rule** | **addressed** | D519 (R6), D40, P98 |
| O D70 V-confidence | addressed | D70 |
| O D399 P10 | addressed | D402 |
| O D410 P21 | addressed | D413 |
| O D428 L19 | addressed in DESIGN; **NOT ADDRESSED at P274** | D431; P274 (minor) |
| O D707 / P856 P19 | addressed at D719; **NOT ADDRESSED at P868** | minor |
| W D325 P18 | addressed | D326, RT37 |
| U1, U2 | addressed | D340, D370 |
| U3 D243 | **NOT ADDRESSED** | minor |
| U4, U5 | addressed | P150, R43 |
| Nits: D291 "±0.05 band"; P17 60% is run A only; L19 ~1.2 KB; L21 "rounded elsewhere" (RT71); P211; P818 | **NOT ADDRESSED** | all nits |
| E3 #4 residue: `abstain_probability` untyped with no call | **NOT ADDRESSED** | minor |
| E3 #5 residue: "without a declared locale", but `x-jevson` has no locale key | **NOT ADDRESSED** | D479, P501 vs D246–254 (minor) |
| E3 #8 residue: recursion | **NOT ADDRESSED** | minor |
| E3 #17 residue: redraft LLM not recorded | **NOT ADDRESSED** | minor |
| E3 #23 residues: "class C decisions whose question reads the source"; screen ordering | **NOT ADDRESSED** | D413 (minor) |
| E3 #7, #12, #13a, #14, #15, #16, #21, #22, #25, #26 | addressed | D71; D469; D256; D259, D554, D588; D606; P593; D619, P381; P382; D7, D453, R24, Admin:43; D602, D257, P53 |
| B2 left-overs: two-sided floor rule; floor per run; P13 p(argmax) < 0.5 flag; H0/H1 hint | **NOT ADDRESSED** | minor |
| D2 left-overs: offset 0/len; `minLength`/`readOnly`/untyped enum rows | **NOT ADDRESSED** | minor |
| B3: grid-top band at 0.45; split-prone probe 4 mentions (initials, acronyms, e-mails) | **NOT ADDRESSED** | P211 (minor) |
| B3: same-role distractor re-test | partial | D719 points to Phase 0 repeated-text cases |
| D3: `aclose()` | addressed | D540 |
| D3: NFC `unicodedata` version in `Result.versions`; `multipleOf` in decimal arithmetic for float fields; CI at the Pydantic floor and at latest | **NOT ADDRESSED** | minor |
| RT defects 1, 3, 4, 5, 8, 9, 10 | addressed | RT37, RT41, RT16, RT120, RT40, RT69, RT104, RT30–32 |
| RT defect 2: P19 "no decision changed" | **NOT ADDRESSED**: RT38 contradicts D318 ("1 of 48 … committed one") | minor |
| RT defects 6, 7: L21 wording (RT71); V-confidence "option-count-dependent formula" (RT86) | **NOT ADDRESSED** | minor |
| RT15 `jevdocs` in `.gitignore` | addressed | `.gitignore:24`; `scripts/redteam/.gitignore:1`; `git check-ignore` confirms |
| Agents :150, :154, :149 | addressed / consistent | Agents :150 "choices up to 0.21"; :154 "does not explain its reasoning" |
| Agents :60 "Secrets live only in Infisical" vs the Jevson `.env` (D615) | **NOT ADDRESSED** | minor |
| Admin :42 (now :43) | addressed | "source-selected values traceable to a verified span, measured (not guaranteed) abstention…" |

None of the NOT ADDRESSED items is recorded as declined: D725–743 lists only changes, and RT120 lists only revisions.

### 3b. E4 majors

| # | status | where / residue |
|---|---|---|
| 1 array holes | addressed | D478, D296, P595 |
| 2 object absence | addressed | D386, P491 |
| 3 pre-filter on parsed fields | addressed | D336, P489. Residue (minor): the P473 deliverable is still unqualified ("candidates violating … rejected before the question") |
| 4 occurrences count toward `max_candidates` | addressed | D318, D602, P488, P833 |
| 5 direct extraction with ≥ 2 candidates | addressed | D334, P490 |
| 6 criterion ties | addressed | D489, D503, P418, P434 |
| 7 multi-draft state layout | addressed in DESIGN | D329, P433. **Residue (minor): P418 still says "state is `{"source": …, "draft": …}` (`DESIGN §5.2`)"**, which contradicts D329's keyed `drafts`; R3 (D516) does not mention the conditional one-call-per-draft fallback |
| 8 undeclared defaults | addressed | D256, P316, P834 |
| 9 member-only components | addressed | D395, P594, P828 |
| 10 step timeouts | addressed | D542, D259, P118, P370, P493 |

### 3c. E4 minors

| # | status | where / residue |
|---|---|---|
| m1 | addressed | D519, D40, P98 |
| m2 | addressed | D221, D436, P501 |
| m3 | addressed | D453 |
| m4 | addressed | P488, P495 |
| m5 | addressed | P744 |
| m6 | addressed | D259, D554, D588–590. Residue (minor): P466 still writes `Jevson(default_extractor=...)`, but D554's constructor has no such parameter (it lives in `JevsonConfig`, D259) |
| m7 | addressed | D164, D572, P434, P492 |
| m8 | addressed | D538, D540, D469, P371 |
| m9 | addressed | P276, P335, P593. Residue (minor): P315 "every class C construct … except union discrimination" does not also except enum arrays, which refuse until Phase 7 (P335) |
| m10 | addressed | P316 |
| m11 | addressed | renamed `raise_on_unresolved_required` (D470, D477, P379) |
| m12 | addressed | D71. See the L17 O in 1a |
| m13 | addressed | P381, D619 |
| m14 | mostly addressed | P382, D492, P590, P199–200. **The paired-interval fix was applied to the retry bar (P497), not to the redraft bar E4 named (then P435, now P438)**: NOT ADDRESSED there (minor) |
| m15 | addressed | D606, D602, D257, D480, D556, P53, RT40–41, D121 |
| m16 | addressed | D7 / R3, R21, Admin :22–23, Admin :43 |

---

## 4. docs/REDTEAM.md consistency

- **Resolution.** Every DESIGN and PLAN tag resolves. Every named script exists, and the P22 script's outputs are in `r4/outputs/`.
- **Round log.**
  - RT16 lists round 4's 3 requests.
  - RT120 matches A4 and E4: 325 = 317 S / 7 O / 1 W, 1 major; 0 blockers, 10 majors, 16 minors.
  - P21 now precedes P22.
- **Gitignore.** `.gitignore` covers `scripts/redteam/jevdocs` (root :24, plus `scripts/redteam/.gitignore:1`).
- **Remaining defects (all minor):**
  1. **RT38 (P19)** "with no decision changed": 1/48 absent-case decision differed, which D318 now states. Fix: "…with 1/48 decisions changed (MIX committed a context-bearing option)".
  2. **RT41 (P22)** "every saved candidate choice": the 120 P5 `"none of the above"` choices are excluded. Fix as in 1a.
  3. **RT67 (L17):** add "observed at 1–11 options".
  4. **RT71 (L21):** "silently rounded elsewhere" should be "by `jcs` and both JS packages" (`canonicaljson` emits 2⁵³+1 exactly).
  5. **RT86 (V-confidence):** "option-count-dependent formula" should be "a spread statistic, illustrated with a three-option approximation".
  6. **RT32 (P13):** name the rounding convention for run 2 (5/60 half-even, 6/60 half-up).
  7. `r4/raw/` is empty, and the P22 raw responses were not saved (RT16 correctly points to `outputs/`).

## 5. Agents/CLAUDE.md and Admin/README.md vs Revision 7

- **Agents :146–155**, the Jev block, is consistent with DESIGN §2:
  - noul without confidence;
  - 2–255 options / 2–10 levels;
  - most probable level;
  - jitter "bools usually ≤ 0.05; choices up to 0.21; up to 0.37";
  - 62% vs 0%;
  - "does not explain its reasoning";
  - limits, price and latency.
- **Agents :149** "a statistic of the distribution that depends on the option count" matches D70.
- **Agents :157–167**, the Jevson block, is consistent with D7, D453, D454 and D408. Its lines :161 and :164 are scoped as DESIGN is.
- **Agents :60** "Secrets live only in Infisical" still conflicts with the gitignored `.env` that D615 and RT7 describe. Minor, carried. Fix: "…Infisical (Jevson's red-team scripts read a gitignored local `.env` until PLAN Phase 11)".
- **Admin**:
  - :22 is now `[x]`, with the spike split out at :23 (E4 m16 fixed);
  - :43 is scoped as DESIGN is (E3 #25 / A4 fixed);
  - :68 and :89 (price, V-models) are consistent;
  - the priority order is unaffected by Revision 7.

## 6. Verdict

- **Tag verdicts:** 324 S, 5 O, 0 W, 0 U. All five O items are minor:
  - two carried PLAN copies of DESIGN fixes (P274, P868);
  - "all 2,154" in P22 (D489, D742);
  - the new sum-tolerance cap, justified by K ≤ 11 evidence (D71).
- **Every A4 item and E4 major is addressed in DESIGN.** Residues in PLAN (P418, P466, P473, P315, P438) and the carried minors are wording, and DESIGN, the SSOT, settles each of them.
- **No blocker, no major.**

**CONVERGED: yes.**
