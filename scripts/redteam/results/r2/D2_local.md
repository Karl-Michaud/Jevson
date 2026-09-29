# D2: round 2 local checks of Jevson Revision 4 (no Jev API)

**Scripts:** `/Users/karlosins/project-asterion/Jevson/scripts/redteam/check_r2_*.py`. Each has a docstring giving the claim and the method.

**Raw outputs:** `/Users/karlosins/project-asterion/Jevson/scripts/redteam/results/r2/outputs/*.txt`.

**Environment**
- Host: Python 3.11.7 (Unicode 14.0).
- Venv `scratchpad/venv-r2local`: pydantic 2.13.5, jsonschema 4.26.0, numpy 2.4.6, scipy 1.17.1, regex 2026.9.29, uniseg 0.10.1 (Unicode 16.0), grapheme 0.6.0 (Unicode 13.0).
- Docker images python:3.13.15, 3.14.7 and 3.15.0rc2, used for the stdlib grapheme check.
- Node, for the JSON canonicalisation comparison.
- No Jev API calls. Check 8 re-reads round 1's recorded responses in `results/r1/raw/`.

| # | claim | verdict |
|---|---|---|
| 1 | grapheme-boundary shorthand (DESIGN §5.5, PLAN Phase 1) | **REFUTED** |
| 2 | Phase 0 n=150 rule, "±6 points near 0.85" | **CONFIRMED** (numbers), **PARTIAL** (rule gaps) |
| 3 | calibration bar (DESIGN §6.2) | **PARTIAL**: the ECE half works; the τ half has no power; binning under ties is ambiguous |
| 4 | Phase 5 coverage bounds | **PARTIAL**: inconsistent with Phase 0 bands |
| 5 | retry bar | **REFUTED as decidable at the stated n** |
| 6 | source-screen bar | **PARTIAL**: at n=100 it is a zero-tolerance test |
| 7 | Pydantic normalisation coverage | **PARTIAL**: 11 gaps |
| 8 | 2-dp rounding and cache canonicalisation | **PARTIAL** |

---

## 1. Grapheme-boundary rule (DESIGN §5.5; PLAN Phase 1 exit criteria)

**Claim.** A span boundary must not fall "before a combining mark, variation selector, skin-tone modifier, or zero-width joiner".

**Scripts**
- `check_r2_grapheme_rule.py`: compares the shorthand, position by position, with UAX #29 extended grapheme clusters from `regex` `\X`. It uses 20 generated classes × 3,000 strings (316,621 interior positions). It runs two readings of "combining mark": gc ∈ {Mn, Me}, and gc ∈ {Mn, Mc, Me}. It cross-checks the result against `uniseg` and `grapheme`.
- `check_r2_grapheme_py315.py`: re-checks the same 60,000 strings against Python 3.15's new `unicodedata.iter_graphemes`, in Docker.

**Results.** FA = false accept (the shorthand allows a split that UAX #29 forbids). FR = false reject. Each cell is a count of positions. Classes with no errors in either reading: Latin + combining marks; keycaps; VS15/VS16 presentation; a mark after a space.

| class | FA (Mn,Me) | FA (Mn,Mc,Me) | example of an accepted split |
|---|---|---|---|
| **CR LF** | 2,238 | 2,238 | `'ab\r' \| '\ncd'` |
| emoji ZWJ: split *after* the ZWJ | 5,981 | 5,981 | `'…♀‍' \| '👦…'` (the rule covers only "before ZWJ") |
| regional-indicator flags | 6,009 | 6,009 | `🇦 \| 🇧` |
| tag-sequence flags (🏴 + E0067…E007F, gc=Cf) | 18,000 | 18,000 | `🏴 \| <tags>` |
| Hangul L\|V\|T jamo | 8,100 | 8,100 | `ᄇ \| ᅫᆯ` |
| Hangul LV + T | 3,000 | 3,000 | `프 \| ᆭ` |
| Devanagari virama conjunct (GB9c, Unicode 15.1) | 5,310 | 2,970 | `ल् \| र` |
| Bengali (U+09BE is Mc but GCB=Extend; conjuncts) | 3,000 | 734 | `ঢ \| া` |
| Tamil spacing vowel signs (Mc) | 2,049 | 0 | `ம \| ு` |
| Thai / Lao SARA AM (gc=Lo, GCB=SpacingMark) | 1,823 / 3,000 | 1,823 / 3,000 | `น \| ำ` |
| Prepend (U+0600, U+0D4E, U+110BD) | 3,000 | 3,000 | `؁ \| क` |
| ZWNJ (Cf, GCB=Extend) | 3,000 | 3,000 | `ی \| ‌…` |
| halfwidth katakana voiced marks (Lm, Extend) | 6,000 | 6,000 | `ｶ \| ﾞ` |
| Mc misc (visarga, musical stem) | 6,000 | 0 | |
| **false reject:** combining mark after `\n`/`\t`/`\r`/NUL (GB4 breaks there) | FR 3,000 | FR 3,000 | the shorthand rejects the valid `'ab\n' \| '́c'` |
| **total** | **76,510 FA / 3,000 FR** | **63,855 FA / 3,000 FR** | of 128,163 interior positions |

**Library comparison**
- `uniseg` 0.10.1 (Unicode 16.0) matches `regex` on 60,000/60,000 strings.
- `grapheme` 0.6.0 (Unicode 13.0) disagrees on 2,863 strings, all of them GB9c conjuncts. This shows that **the boundary verdict depends on the Unicode version**.
- Python 3.15.0rc2 `unicodedata.iter_graphemes` (Unicode 17.0) disagrees on 0/60,000 strings.
- Python 3.11, 3.12, 3.13 and 3.14 have no grapheme API.

**Dependency cost against PLAN Phase 8 ("jsonschema, pydantic, httpx")**

| option | licence | form | Unicode | cost |
|---|---|---|---|---|
| `regex` | Apache-2.0 AND CNRI-Python | C extension, 1.8 MB installed, wheels per platform | 16+ | one new runtime dependency |
| `uniseg` | MIT | pure Python, 164 KB tables (11 MB installed, mostly docs) | 16.0 | one new dependency |
| `grapheme` | MIT | pure Python | **13.0** (stale, no GB9c) | not acceptable |
| stdlib | PSF | `unicodedata.iter_graphemes` | 17.0 | only on Python ≥ 3.15; PLAN says 3.11+ |
| vendored table | own | 2,194 ranges (GCB + ExtPict + InCB), 32 KB JSON, **9.1 KB zlib**; LV/LVT are arithmetic | pinned | ~100 lines of rule code, tested against `GraphemeBreakTest.txt` |

**Verdict: REFUTED.** The shorthand accepts splits inside 15 of 20 cluster classes. That includes CR|LF, which the design specifically calls out, and splits after a ZWJ, which the Phase 1 exit criteria claim to cover ("inside a ZWJ sequence"). It also rejects a valid boundary after a control character.

**Doc change**
- DESIGN §5.5, replace the parenthetical with:
  > …and both `start` and `end` are **extended grapheme cluster boundaries of the source under UAX #29**, computed with a pinned Unicode version that is recorded in `Result` provenance metadata: `unicodedata.iter_graphemes` on Python ≥ 3.15, otherwise a vendored table generated from the same Unicode version and tested against `GraphemeBreakTest.txt`. Offsets 0 and `len(source)` are always boundaries.
- PLAN Phase 1 exit criterion, add:
  > a span ending between CR and LF, after a ZWJ, between two regional indicators, between Hangul jamo, inside a Devanagari conjunct (क्|ष), before Thai SARA AM, or after a Prepend character is rejected; a combining mark directly after `\n` is a valid start; the verifier passes all of `GraphemeBreakTest.txt` for the pinned version.
- PLAN Phase 8 dependencies: either add a vendored table (~10 KB, no new dependency; recommended), or add `uniseg` (MIT, pure Python) as the fourth dependency. `grapheme` is not acceptable.

---

## 2. Phase 0 decision rule at n = 150 (PLAN Phase 0 0b)

**Script:** `check_r2_phase0_oc.py` (exact binomial and multinomial).

**Wilson 95% half-widths at n = 150 (points)**

| p | 0.10 | 0.20 | 0.60 | 0.70 | 0.80 | 0.85 | 0.90 |
|---|---|---|---|---|---|---|---|
| half-width | 4.84 | 6.37 | 7.75 | 7.26 | 6.37 | **5.66** (−6.21/+5.11) | 4.84 |

**Cut-points**
- Probe 1: go k ≥ 128; stop k ≤ 104.
- Probe 2: go k ≥ 120; stop k ≤ 89.
- Probe 3: go k ≤ 15; stop k ≥ 31.

**Operating characteristic** (P(go) / P(cond) / P(stop))

| probe | true rate | P(go) | P(cond) | P(stop) |
|---|---|---|---|---|
| P1 | 0.65 | 0 | .115 | .885 |
| P1 | 0.70 | 0 | .540 | **.460** |
| P1 | 0.72 | 0 | .740 | .260 |
| P1 | 0.75 | .001 | .931 | .068 |
| P1 | 0.80 | .059 | .940 | .001 |
| P1 | 0.85 | **.511** | .489 | 0 |
| P1 | 0.90 | .974 | .026 | 0 |
| P2 | 0.55 | 0 | .125 | .875 |
| P2 | 0.60 | 0 | .535 | .465 |
| P2 | 0.65 | 0 | .914 | .086 |
| P2 | 0.75 | .091 | .909 | 0 |
| P2 | 0.80 | .549 | .451 | 0 |
| P2 | 0.85 | .962 | .038 | 0 |
| P3 | 0.05 | .996 | .004 | 0 |
| P3 | 0.10 | .568 | .432 | 0 |
| P3 | 0.15 | .049 | .913 | .038 |
| P3 | 0.20 | .001 | .548 | .451 |
| P3 | 0.25 | 0 | .091 | .909 |

**Safety of "stop" on probe 1.** The worst case over true rates ≥ 0.70 is at 0.70 exactly, where P(stop | true ≥ 0.70) = **0.46**. It falls to 0.26 at 0.72 and 0.068 at 0.75. Stop is safe (≤ 7%) only from about 0.75 upward.

**The "borderline" flag carries no information.** It fires with probability 0.97 at every edge, and 0.65 even at a true 0.90 for probe 1.

**Dependence between probes 1 and 3** (same 150 cases, multinomial)
- corr(p̂1, p̂3) = −0.79 at (0.85, 0.10).
- P(both go) = 0.436 against an independent product of 0.290.
- At (0.88, 0.07), P(both go) = 0.852.

**Gap.** Probe 1's *stop* verdict has no stated consequence. The abandon criterion names only probes 2 and 3.

**Verdict: CONFIRMED** for the numbers: "about ±6 points" is right (5.66, asymmetric). **PARTIAL** for the rule.

**Doc change** (PLAN Phase 0)
> With n = 150 the Wilson half-width near 0.85 is ±5.7 points (−6.2/+5.1). A true rate exactly at an edge is called either way with probability ≈ 0.5 (probe 1 at 0.70: stop 0.46); stop is called with ≤ 7% probability only once the true rate is ≥ 5 points inside the conditional band. Probes 1 and 3 are read on the same cases (correlation ≈ −0.8) and their joint verdict is reported. The borderline mark is reported but carries no decision weight. **Probe 1 stop** has the same consequence as probe 2/3 stop [or: state what it is].

Paste the operating-characteristic table above into `docs/taxonomy.md`. The exit criteria require this before any probe runs.

---

## 3. Calibration bar (DESIGN §6.2)

**Claim.** The bar has two conditions over ≥ 1,000 decisions. First, the 95% bootstrap upper bound of top-label ECE (15 equal-mass bins) is ≤ 0.05. Second, the accuracy of decisions with p ≥ τ is ≥ τ − 0.02.

**Script:** `check_r2_calibration_bar.py`. It uses R = 500 replicates per cell and B = 300 bootstrap resamples.

**Simulated data.** Each decision is a choice over K ~ U{2..10} options. The model's distribution is Dirichlet(α), **rounded to 2 dp**, and the selected option is the argmax.
- HEAVY (α = 0.02): 61% of top-label p are exactly 1.00, 81% are ≥ 0.90.
- MODERATE (α = 0.05): 34% at 1.00, 61% ≥ 0.90.

Miscalibration is additive: accuracy = p − δ.

**P(pass) of the bar as written** (UB95 ≤ 0.05 AND τ = 0.9 rule)

| scenario, n | δ = −0.05 | −0.02 | 0 (calibrated) | +0.02 | +0.05 | +0.08 |
|---|---|---|---|---|---|---|
| HEAVY 1,000 | 1.00 | 1.00 | **1.00** | 0.92 | **0.002** | 0 |
| HEAVY 2,000 | 1.00 | 1.00 | 1.00 | 1.00 | 0.026 | 0 |
| MODERATE 1,000 | 0.67 | 0.95 | **0.96** | 0.28 | 0 | 0 |
| MODERATE 2,000 | 0.98 | 1.00 | 1.00 | 0.96 | 0.004 | 0 |

**Findings**
- **ECE is biased upward, but the upper bound does not fail a calibrated model often on Jev-like data.**
  - Mean plain ECE for a calibrated model is 0.012 (HEAVY) and 0.022 (MODERATE) at n = 1,000. The debiased values are 0.005 and 0.010.
  - The mean upper bound is 0.025 and 0.042.
  - A calibrated model fails at most 4% of the time (MODERATE, n = 1,000), and 0% at n = 2,000.
  - The concentration near 1.00 shrinks the Bernoulli variance. That is why round 1's alarming n = 300 numbers do not carry over.
  - The 1-sided (95th percentile) and 2-sided (97.5th) readings differ. MODERATE, δ = +0.02, n = 1,000: 0.28 vs 0.13. The doc does not say which it means.
- **The τ rule has no power.**
  - P(τ rule passes) is 1.000 at δ = +0.08 for τ = 0.8, and 0.96–0.99 for τ = 0.9.
  - The reason: with mass at 0.9–1.0, mean p among p ≥ 0.9 is 0.98–0.99. A model that is 8 points overconfident still has accuracy 0.90–0.91, which is ≥ τ − 0.02 = 0.88.
  - The rule compares accuracy with τ instead of with the probabilities being claimed. It only catches gross overconfidence.
- **Equal-mass binning is degenerate under ties.**
  - With quantile edges (`np.quantile`), HEAVY has only **7 of 16 distinct edges, so 7 of 15 bins are non-empty**. MODERATE has 11–12 of 15.
  - With rank splitting, ties at 1.00 spread across up to 9 bins. Re-running with another random tie-break moves ECE by more than 0.002 in up to **43%** of samples (MODERATE, δ = +0.02).
  - The two readings agree on average (plain ECE 0.0117 vs 0.0117), but the estimator is under-specified.
- **Alternative tested (ALT):** Wilson 95% lower bound of accuracy among p ≥ τ ≥ mean(p | p ≥ τ) − 0.03, AND debiased ECE (rank bins) ≤ 0.03.

  | cell | calibrated | δ = +0.02 | δ = +0.05 | δ = −0.05 |
  |---|---|---|---|---|
  | HEAVY, n = 1,000 | 1.00 | 0.27 | 0.000 | 1.00 |
  | HEAVY, n = 2,000 | 1.00 | 0.55 | 0.000 | 1.00 |
  | MODERATE, n = 1,000 | 0.98 | 0.16 | 0.000 | 0.82 |
  | MODERATE, n = 2,000 | 1.00 | 0.36 | 0.000 | 0.86 |

  For τ = 0.8 the numbers are similar. ALT has much more power in the region the threshold would actually operate in.

**Verdict: PARTIAL.**
- The ECE upper-bound half is well-powered at n ≥ 1,000 on concentrated 2-dp data: calibrated ≥ 0.96, δ = 0.05 ≤ 0.03.
- The τ half is vacuous.
- The binning, and the 1- vs 2-sided bound, need pinning.

**Doc change** (DESIGN §6.2, PLAN §6)
> …over ≥ 1,000 pre-labelled decisions: (1) the one-sided 95% percentile-bootstrap upper bound (B ≥ 1,000) of top-label ECE on p(selected), **15 equal-count bins formed on the sorted distinct values so that tied probabilities are never split** (reported with the number of non-empty bins), is ≤ 0.05; **and** (2) among decisions with p ≥ τ, the Wilson 95% lower bound of accuracy is ≥ **mean(p | p ≥ τ) − 0.03** (not τ − 0.02, which an 8-point-overconfident model passes 96–100% of the time). Brier score and debiased ECE are reported alongside. Simulated operating characteristic: calibrated passes ≥ 0.98; 2 points overconfident passes 0.16–0.55; 5 points overconfident passes 0.00.

---

## 4. Phase 5 coverage rule (PLAN Phase 5)

**Script:** `check_r2_phase5_bars.py`.

**Pass regions at n = 150.** The doc does not name the interval; Wilson 2-sided and Clopper-Pearson are almost identical here.
- Abstention LB ≥ 0.60 needs **k ≥ 102 (0.680)**; Clopper-Pearson needs 103.
- False-abstention UB ≤ 0.20 needs **k ≤ 20 (0.133)**.

**P(pass)** (Wilson; n = 150 absent, 150 present)

| true abstention | 0.60 | 0.65 | 0.70 | 0.75 | 0.80 | 0.89 |
|---|---|---|---|---|---|---|
| P(pass) | .026 | .248 | .736 | .979 | 1.000 | 1.000 |

| true false-abstention | 0.05 | 0.10 | 0.12 | 0.15 | 0.18 | 0.20 |
|---|---|---|---|---|---|---|
| P(pass) | 1.000 | .928 | .741 | .332 | .080 | .022 |

**Both bars together**
- (0.89, 0.10): 0.928.
- (0.80, 0.15): 0.331.
- (0.70, 0.10): 0.683.

**Inconsistency with Phase 0.** Phase 0 calls 0.60–0.80 abstention and 0.10–0.20 false abstention *conditional* (proceed with a second gate). Phase 5 then abandons with high probability inside that band, at the same true rate:

| true rate | P(Phase 0 not stop) | P(Phase 5 abandons) | P(both) |
|---|---|---|---|
| abstention 0.65 | .914 | .752 | .687 |
| abstention 0.70 | .997 | .264 | .263 |
| false-abstention 0.15 | .962 | .668 | .643 |
| false-abstention 0.17 | .861 | .863 | .743 |

Phase 5's effective thresholds (0.68 and 0.133) are not Phase 0's (0.60 and 0.20).

**n needed** (P(pass) ≥ 0.9, Wilson)
- True abstention 0.70: n = 240.
- True false-abstention 0.12: n = 230.
- True false-abstention 0.15: n = 620.

**Verdict: PARTIAL.** The bar is well defined once the interval is named, but it contradicts Phase 0's conditional band.

**Doc change.** Pick one of the following, and name the interval (Wilson, two-sided 95%).
- (a) PLAN Phase 5:
  > …abandon only if the Wilson 95% **upper** bound of abstention is < 0.60 or the **lower** bound of false abstention is > 0.20 (i.e. Phase 5 re-tests Phase 0's *stop* band)

  and add:
  > the *conditional* second gate must bring the point estimates into Phase 0's go band.
- (b) Keep the strict bound, but record in Phase 0:
  > a *conditional* verdict with point estimates below 0.70 abstention or above 0.12 false abstention predicts Phase 5 abandonment (P ≥ 0.26–0.75); Phase 5 uses n ≥ 250 per arm (P(pass) ≥ 0.9 at 0.70 abstention / 0.12 false abstention).

---

## 5. Retry bar (DESIGN §5.4, PLAN Phase 5)

**Script:** `check_r2_phase5_bars.py` §5.

**Recovery ≥ 10% over 100 present-answer abstentions** (point estimate; pass iff k ≥ 10)
- P(pass) = .028 at 5%, .549 at 10%, .945 at 15%.
- This separates 5% from 15% adequately.

**The ≥ 100 abstentions are not obtainable from the stated corpus.** At a false-abstention rate of 0.10, getting ≥ 100 abstentions with P ≥ 0.9 takes **1,130 present-answer cases**; at 0.05 it takes 2,260. PLAN §1.1 budgets ≥ 150 present cases, which yield about 15 abstentions.

**False-commit increase ≤ 2 points.** Retry acts only on abstentions, so the increase is x/N: the absent cases that commit after retry, over N absent cases, as a paired one-sided count.
- At N = 150 (the Phase 5 absent arm), a point-estimate pass needs **x ≤ 3**. P(pass) = .935 at a true increase of 1%, .647 at 2%, .338 at 3%, .146 at 4%.
- As a CI rule it **cannot pass at N < 183** even with 0 events: the Clopper-Pearson upper bound for 0/150 is 0.0243. At N = 200 it needs 0 events, and P(pass | 0.5%) = 0.37.
- For 90/90 separation, the point-estimate rule needs **N ≥ 175** to separate 0.5% from 4%, and **N ≥ 475** to separate 1% from 3%.

**Joint bar at (100 abstentions, 150 absent)**
- recovery 0.15 with +0.02: 0.61.
- recovery 0.10 with +0.00: 0.55.

**Verdict: REFUTED as decidable at the stated n.** The rule is unspecified (point estimate or bound), 100 abstentions cannot be collected from a 150-case arm, and "≤ 2 points" at N = 150 is a 3-event threshold.

**Doc change** (DESIGN §5.4 and PLAN Phase 5)
> **Retry bar (two-sided, point estimates, pre-registered).** Recovery is measured on ≥ 100 present-in-source cases whose first choice abstained, collected by removing the correct span from the first-pass candidate set of present-answer cases (an extractor miss), so they need not be harvested from ~1,000 natural cases. The false-commit increase is the paired count of truly-absent cases that commit only after retry, over **N ≥ 300** absent cases (pass iff ≤ 6; P(pass) 0.97 at 1%, 0.20 at 3%, 0.04 at 4%). Retry stays on iff recovery ≥ 10% **and** increase ≤ 2 points.

---

## 6. Source-screen bar (PLAN Phase 5)

**Script:** `check_r2_phase5_bars.py` §6.

**Pass regions at n = 100**
- The FP upper bound ≤ 0.05 needs **0 false positives** (Wilson and Clopper-Pearson). Wilson one-sided allows 1.
- The TP lower bound ≥ 0.80 needs ≥ 88/100 (Wilson) or ≥ 89/100 (Clopper-Pearson).

**P(FP pass)** at n = 100

| true FP | 0.005 | 0.01 | 0.02 | 0.03 |
|---|---|---|---|---|
| P(FP pass) | .606 | .366 | .133 | .048 |

**P(TP pass)** at true TP 0.90: .80 (Clopper-Pearson .70). At 0.95: ≈ 1.

**Joint P(pass)** at (FP .01, TP .95): **0.37**. A screen whose true FP rate is 1%, five times better than the bar asks, stays opt-in 63% of the time.

**At other n**

| n | FP rule | P(pass) at FP .01 / .02 / .03 | TP rule | P(TP pass) at .90 |
|---|---|---|---|---|
| 300 | ≤ 7 FP | .989 / .745 / .320 | ≥ 254 TP | .999 |
| 500 | ≤ 15 FP | 1.0 / .953 / .568 | | |

**Verdict: PARTIAL.** The bar is safe but, at n = 100, a zero-tolerance test. The interval method changes the TP threshold.

**Doc change** (PLAN Phase 5)
> …measured on ≥ **300** benign and ≥ **150** attacked real documents; default-on only if the Wilson 95% upper bound of FP ≤ 0.05 (≤ 7/300) and the lower bound of TP ≥ 0.80 (≥ 130/150).

---

## 7. Pydantic normalisation coverage (DESIGN §3, §4.2, §10; PLAN Phase 2)

**Script:** `check_r2_pydantic_coverage.py`. It covers 25 models in validation and serialization mode, walks every keyword, and greps each keyword against DESIGN and PLAN with word boundaries.

**Handled**
- Static `$ref`/`$defs`, including generic `Box_int_`/`Box_str_`.
- `Optional[nested]` becomes `anyOf[$ref, null]`.
- A recursive model (root `$ref` cycle) is refused.
- `Union[A,B]` is refused `not_yet_supported`.
- An int Enum and IntEnum become `enum` → choice.
- `Literal[a,b,c]` becomes `enum`.
- `Literal[True]` becomes `const`.
- set/frozenset (`uniqueItems`), conlist (`minItems`/`maxItems`), `maxLength` and `pattern` are validated.
- conint ge/le becomes `minimum`/`maximum`.

**Gaps.** These keywords appear nowhere in DESIGN.md or PLAN.md, or they get wrong routing.

| # | shape | emitted | problem |
|---|---|---|---|
| 1 | `dict[str,X]`, bare `dict` | `additionalProperties: X` / `true`, no `properties` | open key set; no mapping and no refusal rule |
| 2 | `extra='forbid'` | `additionalProperties: false` | not mentioned; harmless for assembly, but should be declared as class A |
| 3 | discriminated union | `oneOf` + **`discriminator`** + `const` tags | a declared tag could make the branch deterministic, yet Phase 6 plans a Jev choice. `discriminator` is ignored by jsonschema |
| 4 | datetime/date/time/timedelta/UUID/EmailStr/HttpUrl/bytes | `type: string` + **`format`** (`date-time`, `date`, `time`, `duration`, `uuid`, `email`, `uri`, `binary`) | all route to "undeclared unbounded string → refuse". Phase 5's `patterns.py` extracts dates and emails, but no rule maps `format` to candidate extraction |
| 5 | `constr`, HttpUrl | **`minLength`** | only `maxLength` is named |
| 6 | `conint(gt,lt)`, `confloat(gt,lt)` | **`exclusiveMinimum`/`exclusiveMaximum`** | "integer range of 2–10 values" and "bounded" consider only min/max; `conint(gt=0, lt=6)` is a 5-level range the rule would miss |
| 7 | `conint(ge=0, le=100, multiple_of=5)` | **`multipleOf`** | 21 values; the range-size rule is undefined with a step |
| 8 | `tuple[int,str]` | **`prefixItems`** + `minItems=maxItems=2` | no mapping for fixed-arity positional arrays |
| 9 | `computed_field` | **`readOnly`**, *serialization mode only* | "its emitted JSON Schema" never says which mode. Decimal also differs between modes |
| 10 | **`Decimal`** | validation: `anyOf[{number}, {string, pattern}]`; serialization: `{string, pattern}` | a 2-non-null-branch `anyOf`, so it is refused `not_yet_supported` and Phase 6 would ask Jev to discriminate number from string. Money fields typed `Decimal`, the idiomatic choice, cannot compile |
| 11 | 1-member `Enum` | `$ref` → `enum: ["only"]` | the "enum < 2 values" refusal fires, while `Literal["only"]` (`const`) is normalised to a constant. Inconsistent |
| 12 | `Any` | `{}` (no `type`) | typeless schema, no rule |
| 13 | `Literal[1, "one"]` | `enum` without `type` | the mapping assumes typed enums |
| 14 | `json_schema_extra={"jevson": …}` | bare `jevson` keyword | raw JSON Schema uses `x-jevson-generate`, so there are two spellings |
| 15 | required `Optional[bool]` | `anyOf[boolean, null]`, required | when a nullable field gets `null` vs `Unresolved` is still undefined (R1 item). DESIGN §6.1 says unresolved is omitted, never null |

Round 1's L4 recommendation to map an integer range to `score` only when the field is annotated as ordinal is **not adopted** in Rev 4 §4.2. `Annotated[int, Field(ge=1, le=5)]` (a count or a rating) still becomes a `score`.

**Verdict: PARTIAL.** The Rev 4 normaliser covers $ref, nullable, const and Enum. Gaps remain: additionalProperties, discriminator, format, minLength, exclusive bounds, multipleOf, prefixItems, readOnly/mode, the Decimal union, 1-member Enum, and the empty schema.

**Doc change** (PLAN Phase 2 `normalise.py` / `mapping.py`, and DESIGN §10)
> The normaliser also: (i) rewrites `exclusiveMinimum/Maximum` on integers to inclusive bounds and counts `multipleOf` steps when sizing a range; (ii) collapses `anyOf[{type:number},{type:string,pattern}]` (Pydantic `Decimal`) to a number; (iii) treats a single-value `enum` like `const`; (iv) treats a `oneOf` whose branches carry distinct `const` values at a `discriminator.propertyName` as a declared tag (still a Jev choice between branches, but options named by tag); (v) accepts `x-jevson-*` and Pydantic's `jevson` key as one spelling. Mapping: `format` ∈ {date, date-time, email, uri, uuid} on a string routes to candidate extraction (class D + F) in Phase 5 and refuses with `not_yet_supported` before it; `additionalProperties` other than `false`, `prefixItems`, and the empty schema refuse with named reasons; `minLength`, `readOnly`, `additionalProperties:false` are class A / validated. **The compiler reads the validation-mode schema**, and a test pins that choice.

---

## 8. Two-decimal rounding and cache canonicalisation (DESIGN §2.1, §4.2, §5.6, §6.2, §8.4; PLAN Phase 3)

**Script:** `check_r2_rounding.py`.

**A. Real responses.** These are 630 unique choice/score distributions and 1,616 noul values mined offline from round 1's raw jev-1.13.0 JSON.
- **Sums:** 626 are exactly 1.00 and 4 are 0.99. The maximum |sum − 1| is 0.01.
- **Zeros:** there are 1,907 option probabilities of exactly 0.00, but the selected option was never at 0.00.
- **Ties and argmax:** 0 exact top ties, and `choice` equals the argmax in 618/618.
- **Types:** every value is a JSON float.
- **Nouls:** none at exactly 0.5 in these files. P1 reports 2/30 elsewhere.

**B. Simulated rounding.** With naive 2-dp rounding:
- The sum is ≠ 1.00 in 23–59% of distributions for K ≥ 3, with |dev| up to 0.04 at K = 11 (bound K × 0.005). Jev's real sums are tighter, so it probably renormalises, but not always.
- Top ties after rounding: 0.1–7.5% depending on K and flatness (7.5% at K = 11, α = 2).

**C. Float comparisons.** These are safe on the parsed floats:
- `p > 0.5` and `p ≥ τ` match exact decimal comparison for all 101 values.
- `p ≤ floor` is safe.
- 0.50 parses exactly.

These go wrong:
- `1 − p` differs from the 2-dp complement for 40/101 values (1 − 0.7 = 0.30000000000000004).
- **PLAN Phase 3's fixture rule "top-two margin ≥ 0.10" computed in floats excludes 56 of 91 pairs whose exact margin is 0.10** (e.g. 0.12 − 0.02 = 0.0999…).
- A sum check with `abs(sum − 1) ≤ 1e-9` rejects 4/630 real responses.

**D. Canonicalisation.**
- Sorting `probabilities` keys is lexicographic: `c10 < c2`. It makes iteration deterministic, but `max(..., key=get)` over the two orders of one tied response returned `c10` vs `c2`, so tie-breaking is order-dependent unless a tie rule exists.
- Python `json.dumps` vs JS `JSON.stringify` differ:
  - `1.0` vs `1`, `100.0` vs `100`, `-0.0` vs `0`, `1e-07` vs `1e-7`;
  - key order for non-BMP keys (Python sorts by code point, JS and RFC 8785 by UTF-16 units: `ﬁ` vs `😀` reversed);
  - `ensure_ascii` changes bytes;
  - `json.dumps(nan)` emits invalid `NaN`.

  A Python cache key therefore does not reproduce in the Phase 10 port.

**Verdict: PARTIAL.** Binary rules (`> 0.5`, `≤ floor`) are sound on 2-dp values. These are undefined or fragile: choice/score ties, the sum tolerance, float margins, and cross-language hashing. The sort alone is enough for a Python-only cache hash, but not across languages.

**Doc changes**
- DESIGN §2.1 / PLAN Phase 3:
  > Probabilities are handled internally as **integer hundredths** (`round(p*100)`); margins, sums and thresholds are computed on integers. A distribution is valid iff every value is in [0, 100] and |Σ − 100| ≤ ⌈K/2⌉ (observed ≤ 1); otherwise `invalid_backend_answer`.
- DESIGN §6.2:
  > **A choice or score whose top two probabilities are equal yields `Unresolved(reason=tie)`**, like a binary tie; the response's `choice` field is used only if it is an argmax, else `invalid_backend_answer`.
- DESIGN §8.4:
  > The request hash is SHA-256 over **RFC 8785 (JCS)** canonical JSON, UTF-8, with a canonicalisation-version prefix; non-finite numbers are refused before hashing; `probabilities` are stored in JCS order. Option-id ordering for display uses numeric id order (`c2 < c10`).
