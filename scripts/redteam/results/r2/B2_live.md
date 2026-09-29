# B2: live probes of DESIGN Revision 4 rules (red-team round 2)

- **Date:** 2026-09-29.
- **Model:** pinned `jev-1.13.0`, called through raw httpx using `scripts/redteam/jevclient.py`.
- **Requests:** 941 HTTP requests in total, including retries. The budget was 1,500. No 429s were hit.
- **Scripts:** `scripts/redteam/probe_r2_*.py`. Each script's docstring states the claim it tests and the method.
- **Raw JSON:** `scripts/redteam/results/r2/raw/r2_*.json`.
- **Console outputs:** `scripts/redteam/results/r2/r2_*.txt`.
- **Key check:** the key was read from `.env` only inside the scripts. A scan of all 40 r2 scripts and outputs found the key in **0 files**. The scanning script compared the value in memory and printed only a count.
- **Intervals:** Wilson 95%.
- **All datasets are synthetic, author-written pilots.** They are not the pre-registered Phase 0 probes. Where a result sits at ceiling, the likely cause is that the cases are easy.

---

## Probe 1: `conflict_floor` selection rule and per-component policy (DESIGN §5.6; PLAN Phase 0 probe 4)

**Claims tested:**
- §5.6.3: a component is merged unless some pair inside it is confidently different (p ≤ `conflict_floor`). Pairs between the floor and 0.5 count as "absence of evidence".
- PLAN probe 4 selection rule: "the largest value in {0.05, 0.10, 0.20, 0.30} such that same-entity pairs at or below it are ≤ 2% of all same-entity pairs."

**Method.** `probe_r2_entity_floor.py` collects the data and `probe_r2_entity_floor_analysis.py` scores it.
- **Documents: 48.**
  - The 24 probe_06 docs, reproduced verbatim.
  - **24 new docs** with realistic coreference chains, including near-duplicate different people:
    - t3, co-op minutes: Katherine Doyle / Ms. Doyle / Kate / the Chair, vs. Kevin Doyle / Mr. Doyle / Kevin, vs. Katherine Boyle.
    - t4, email: Dr. Michael Grant / Dr. Grant / Mike, vs. Michaela Grant / Ms. Grant, vs. Michael Granger.
    - t5, news: Senator Paul Whitaker / Whitaker / Paul, vs. Judge Paula Whitaker, vs. Paul Whittaker.
- **Pairs:** 1,824 pairwise nouls (488 gold-same, 1,336 gold-different), sent as one keyed request per doc.
- **Runs:** the whole set was sent **twice** (runs A and B), byte-identical. Every pair probability is stored.

### (a) Distribution of p(same)

| p bin | gold-same, A | gold-same, B | gold-diff, A | gold-diff, B |
|---|---|---|---|---|
| < 0.05 | 0 | 0 | 994 | 982 |
| 0.05–0.10 | 0 | 0 | 194 | 199 |
| 0.10–0.20 | 0 | 1 | 73 | 74 |
| 0.20–0.30 | 6 | 4 | 27 | 25 |
| 0.30–0.40 | 3 | 4 | 15 | 17 |
| 0.40–0.50 | 5 | 6 | 4 | 9 |
| 0.50–0.80 | 26 | 22 | 16 | 18 |
| ≥ 0.80 | 448 | 451 | 13 | 12 |

- **Pair accuracy** at p > 0.5:
  - A: 1,782/1,824 = 0.977 [0.969–0.983].
  - B: 1,778/1,824 = 0.975.
- **False merges** (gold-different pairs above 0.5): 28/1,336 = 0.021 [0.015–0.030] in A.
- **False splits** (gold-same pairs at or below 0.5): 14/488 = 0.029 [0.017–0.048] in A.
- **Exact 0.50:** 1 pair per run.
- **The lowest gold-same pairs** are:
  - "the Landlord" ↔ "X. Surname for the Landlord", at 0.17–0.34;
  - Louis Bennett ↔ the businessman, at 0.20–0.27.
- **The highest gold-different pairs** are the lease signature line ("S. Okoro for the Landlord" ↔ Samuel Okoro [agent], at 0.94–0.95). My lease gold is debatable, as it was in round 1.

### (b) The pre-registered rule, applied verbatim

| subset / run | same ≤ 0.05 | ≤ 0.10 | ≤ 0.20 | ≤ 0.30 | **selected** |
|---|---|---|---|---|---|
| ALL, A | 0.0% | 0.0% | 0.0% | 1.2% (6/488) | **0.30** |
| ALL, B | 0.0% | 0.0% | 0.4% | 1.0% (5/488) | **0.30** |
| old p06 only, A and B | 0 | 0 | 0–0.5% | **2.1%** (4/192) | **0.20** |
| new t3–t5 only, A and B | 0 | 0 | 0 | ≤ 1% | **0.30** |

- **The rule is computable and was stable across the two runs.**
- **The top of the grid binds.** On ALL-A, 9/488 = 1.8% of same-pairs sit at or below 0.40, so the rule would have gone higher if the grid allowed it.
- **The selected value depends on the corpus mix.** It is 0.20 on the old docs and 0.30 overall.
- The share of gold-different pairs at or below the floor, which is the conflict-detection power, is 96.5% at 0.30 and 94.5% at 0.20.

### (c) Per-component outcomes

Predicted components are scored as follows:
- **correct**: equal to a gold cluster;
- **Unresolved**;
- **silently wrong**: either a merge of two gold entities, or a split that emits a duplicate element.

| policy | run | components correct | Unresolved | **silently wrong** (merge / split) | docs fully correct | docs silently wrong |
|---|---|---|---|---|---|---|
| plain connected components | A | 117/133 = 0.880 | 0 | **16/133 = 0.120** [0.075–0.186] (13/3) | 35/48 | 13/48 |
| plain connected components | B | 117/134 = 0.873 | 0 | 17/134 = 0.127 (12/5) | 34/48 | 14/48 |
| Rev 3 (any pair < 0.5 → whole array Unresolved) | A | 106/133 = 0.797 | 25/133 | **2/133 = 0.015** [0.004–0.053] (1/1) | 35/48 | 1/48 |
| Rev 3 | B | 105/134 = 0.784 | 25/134 | 4/134 = 0.030 [0.012–0.074] (1/3) | 34/48 | 2/48 |
| **Rev 4 @ 0.30 (rule-selected)** | A | **117/133 = 0.880** [0.814–0.925] | 11/133 | **5/133 = 0.038** [0.016–0.085] (2/3) | 35/48 | 2/48 |
| **Rev 4 @ 0.30** | B | 117/134 = 0.873 [0.806–0.919] | 11/134 | **6/134 = 0.045** [0.021–0.094] (1/5) | 34/48 | 3/48 |
| Rev 4 @ 0.05 | A | 117/133 | 8/133 | 8/133 = 0.060 | 35/48 | 5/48 |
| Rev 4 @ 0.20 | B | 117/134 | 10/134 | 7/134 = 0.052 | 34/48 | 4/48 |

By subset, under Rev 4 @ 0.30:
- **new docs:** silently wrong 3/72 = 0.042 (A) and **4/72 = 0.056** (B, which is above the 0.05 stop line);
- **old docs:** 2/61 and 2/62.

Rev 4 compared with the other policies:
- **Against Rev 3:** Rev 4 recovers 11–12 more correct components per run. It **roughly doubles or triples the silently-wrong components**: 2 → 5 in A and 4 → 6 in B.
- **Against plain connected components:** both have the same number of correct components. Rev 4 turns about 11 of the 16–17 silent errors into Unresolved.

Against the PLAN probe-4 band (≥ 0.85 correct and ≤ 0.05 silently wrong):
- Rev 4 @ 0.30 on ALL is a **go on the point estimate in both runs**.
- Both silent-wrong CIs cross 0.05 (upper bounds 0.085 and 0.094), so under the pre-registered rule the verdict is **borderline**.

### (d) Clique completeness

Clique completeness is the fraction of gold clusters of size ≥ 2 whose pairs are all above 0.5:

| set | run A | run B |
|---|---|---|
| ALL | 135/144 = **0.938** [0.885–0.967] | 133/144 = 0.924 |
| old docs | 65/72 = 0.903 | — |

Non-transitive triples and docs with at least one violation:

| set | non-transitive triples | docs with ≥ 1 violation |
|---|---|---|
| ALL | 47/4,520 = 0.010 | **12/48 = 0.25** |
| old docs | 41/1,568 = 0.026 | 10/24 = 0.42 (reproduces **[P6]** exactly) |

### (e) Is the rule well-defined and sensible?

The rule is well-defined, but it does not do what the design needs. Findings:

1. **The rule is one-sided.**
   - It limits *false conflicts*: same-entity pairs at or below the floor. It never looks at the quantity the verdict gates on, which is silent merges.
   - A larger floor always detects more conflicts, so "largest value such that…" is the right direction. But the grid caps the result at 0.30, and the cap is what bound here.
2. **The "absence of evidence" band lets wrong merges through.**
   - In run A, the component {"Louis", "Mr. Bennett", "the businessman"} merged Senator Louis Bennet's first-name mention into businessman Louis Bennett's cluster. Its weakest pair was 0.37, which is above the floor and below 0.5, so it was emitted.
   - This is exactly the case §5.6 defines as "not conflict".
3. **Most Rev 4 silent errors are splits, and no floor can catch a split.**
   - Splits were 3 of 5 silent errors in A and 5 of 6 in B.
   - A split mention (e.g. "the Landlord" or "Adrian" alone) forms its own clean component and is emitted as a **duplicate array element**.
   - §5.6 only guards merges. Rev 3 caught these splits only because it poisoned the whole array.
4. **Consistent-but-wrong merges remain.** The Sam/Samuel Okoro lease merge was at 0.82–0.95 in both runs. This is the stated limit.
5. **Jitter moves pairs across both thresholds.** See the jitter addendum below: one pair ranged 0.22–0.59 over 12 identical calls. A pair near the floor is therefore not "confident" in any stable sense.

**An exploratory fix, not pre-registered and tuned in-sample.** Also mark a component Unresolved when any *cross-component* pair lies in (floor, 0.5]. At floor 0.30 this gave:
- **silently wrong 0/133 and 0/134**;
- correct components 113/133 and 109/134, compared with 117;
- Unresolved 20 and 25, compared with 11.

It catches both the split and the band-merge failures. It needs out-of-sample confirmation.

**Verdict: PARTIAL.**
- Per-component handling does recover components compared with Rev 3.
- But the silent-wrong rate rises from Rev 3's 1.5–3.0% to 3.8–4.5%, borderline against the 0.05 stop line.
- The selection rule controls the wrong error type and cannot see splits.

**Doc changes:**
- **DESIGN §5.6.3**
  - Add: "Splits are not detected by any intra-component rule. A component that has any cross-component pair in (`conflict_floor`, 0.5] is also `Unresolved`, because a duplicate element is a silent error."
  - Alternatively, state duplicates as a named limit next to consistent-but-wrong merges.
  - Delete or qualify "pairs between the floor and 0.5 are absence of evidence": measured, a 0.37 pair sat inside a wrong merge.
- **PLAN probe 4**
  - Extend the grid to {…, 0.30, 0.40}, or state the cap.
  - Make the rule two-sided: the chosen floor must also meet the silent-wrong bar.
  - Compute it on ≥ 2 independent runs, because pairs jitter by up to 0.37.
  - Record splits and merges separately.
- **DESIGN §5.6 pilot numbers:** the 42% non-transitive figure is template-specific. It was 38–42% on the probe_06 docs and 8–13% (2–3/24) on the new realistic-chain docs.

---

## Probe 2: single-candidate two-option choice (DESIGN §5.2, rule 4)

**Claim tested:** `choice([c0, none_of_these])` catches a lone wrong candidate at a low false-abstention cost.

**Method.** `probe_r2_single_candidate.py`.
- **Cases:** 6 field kinds × 2 styles, n = 42 per condition.
- **Conditions:**
  - **a:** the lone candidate is correct.
  - **b1:** the lone candidate has the wrong role, and the correct value is in the doc (Ship To for billing; sales rep for customer; invoice date for due date; subtotal for total; physician for patient; signing date for effective date).
  - **b2:** the lone candidate has the wrong role, and the correct value is absent (packing slip, quote, draft, rota).
  - **c:** the lone candidate is a partial span (street without city, first name only, date without year, amount without cents).
- **Questions per doc:**
  - **S2:** the 2-option choice.
  - **S4:** the same candidate among 2–3 same-type competitors, plus none.
  - **N1:** noul "Is X the field?".
- **Follow-up:** `probe_r2_single_candidate_completeness.py` repeats a and c with completeness wording **W1**:
  - instruction: "…the {field}, complete and exactly as written in full in the text?";
  - none option: "…an option that is only part of it (missing city, year, surname, cents) does not count".

| condition | direct commit | **S2 commit** | S2 abstain | S4 commits same cand | N1 pass |
|---|---|---|---|---|---|
| a, correct | 42/42 | **40/42 = 0.952** [0.842–0.987] | 2/42 (both "total") | 41/42 | 39/42 |
| b1, wrong role, correct present | 42/42 **wrong** | **0/42** [0–0.084] | 42/42 | 0/42 | 0/42 |
| b2, wrong role, correct absent | 42/42 **wrong** | **0/42** [0–0.084] | 42/42 | 0/42 | 0/42 |
| c, partial span | 42/42 **wrong** | **32/42 = 0.762** [0.615–0.865] **wrong** | 10/42 | 29/42 | 37/42 |
| c, S2 with **W1** wording | — | **0/42** [0–0.084] | 42/42 | 0/42 (S4 W1) | — |
| a, S2 with **W1** wording | — | **42/42** [0.916–1] | 0/42 | 42/42 | — |

**Partial-span commits by field kind (S2, base wording):**

| field kind | committed |
|---|---|
| street without city | 7/7 |
| date without year: due date | 7/7 |
| date without year: effective date | 7/7 |
| first name: customer | 3/7 |
| first name: patient | 4/7 |
| amount without cents | 3–4/7 |

- Wrong partial commits often had high confidence, **0.85–1.00** for streets and dates.

**Two-option vs 3–5 options:**
- S2 and S4 disagreed on commit in 1/42 (a), 0/84 (b) and 5/42 (c).
- No systematic difference was found. A 2-option choice behaves like the same candidate among competitors.
- The noul gate N1 was worse on both sides: 3/42 false rejects on a, and it passed 37/42 partials.

**Verdict: PARTIAL.**
- **CONFIRMED for wrong-role lone candidates:** 84/84 abstained, with false abstention 2/42 = 4.8%. These short documents may be at ceiling.
- **REFUTED for partial candidates under generic wording:** 76% were committed, and the provenance guarantee then points at a truncated value.
- Completeness wording fixed it completely in this pilot, at 0 cost on correct candidates.

**Doc changes:**
- **DESIGN §5.2 / §5.3:** pin the compiled question and `none_of_these` description to demand the complete value, e.g. "complete and exactly as written; a part of it does not count". Cite this probe.
- **PLAN Phase 0 probe 2:** add a partial-span stratum, because the extractor's likeliest lone-candidate error is a truncated span.
- Keep the 2-option design. Do not use a noul gate.

---

## Probe 3: the tie rule (DESIGN §4.2, §6.2)

**Claim tested:** bool is true iff p > 0.5, and an exact 0.50 gives `Unresolved(tie)`.

**Method.** `probe_r2_tie_rule.py`.
- **Documents:** 40 synthetic service contracts, each built from 5 of 6 clause topics. Each clause is clearly yes, clearly no/absent, or deliberately hedged. The pools hold 36 clause variants.
- **Questions:** 200 yes/no nouls (e.g. "Does the contract include an automatic renewal clause?").
- **Repeats:** the full set was sent **10 times** byte-identically (400 requests), giving 2,000 observations.

**Results:**
- **Exact 0.50:** 1/2,000 observations = 0.05% [0.00–0.3%]. Only 1/200 questions ever produced one, and 0/200 did on the first pass.
- **In [0.45, 0.55]:**

  | measure | count | rate |
  |---|---|---|
  | observations | 23/2,000 | 1.1% [0.8–1.7%] |
  | questions, first pass | 2/200 | 1.0% |

- **Decision flips** (p > 0.5 differs across the 10 repeats): 2/200 = 1.0% [0.3–3.6%]. Both came from hedged clauses:
  - liability "…limited to the extent permitted by law": 0.45–0.56;
  - exclusivity "preferred provider": 0.50–0.57.
  - Clear-yes and clear-no clauses: 0 flips out of 135.
- **Jitter** over 10 repeats: per-question range p50 0.01, p90 0.05, p99 0.13, max **0.16**; per-question sd max 0.043.

| tie band b (Unresolved iff \|p − 0.5\| ≤ b) | questions with a true↔false flip | questions whose outcome is not identical across 10 calls | tie observations |
|---|---|---|---|
| 0 (exact, Rev 4) | 1/200 | 2/200 | 1/2,000 |
| 0.02 | 1/200 | 3/200 | 9/2,000 |
| **0.05** | **0/200** | 3/200 | 23/2,000 = 1.1% |
| 0.10 | 0/200 | 5/200 | 45/2,000 = 2.2% |

**Verdict: PARTIAL.**
- The rule is well-defined but near-vacuous. An exact 0.50 occurs in about 1 in 2,000 answers here (and in 1 of 1,824 entity pairs per run), so it almost never fires.
- The real risk is near-threshold flips, which the exact rule leaves in place.
- A ±0.05 band removed every true↔false flip on this set, at a cost of about 1% of answers. It converts them into tie-vs-decided inconsistency: no band makes replay exact, and that is the cache's job.
- Entity pairs jittered far more than ±0.05 (next section), so a band sized on these contract nouls is not enough for merges.

**Doc changes:**
- **§4.2 / §6.2:** replace "exact 0.5 → tie" with "|p − 0.5| ≤ `tie_band` → `Unresolved(near_tie)`", default 0.05, measured cost ~1% on contract nouls.
- **§6.2:** state that replay stability comes only from the cache (§8.4).
- **§2.1:** reword "exact ties such as 0.50 occur" to "occur rarely (1 in ~2,000)".

### Addendum: jitter is larger than DESIGN §2.3 states (`probe_r2_jitter_entity.py`, 60 requests)

**Trigger.** Entity runs A and B were identical requests sent minutes apart, yet they differed by up to 0.26, with **16/1,824 pair decisions flipped**.

**Method.** The 6 docs with the largest A–B differences were each re-sent 10 more times, giving 12 observations per pair.

**Results:**
- **Largest ranges:** one pair spanned **0.22–0.59** (range 0.37, sd 0.13), and another 0.11–0.45.
- **Spread:** 29/192 pairs had a range above 0.10, and 35/192 had sd above 0.022.
- **Decision flips:** 12/192 pairs flipped.
- The same 0.37 range appears within 10 back-to-back calls alone, so this is not drift between sessions.
- These docs were selected for high jitter, so the rate is not representative. The maximum still refutes the §2.3 bound.

**Doc changes:**
- **§2.3 and §6 honest limits:** replace "jitter by up to 0.10 / ±0.05; sd ≤ 0.022" with "typically ≤ 0.05; up to 0.37 range (sd 0.13) on ambiguous entity-pair nouls in 36–55-question requests".
- The cause is unmeasured: it could be question type, instruction objects, or batch size.

---

## Probe 4: score value = most probable level (DESIGN §4.2)

**Method.** `probe_r2_score_decode.py`.
- **Questions:** 12 texts × 5 score questions (3, 4, 5, 7 and 10 levels) = 60. Several texts were written to be mixed or polarised.
- **Runs:** 2 (24 requests).

**Results:**
- **`score` is a probability-weighted float.**
  - It matches Σ level·p within ±0.011 in 53/60 cases. The remaining 7 differ by up to 0.08, which is consistent with a computation on unrounded probabilities.
  - It is an integer in only 9/60 cases.
- **`legend`** is present in 60/60 answers. It is exactly `{index: level text}`, an echo of the request's levels, and carries no extra information.
- **Decode agreement:**

  | comparison | disagreements | 95% CI |
  |---|---|---|
  | round(score) vs argmax | 8/60 = 0.133 | 0.069–0.242 |
  | argmax vs median level | 4/60 | — |

  - Where round(score) and argmax disagree: **6/12 of the 10-level questions**, 2/12 of the 4-level questions, and **0** of the 3-, 5- and 7-level questions.
- **Zero-probability levels:** round(score) landed on a level with p < 0.10 in 0/60 cases. The **[L4]** pathology (a zero-probability level) was not observed live.
- **Flat distributions:**
  - max p < 0.5 in 9/60 cases: 8 of the 12 ten-level questions, and 1 four-level question.
  - Only 1/60 was bimodal: P = [0.26, 0.06, 0.10, 0.11, 0.16, 0.22, …]. There argmax = 0 while the median is 3 and the score is 2.89. Neither decode represents that distribution well.
- **Between runs:**
  - argmax changed 2/60 times (a 0.55/0.45 four-level question, and a 10-level 0.26/0.22/0.22 question).
  - round changed 2/60 times.

**Verdict: CONFIRMED with a caveat.**
- argmax is a well-defined, declared-option value, and it never selects an unsupported level.
- On 10-level scales the distribution is usually flat: 8/12 had max p < 0.5. There argmax is unstable and can sit far from the mass.

**Doc changes:**
- **§4.2:** keep argmax.
- Report `p(argmax)`, and flag it as low-support when it is below 0.5.
- Note that `legend` only echoes the levels.
- Recommend ≤ 7 levels, or a coarser rubric, where a stable single level matters.
- Do not claim the zero-probability-rounding failure was observed.

---

## Probe 5: source ceiling (DESIGN §8.2)

**Claim tested:** "a 255-option candidate `choice` costs ~2.5k tokens **[P2]**".

**Method.** `probe_r2_source_ceiling.py` (33 requests).
- **Question:** 254 opaque-id candidates plus `none_of_these`.
- **Question cost:** usage.input_tokens with a 1-word state, minus a 2-option baseline.
- **Ceiling search:** a binary search on the state size accepted alongside the realistic 255-option question, for two corpora.

**Token cost of the 255-option question, by option description:**

| option description | description chars | tokens over baseline |
|---|---|---|
| r1 (P2): bare keys, no description | — | ~2,485 total |
| short span, 5–12 chars | 2.8k | **4,672** |
| **realistic span, 5–80 chars** | 11.9k | **6,854** |
| long span, ~80 chars | 20.3k | 8,806 |
| span + ±70-char context window (the format probe 6 needs) | 62.6k | **20,114** |

**Largest state accepted:**

| corpus | chars/token | max state with the realistic 255-option question | max state with a short noul |
|---|---|---|---|
| A: business-document prose (names, dates, money) | 2.44 | **62,343 chars** (32,723 input tokens) | 80,155 chars |
| B: plain English prose (DESIGN.md text) | 4.21 | **108,437 chars** (32,886 input tokens) | 137,499 chars |

- The 32,768-token limit on state plus the longest question holds, as measured in round 1.

**Verdict: REFUTED (figure).**
- The ~2.5k figure applies only to options with no description. Realistic span descriptions cost **~6.9k** tokens, and context-window descriptions **~20k**. With context windows, the state is left with about 12k tokens (~30k to 50k chars).
- Practical ceilings with realistic span options: about **108k chars** of plain English prose, and about **62k chars** of dense business text.

**Doc changes:**
- **§8.2:** replace "(a 255-option candidate `choice` costs ~2.5k tokens [P2])" with measured numbers: ~18 tokens per option for bare spans, ~27 for realistic spans, ~80 for context windows.
- State the ceilings in characters.
- Require preflight to budget option descriptions, not option counts.
- **§10:** "≤ 254 candidates" is feasible only with short descriptions over a small source.

---

## Probe 6: opaque ids for identical text at two offsets (DESIGN §5.1)

**Method.** `probe_r2_opaque_ids.py` (40 requests).
- **Documents:** 40 docs, 4 types × 10. Each holds the same string twice: once in the correct role, and once in a wrong role inside a quoted or prior block.
  - Vendor in the header vs. the customer of an attached prior invoice.
  - This invoice's date vs. a prior invoice's due date.
  - Latest email's To vs. the quoted original's From.
  - Amount due vs. last period's payment received.
- **Placement:** the quoted block is placed first or last at random.
- **Candidates:** both occurrences plus 2 distractors plus none.

| description format | right occurrence | wrong occurrence (same text, wrong provenance) | abstain |
|---|---|---|---|
| F0: text only (control) | 22/40 = 0.55 | 18/40 | 0 |
| F1: text + character offsets | 30/40 = 0.75 | 10/40 | 0 |
| **F2: ±40-char context, span in [[ ]]** | **40/40** [0.912–1] | 0 | 0 |
| F3: ±100-char context | 40/40 | 0 | 0 |
| F4: the full source line | 40/40 | 0 | 0 |

- F1's gain looks like a position bias rather than offset reading: it scored 20/20 when the correct occurrence came first and 10/20 when it came second.

**Absent sets.** The correct occurrence was removed, but the identical-text wrong occurrence remained:

| format | abstain | commits the wrong occurrence |
|---|---|---|
| F2 | **16/40 = 0.40** [0.26–0.55] | **22/40** |
| F3 | 7/40 = 0.175 | **33/40** |
| F4 | 18/40 = 0.45 | 19/40 |

- By type, the To/From and amount cases (t3, t4) almost never abstained (0–1/10).

**Verdict: PARTIAL.**
- With a context window of about 40 chars or the source line, Jev picks the right occurrence 40/40. **"Ids represent identical text at two offsets" is a real capability when both occurrences are offered.**
- It is text-only (F0) that is merely representable, at chance.
- **But `none_of_these` does not protect provenance:** when only the wrong-role occurrence is offered, Jev commits it 48–83% of the time.
  - The *value* string is then right, but the *span* is wrong.
  - Wider windows (±100) abstain less, plausibly because the window reaches the correct occurrence's context.

**Doc changes:**
- **§5.1:** option descriptions carry a ±40-char context window or the source line. Text alone is not enough (0.55, chance).
- **§5.1 / §5.5:** add that identical-text occurrences should be offered together; state the measured failure to abstain on a lone wrong-role occurrence.
- **§5.4 retry:** when retry finds a new occurrence of an already-seen *text*, it must offer both.
- **§8.2:** context windows cost about 3× the tokens (probe 5).

---

## Probe 7: scoping hint (DESIGN §5.3)

**Method.** `probe_r2_scoping_hint.py` (36 requests).
- **Cases:** the 36 round-1 S-long cases. They were regenerated exactly, and the correct answers and candidate sets were verified 36/36 against the r1 raw data.
- **Question:** choice + none, with text keys as in round 1, and present and absent sets.
- **Wordings:**
  - **H0:** no hint (round 1).
  - **H1:** the generic hint "…of this document's main item (the one being issued or described), not of the other invoices, notes…".
  - **H2:** anchored to the target passage ("In the passage that begins '…'"). This is an upper bound: a compiler usually cannot know where the passage is.

| wording | abstain when absent | correct when present | false abstain |
|---|---|---|---|
| H0 | 32/36 = 0.889 [0.747–0.956] (reproduces r1 exactly) | 36/36 | 0/36 |
| **H1 generic** | **35/36 = 0.972** [0.858–0.995] | **33/36 = 0.917** [0.782–0.971] | 2/36 |
| H2 anchored | 36/36 [0.904–1] | 36/36 | 0/36 |

- **Paired on the absent sets:** H1 abstained where H0 committed in 3 cases, and the reverse happened in 0 (exact McNemar p = 0.25).
- **Paired on the present sets:** H1 lost 3 cases that H0 got right, all T7 customer-name cases (p = 0.25).

**Verdict: PARTIAL.**
- The generic hint moved abstention 32 → 35/36, but cost 3/36 on present answers. The net effect is a trade, not significant at n = 36.
- Only anchoring to the target passage improved both sides, and that needs information the compiler generally lacks.

**Doc changes:**
- **§5.3:** stop presenting the scoping hint as a fix.
- Say instead: "a generic scope hint traded false commits for false abstentions (+3/−3 of 36); anchoring the question to the target section removed both, so scope must come from the caller (e.g. a declared section or anchor), not from generic wording."
- **Phase 0:** measure H0 vs H1 on real documents.

---

## Request accounting

| script | requests |
|---|---|
| probe_r2_entity_floor (A + B) | 96 |
| probe_r2_single_candidate | 168 |
| probe_r2_single_candidate_completeness | 84 |
| probe_r2_tie_rule | 400 |
| probe_r2_score_decode | 24 |
| probe_r2_source_ceiling | 33 |
| probe_r2_opaque_ids | 40 |
| probe_r2_scoping_hint | 36 |
| probe_r2_jitter_entity | 60 |
| **total** | **941** (no 429s, no retries needed) |

## Verdict summary

| probe | claim | verdict |
|---|---|---|
| 1 | conflict_floor rule + per-component policy | **PARTIAL:** the rule selects 0.30, grid-capped. Rev 4 components are 0.873–0.880 correct and **3.8–4.5% silently wrong** (Rev 3: 1.5–3.0%). Splits are undetectable. A 0.37 pair sat inside a wrong merge |
| 2 | single-candidate 2-option choice | **PARTIAL:** wrong-role 84/84 abstained; false abstain 2/42; **partial spans committed 32/42** unless the wording demands completeness (then 0/42, with 42/42 correct kept) |
| 3 | exact-0.5 tie | **PARTIAL:** well-defined but fires 1 in 2,000. A ±0.05 band removed all true/false flips (cost ~1%). Jitter reaches 0.37 on entity pairs (§2.3 refuted) |
| 4 | score = argmax | **CONFIRMED** (argmax is never on an unsupported level); round ≠ argmax 13%, concentrated at 10 levels, where argmax is flat and unstable |
| 5 | ~2.5k tokens per 255 options | **REFUTED:** 4.7k (short) / 6.9k (realistic) / 20k (context); ceiling about 108k chars of prose and 62k of dense business text |
| 6 | opaque ids for identical text | **PARTIAL:** context windows pick the right occurrence 40/40 (text alone: 22/40), but a lone wrong-role occurrence is committed 48–83% |
| 7 | scoping hint | **PARTIAL:** 32 → 35/36 abstention but 36 → 33/36 present accuracy; only a passage anchor fixed both |
