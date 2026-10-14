# Jevson

## Findings so far, measured on `jev-1.13.0` (2026-09-29): source selection does not work well enough

Before building anything, we tested Jevson's central idea on real documents: contracts, CVs, medical case reports, receipts, product listings and support tickets. Every rule and threshold was fixed before any call to Jev. The idea was to extract candidate spans from a document, have Jev pick the one that is the field's value, and have Jev answer *none of these* when the value is not there.

| what we measured | result |
|---|---|
| Jev picks the right span when it is among the options | **good**: 82–88% |
| Jev says *none of these* when the right span is **not** among the options | **not good enough**: it commits a wrong value about 21% of the time, a quarter of those with a probability of 0.95 or more |
| Adding a second check, a yes/no "is this the complete value?" question on the chosen span | cuts those wrong commits from 21% to 7%, but **rejects 45% of correct answers** |

So the probability Jev reports cannot tell a confident right answer from a confident wrong one when the answer is missing. The verification gate fixes most of that only by throwing away almost half the right answers. Under the rule we fixed in advance, the verdict is **drop source selection**. Pairwise entity resolution (deciding whether two mentions are the same person or company) also failed its probe.

**What still works:** bounded decisions, where the options are declared up front (enums, yes/no, scores), and checking generated text against declared criteria. The likely product is the fallback already in the plan: a compiler for bounded decisions and criteria-checked generative fields, *without* "find this value in the document".

Full record: the numbers, pre-registration, corpus, labels and code are in [PR #2](https://github.com/Project-Asterion/Jevson/pull/2) (`docs/taxonomy.md`, `docs/gate-probe.md`). The design text below predates these results.

On 2026-10-14 the [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions) replaced Jev as the decision model; these findings have not yet been re-measured on it, and [Phase 0r](docs/PLAN.md) does that.

---

A schema compiler for source-grounded structured extraction — **in design, not yet built**. Give it a Pydantic model or JSON Schema and a document; it will turn the schema into a graph of bounded decisions, have a decision model — the [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions) — make them, assemble the object in code, and record for every field how it was decided — with the source span or declared option, and the probability, where the decision model decided it — or a typed reason it could not be resolved.

## Why not just use structured outputs?

For shape — you should. Grammar-constrained decoding already makes a missing brace or a wrong nesting depth very hard to produce, and Jevson validates everything it assembles anyway.

Here is the problem it doesn't solve:

```json
{ "first_name": "Whitfield", "last_name": "Dana" }
```

Schema-valid. Completely wrong. A grammar cannot see it, `jsonschema` cannot see it, and nothing downstream knows anything happened.

Jevson targets **semantic selection** — *which interpretation of the source belongs in this field*:

- **Bounded fields** are chosen by the decision model from options declared in advance.
- **Source-grounded fields** are chosen by the decision model among candidate spans extracted from the document, with a *none of these* option by default. Every committed value is a verified span of the source, or parsed from exactly one (an amount or a date).
- **Generative fields** — a summary, a description — are drafted by your LLM and admitted only after the decision model checks them against the criteria you declare (a field with none is admitted and flagged as ungated).
- **Structure** is assembled by ordinary code. No model writes a brace.

For source-selected fields, when the source does not support any candidate you get an explicit *absent* or *unresolved* entry instead of a confident guess — a signal your pipeline can branch on. A question the Decisions API refuses to answer is *unresolved* too, never a default.

## Where it comes from

Selecting among pre-extracted candidates with a *none* escape hatch is [TypeSafe's own documented extraction pattern](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook) for Jev, the model Jevson was first designed on, and several open projects implement it for single fields or fixed record types. Jevson is designed to generalise it into a compiler: nested objects, unions decided before anything is built, arrays with entity resolution, criteria-gated generative fields, and a typed three-outcome result verified by an adversarial suite. See [docs/DESIGN.md §9](docs/DESIGN.md#9-prior-art) for everything it builds on.

## What it does not claim

- It cannot tell you a value is *correct*. Nothing can.
- **Provenance proves where a value came from, not that the source is honest.** Text inside a document can steer the model's choice; this is measured and documented, not solved.
- Abstention covers source-selected fields and is measured, not guaranteed. Calibration on this task will be measured, not assumed: the Decisions API makes no calibration claim.
- Only fields the decision model decides carry a probability; constants, defaults, direct extractions, values you supply, and ungated drafts do not.

## Status

**Design, pre-implementation.** No code yet, by design.

- **[docs/DESIGN.md](docs/DESIGN.md)** — the SSOT: architecture, tiered guarantees, limits, and the evidence behind each claim
- **[docs/PLAN.md](docs/PLAN.md)** — phases 0, 0r and 1–8 to v0, plus planned post-v0 phases 9–11, each with testable exit criteria and abandon criteria
- **[docs/EVIDENCE.md](docs/EVIDENCE.md)** — the evidence register: every factual claim in DESIGN and PLAN, and the probe or source that established it

Phase 0 is an empirical taxonomy plus probes with pre-registered thresholds, and it is allowed to conclude that the library should be smaller than described above.

## Licence

MIT.
