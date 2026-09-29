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

*Recorded after the live run.*
