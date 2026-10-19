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

- A generative field's draft no longer reaches the level's bounded questions (ASTERION-50).
  Adjudication questions were batched with the same level's enum, boolean, ordinal, membership and
  discriminator questions, whose shared state then carried the LLM's draft, so drafted text could
  steer a bounded decision it was not written for. Adjudication now goes in request(s) of its own,
  the only ones whose state holds `drafts`; each group is budgeted, split and bisected separately.
  A level that holds both bounded questions and adjudication costs one more decision request; a
  level of adjudication only is unchanged. DESIGN Revision 11.5.
- Bisecting an adjudication request rebuilds each half's state, so it carries only its own
  questions' drafts (ASTERION-50).
- Preflight budgets the `drafts` wrapper, so a request no longer goes out a few tokens over
  `max_input_tokens` (`Result.versions["budget_estimator"]` is now `bytes/3+160q+8o+dw`;
  ASTERION-50).
- `CachingBackend` recordings of levels that mix bounded and generative fields no longer match
  (with `replay_only=True` that is `BackendError(replay_miss)`); re-record them (ASTERION-50).
- The estimate recorded for each decision request (`CostEvent.estimated_input_tokens`,
  `Cost.decision_input_tokens_estimated`) is the one preflight budgeted; an adjudication request's
  draft and `drafts` wrapper were counted twice in it (ASTERION-50).
- A `BackendError` on a level's adjudication request keeps that level's bounded answers, already
  received and billed, in the partial `Result` it carries (ASTERION-50).
- `Cost.level_splits` counts only splits and bisections within a request group; the separate
  adjudication request is not a split (ASTERION-50).

**Fixed before release** (ASTERION-44, the post-merge review of the v0 pull requests)

- Final validation checks `format`: `Result.violations` names a value that fails `email`,
  `date`, `uuid`, `ipv4`/`ipv6` or `regex`, which `jsonschema` checks on its own; formats that
  need `jsonschema[format]` (`date-time`, `uri`, …) are still checked only with those extras.
- `JevsonConfig.transport_retries` is removed: nothing read it. Transport retries are set on the
  backend that makes the requests, `DecisionsBackend(transport_retries=...)` (default 2). Passing
  `transport_retries` to `JevsonConfig` is now a `TypeError`; move it to `DecisionsBackend`.
- `DecisionsBackend` ignores a malformed `Retry-After` (`nan`, `inf`, `1e309`, negative) and
  backs off as usual, and no longer retries early when the server asks for more than 30 s: it
  raises `BackendError` at once, with that attempt in `Cost`.
- New `RefusalCode.INDISTINGUISHABLE_OPTIONS`: an enum with two values whose options render alike
  (`["a", "a"]`, `["1", 1]`) refuses at compile time instead of asking a choice the model cannot
  answer. The `enum_size` message states the real bound ("at most 255"; one value is a constant).
- A multi-label enum array whose item enum includes `null` (`list[Literal[...] | None]`) refuses
  with `enum_value_type` instead of dropping the `null` silently.

**Not included** (refused with a named reason, never half-supported): source selection
(`x-jevson.source`, `default_extractor` → `source_selection_dropped`), pairwise entity resolution,
arrays of objects, generative lists, multi-source input. See the README's "What did not ship".
