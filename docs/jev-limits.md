# What Jev can and cannot do: findings from 1,069 pre-registered calls

> **Status:** a summary for readers outside the project, written 2026-09-30. It draws on Phase 0 (`docs/taxonomy.md`, tags Z1–Z8, 796 requests) and probe 9 (`docs/gate-probe.md`, tag Z9, 273 requests). All requests went to TypeSafe's Jev, pinned to `jev-1.13.0`. Every number here comes from those records.

## What we were trying to do

Jevson is designed as a schema compiler. It takes a JSON Schema and a document, breaks the schema into small bounded questions, has Jev answer each one, and assembles the JSON in code. The hardest and most valuable part is **source selection**. Take a field such as "the contract's effective date". Code first lists every candidate date in the document as an option. Jev then picks the one that is the effective date, or answers `none_of_these` when the document does not state one. If that works, the output can never contain a confident, schema-valid wrong value.

## How we tested it

- **Real documents only:** 373 of them in total, drawn from six sources: SEC contracts (CUAD), federal judge biographies (FJC), medical case reports (Europe PMC), receipts in Indonesian (CORD), government auction listings (GSA), and English and Spanish support questions (Stack Exchange). Every licence permits redistribution.
- **Ground truth set without Jev:** labelling agents that never saw a Jev answer marked every candidate as correct, partial or wrong. A second labeller independently labelled a random 20% sample; agreement on option labels was κ = 0.94 in both rounds. A third agent resolved every disagreement.
- **Rules fixed in advance:** templates, thresholds and pass/fail rules were committed to git before the first live call and not changed afterwards.
- **Two kinds of case:**
  - *Present:* the right span is among the options.
  - *Absent:* every correct span is removed, and at least three wrong options remain. The right answer is then `none_of_these`.
- **Hard cases:** at least 30% come from long documents with several parties, or with a value that is later superseded.

## What Jev is good at

| task | result |
|---|---|
| Pick the right span when it is among the options (Phase 0) | **132/150 = 0.88** |
| Same, on 157 fresh documents (probe 9) | 123/150 = 0.82 |
| Wrongly say "none" when the answer *is* there | **2/150 = 0.013** |
| Commit a lone correct candidate | 49/50 |
| Refer to list items by a key such as `candidates.c7` | **0/320 wrong** |
| Flag documents containing injected "notes to the extractor" | 50/50 flagged, 3/50 false alarms |
| Overall calibration (280 committed decisions) | ECE 0.046; mean confidence 0.904 against accuracy 0.864 |

Jev chooses well among declared options, and at p = 1.00 it was right on 82 of 83 decisions.

## Where it breaks

### 1. It commits a wrong value when the answer is missing

| | commits a wrong or partial value when the right answer is absent |
|---|---|
| Phase 0 | 31/150 = **0.21** |
| Probe 9, fresh documents | 29/139 = **0.21** |

About one time in five, Jev picks a plausible wrong span instead of `none_of_these`. These commits are not all low-confidence. In Phase 0 their probability ranged from 0.54 to 1.00, and 8 of the 31 were at 0.95 or above. A confidence threshold therefore cannot filter them out without also discarding a large share of correct answers.

The failure is concentrated in the cases that matter most:

- Hard cases (long documents with several parties, or superseded values) went wrong more often, even with the second check described below: 6/52 hard against 4/87 other on fresh cases.
- On the 45 hard absent-answer cases in Phase 0, Jev correctly said `none_of_these` on only 24, against 86/105 on the rest.

### 2. Confidence is well calibrated on average, but not per decision

Averaged over all decisions, the probabilities are close to honest (ECE 0.046). Within some confidence bins they are not:

| stated confidence | n | actually correct |
|---|---|---|
| 0.94–0.95 | 18 | 0.667 |
| 0.80–0.87 | 21 | 0.714 |
| 0.99 | 46 | 0.957 |
| 1.00 | 83 | 0.988 |

Calibration says how often a 0.95 is right across many decisions. It cannot tell you which particular 0.95 is wrong, and that is exactly what an extraction pipeline needs to know.

### 3. A second check does not rescue it

We tested the obvious fix before building it. After the choice, the same call asks one yes/no question about each option: *"Is `candidates.X` the complete {field} as written in the source?"* A pick is kept only if its check passes (p ≥ 0.56). The test used 157 new documents, and the rule was committed before any data existed.

| on fresh cases | without the check | with the check |
|---|---|---|
| wrong commit when the answer is absent | 29/139 = 0.21 | **10/139 = 0.07** |
| wrong commit when the answer is present | 10/150 | 4/150 |
| correct commit when the answer is present | 123/150 = 0.82 | **105/150 = 0.70** |
| no answer although one exists | 17/150 | **32/150 = 0.21** |

How often the check passes each kind of option:

- correct: **124/227 (55%)**
- partial: 2/96
- wrong: 40/3,055 (1.3%)

The check is strict about everything. It removes about two thirds of the wrong commits, but it also throws away 45% of the correct ones. The residual 7% of wrong commits is still above the 5% bar we set in advance. **Pre-registered verdict: drop.**

### 4. Entity resolution (are two mentions the same person?) fails in a structured way

Pairwise same-or-different questions look accurate: 1,560/1,592 = 0.98 at a 0.5 threshold. But assembling the pairs into entities fails in one of two ways:

- **Trusting the pairs:** 30/330 groupings come out silently wrong (20 wrongly split, 10 wrongly merged).
- **Requiring every pair to be confident:** the wrong groupings fall to 4/330, but only 163/330 groupings survive at all.

### 5. Text in the document can steer it

We injected "notes to the automated extractor" into documents. Jev then picked the span the note advocated in 10/50 present cases (0/50 without the note). In absent cases, abstention fell from 39/46 to 17/46. A separate screening question caught every injected document, so the defence exists, but it has to be asked.

### 6. Positional references fail

Asking about "item [37] of the list" instead of a keyed id gave the wrong answer 199/320 times (0.62). With keys the error rate was 0/320. This is easy to design around, but it is a hard rule.

## What this means

- **Jev is a good chooser among declared options, and its probabilities are honest on average.** Enums, yes/no questions, scores and criteria checks on generated text all fit it well.
- **Jev is not a reliable judge of "the answer isn't here"** when the options contain a plausible impostor. Its confidence does not separate a right answer from a plausible wrong one on individual decisions.
- **Source selection is therefore out of Jevson's v0.** The project falls back to a compiler for bounded decisions and criteria-checked generative fields, without "find this value in the document".
- **The test is reusable.** The corpus, labels, cases and scoring code are all in `tests/phase0/`. Any model that answers a choice with `none_of_these`, such as a later Jev or OpenAI's Decisions API, can be run on exactly the same 589 cases and compared number for number.

## Limits of this study

- **One model version:** `jev-1.13.0` only, with one wording of each template. The gate's wording was a single pre-registered try, not a search.
- **Stand-in documents in four domains:** these are real documents of the right kind, but not the documents each schema was written for. For example, judge biographies stand in for résumés.
- **Shortfalls:**
  - Receipts reached 11 of the 30 planned in probe 9.
  - Absent cases reached 139 of the 150 planned in probe 9.
  - Sources that state only a partial value reached 17 of the 50 planned in Phase 0.
- **Labels come from AI agents, not humans:** agreement was high (κ ≈ 0.94) and every disagreement was adjudicated, but no human review was done.
