# Jevson

Source-grounded structured extraction. Values are traceable to source evidence or declared options, bounded semantic choices are made by a calibrated decision model, and structure is enforced deterministically.

## Why not just use structured outputs?

For shape — you should. Grammar-constrained decoding already makes an out-of-enum value, a missing brace, or a wrong nesting depth *unreachable*, not merely unlikely. That problem is solved, and Jevson does not claim to solve it better.

Here is the one it doesn't solve:

```json
{ "first_name": "Whitfield", "last_name": "Dana" }
```

Schema-valid. Completely wrong. A grammar cannot see it, `jsonschema` cannot see it, and nothing downstream knows anything happened.

Jevson attacks **semantic selection** — *which interpretation of the source belongs in this field.* It never asks a model to conjure a value:

- **Bounded fields** are chosen from options declared in advance, so an invalid value is unrepresentable.
- **Free-form fields** are chosen from candidate spans extracted from the source, so every committed string is verifiable against the document it came from.
- **Structure** is assembled by ordinary code. No model writes a brace.

Every value arrives with a calibrated confidence and a pointer to its origin. When no candidate is supported by the source, you get an explicit abstention instead of a confident wrong answer.

In a pipeline, that is the difference between a bad value propagating silently and a signal you can branch on.

## Status

**Design, pre-implementation.** No code yet, by design.

- **[DESIGN.md](DESIGN.md)** — the SSOT: architecture, tiered guarantees, limits, and the reasoning behind each
- **[PLAN.md](PLAN.md)** — the build plan: nine phases with testable exit criteria, and the abandon criteria that would shrink or stop the project

Scope is not yet settled. Phase 0 is an empirical taxonomy plus a feasibility spike with pre-registered thresholds, and it is allowed to conclude that this library should be smaller than described above. That outcome is planned for rather than argued against.

Built on [Jev](https://jevapi.dev/), TypeSafe's constrained System One model.

## What it does not claim

It cannot tell you a value is *correct*. Nothing can. What it provides is shape that cannot be wrong, provenance you can verify by substring match, a calibrated number on every decision, and an abstention when the source does not support an answer.

## Licence

MIT.
