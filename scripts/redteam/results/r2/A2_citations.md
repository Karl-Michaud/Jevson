# A2 — Citation audit of Revision 4 (red-team round 2)

Scope: every evidence tag in `DESIGN.md`, `PLAN.md`, `README.md` (working tree, branch `docs/revision-3-decisions`), resolved against `docs/REDTEAM.md` and the round-1 evidence in `scripts/redteam/results/r1/`. Numbers were recomputed from `raw/*.json` wherever the raw data holds them. External items were spot-checked with `gh api` and the PyPI/npm registries on 2026-09-29. No design doc was edited.

Tag inventory: 193 tag instances (DESIGN 138, PLAN 55, README 0). `DESIGN.md:9` and `PLAN.md:5` are example tags inside the evidence rule, not claims. Every tag used resolves to a row in `docs/REDTEAM.md`.

Line references are `D<n>` for DESIGN.md, `P<n>` for PLAN.md, `R<n>` for README.md and `RT<n>` for docs/REDTEAM.md.

Recomputation scripts written for this round (scratchpad): `r2/sim_bar.py`, `r2/sim_bar2.py`. Everything else was computed inline from `raw/*.json` with `python3 -c`, as noted in each row.

---

## (a) Tag verdict table

Verdicts: **S** = supported, **O** = overstated or misattributed, **W** = wrong, **U** = unsupported by the cited evidence.

### DESIGN.md

| # | line | claim (short quote) | tag | evidence checked | verdict |
|---|---|---|---|---|---|
| 1 | D17 | constrained decoding ships in OpenAI SO, Anthropic strict, vLLM, Outlines, XGrammar, llama.cpp GBNF | X1 | C row 1a | S |
| 2 | D17 | not unconditional: refusals, max_tokens, silently skipped keywords, Anthropic enum capitalisation | X1 | C rows 1b, 1c (quotes) | S. The sentence still opens with "an out-of-enum value … unreachable", which its own caveat contradicts (C-1b asked to drop the universal) |
| 3 | D29 | shape → constrained decoding | X1 | C 1a | S |
| 4 | D31 | value absent: LangExtract, Instructor; vendor candidate cookbook | X2, V-preparsed | C row 2; `pre_parsed…cookbook.md:25-26,54` | S |
| 5 | D32 | wrong entity: Sensible, Extend; vendor cookbook | X2, V-preparsed | C row 2, landscape §2 | S |
| 6 | D33 | per-field scores in Cleanlab TLM, LlamaExtract, Azure DI, "mostly proprietary, none deterministic" | X2 | C landscape: "Most of these are proprietary … None is deterministic" | S |
| 7 | D34 | wrong branch: "no tool found" | X2 | C: "Wrong branch: nothing targeted found" | S |
| 8 | D36 | candidates + none is TypeSafe's documented pattern | V-preparsed | cookbook lines 9-10, 54 | S |
| 9 | D36 | several open projects implement it for single fields or fixed record types; the combination is absent "as far as we found" | X3 | C landscape §1; gh descriptions (playground, jev-extract, jev-reviewer, jev-json-builder) | S |
| 10 | D56 | official docs at docs.typesafe.ai | V-index | every jevdocs page header | S |
| 11 | D56 | jevapi.dev is third-party and unaffiliated | X4 | C row 8 footer quote | S |
| 12 | D58 | POST …/v1/systemone, Bearer, `{model, state, questions}` | V-api | A row 1 (api.md) | S |
| 13 | D58 | "The question key is not sent to the model" | V-primitives, P1 | `primitives.md:276` "Question IDs are for your code. They are not sent to the model."; `api.md:36` "not sent to the underlying model and is not used in inference"; P1 keyname 8 keys, all 0.07–0.08 (p01_determinism_now.json `keyname`) | S. P1 caveat: the key test used saturated targets (noul ≈ 0.07, choice p = 1.0), so it is weak on its own. The vendor quote carries the claim |
| 14 | D60 | jev-1.13.0 accepted, jev-1.13 rejected, jev-latest alias moves | P9, V-models | p00_smoke: `jev-1.13` → 400 "Unknown model: jev-1.13"; jev-latest → model jev-1.13.0; `models.md:40` | S |
| 15 | D60 | "The vendor's cookbooks were measured on `jev-1.12`" | V-cookbooks | `grep TYPESAFE_MODEL cookbooks__*.md`: 14 of 18 set jev-1.12; consistency_noul and consistency_choice set jev-latest and print "TypeSafe returned models (calls): {'jev-1.13.0': 15}" (`consistency_noul…:467`, `consistency_choice…:581`); hierarchical_classification and sde_cascade set none | **O**. The σ≈0.0102 cookbook that D90 cites was measured on jev-1.13.0 |
| 16 | D66 | noul: no confidence field | V-confidence, P2 | `confidence.md`: "(Noul answers don't carry one.)"; p02 `noul_with_confidence?` → `{type, noul}` | S |
| 17 | D67 | choice 2–255 in practice; API accepts 1 | P2 | p02 choice_1 200 (n_probs 1); choice_256 400 | S |
| 18 | D68 | score is a probability-weighted float; 1 level accepted | P2, L4 | p02 score_10 score 4.94; score_1 200; check_mapping_semantics.txt (2) | S |
| 19 | D70 | "The vendor trains calibration into the probabilities. `confidence` is computed from the distribution, and its formula depends on the number of options" | V-confidence | `/confidence` says only "`confidence` is a statistic computed from the probability distribution" and gives a *demo* approximation "(3 × largest probability − 1) / 2 … for three options". Calibration of probabilities is stated on `concepts__system-one.md:21` ("their probabilities are optimized against outcomes") and `introduction__machine-learning-primer.md:57-61`, **not** on /confidence. Other vendor pages call confidence itself calibrated: `cookbooks__date_extraction_cookbook.md:359` "Every answer comes back with a calibrated confidence"; `concepts__how-to-build…:293` card "Calibrated confidence" | **O** (misattributed; vendor is inconsistent) |
| 20 | D71 | values rounded to 2 dp; exact 0.50 ties occur | P1 | all p01b values are 2 dp (recomputed); p01c q03 `n_exact_0.5: 2` of 30 | S |
| 21 | D72 | lower bounds unenforced; 1-option choice p = 1.0; 1-level score accepted | P2 | p02 | S |
| 22 | D73 | validation errors are HTTP 400 (documented 422), JSON `detail` | P2 | p02 bodies; `api.md:332` lists 422 | S |
| 23 | D79 | state + longest question ≈ 32,768; 400 max_tokens_exceeded | V-models, P3 | `models.md:15,20`; p03 search: 1735 sentences 200 at 32,778, 1750 → 400 | S |
| 24 | D80 | state + all questions ≈ 65,536 | V-models, P3 | p03b: nq 2515 → 65,401 (200); 2531 → 400 | S |
| 25 | D81 | 255 options → 400 | P2 | p02 choice_256 | S |
| 26 | D82 | 10 levels → 400 | P2 | p02 score_11 | S |
| 27 | D83 | no count limit (2,515 accepted) | P2, P3 | 2,515 is p03b, not p02 (p02 max is 1000) | S |
| 28 | D84 | ~1,200 req/min, ~250k tok/s "(early access)" | V-api | numbers are on `models.md:14`; api.md holds none; "early access" appears only in the launch blog (A row 3), not in jevdocs | **O** (misattributed; should be V-models plus an untagged blog source) |
| 29 | D86 | 400 has no token counts; no tokenizer published | P3 | p03 bodies `{"detail":{"error_type":"max_tokens_exceeded"}}` | S |
| 30 | D86 | no silent truncation; every over-limit request rejected | P3 | p03 needle_1730/1735 start/end facts at 1.0/0.99; every search point over the limit → 400 | S |
| 31 | D90 | jitter up to 0.10 (range over 25 repeats), per-question sd ≤ 0.022 | P1 | recomputed from p01b_borderline_now raw: noul pstdev mean 0.0076, max 0.0220; range max 0.10 (n10: 0.65–0.75); later session max range 0.07 | S |
| 32 | D90 | "Decisions away from a threshold never flipped in 110 questions" | P1 | Not reproducible from raw. B line 35 gives "110 … (40 in 01b plus the probe_01 targets)", which is 43. p01b has 40 questions × 25 repeats × 2 sessions with 0 flips, but several are *near* 0.45 (n05, n06), so "away from a threshold" does not describe how they were selected | **U** (the count) |
| 33 | D90 | 0.50 in 2 of 30 identical calls | P1 | p01c q03 | S |
| 34 | D90 | vendor σ ≈ 0.01 measured with a fresh uid | V-consistency | `consistency_noul…:26,31,199` | S |
| 35 | D91 | keys, order, co-batching: no measurable effect; 0/120 | P1, V-primitives | recomputed: p05_abstention rows, 120 CH batched-vs-alone pairs, 0 changes; order/cobatch nouls all 0.07–0.08; `primitives.md:310,456` | S |
| 36 | D92 | state billed once; ~22–26 tokens per short noul; ~280 overhead | P3 | p03b bill_1/10/100 = 14,841 / 15,048 / 17,208 → 23.0 and 23.9 tokens per question; p02 tiny 1-q request 283 tokens | S |
| 37 | D92 | p50 0.15 / 0.17 / 0.22 s for 1 / 100 / 300 questions | P8 | p08 report p50 0.149 / 0.170 / 0.223 (numpy median 0.150 / 0.171 / 0.223) | S |
| 38 | D93 | $0.042 / M input, output free | V-api | on `models.md:13,18`, not api.md | **O** (misattributed to V-api) |
| 39 | D93 | `usage.input_tokens` **and `x-typesafe-request-id`** present on every successful response | P8 | usage: 227 of 227 status-200 records carry input and output tokens (recomputed). request-id: captured **once** (p00_smoke `headers`); `jevclient.py` records no headers | **O** (the "every" claim for the header) |
| 40 | D97 | cannot produce free text, arrays, nested objects; cannot read images; no step-by-step reasoning | V-jagged | jagged §Generation (text) and §Indirection (multi-hop). Images: `models.md:16`. No reasoning explanations: `concepts__system-one.md:23` | **O** (images and reasoning are not on V-jagged; add V-models) |
| 41 | D98 | reads structure in state and instructions well | V-advanced | A row 27: "System One models are trained to understand structure" | S |
| 42 | D99 | items[137] in a 320-list: 62% wrong; keyed, inline, per-request 0/320; error grows with list length | P4 | p04 recomputed: IDX-all-150/25/320 198/320; chunk-150 136; chunk-25 7; KEY/INLINE/PER-REQ 0 | S |
| 43 | D99 | vendor examples use `items[i]` | V-jagged | `model-jaggedness…:58` `f"Is \`items[{i}]\` …"` | S |
| 44 | D100 | content in state can steer answers | V-jagged | jagged §Adversarial content, "can move the answer" | S |
| 45 | D100 | "a single note … advocating the wrong span moved selection 20/20 and defeated none_of_these 20/20 at confidence up to 1.0"; drafts 0/20 | P7 | p07 B.advocacy: picked advocated 20/20, abstain 0/20, conf 0.76–0.91. The 0.93–**1.00** range is the *injected-instruction* variant. A 0/20 in every variant | **O** (two variants merged; the advocacy note peaks at 0.91) |
| 46 | D101 | no arithmetic, counting, date comparison | V-jagged | jagged rows 2, 3; §Counting | S |
| 47 | D102 | distractors hurt | V-jagged | jagged §Large state, line 96 | S |
| 48 | D102 | long multi-entity docs the only regime where none_of_these failed | P5 | p05 60/60, p05b 70/70, p05c partial 24/24, S-long 32/36 | S |
| 49 | D103 | English primary; CJK handled less well | V-models | `models.md:52` | S |
| 50 | D148 | "that is what the schema-first prior art does [X3], and why it refuses everything interesting" | X3 | C row 3: jev-json-builder "does not refuse" (spans.ts "we find candidate spans with regex and let Jev select", re-verified via gh) | **O** |
| 51 | D190 | vendor documents speculative fan-out | V-fanout | A row 30 quote | S |
| 52 | D199 | state billed once; questions independent | P1, P3 | as rows 35–36 | S |
| 53 | D233 | open projects in §9 | X3 | — | S |
| 54 | D237 | jev_jsonschema mapping adopted with two corrections | X3 | C 4b: mapping confirmed, including "integer range → score … argmax decode". So the score row is not a correction *to jev_jsonschema* | S (the wording is ambiguous about which two rows are the corrections) |
| 55 | D243 | score float, e.g. 3.20 for p = [.45,0,0,0,.55]; fails `type: integer`; rounding picks a zero-probability level | L4 | check_mapping_semantics.txt (2): "weighted_score=3.20 validates_as_integer=False round=3 argmax=5 (round has prob 0.00)" | S |
| 56 | D243 | vendor warns against interpolating | V-jagged | jagged:76 | S |
| 57 | D244 | 0–1 number → probability writes a belief into value fields | L4 | check_mapping_semantics.txt (3) | S |
| 58 | D262 | vendor's documented pattern | V-preparsed | — | S |
| 59 | D264 | "Text keys and opaque ids performed **identically** (35/36 identical selections)" | P5 | p09: TXT abstain 32/36, ID 31/36; selection agreement 35/36 | **O** (equivalent, not identical) |
| 60 | D268 | near-zero marginal cost | P3, P8 | rows 36–37 | S |
| 61 | D280 | ceiling on short and trap docs; long docs 32/36 = 0.89 (0.75–0.96); noul gate 0.56 | P5 | recomputed from p05c rows: CH abstain 32/36; G ≤ 0.5 in 20/36; PC 26/36 | S |
| 62 | D280 | "under-specified scope was the pilot's main failure" | P5 | B:196-198: 3 of 4 wrong commits were "T1 superseded due date"; the "partly under-specified" point is only a caveat | **O** |
| 63 | D298 | re-asking unchanged returns same decision away from ties | P1 | 0 flips in p01b; p01c | S |
| 64 | D316 | code-point offsets, half-open | L1 | D §1 | S |
| 65 | D317 | exact equality accepts a span that cuts an accent off | L1 | D §1 `[i,i+4)` "Jose" → True | S (skin-tone and variation-selector cases were not tested) |
| 66 | D318 | NFC/NFD and `\r\n`/`\n` mismatches rejected | L1 | D §1 find = −1 | S |
| 67 | D328 | 95.1% pairs correct; 42% docs non-transitive | P6 | p06 report 700/736; 10/24; recount of `detail` = 10 | S. Omits B's caveat that the lease template's gold "may be debatable"; without it, 13/16 correct and 0 silently wrong |
| 68 | D330 | casefold merges `US`/`us`, `Apple`/`apple`, **`CO`/`Co`**, `IT`/`it` | L1 | check_span_unicode.txt:43-49 tests US, Apple, MAY, Straße, Acme, CAT, IT; **no CO/Co** | **O** (swap in CAT/cat or MAY/May) |
| 69 | D330 | initials and first names were the dominant failure | P6 | 36 pair errors in p06 detail: about 15 involve "X. Surname" initials and about 15 role nouns ("the Landlord", "the agent"), mostly in the lease template | S (weak) |
| 70 | D335 | consistent-but-wrong partition once in 24 | P6 | policy_outcomes silently_wrong 1 | S |
| 71 | D339 | note beside wrong address: 20/20; 20/20 abstentions → commits at 0.76–1.00 | P7 | advocacy 0.76–0.91, inject 0.93–1.00 | S (range spans both variants; say so) |
| 72 | D339 | documented weakness | V-jagged | — | S |
| 73 | D344 | detector wording 40/40 attacks, 0/40 FP; second wording 20/20 benign | P7 | p07b d1 advocacy 20 + inject 20; clean 0 + benign 0; d2 benign 20/20 | S |
| 74 | D347 | adjudication not steered (0/20) | P7 | p07 A flip_fail_to_pass V1–V4 0/20 | S |
| 75 | D357 | constrained decoding reduces redrafts, not relied on | X1 | — | S |
| 76 | D360 | nouls report a probability only | V-confidence | — | S |
| 77 | D369 | "Probabilities jitter by up to **±0.05** on identical input" | P1 | recomputed max deviation from the per-question mean: 0.063 (session 1), 0.046 (session 2) | **W** (minor; say "±0.06, range 0.10") |
| 78 | D370 | non-English less well | V-models | — | S |
| 79 | D394 | metric on probabilities, not confidence | V-confidence | — | S (see row 19 for attribution) |
| 80 | D394 | "At n = 300 **the same bar** misclassifies: calibrated passed 47–99% depending on binning, overconfident-by-0.05 passed **30–40%**" | L6 | check_ece_bar.txt n=300 δ=0: 0.988 / 0.961 / 0.766 / 0.472; δ=0.05: 0.403 / 0.334 / 0.305 / **0.137**. The simulation used *point-estimate* ECE with *equal-width* bins, not the adopted bootstrap upper bound with 15 equal-mass bins. The spread depends on the confidence distribution as well as the binning | **W** |
| 81 | D428 | R13: never by position; keys not sent | P4, P1 | — | S |
| 82 | D456 | SDK pre-1.0, breaking releases days apart, httpx2 + tenacity, **"retries billed requests by default"**, unredacted debug bodies | V-sdk, X5 | changelog v0.6.0 09-15, v0.7.0 09-18; `retries.md` max_retries=2 on {408, 429, 500–599}; `usage.md:550` "Request and response bodies are **not** redacted"; PyPI 0.7.2 requires httpx2, tenacity (re-checked). No doc says retried attempts are **billed**; A-N4 says "may be billed" | **O** (minor; "billed" is inferred) |
| 83 | D464 | AnyJev, jevfire: Jev-style decisions over other models | X3 | gh descriptions | S |
| 84 | D491 | two limits | V-models, P3 | — | S |
| 85 | D494 | questions independent → split answer-neutral | P1 | — | S |
| 86 | D498 | "a 255-option candidate `choice` costs ~2.5k tokens" | P2 | p02 choice_255 = 2,485 tokens, but options were bare keys `opt0…opt254` with `None` descriptions (`probe_02_limits.py:11`). A candidate choice carries span text in its descriptions | **O** (this is a floor, not the cost) |
| 87 | D501 | "~28 tokens per pair question [P6]"; 435 → ~12k | P6 | p06 raw records **no usage**; B's "36 pairs cost about 1k tokens" has no raw backing, and 1k/36 would include state and overhead. L7 (cl100k) puts the lowest template at 42 tokens/question, ≈18.3k for 435 | **U**; also conflicts with L7 |
| 88 | D501 | verbose template ~58k | L7 | check_pairwise_budget: 57.8k | S |
| 89 | D501 | keyed batching measured to 320 | P4 | — | S |
| 90 | D501 | "non-transitive triples grow with n³ [P6]" | P6 | P6 measured only n = 8–9; n³ is triple-count arithmetic, not a P6 result | **U** (as cited) |
| 91 | D507 | env var `TYPESAFE_API_KEY` | V-sdk-constants | constants.md:24 | S |
| 92 | D514 | `probabilities` key order varies | P1 | p01 keyname and order dumps show varying key order | S |
| 93 | D522 table | TypeSafe cookbook pre-parsed extraction | V-cookbooks | — | S |
| 94 | D522 table | vendor cookbooks SDE cascade, citation, entity alignment, dates, function calling | V-cookbooks | A rows 32–34, 37 | S |
| 95 | D528 | `TypeSafeAI/typesafe-playground` is "the vendor's own reference implementation of candidate extraction" | X3 | gh description: "**Community** TypeSafe AI playground: 110 use cases, games, dilemmas…". docs/document-extraction.md confirms offsets, candidate IDs and a `null` choice | **O** ("reference implementation" is not stated) |
| 96 | D529 | gbesse/jev-extract | X3 | gh + C | S |
| 97 | D530 | choxos/jev-reviewer multi-file, verbatim quotes | X3 | gh description | S |
| 98 | D531 | jev-span (span NER), mateonunez/jod (semantic schemas, npm), pydantic-jev (Pydantic helpers) | X3 | gh: jev-span "Zero-shot named entity recognition on TypeSafe Jev"; jod "Semantic schemas over TypeSafe's Jev" (TS, npm `@mateonunez/jod`); pydantic-jev "A thin shim between Pydantic and Jev" | S (jod is not in RT X3's source list) |
| 99 | D532 | jev_jsonschema refusal list, no LLM | X3 | C 4a | S |
| 100 | D533 | jevc transpiles prompts and schemas, residual prompt | X3 | jevc README:93 "residual prompt"; :100 "JSON Schema is still a first-class input — it is just no longer the front door" | S |
| 101 | D534 | llm-to-jev, jev-swap | X3 | gh | S |
| 102 | D535 | AnyJev, jevfire | X3 | gh | S |
| 103 | D536 | eortizs/jev-json-builder: Express middleware, regex candidate spans **plus presence gates**, TS | X3 | gh description "Express middleware"; spans.ts:5 "we find candidate spans with regex"; C 4d "`<name>_stated` presence noul" (verified by C via gh) | S |
| 104 | D538 | LangExtract, Instructor, Cleanlab, LlamaExtract, Azure DI, Reducto, Extend, Sensible, AWS BDA, GLiNER | X2 | C landscape §2 covers all ten; RT X2 lists neither Reducto nor AWS BDA | S (register gap) |
| 105 | D600 | 95% pairs, 42% docs | P6 | — | S |
| 106 | D603 | screen wording fragile | P7 | — | S |
| 107 | D606 | jevapi.dev asserts trademark | X4 | C row 10 | S |
| 108 | D608 | closed: splitting (P1), keyed (P4), noul gate (P5) | P1, P4, P5 | — | S |
| 109 | D622 | positioning credited | X2, X3, V-preparsed | — | S |
| 110 | D623 | "probabilities are calibrated, confidence is a statistic" | V-confidence, P1–P3 | as row 19 | **O** (same misattribution) |
| 111 | D624 | R13 | P4, P1 | — | S |
| 112 | D625 | source trust | P7, V-jagged | — | S |
| 113 | D627 | entity resolution | P6, L1 | — | S |
| 114 | D628 | mapping | L4 | — | S |
| 115 | D630 | Pydantic normalised | L3 | check_pydantic_schema.txt "10/14 models need $ref/anyOf/const handling" | S |
| 116 | D632 | raw httpx | V-sdk, X5 | — | S |
| 117 | D633 | "≥ 300 misclassifies" | L6 | — | S. **But the adopted replacement bar was never simulated** (see REDTEAM defect 12) |

### PLAN.md

| # | line | claim | tag | evidence | verdict |
|---|---|---|---|---|---|
| 118 | P29 | jev_jsonschema already provides a bounded-schema compiler | X3 | C 4a | S |
| 119 | P29 | "Phase 4 alone already combines things no single existing project does" | X3 | A row 34 REFUTED the Rev-3 version and asked for removal. C lists criteria-gated generative fields as unshipped ("jevc and sde_cascade are adjacent") | **O** (unhedged negative; needs "as far as we found") |
| 120 | P133 | pilots are synthetic | P1–P9 | RT:9 | S |
| 121 | P163 | existing Jev implementations column | X3 | — | S |
| 122 | P173 | long multi-entity or superseded values: "the only regime where the pilot failed" | P5 | B:211; but superseded values in *short* docs (p05b T1) were at ceiling. Failure was long docs; 3 of 4 failures were superseded values *inside* long docs | S (imprecise) |
| 123 | P183 | probe 5 reproduces P4 | P4 | — | S |
| 124 | P187 | "With n = 150 the half-width near p = 0.85 is about ±6 points … [L5]" | L5 | check_probe_stats.txt computes n = 20/50/100 only (n=100, .85: ±7.0). ±6 at n = 150 is correct arithmetic (Wald 5.7) but is not in L5 | **U** (as cited) |
| 125 | P214 | pilot showed steering | P7 | — | S |
| 126 | P279, P285, P294 | $ref / nullable / const; shared $defs; idiomatic Pydantic | L3 | — | S (3 rows) |
| 129 | P330 | canonicalise probabilities order | P1 | — | S |
| 130 | P331 | 400 bodies typed; usage and request id recorded | P2, P8 | — | S (deliverable) |
| 131 | P349 | live stability over decisions whose top-two margin is ≥ 0.10 | P1 | P1 observed a per-question range of 0.10 and a deviation of 0.063 from the mean. A noul with margin 0.10 (p = 0.55) can reach 0.49 and flip. P1 does not show that 0.10 is safe | **O** (use ≥ 0.20, or cite a measured flip-free margin) |
| 132 | P366 | splitting closed | P1 | — | S |
| 133 | P389, P399 | draft-injection set 20 × 4; upper CI 0.16 | P7 | p07 A CI 0–0.161 | S (2 rows) |
| 135 | P453 | retry bar ≥ 100 abstentions | L8 | L8 ≈ 60 needed | S (the ≤ 2-point false-commit arm has no power analysis) |
| 136 | P546 | keyed batching measured only to 320 | P4 | — | S |
| 137 | P580 | fair comparison | X2, X3 | — | S |
| 138 | P582 | jevson free on PyPI and npm | X6 | re-checked: PyPI 404, npm E404 | S |
| 139 | P593 | format unchecked without extras | L10 | — | S |
| 140 | P606 | jev-reviewer, jev-extract multi-file or chunked | X3 | — | S |
| 141 | P640 | Zod v4 toJSONSchema | X7 | — | S |
| 142 | P646 | code points vs UTF-16 | L2, X7 | check_js_offsets_py.txt | S |
| 143 | P661–663 | infisical run injects env; machine identity; CLI keeps local copy | X8 | C row 11 | S (3 rows) |
| 146 | P682 | near-deterministic | P1 | — | S |
| 147 | P710, P712 | hostile drafts and sources | P7 | — | S (2 rows) |
| 149 | P720 | maxLength/pattern/minItems/uniqueItems | L9 | — | S |
| 150 | P736, P742 | risks | P7, P1 | — | S (2 rows) |
| 152 | P744 | SDK churn, hidden retries, body logging | V-sdk | — | S |
| 153 | P745 | Pydantic | L3 | — | S |
| 154 | P747 | non-transitive | P6 | — | S |
| 155 | P760 | every mechanism predates us | X2, X3 | — | S |
| 156 | P765 | "hidden **billed** retries" | V-sdk, X5 | as row 82 | **O** (minor) |
| 157 | P766 | aliases move | P9, V-models | — | S |
| 158 | P770 | 62% vs 0% | P4 | — | S |
| 159 | P771 | equivalent accuracy, duplicate text | P5 | — | S |
| 160 | P773 | 0.56 vs 0.89 | P5 | — | S |
| 161 | P775 | ≥ 300 misclassifies | L6 | — | S |
| 162 | P777 | casefold merges; conflicts frequent | L1, P6 | — | S |
| 163 | P779 | selection steerable | P7 | — | S |
| 164 | P787 | jevc and AnyJev Apache-2.0 | X6 | gh re-check | S |
| 165 | P811 | closed by evidence | P1, P4, P5 | — | S |
| 166 | P846 | wording fragile | P7 | — | S |

**Counts (166 claim rows; grouped PLAN rows counted per line):** SUPPORTED 142, OVERSTATED 18 (rows 15, 19, 28, 38, 39, 40, 45, 50, 59, 62, 68, 82, 86, 95, 110, 119, 131, 156), WRONG 2 (rows 77, 80), UNSUPPORTED 4 (rows 32, 87, 90, 124). README carries no tags.

---

## (b) Untagged factual claims (violating D9: "Every factual claim … carries an evidence tag")

| # | where | sentence | should carry |
|---|---|---|---|
| 1 | D56 | "released in September 2026" | launch blog (no REDTEAM tag exists; add V-blog) |
| 2 | D56 | "**Jev is non-autoregressive: it does not generate tokens.**" | nothing in jevdocs contains "autoregress" (grep). Unsupported; cite a source or delete |
| 3 | D58 | "State is text or JSON. Questions are a map from key to a typed question." | V-api / V-models (`models.md:16`) |
| 4 | D84 | "(early access)" | blog only |
| 5 | D190 | "saves a round trip (~0.15 s)" | P8 |
| 6 | D272, D367 | "Jev's probabilities are calibrated over the options it was handed/given" | V-jagged #8 ("the Choice is relative"), V-confidence |
| 7 | D299 | "Jev's distribution is relative to the offered set" | V-jagged |
| 8 | D358 | Constraint tier "holds unconditionally: yes" via jsonschema 2020-12, with no mention that `format` is unchecked by default | L10 (and D-10 asked for the caveat here) |
| 9 | D544 | "Grounding checks and per-field confidence exist elsewhere" | X2 (a restatement) |
| 10 | D553–568 (§10) | "`choice` ≤ 255", "Jev has no vision", "state + longest question ≤ ~32k" and similar | restate §2 facts without tags (P2, V-models, P3) |
| 11 | D618 | "1,555 live API requests" | REDTEAM P header (no tag) |
| 12 | P641 | "browsers and edge runtimes have no process environment" | general knowledge; E-44 |
| 13 | P762 | "**Prior art and the target ecosystem are Python-first**" | untagged and **contradicted** by C-17 and gh `language`: jod, jevc, jev-json-builder, playground (TS), gbesse/jev-extract, jevfire, llm-to-jev (JS) against pydantic-jev, jev-span, jev_jsonschema, AnyJev (Python) |
| 14 | P783 | "Two languages in v0 finish neither" | opinion (acceptable as a design decision) |
| 15 | R7 | "Grammar-constrained decoding already makes a missing brace or a wrong nesting depth very hard to produce" | X1 |
| 16 | R28 | "TypeSafe's own documented extraction pattern, and several open projects implement it" | V-preparsed, X3 (hyperlinked, untagged) |
| 17 | R33 | "Text inside a document can steer the model's choice; this is measured" | P7 |
| 18 | R42 | README calls REDTEAM "every factual claim", yet the README itself tags nothing | either tag the README or scope the rule to DESIGN and PLAN |

---

## (c) Traceability of round-1 findings

Key: ✓ addressed; **PARTIAL**; **NOT ADDRESSED**; **DECLINED**.

### E — logic review (1–45)

| E | status | where in Rev 4 |
|---|---|---|
| 1 | ✓ | D §3.1 StepNode (D168-173); D §6.3 (D400); PLAN Ph4 (P382-383) |
| 2 | ✓ | PLAN Ph2 (P279-283, P294) |
| 3 | ✓ | D §5.6 step 3 (D332); PLAN Ph7 chain case (P541); probe 4 clique completeness (P191) |
| 4 | ✓ | D §3.2 (D188); PLAN Ph6 (P488, P494) |
| 5 | ✓ | D §5.5 (D320); §10 (D564) |
| 6 | ✓ | D §6.1 (D382); §8.1 |
| 7 | ✓ | D383; P346 |
| 8 | ✓ | PLAN §3 (P682); Ph3 (P348-349); Ph5 (P458) |
| 9 | ✓ | D §8.2 (D499); R14 (D429) |
| 10 | ✓ | D357; D404; P384 |
| 11 | ✓ | README R19-24, R34, R41 |
| 12 | ✓ | D393 |
| 13 | ✓ | R10 (D422) |
| 14 | ✓ | closed by evidence (D494, D608) |
| 15 | ✓ | P25 |
| 16 | ✓ | D206; P432; P579 |
| 17 | ✓ | P342; P29; schema-enum none → PLAN §9 (P854) |
| 18 | ✓ | P333, P345, P389, P398, P438, P459, P700 |
| 19 | ✓ | P439, P193 |
| 20 | PARTIAL | Rejection and Cost in types.py (P48-49); no module owns LLM drafting (steps run "through Extractor / LLM protocols", D128) |
| 21 | ✓ | D447-454 |
| 22 | ✓ | P5; grep finds no bare § in PLAN |
| 23 | ✓ | R6 "(§5.6)" D418 |
| 24 | ✓ | P84 |
| 25 | ✓ | P414, P806 |
| 26 | ✓ | P185 (probe 7), P366, P546 |
| 27 | ✓ | P35-39, P27 |
| 28 | ✓ | P745-746 |
| 29 | ✓ | P446-448 |
| 30 | ✓ | D403, P383, P397 |
| 31 | ✓ | D378, D385, P329, P344, D462 |
| 32 | ✓ | D §5.2, R4 |
| 33 | ✓ | D474, D487 |
| 34 | PARTIAL | D384 (key omitted); the root-pointer (`{}`) case is unstated |
| 35 | ✓ | D332 |
| 36 | PARTIAL | P535 gives the order; "unresolved components count toward overflow as unknown" is absent |
| 37 | ✓ | D299, D301, P436, P453 |
| 38 | ✓ | D462 |
| 39 | ✓ | D300 |
| 40 | **DECLINED. The rationale is restated but is not a response** | P27 and P764 repeat "adjudication does not depend on candidates and survives their abandon criterion", the argument E-40 rebutted (it justifies Phase 4 *existing* in the fallback, not running *first*). Neither doc records that the order is an owner decision, nor that E-40 was considered and declined. E-40's fallback suggestion (unions straight after Phase 3) is not discussed either |
| 41 | ✓ | D330, P543 |
| 42 | ✓ (bar adopted) | D394, P454. The adopted bar is unvalidated and my simulation shows it fails calibrated models at n = 1,000 (REDTEAM defect 12) |
| 43 | ✓ | D301 |
| 44 | ✓ | D462, P641 |
| 45 | PARTIAL | R7 refusal (D419, P534); `Result` records no `ordering: source` |

### A — vendor docs (refuted, partial, gap and unverifiable rows; N1–N13)

| A | status | where / gap |
|---|---|---|
| 1 | ✓ | D58 |
| 2 | ✓ | D56 |
| 3 | ✓ | D60 (overstated, row 15) |
| 4 | ✓ | D456 |
| 5 | ✓ (moot) | SDK not used; model always passed explicitly |
| 6 | **NOT ADDRESSED** | D §8.3 does not say what `api_key=""` does |
| 9, 10, 11, 12, 13, 14, 15, 16 | ✓ | D66-73, D90-91, §8.1 `model`, D514 |
| 17 | ✓ | D79-80, D491-501 |
| 19 | PARTIAL | D84 does not say the limits "can change without notice" (`models.md:24`) |
| 21 | ✓ | D93 |
| 22 | PARTIAL | `Cost` records no Jev `output_tokens` (D480-483) |
| 27, 28, 29, 29b, 30 | ✓ | D98, D264, D99, D428, D190 |
| 31 | PARTIAL | D392 still calls none_of_these "a structural signal about the option set", the wording A called overstated (relative softmax); the noul-gate arm was piloted (P5) |
| 32, 33, 35 | ✓ | D §1, §9, P580 |
| 34 | PARTIAL | P29 keeps a novelty claim for Phase 4 (row 119) |
| 36 | DECLINED (reason stated) | uncertain band not adopted; argmax plus exact-tie rule, "a decision rule, not a confidence gate" (D393) |
| 37 | **NOT ADDRESSED** | no date-component choices (class D/C front half); money candidates carry no semantic context |
| 38 | PARTIAL | distractors noted (D102) and long docs required in Phase 0 (P173); no state-scoping step |
| 39 | ✓ | D §5.7. Draft and source under separate named state keys is not specified |
| 40 | **NOT ADDRESSED** | no compiler rule against negated or indirect question phrasing (grep "negat" hits only D280) |
| 41, 42 | ✓ | P2, P3; D385 |
| 43 | **NOT ADDRESSED** | P342 and P707 treat "distributions that do not sum" as hostile with no tolerance. Raw data: **3 of 1,328** legitimate choice/score distributions sum to 0.99 |
| 44 | ✓ | D264 |
| N1–N13 | ✓ | N1 D360/§8.1; N2 D70; N3 D60, R15; N4 D385; N5 P349; N6 D456, D460; N7 D498; N8 D494; N9 §5.7; N10 §9; N11 D60 (overstated); N12 D456; N13 D103, D370 |

### B — implied changes

All implied changes for probes 1–9 (a–k) are addressed: D §2.1–2.4, §5.3, §5.6, §5.7, §8.1 (`jev_request_ids`), §8.2, §8.4; PLAN Ph0 corpus rules, Ph3 R13 test (P339), Ph5 screen and scoping hint, Ph7 cap. B-P5 item 5 ("record, do not act") is recorded in RT22 ("confidence ≤ 0.74").

### C — required doc changes

| C | status | where / gap |
|---|---|---|
| 1a, 1c, 2, 3, 4, 4a–4e, 6, 7, 8, 8a–8d, 9, 11, 12, 13, 14, 15, 16 | ✓ | §1, §6, §9, §9.1, PLAN Ph8, Ph10, Ph11, §6 |
| 1b | PARTIAL | D17 still opens with "an out-of-enum value … unreachable" |
| **1d** | **NOT ADDRESSED** | nothing requires down-projecting the user schema to each provider's tool-schema subset (grep: none) |
| 5 | PARTIAL | missing: PyPI `jev` 0.3.0 (`@jev.fn`, Pydantic → Jev), finetuningsingh/jev-extract, dangquan1402/jev-extract, ruby_llm-typesafe, the pedramamini gist skill. entity_alignment is not credited as precedent in §5.6 |
| 8e | PARTIAL | release month untagged; blog not cited |
| 10 | PARTIAL | trademark noted (D606); "ask TypeSafe before release" not stated |
| **17** | **NOT ADDRESSED / WRONG** | P762 "Prior art and the target ecosystem are Python-first" |
| README "nine phases" | ✓ | R41 |

### D — required doc changes

| D | status | where / gap |
|---|---|---|
| 1 (a–c) | ✓ | D316-318 |
| 1 (d) | PARTIAL | case-preserving default ✓; whitespace set (NBSP, zero-width) unspecified |
| **2** | **NOT ADDRESSED** | Phase 10 (P646) has no "span boundary inside a surrogate pair is rejected" fixture |
| 3 | ✓ | P279-285; D384; D567 |
| **4** | PARTIAL / **NOT ADDRESSED (ordinal)** | 0–1, argmax and `> 0.5` ✓. Integer range 2–10 → `score` is still unconditional (D242); counts such as bedrooms or quantity should be class D + F unless annotated ordinal |
| 5 | ✓ | P177-187 (n = 150, point estimate + Wilson, OC recorded, P4 unit = cluster) |
| 6 | PARTIAL | n ≥ 1,000, bootstrap, reliability ✓. **Brier score not added**; bins changed to equal-mass without simulation |
| 7 | ✓ | D491-501 |
| 8 | ✓ | P453 |
| 9 | PARTIAL | P720 ✓; "Cost is monotonic within a call" (P722) is not defined componentwise over counters |
| 10 | PARTIAL | PLAN Ph8 (P593) ✓; the DESIGN §6 Constraint tier is not caveated |
| **11** | PARTIAL | $0.068 removed ✓. **The unicodedata version is not pinned in conformance fixtures** |

---

## (d) docs/REDTEAM.md defects

1. **RT59 V-confidence**: "probabilities carry the calibration" is not on `/confidence`. It is on `/concepts/system-one` (line 21) and `/introduction/machine-learning-primer` (lines 57-61). Other vendor pages call *confidence* calibrated (`date_extraction:359`, `how-to-build:293`). "option-count-dependent formula" is inferred from a demo approximation. Add a V-primer tag and record the vendor inconsistency.
2. **RT56 V-api**: price and rate limits are on `/models` (lines 13-14, 18), not `/api`. Move them to V-models.
3. **RT64 V-cookbooks**: "cookbooks set `TYPESAFE_MODEL = "jev-1.12"`" holds for 14 of 18 cookbook pages. The two consistency cookbooks use jev-latest and report returned model `jev-1.13.0`.
4. **RT65 V-consistency**: omits that σ ≈ 0.0102 was on jev-1.13.0 (`consistency_noul…:467`).
5. **RT18 P1**: "no argmax flip in 110 questions away from threshold" cannot be derived from raw (B's own breakdown sums to 43). Replace with "0 flips across 40 ambiguous questions × 25 repeats × 2 sessions and 3 targets × 20 repeats".
6. **RT19 P2**: "2,515 questions accepted" is a probe_03b result; p02 tested up to 1,000.
7. **RT20 P3**: "~70k rejected" and "~34k single question rejected" are extrapolations: 400s carry no usage; st25_1700 extrapolates to ≈ 67k and longq_1800 to ≈ 33k. Mark them as estimates.
8. **RT22 P5**: "130 trap … documents" is 70 docs yielding 60 present + 70 absent cases.
9. **RT23 P6**: "~28 tokens per terse pair question" has no raw backing (p06 stores no usage). The lease-template gold caveat is missing (excluding it: 13/16 correct, 0 silently wrong).
10. **RT25 P8**: "`x-typesafe-request-id` on every 200" rests on one captured header set (p00_smoke). p50 over 20k state is 0.282–0.304 by the script's quantile but 0.292–0.305 by median.
11. **RT36 L1**: "normaliser output identical on Python 3.11 and 3.12" cannot be checked from committed artifacts. `check_unicode_version_drift.NOTE.txt` lists *different* dump hashes (9aede14756fa7adc vs b164645642960bb2) and a digest for 3.11 only. `CO`/`Co` (cited at D330) was not tested.
12. **RT41 L6**: "overconfident by 0.05 passes 30–40%" should read 14–40% (0.137 in Uniform/15-bin). "depending on binning" should read "depending on binning and confidence spread". More seriously, **no L-check covers the adopted bar.** My re-simulation (`r2/sim_bar.py`, `r2/sim_bar2.py`; 15 equal-mass bins, 200 bootstrap resamples, 200–300 replicates) of a *perfectly calibrated* model gives:
   - n = 1,000, two-sided 97.5% UB ≤ 0.05: pass rate **0.00** (conf ~ Uniform(.5,1)), **0.26** (Beta(18,2))
   - n = 1,000, one-sided 95% UB: **0.00** / **0.50**; mean point ECE 0.038 / 0.027
   - n = 3,000, one-sided 95% UB: 0.995 / 1.00

   As written, the Rev-4 bar at "≥ 1,000" would reject a calibrated Jev most of the time.
13. **RT42 L7 vs DESIGN D501**: L7's lowest template is ≈ 18.3k for 435 questions; DESIGN says ~12k via P6. Reconcile.
14. **RT78-79 X2/X3**: X2 omits Reducto and AWS Bedrock Data Automation (cited at D538). X3 omits `mateonunez/jod` (cited at D531).
15. **RT94 round log**: "All addressed in Revision 4" is overstated. See NOT ADDRESSED and PARTIAL above, and E-40 declined without a record.
16. Scripts: every script named in REDTEAM exists. `check_r2_grapheme_rule.py` exists but is unregistered (round 2 in progress). The `jevdocs/` symlink points into a session scratchpad and is gitignored; RT10 says so. The API key (length 107) is present in no script, output, or doc (grep verified).
