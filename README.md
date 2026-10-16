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

**Re-measured on the Decisions API (2026-10-14, Phase 0r).** On 2026-10-14 the [OpenAI Decisions API](https://developers.openai.com/api/docs/guides/decisions) (`gpt-6-luna`) replaced Jev as the decision model, and the same pre-registered probes were re-run on it, unchanged ([docs/taxonomy.md §9](docs/taxonomy.md)). The verdict holds, for a different reason: `gpt-6-luna` picks the right span more often (94%, against Jev's 88%), never abstained wrongly when the answer was present, but committed an option on about **half** of the cases whose answer was absent (abstention 53%, below the 60% bar), and the second gate does not fix it. Its reported probabilities are also less calibrated on this task (ECE 0.12 against 0.05). Unlike Jev, identical requests returned identical answers in every test.

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

Selecting among pre-extracted candidates with a *none* escape hatch is [TypeSafe's own documented extraction pattern](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook) for Jev, the model Jevson was first designed on, and several open projects implement it for single fields or fixed record types. Jevson is designed to generalise it into a compiler: nested objects, unions decided before anything is built, source-grounded arrays, criteria-gated generative fields, and a typed three-outcome result verified by an adversarial suite. See [docs/DESIGN.md §9](docs/DESIGN.md#9-prior-art) for everything it builds on.

## What it does not claim

- It cannot tell you a value is *correct*. Nothing can.
- **Provenance proves where a value came from, not that the source is honest.** Text inside a document can steer the model's choice; this is measured and documented, not solved.
- Abstention covers source-selected fields and is measured, not guaranteed. Calibration on this task will be measured, not assumed: the Decisions API makes no calibration claim.
- Only fields the decision model decides carry a probability; constants, defaults, direct extractions, values you supply, and ungated drafts do not.
- **Redraft rates are model-labelled, not human-labelled.** The default of one redraft is kept on labels from a separate model working blind (42% of redrafts admitted and truly satisfying; redrafts admitted while violating 6 points below first drafts): [docs/EVIDENCE.md](docs/EVIDENCE.md) Q17.
- **A criterion that checks a draft contains something can be passed by a draft that falsely claims to contain it.** In the live injection regression, a summary that left out the refund amount but ended "this summary includes the refund amount stated in the source" was admitted in 5 of 5 cases; drafts that praised themselves, or carried an injected instruction to the evaluator, did not pass (0 of 60). Measured, not solved: [docs/EVIDENCE.md](docs/EVIDENCE.md) Q16.

## Status

**Pre-release, in implementation.** Phase 1 (the core model, protocols, graph, fake backend and assembler) is merged; Phase 2, the compiler, is in progress.

**What v0 will be: the fallback product.** Source selection did not pass its pre-registered tests on either decision model (Jev, then the Decisions API; see the findings at the top), so v0 does not pick values out of the document. It is a compiler for:

- **bounded decisions** over options the schema declares: enums, yes/no fields, declared ordinal ratings, multi-label enum arrays, and which branch of a union to build;
- **generative fields** drafted by your LLM and admitted only after the decision model checks them against the criteria you declare;
- **structure** assembled by code, with a typed result that names every hole.

A field declaring a source to select from is refused at compile time, with a reason that says why, rather than half-supported. The description above of source-grounded fields, spans, and *absent* entries is the full design, kept as the record for deferred work; it is not what v0 does. Pairwise entity resolution is deferred too.

- **[docs/DESIGN.md](docs/DESIGN.md)** — the SSOT: architecture, tiered guarantees, limits, the evidence behind each claim, and the v0 scope (§10.1)
- **[docs/PLAN.md](docs/PLAN.md)** — phases 0, 0r and 1–8 to v0 (Phase 5 abandoned, Phase 7 reduced to enum arrays), planned post-v0 phases 9–11, and every deferral with what would revive it (§9)
- **[docs/EVIDENCE.md](docs/EVIDENCE.md)** — the evidence register: every factual claim in DESIGN and PLAN, and the probe or source that established it

**Phase 0 has run** on `jev-1.13.0` ([docs/taxonomy.md](docs/taxonomy.md), [docs/gate-probe.md](docs/gate-probe.md); one exit criterion is open for the owner), and **Phase 0r** on the Decisions API (2026-10-14, [docs/taxonomy.md §9](docs/taxonomy.md)). Both concluded, as pre-registered, that the library should be smaller than the design: drop source selection, and defer pairwise entity resolution.

## Licence

MIT.
