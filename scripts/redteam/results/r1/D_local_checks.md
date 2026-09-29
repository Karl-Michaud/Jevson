# D — Local verification of Jevson DESIGN/PLAN claims (no Jev API)

Scripts: `/Users/karlosins/project-asterion/Jevson/scripts/redteam/check_*.py|.mjs`.
Raw outputs: `.../scratchpad/redteam/r1/outputs/*.txt` (host Python 3.11.7, Unicode 14.0) and `.../r1/py312/*.312.txt` (Docker python:3.12.14, Unicode 15.0).
Libraries used: pydantic 2.13.5, jsonschema 4.26.0, numpy 2.4.6, scipy 1.17.1, tiktoken (cl100k_base, used as a proxy tokenizer), Node 24.10.0.
Python 3.12 cross-check: `check_span_unicode`, `check_pydantic_schema` and `check_property_claims` produce byte-identical output on 3.11 and 3.12. `check_unicode_version_drift` shows that NFC+casefold+isspace gives the same result for every code point on both versions (digest `d957d8fb521aec4b`, 0 differing rows).

---

## 1. Span semantics and the default Normalizer — DESIGN §5.5, §5.6, PLAN Phase 1/7
**Script:** `check_span_unicode.py`

**Results**
- Code-point offsets verify correctly for é, 👍🏽 (2 code points: U+1F44D U+1F3FD), CJK and combining text. Byte offsets used as str offsets fail in every case, so the design is right to reject byte offsets. The rule "`source[start:end]==text`, half-open" behaves as written.
- **Exact matching rejects legitimate candidates.** Take a source with decomposed `José` and an extractor that returns precomposed `José`: `find = -1`, so the span is rejected. The same happens for CRLF source vs an LF candidate (`-1`). After NFC the source shrinks from 25 to 24 code points, so NFC-space offsets are not source offsets.
- **A span can split a grapheme and still verify:** `[i,i+4)` = `"Jose"` cuts off U+0301 and still returns `True`. `"👨‍👩‍👧"[0:1]` also verifies. The verification rule does not check grapheme boundaries.
- Confusables: Cyrillic `Acmе` is neither found as, nor merged with, Latin `Acme`. That is safe.
- The normalizer changes lengths: `ß→ss` (1→2), `İ→i̇` (1→2), `ﬃ→ffi` (1→3), `ΐ→` 3 code points, `Straße` 6→7. In the sample text the offset of "Dana" moves 36→37, so normalized offsets would fail verification. Pre-merge must therefore compare normalized *keys* only and never emit normalized offsets. The design does not say this.
- **Unsafe merges with the default:** `US/us`, `Apple/apple`, `IT/it`, `CAT/cat`, `MAY/May` all merge. `Straße/STRASSE` merges (probably intended). Zero-width space defeats the merge (`Dana​Whitfield` ≠ `DanaWhitfield`). NBSP merges. Fullwidth `１２３`/`123` and `Ⅻ`/`XII` do not merge, because the design uses NFC, not NFKC.
- NFC→casefold is not canonical caseless matching. Scanning all code points found 11 pairs (Greek dialytika and ypogegrammeni) that are canonically caseless-equal but not merged. This is a minor edge case.

**Verdict:** PARTIAL. Offsets: CONFIRMED. Casefold as a default for entity types: REFUTED as "safe".

**Required doc change**
- (a) §5.5: state that extractors must locate spans in the raw source. Specify whether candidate text is matched after NFC. Recommended: verify exact raw text, but locate by searching the raw source, and record an "LLM text ≠ source text" rejection reason.
- (b) State whether spans must lie on grapheme-cluster boundaries. Recommend requiring this, using `\X` from the `regex` package.
- (c) §5.6: pre-merge keys are never offsets. Provenance always points at the representative's raw span.
- (d) Make the default normalizer case-preserving (NFC + whitespace collapse, where whitespace includes NBSP and zero-width characters). Casefold should be opt-in per entity type, or casefold only when the strings are not all-caps tokens of ≤4 letters. At minimum, add `US`/`us` and `Apple`/`apple` to the Phase 7 exit tests as must-not-merge-by-default cases.

## 2. JS UTF-16 vs Python code points — PLAN Phase 10
**Script:** `check_js_offsets.mjs` + `check_js_offsets_py.py` (runs node and compares)

**Results:** in `"Paid 👍🏽 to 𝐀cme 東京 José́ — Dana Whitfield"`:
- "Dana Whitfield" is code point `[27,41)` but UTF-16 `[30,44)`.
- Using Python offsets directly in JS `slice()` failed for all 5 targets. Explicit conversion succeeded for all 5.
- Code-point offsets computed in node equal Python's (`True`).
- BMP-only content (é, CJK, combining) gives identical indices. Only astral characters shift the offsets.
- JS can slice a lone surrogate (`"👍".slice(0,1)`), which encodes to U+FFFD.

**Verdict:** CONFIRMED.

**Required doc change (small):** the Phase 10 fixture should also assert that a span boundary inside a surrogate pair is rejected.

## 3. Pydantic → JSON Schema vs phase ordering — PLAN Phase 2 vs Phase 6
**Script:** `check_pydantic_schema.py`

**Results:** 10 of the 14 common model shapes emit keywords that Phase 2 excludes, since unions and `$ref` are Phase 6:
- nested submodel → `$defs` + `$ref`
- `Enum` class → `$ref` (a plain string enum becomes `$ref` to `#/$defs/Tier`)
- `Optional[X]` → `anyOf:[X,{type:null}]`
- `Optional[Enum]` → `anyOf:[{$ref},{null}]`
- `Literal["x"]` → `const`
- a default on an enum field → `$ref` + `default`
- a discriminated union → `oneOf` + `discriminator` + `const`
- a three-level nested model → `$ref` chain
- a recursive model → a root `$ref`

Only `Literal[a,b,c]` (inline `enum`), conint, confloat and `list(max_length)` are free of these keywords. Two fields of one submodel type share `#/$defs/Address`, so node ids must come from instance pointers after inlining. Serialization-mode and validation-mode schemas were identical for every model tested.

**Verdict:** REFUTED as sequenced. Phase 2's "nested object support", "a three-level nested object compiles" and "a Pydantic model and its emitted JSON Schema compile to identical graphs" cannot be met for any Pydantic model with a submodel, an Enum class or an Optional field unless Phase 2 already resolves static `$ref` and treats `anyOf[X,null]` as nullability (class A), not union discrimination.

**Required doc change**
- Move static acyclic `$ref`/`$defs` inlining and the `anyOf[X,{type:null}]` → nullable-X rule into Phase 2.
- Define that a nullable pattern is not a Jev union choice. Also define how `null` interacts with `Unresolved`: null is a legitimate value, and an abstention is not.
- Map `const` to class A.
- Keep only real multi-branch unions in Phase 6.
- Require node ids to be derived from instance pointers.
- Update DESIGN §10's `$ref` row accordingly.

## 4. Mapping precedent — DESIGN §9, PLAN Phase 2; also DESIGN §2 primitive table
**Script:** `check_mapping_semantics.py`

**Results**
- Vendor `api.md`: a **noul answer has fields `['type','noul']` only, with no confidence**. Only choice and score carry `confidence`. DESIGN §2 says noul returns "boolean probability + confidence", and §8.1 promises a `Confidence` per decision.
- Score `score` is "probability-weighted … can land between levels". For probs `[.45,0,0,0,.55]` over levels 1–5, the weighted score is 3.20, which fails `type: integer`. `round()` gives 3, which has probability 0.00, while argmax is 5.
- A field bounded 0–1 is usually a value (tax_rate 0.20, discount 0.15, share 0.51). Writing a noul probability into it produces a wrong-but-valid value, and `minimum:0,maximum:1` cannot tell a value field from a probability field.
- Integer ranges with 2–10 levels include counts (bedrooms 1–10, quantity 1–10), which are source-extractable values, not ordinal ratings.
- The comparison direction at the 0.5 threshold (≥ or >) is unspecified.

**Verdict:** REFUTED as a default mapping. It is a design risk.

**Required doc change**
- "number bounded 0–1 → raw probability" must only apply when the field is explicitly annotated as a probability (for example `x-jevson: probability`). Otherwise route it to class D/F: source span plus parse.
- Integer range → `score` only for fields annotated as ordinal. Use the argmax level, never the weighted `score`.
- Fix DESIGN §2: noul has no vendor confidence. Define the reported noul confidence (for example `max(p,1-p)`) as a Jevson-derived quantity, or drop it.
- Pin the bool threshold as `p ≥ 0.5 → true` (or `>`).

## 5. Probe statistics — PLAN Phase 0
**Script:** `check_probe_stats.py`

**Results** (95% intervals)
- n=100, Wald half-width: p=.5 ±9.8, .7 ±9.0, .8 ±7.8, .85 ±7.0, .9 ±5.9, .95 ±4.3, .10 ±5.9. Wilson widths are 19.2 / 17.7 / 15.5 / 14.0 / 11.9 / 9.0 points respectively.
- n=20: ±21.9 at .5, ±15.6 at .85, ±13.1 at .9.
- Probability of each verdict at the band edges (point-estimate rule, n=100):
  - P1, true .85: go 0.568, conditional 0.432. True .87: go 0.776. True .80: go 0.129. True .70: stop 0.451, conditional 0.549.
  - P2, true .80: go 0.559. True .60: stop 0.457.
  - P3, true .10: go 0.583, conditional 0.416. True .08: go 0.824. True .12: go 0.334. True .20: stop 0.441.
  - P4 (50 clusters), true .85: go 0.519. True .70: stop 0.431.
- P3: the Wilson CI at an observed 10/100 is [0.055, 0.174], wider than the 10-point conditional band.
- Joint P1-go ∧ P3-go (same 100 cases, multinomial): 0.828 when the true rates are (.88 correct, .07 abstain), and 0.475 at (.85, .10).
- **n=20 claim:** at n=20, true .90 is classified stop with probability 0.002 and true .65 is classified go with probability 0.044. So n=20 does separate go from stop under a point-estimate rule. What it cannot do is separate adjacent bands.
- Minimum n for true .65 to be called stop with probability ≥0.9 is 155. For true .90 to be called go with probability ≥0.9 it is 40.

**Verdict:** PARTIAL.
- "±8–10 points" is correct only for p between 0.5 and 0.75. At the operating points it is ±6–8. That is conservative and harmless.
- "Enough to separate the bands" is true for go vs stop (P1 true .90 → stop 6e-9), but adjacent bands are a coin flip at the edges.
- "n=20 could not distinguish go from stop" is REFUTED under a point-estimate rule and true only under a CI rule.

**Required doc change**
- Pre-register the decision rule: point estimate, or the CI lower/upper bound relative to the band.
- State the expected misclassification at the edges (≈43% at the P1 go edge).
- Correct the half-width text to "±6–10 points depending on p".
- Either accept that edge cases fall into "conditional", or raise n to about 150–200 for P1/P2 and P3.
- Define the P4 unit (cluster vs pair) and note its wider interval (±9.9 at .85).

## 6. ECE ≤ 0.05 over ≥ 300 decisions — DESIGN §6.2, PLAN Phase 5, §6, §9
**Script:** `check_ece_bar.py` (4000 Monte Carlo replicates per cell)

**Results** (top-label ECE, equal-width bins; "P(pass)" means measured ECE ≤ 0.05)

| confidence dist | bins | n | calibrated P(pass) | δ=0.05 overconf. P(pass) | δ=0.08 P(pass) | δ=0.10 P(pass) |
|---|---|---|---|---|---|---|
| Beta(18,2) (mass .8–1) | 10 | 300 | 0.988 | 0.403 | 0.056 | 0.006 |
| Beta(18,2) | 15 | 300 | 0.961 | 0.334 | 0.036 | 0.003 |
| Uniform(.5,1) | 10 | 300 | 0.766 | 0.305 | 0.062 | 0.012 |
| Uniform(.5,1) | 15 | 300 | **0.472** | 0.137 | 0.022 | 0.004 |
| Uniform(.5,1) | 15 | 1000 | 0.993 | 0.382 | 0.009 | 0.000 |
| Beta(18,2) | 10 | 1000 | 1.000 | 0.444 | 0.003 | 0.000 |

- At n=300, a perfectly calibrated model has mean measured ECE of 0.025–0.052, depending on the confidence spread and the number of bins.
- With a wide confidence spread and 15 bins, a calibrated model fails the bar 53% of the time.
- The debiased ECE at n=300 fixes false failures (calibrated pass rate 0.95–0.998), but it lets δ=0.08 pass 18–37% of the time.
- A model overconfident by exactly 0.05 passes about 45% of the time at any n, because that is the threshold itself.

**Verdict:** REFUTED as a pre-registered bar. The number of bins, the binning scheme, the estimator and the decision rule are all unspecified, and at n=300 the outcome depends on them (pass rate for a calibrated model ranges from 0.47 to 0.99).

**Required doc change:** pre-register all of the following:
- top-label confidence over candidate choices, including `none_of_these`
- 10 equal-width bins (or 10 equal-mass bins)
- the plain ECE estimator
- **n ≥ 1000**: calibrated passes ≥0.99 and δ=0.08 passes ≤0.01 in both distributions
- or keep n=300, but report the bootstrap 95% CI and a reliability diagram, pass only if the debiased ECE is ≤ 0.05 *and* the calibration gap in the bin(s) containing the proposed threshold is within ±0.05 by CI

Also add Brier score, since ECE averages away exactly the gap at a threshold.

## 7. Pairwise counts and context budget — DESIGN §8.2, §12, PLAN Phase 7
**Scripts:** `check_pairwise_budget.py`, `check_vendor_limits.py`

**Results**
- 190 / 435 / 32385: CONFIRMED.
- Vendor `models.md`: "64k tokens per request; **32k tokens for `state` plus the longest question**". DESIGN only mentions ~64k.
- Question-map tokens for n=30 (435 questions), cl100k proxy, as JSON:
  - keys-only template: ≈18.3k (42/question), leaving ≈47k for the state
  - inline candidate strings: ≈27.5k (63/question), leaving ≈38k
  - inline strings plus a context snippet: ≈57.8k (133/question), leaving ≈7.8k
- n=35 with context snippets does not fit (≈78.9k).
- Also, 435 keyed questions in one call is outside the measured keyed-batching regime: §2.1 measured 0/320 errors at 320 items per request.

**Verdict:** PARTIAL. The arithmetic is confirmed, and n=30 fits with compact questions and a state up to ~38–47k tokens. However, the per-question limit is 32k, not 64k, and n=30 exceeds the batch size that was actually measured.

**Required doc change**
- §2 and §8.2 must state both vendor limits. The "single oversized question refuses" rule must use **state + longest question ≤ 32k**. Otherwise a 40k-token state passes the design's check and fails at the API.
- Pairwise questions must reference candidates by key, not inline context. Record the per-question token size as a budget input.
- Note that 435 is beyond the 320 items validated in §2.1, or split pairwise batches at ≤320.
- Tokenizer caveat: the counts use cl100k as a proxy, and Jev's tokenizer is unpublished.

## 8. Retry recovery < 10% → budget 0 — DESIGN §5.4, PLAN Phase 5
**Script:** `check_retry_threshold.py`

**Results**
- The denominator is abstention events, not decisions. A 300-decision corpus yields only about 15–30 abstentions when all answers are present, or about 90–100 if a third of the cases have the answer removed.
- P(observed < 10%):
  - n=30 abstentions: true .05 → 0.812, true .10 → 0.411, true .15 → 0.151, true .20 → 0.044
  - n=100: 0.972 / 0.451 / 0.055 / 0.002
- Wilson CI at an observed 10%: n=30 [0.035, 0.256], n=100 [0.055, 0.174].
- Separating true 5% from true 15% with probability ≥0.9 each way needs **≈60 abstentions**. With probability ≥0.8 it needs ≈28.
- A true rate of exactly 10% is a coin flip at any n (0.41–0.48).

**Verdict:** PARTIAL. It is measurable, but the plan sets no minimum number of abstention events, and a 300-decision corpus may produce as few as 15.

**Required doc change**
- Pre-register "≥ 60 abstention events (candidate-backed) in the denominator".
- Separate abstentions where the answer was present (recovery desirable) from abstentions where it was absent (the correct outcome is `Unresolved`). Recovery on the absent set is a wrong commit.
- Report the retry's new-wrong-commit rate alongside recovery. The rule should be "recovery < 10% **or** wrong commits ≥ recoveries → 0".

## 9. Property invariants — PLAN §4.3, §3 determinism
**Script:** `check_property_claims.py`

**Results.** Each of the following "fully resolved" assemblies is built from design-legal parts, and each fails jsonschema validation:
- a verified span violating `maxLength`
- a verified span violating `pattern`
- 1 accepted member with `minItems:2`
- unmerged duplicates with `uniqueItems`
- a missing `dependentRequired` field
- a weighted score written into an `integer` field

`format: date` passes by default and fails only with a FormatChecker.

For Cost:
- Across two identical runs the counters are equal, but the whole Cost is not, because `wall_clock_by_component` differs.
- Retry 0 vs 1 counters are componentwise ≤.

**Verdict:** PARTIAL / ill-posed.
- "Assembly of a fully resolved graph always validates" is false unless the compiler refuses such constraints, or the assembler turns a violating resolved value into `Unresolved` / `SchemaViolation`.
- "Cost monotonic" is well-defined only as a componentwise order on the counters.
- "Same input → same output" is false for `Result` as pinned, because it contains wall-clock times.

**Required doc change**
- Restate the invariant as "a fully resolved graph assembles to a value that validates, **or** the violating pointers are reported as `Unresolved(reason=constraint)` / `SchemaViolation`". This matches DESIGN §6.1.
- Define Cost monotonicity over the counter fields only.
- Exclude `cost.wall_clock_by_component` from the determinism and conformance comparisons.

## 10. jsonschema library — PLAN Phase 8 dependency
**Script:** `check_jsonschema_lib.py`

**Results**
- jsonschema 4.26.0 ships Draft3/4/6/7/2019-09/2020-12 validators. `validator_for({})` returns Draft202012Validator.
- Pydantic output carries no `$schema` key, but it passes the 2020-12 metaschema, and its `$ref`/`$defs` resolve.
- **`format` is not asserted by default.** `jsonschema.validate("garbage", {"format":"date"})` returns valid. With a bare `FormatChecker()`, only 9 formats are checked on 3.11 (date, email, idn-email, idn-hostname, ipv4, ipv6, regex, time, uuid) and 8 on 3.12, where idn-hostname is missing. `date-time` and `uri` are not checked without optional extras.

**Verdict:** CONFIRMED (2020-12 support). PARTIAL for "validate against the original schema", because format is silently unchecked.

**Required doc change**
- State that validation uses `Draft202012Validator(schema, format_checker=FormatChecker())`, plus the `jsonschema[format]` extra (rfc3339-validator etc.), or explicitly exclude `format` from the Constraint tier in DESIGN §6.
- Pin the draft when `$schema` is absent.

## 11. Additional findings
**Scripts:** `check_vendor_limits.py`, `check_unicode_version_drift.py`
- "$0.068 per 1000 decisions" (DESIGN §2): no vendor doc mentions it (grep: none). At $0.042/Mtok it implies ≈1619 input tokens per decision, which depends on state size and batching. **PARTIAL:** mark it as an estimate with its assumption, or remove it.
- Normalizer determinism across 3.11 (Unicode 14.0) and 3.12 (Unicode 15.0): identical for all code points. **CONFIRMED.** Python 3.13 (Unicode 15.1) is untested. Pin the "unicodedata version" in the conformance fixtures.
