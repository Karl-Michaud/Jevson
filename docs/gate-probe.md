# Jevson — probe 9: the second gate, measured before Phase 1

> **Status:** follow-up to Phase 0 (`docs/taxonomy.md`), written in pre-registered order like it: this plan and its decision rule → the fresh corpus and labels → live results. Evidence tag **[Z9]** in [`EVIDENCE.md`](EVIDENCE.md).
>
> **Why now.** Phase 0 put candidate selection in the *conditional* band: with the right span removed, Jev still committed a wrong or partial value on 31/150 cases **[Z2]**. `PLAN.md` Phase 5 answers with a second gate, but Phase 5 runs after Phases 1–4. On 2026-09-29 the owner decided to measure the gate first, so the decision to build source selection rests on evidence rather than on weeks of work already spent.

---

## 1. The gate

`PLAN.md` Phase 5's second gate: *an independent verification noul per committed span, batched into the same call; a failed verification yields `Unresolved(verification_failed)`*. Because the committed option is not known until the call returns, the gate asks one verification noul **per candidate option** in the same call as the choice; only the selected option's answer is used.

`GATE_TEMPLATE_VERSION = 1.0.0` (the Phase 0 templates, version 1.0.0, are unchanged):

- state: `{"source": <document>, "candidates": {"f<i>c<k>": <option description>}}`, where the description is the §1 option text of `docs/taxonomy.md` (quoted text, with its context window when the text repeats), and `f<i>` numbers the case within the request so ids are unique in the level (R13);
- one `noul` per option: `In the source, is `candidates.{cid}` the complete {label} as written in the source?`
- a verification **passes iff p ≥ 0.56** (the bool rule of `DESIGN.md` §4.2; the tie band 0.45–0.55 fails); an invalid verification answer fails.

**Outcome of a case with the gate:** the choice is decoded exactly as in Phase 0 (`docs/taxonomy.md` §2.1). A tie stays a tie; `none_of_these` is an abstention; an invalid answer stays invalid; a selected candidate is **committed** only if its verification passes, otherwise the case is `verification_failed`. The same answers also give the Phase 0 (ungated) outcome of every case, reported beside it.

## 2. Corpus and labels

- **Fresh and disjoint from Phase 0:** new documents from the same six sources, selected by the same seeded rules (`docs/taxonomy.md` §3), recorded with `pool: "gate"` in the corpus manifest; none appears in the Phase 0 sample. Where a source is a live feed or search (Stack Exchange, Europe PMC, GSA), a later window is used.
- **Same pipeline, unchanged:** the recorded extractor prompts, the pattern extractors, the labelling protocol, a 20% independent second labeller with Cohen's kappa, and adjudication of every disagreement by a third agent. No labeller sees any Jev output.
- **Same case rules** as `docs/taxonomy.md` §2.2: a P/A document split per domain, present cases with ≥ 3 competitors, absent cases with every correct and same-text option removed and ≥ 3 options left, at most 8 cases per document, ≥ 30% hard-regime cases, ≥ 20 repeated-text present cases, 150 present and 150 absent cases by the same seeded sampler.

### 2.1 Achieved (recorded before the first live call)

- **Documents:** 157 in `pool: "gate"`: contracts 50 (CUAD), resumes 30 (FJC), medical intake 22 (Europe PMC, Feb 2024), product listings 22 (GSA Auctions), support tickets 22 (Stack Exchange, 12 en + 10 es, January 2024), receipts 11 (CORD). **Shortfall:** CORD had only 11 eligible receipts not already used by Phase 0 (target 30).
- **Extraction:** the recorded extractor prompt, per document (`extraction/llm/`), then `build options gate` → `extraction/options_gate.jsonl`: 780 field instances, 6 over the 50-option cap. Two extractor deviations, both disclosed: the support-ticket extractor dropped 7 spans that were not verbatim, and one contract extractor replaced 6 non-verbatim spans by shorter verbatim forms. The pattern extractors and `extract.locate` accept only exact text, so neither can put non-source text into an option.
- **Labels:** a primary labeller on all 780 instances (`labels/candidates/`). An independent second labeller on the seeded 20% sample: 155 instances in 92 documents (`labels/second/candidates/`). Agreement (`labels/agreement_gate.json`): options κ = 0.940 (98.2% raw, 1,180 labels), field status κ = 0.925, multi_entity κ = 0.813. All 23 disagreements (8 doc, 15 field) were adjudicated by a third agent that saw the document and both labels, never Jev output. It agreed with the first labeller 11 times and the second 12 times (`labels/adjudication_gate.jsonl`).
- **Cases** (`cases/gate_present.jsonl`, `cases/gate_absent.jsonl`, `cases/gate_build_summary.json`): **150 present** (pool 152) and **139 absent** (pool 139). This is a **shortfall of 11** absent cases, so every eligible case is used (taxonomy §2.2 item 8). Hard-regime share 108/289 = 37.4% (56 present, 52 absent; ≥ 30% required). Repeated-text present cases: 63 (≥ 20 required). Cases from non-English documents: 47.
- **Operating characteristic at the achieved n = 139** (for reference; it changes no rule): at a true committed-when-absent rate of 0.02 / 0.03 / 0.05 / 0.07 / 0.10 / 0.12 / 0.15, P(estimate ≤ 0.05) = 0.978 / 0.874 / 0.454 / 0.139 / 0.012 / 0.002 / 0.000 and P(estimate > 0.10) = 0.000 / 0.000 / 0.010 / 0.109 / 0.530 / 0.794 / 0.965.
- **Requests:** 273 (7,159 questions), fresh and paired cases together.

## 3. Decision rule (fixed now, before any fresh data exists)

On the 150 fresh present-answer and 150 fresh absent-answer cases, with the gate:

| measure | definition |
|---|---|
| correct commits | committed `correct` options / present cases |
| wrong commits when present | committed `partial` or `wrong` options / present cases |
| **committed when absent** | any committed option / absent cases (every such commit is wrong or partial) |
| probe 1′ | correct commits, Phase 0 probe 1 bands |
| probe 2′ | (abstentions + verification failures) / absent cases, Phase 0 probe 2 bands; a tie is not abstaining |
| probe 3′ | (abstentions + verification failures) / present cases, Phase 0 probe 3 bands; a tie is not a false abstention |

**Verdict** (`stats.gate_verdict`, comparisons exact):

- **drop source selection** if committed-when-absent > 0.10, or correct commits < 0.70, or any of probes 1′–3′ is in its stop band;
- **proceed** if committed-when-absent ≤ 0.05 and wrong-commits-when-present ≤ 0.05 (and nothing above);
- **marginal** otherwise: the owner decides.

**Consequences:** *proceed* keeps `PLAN.md` as it stands, with the gate in Phase 5 and its template recorded here; *drop* applies Phase 5's abandon criterion now, so the product becomes the fallback of `PLAN.md` §1 (phases 1–4, 6 and 8 plus multi-label enum arrays); *marginal* goes to the owner with the numbers. Phase 5 still re-measures on its own disjoint corpus.

**Operating characteristic** of the deciding margin:

<!-- BEGIN:gate_oc -->
Exact binomial at n = 150 absent-answer cases (`stats.gate_oc`):

| true committed-when-absent rate | P(point estimate <= 0.05) | P(point estimate > 0.10: drop) |
|---|---|---|
| 0.02 | 0.989 | 0.000 |
| 0.03 | 0.917 | 0.000 |
| 0.05 | 0.523 | 0.004 |
| 0.07 | 0.169 | 0.061 |
| 0.10 | 0.014 | 0.432 |
| 0.12 | 0.002 | 0.729 |
| 0.15 | 0.000 | 0.951 |
<!-- END:gate_oc -->

**Secondary, not deciding:** the 300 Phase 0 cases are re-asked with the gate, for a paired before/after on the same cases. They are in-sample (the gate's wording was written after the Phase 0 results were known), so they cannot change the verdict.

**Budget:** about 140 requests for the fresh cases and 138 for the paired re-run, under the 5,000 cap.

**After the first live call** nothing in §1–§3 and no label changes except a genuine bug fix, recorded here with its commit and effect.

## 4. Results

Live run on 2026-09-29, committed in `7ed8e05`: 273 requests to `jev-1.13.0`, all HTTP 200, all 273 records scored (`tests/phase0/results/probe9.json`). Nothing in §1–§3 and no label changed after the first live call.

**Fresh cases (deciding).** Wilson 95% intervals.

| measure | with the gate | without (Phase 0 decoding, same answers) |
|---|---|---|
| correct commits | 105/150 = 0.700 [0.622, 0.768] | 123/150 = 0.820 |
| wrong commits when present | 4/150 = 0.027 [0.010, 0.067] | 10/150 = 0.067 |
| **committed when absent** | **10/139 = 0.072 [0.040, 0.127]** | 29/139 = 0.209 |
| probe 1′ (correct commits) | 105/150, *conditional* (9 ties) | |
| probe 2′ (abstain or fail, absent) | 115/139 = 0.827, *go* (14 ties) | |
| probe 3′ (abstain or fail, present) | **32/150 = 0.213, *stop*** (9 ties) | |

Outcomes, present cases: 105 committed correct, 4 committed wrong, 24 verification failed, 8 abstained, 9 ties. Absent cases: 96 abstained, 19 verification failed, 14 ties, 9 committed wrong, 1 committed partial. Committed when absent by regime: hard 6/52, other 4/87.

How the gate treats each kind of option (the verification `noul` is asked for every option): **correct options pass 124/227 (55%)**, partial 2/96, wrong 40/3,055 (1.3%).

**Verdict: drop** (`stats.gate_verdict`). Probe 3′ is in its stop band (k = 32; the band starts at k = 31). Committed-when-absent (0.072) is also above the 0.05 needed to proceed, but below the 0.10 drop line. Correct commits are exactly 0.70, which is not below 0.70.

**Paired Phase 0 cases (secondary, in-sample, not deciding):** correct commits 109/150 (135 without the gate); wrong when present 4/150 (4); committed when absent 15/150 = 0.100 (33/150 without); probe 3′ 28/150, *conditional*. The rule applied to these cases would give *marginal*.

**Reading.** The gate does what it was meant to do on the absent-answer side: it removes about two thirds of the wrong commits (29 → 10 of 139) and more than half of the wrong commits when the answer is present (10 → 4). It does this by being strict about everything. It rejects 45% of the correct answers, which turns 18 correct commits into verification failures and puts false abstention in the stop band. The residual 7% wrong commits on absent answers is not low enough to proceed either. At this wording, `jev-1.13.0` cannot say "yes, this is the complete value" reliably enough for a single verification `noul` to separate right from wrong.

**Consequence (§3):** *drop* applies Phase 5's abandon criterion now: the product becomes the fallback of `PLAN.md` §1. `PLAN.md` and `DESIGN.md` are not edited in this commit; the owner confirms the scope change first. A differently worded or multi-question gate would be a new pre-registered probe on a new disjoint corpus, not a re-reading of this one.
