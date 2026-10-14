# Phase 0 labelling protocol (version 1)

Labels are produced by labelling agents (Claude Code subagents, fresh context each) that **never see any Jev
output**: they receive the document, the field definitions, and the candidate list only. Labels are committed before
any Jev call on the data. Summary and agreement: `docs/taxonomy.md` §2.11 and §4.

## Candidate labels (probes 1–3, 6, 8)

For each document:

- **`multi_entity`** — `true` if the document involves two or more distinct parties (people or organisations) in
  different roles, or several addresses, invoices, or transactions; otherwise `false`.
- **`processing_note`** — the exact quote of one sentence that is an ordinary processing note (instructions about
  routing, filing, payment, portals, inspection or pick-up, or how the document is to be submitted or processed), or
  `null` if there is none.

For each field of the document:

- **`status`** — `present`: the document states the complete value of the field; `absent`: it does not state it at
  all; `partial_only`: it states only part of the value (a date without its year, a first name without the surname,
  a street without its city).
- **`value`** — the complete value exactly as written (for `present`), the partial form (for `partial_only`), or `null`.
- **`superseded`** — `true` if the document also states an earlier, superseded, amended, or replaced value for this
  field (an earlier position, an amended date, an original price later changed).
- **`options`** — for every candidate option (an occurrence of a text at an offset, shown with its context):
  - **`correct`** — this occurrence gives the complete value of the field, in the role the field asks for. Words that
    belong to the same phrase (a currency symbol, a unit, or a label such as "TOTAL" or "Effective Date:") may be
    included; text belonging to another value may not.
  - **`partial`** — this occurrence gives only part of the correct value, in the correct role.
  - **`wrong`** — anything else, **including the right text at an offset where it plays a different role** (the
    same amount printed as the subtotal, the same date as the signing date).
- **`rationale`** — one short sentence.

## Mention labels (probe 4)

For each passage and its mention strings (already located and pre-merged): assign each mention a gold entity id
(`E1`, `E2`, …) with a one-line description of each entity; mark **`role_noun`** if the mention is a role noun or
defined term ("the Company", "Licensee", "the patient") rather than a name; mark **`ambiguous`** if the string refers
to more than one entity within the passage (such mentions are excluded from the cluster).

## Second labeller and disagreements

An independent second labelling agent re-labels a seeded 20% sample of field instances and of clusters, without the
first labels. Cohen's kappa is reported on option labels, field status, and mention-pair same/different judgements.
Every disagreement on a sampled item is adjudicated by a third independent agent that sees the document, both labels,
and both rationales (never Jev output); its decision replaces the first label, and every case is recorded in
`adjudication.jsonl`.
