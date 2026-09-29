# Jevson

A schema compiler for source-grounded structured extraction — **in design, not yet built**. Give it a Pydantic model or JSON Schema and a document; it will turn the schema into a graph of bounded decisions, have [Jev](https://docs.typesafe.ai/) make them, assemble the object in code, and record for every field how it was decided — with the source span or declared option, and the probability, where Jev decided it — or a typed reason it could not be resolved.

## Why not just use structured outputs?

For shape — you should. Grammar-constrained decoding already makes a missing brace or a wrong nesting depth very hard to produce, and Jevson validates everything it assembles anyway.

Here is the problem it doesn't solve:

```json
{ "first_name": "Whitfield", "last_name": "Dana" }
```

Schema-valid. Completely wrong. A grammar cannot see it, `jsonschema` cannot see it, and nothing downstream knows anything happened.

Jevson targets **semantic selection** — *which interpretation of the source belongs in this field*:

- **Bounded fields** are chosen by Jev from options declared in advance.
- **Source-grounded fields** are chosen by Jev among candidate spans extracted from the document, with a *none of these* option by default. Every committed value is a verified span of the source, or parsed from exactly one (an amount or a date).
- **Generative fields** — a summary, a description — are drafted by your LLM and admitted only after Jev checks them against the criteria you declare (a field with none is admitted and flagged as ungated).
- **Structure** is assembled by ordinary code. No model writes a brace.

For source-selected fields, when the source does not support any candidate you get an explicit *absent* or *unresolved* entry instead of a confident guess — a signal your pipeline can branch on.

## Where it comes from

Selecting among pre-extracted candidates with a *none* escape hatch is [TypeSafe's own documented extraction pattern](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook), and several open projects implement it for single fields or fixed record types. Jevson is designed to generalise it into a compiler: nested objects, unions decided before anything is built, arrays with entity resolution, criteria-gated generative fields, and a typed three-outcome result verified by an adversarial suite. See [DESIGN.md §9](DESIGN.md#9-prior-art) for everything it builds on.

## What it does not claim

- It cannot tell you a value is *correct*. Nothing can.
- **Provenance proves where a value came from, not that the source is honest.** Text inside a document can steer the model's choice; this is measured and documented, not solved.
- Abstention covers source-selected fields and is measured, not guaranteed. Calibration on this task will be measured, not assumed.
- Only fields Jev decides carry a probability; constants, defaults, direct extractions, values you supply, and ungated drafts do not.

## Status

**Design, pre-implementation.** No code yet, by design.

- **[DESIGN.md](DESIGN.md)** — the SSOT: architecture, tiered guarantees, limits, and the evidence behind each claim
- **[PLAN.md](PLAN.md)** — phases 0–8 to v0, plus planned post-v0 phases 9–11, each with testable exit criteria and abandon criteria
- **[docs/REDTEAM.md](docs/REDTEAM.md)** — the evidence register: every factual claim in DESIGN and PLAN, and the probe or source that established it

Phase 0 is an empirical taxonomy plus probes with pre-registered thresholds, and it is allowed to conclude that the library should be smaller than described above.

## Licence

MIT.
