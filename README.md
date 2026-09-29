# Jevson

Guaranteed LLM JSON output that will ALWAYS follow the given structure.

Jevson never lets the LLM emit the JSON. Bounded fields — booleans, enums, scores — are decided by [Jev](https://jevapi.dev/), whose outputs cannot violate a declared schema. Free-form fields are drafted by the LLM and admitted only after Jev adjudicates them against declared criteria. The object itself is assembled by ordinary code, so no model ever writes a brace.

Status: **design, pre-implementation.** See **[DESIGN.md](DESIGN.md)** for the architecture, the limits (arrays are the hard case), and how this differs from the schema-first Jev converters that already exist.
