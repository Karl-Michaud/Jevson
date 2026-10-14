# Phase 1 packaging, dependencies, and CI

**Date:** 2026-10-14 · **Ticket:** ASTERION-24 · **Status:** accepted

## Context

Until Phase 1 the repository was the Phase 0 probe harness (`package = false`), with no CI beyond the
branch policy. Phase 1 (PLAN §2, Phase 1) makes `jevson` an installable package, and Agents/CLAUDE.md
§7.1 holds every product repo to separate ≥ 90% line and branch coverage, strict typing, lint, and
import contracts in CI. That rule also requires a decision record for each new dependency.

## Decision

- **Runtime:** `jsonschema` only. It is on PLAN Phase 8's list, and Phase 1 needs it: `satisfies_schema`
  is computed by draft 2020-12 validation (DESIGN §6.1). `pydantic` and `httpx` stay dev-only until a
  phase needs them in the package (`httpx` arrives with `DecisionsBackend`, Phase 3).
- **Build:** `hatchling`, build-time only; the wheel ships `jevson/` and nothing from `tests/`.
- **Dev:** `ruff` (lint and format), `pyright` (strict over `jevson/`), `import-linter` (PLAN §2 module
  discipline), alongside the existing `pytest`, `pytest-cov` and `hypothesis`.
- **CI** (`.github/workflows/ci.yml`): ruff, pyright, import-linter, pytest on Python 3.11 and 3.12 with
  branch coverage over `jevson/`, gated by `scripts/ci/coverage_gate.py` (ported from Asterion, see its
  `docs/decisions/2026-10-06-tooling-and-ci.md`) on line and branch coverage separately at ≥ 90%,
  and a wheel build imported in a clean environment. Actions are pinned by SHA to Asterion's versions.
- The Phase 0 harness keeps running in the same pytest session but is not held to the new lint and
  typing gates; it predates them and is a record, not product code.

## Consequences

- Each later phase adds its own runtime dependency here (or in a new record) when it first needs it.
- `compile/` and `execute/` join the import-linter contract when they land; until then
  `tests/architecture/test_module_discipline.py` checks them by path.
