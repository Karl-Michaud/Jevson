# Changelog

## Versioning policy

Jevson is `0.x`. Until 1.0, **a minor release (`0.1` → `0.2`) may break the public API**; a patch
release (`0.1.0` → `0.1.1`) does not. Every breaking change is recorded here, under the release
that makes it, with what to change. The public API is exactly `jevson.__all__`; anything else may
change in any release. Behaviour that depends on the decision model's answers is not part of the
API: `gpt-6-luna` cannot be pinned, and the model string each result records is the only version.

## 0.1.0 — unreleased

The first release: the v0 fallback product (DESIGN §10.1). Not yet published; the package name is
pending the owner's decision (PLAN §6).

**Added**

- `compile_schema()` and `Jevson.resolve()` / `aresolve()`: a Pydantic model or JSON Schema
  (draft 2020-12) compiled into bounded decisions (enums as `choice`, described booleans as
  `predicate`, integer ranges marked `x-jevson.ordinal` as `score`), multi-label enum arrays,
  and discriminated unions decided before construction (fan-out by default).
- Generative fields (`x-jevson.generate`): drafted by the caller's `LLM`, adjudicated against
  declared criteria and an optional rubric, with one redraft by default; `dry_run()` for criteria.
- `Result`: the three-outcome result, with `unresolved`, `violations`, `rejections`, `ungated`,
  `decided_by`, `decisions`, `provenance`, `cost`, `model` and `versions`.
- Backends: `DecisionsBackend` (the OpenAI Decisions API over `httpx`), `FakeBackend` (offline,
  scripted) and `CachingBackend` (exact replay); `ReplayLLM` for exact LLM replay.
- `InMemoryCostSink`, the default `CostSink`.
- Examples in `examples/`, each runnable offline with no API key.

**Changed**

- Repository tooling, not the package: the Plane workflow pointers (`.claude/plane-workflow.json`,
  `.github/workflows/branch-policy.yml`) now name the shared `plane-workflow` skill in
  `Agents/.claude/skills/plane-workflow` instead of a global one (ASTERION-43).

**Fixed**

- A generative field's draft no longer reaches unrelated questions (ASTERION-50). Adjudication
  questions were batched with the same level's enum, boolean, ordinal, membership and
  discriminator questions, whose shared state then carried the LLM's draft, so drafted text could
  steer a bounded decision it was not written for. Adjudication now goes in request(s) of its own,
  the only ones whose state holds `drafts`; each group is budgeted, split and bisected separately.
  A level with drafts costs one more decision request. DESIGN Revision 11.5.

**Not included** (refused with a named reason, never half-supported): source selection
(`x-jevson.source`, `default_extractor` → `source_selection_dropped`), pairwise entity resolution,
arrays of objects, generative lists, multi-source input. See the README's "What did not ship".
