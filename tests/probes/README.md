# Probes

The scripts behind every evidence tag in [`docs/EVIDENCE.md`](../../docs/EVIDENCE.md). They are the starting material for Jevson's test suite, not tests yet: they print measurements rather than assert.

| folder | what it covers |
|---|---|
| `jev_api/` | Jev's own behaviour: determinism, jitter and ties, limits, context budget, state references, latency, score decoding, probability sums |
| `candidates/` | candidate selection and `none_of_these`: abstention, single candidates, complete-value wording, repeated text, option keys and descriptions, scoping |
| `entities/` | pairwise entity resolution: conflict floor, pair jitter, out-of-sample rules, pairwise budget |
| `adversarial/` | injected drafts and hostile sources; the source screen |
| `calibration/` | statistics behind the pass/fail bars: calibration, Phase 0 and Phase 5 bands, retry threshold, tie margin, sum tolerance, rounding |
| `schema/` | Pydantic and JSON Schema behaviour: emitted shapes, normalisation, mapping, absence/null, validation |
| `unicode/` | offsets, grapheme boundaries, normaliser stability, Python vs JavaScript |
| `runtime/` | async design, client lifecycle, canonical JSON, provider tool schemas |

- `probe_*.py` call the live Jev API (`jev-1.13.0`). They read `TYPESAFE_API_KEY` from the repository's gitignored `.env` (template: `.env.example`), never print it, and cost money: check the request count in each docstring before running.
- `check_*.py` / `.mjs` run locally with no API key.
- Run any script from anywhere, e.g. `python tests/probes/jev_api/probe_smoke.py`. Every script writes to the shared, gitignored `tests/probes/out/`. A few checks (`calibration/check_rounding.py`, `calibration/check_calibration_bar_empirical.py`, `calibration/check_tie_margin_pooled.py`, `calibration/check_sum_tolerance.py`) analyse saved live answers, so run the probes first.
- `fetch_vendor_docs.sh` snapshots TypeSafe's documentation into `jevdocs/` (gitignored) for the checks that read it.
- `jevclient.py` is the shared HTTP client for the probes.

Each script's docstring names the claim it tests and its method. Pilot datasets are synthetic and author-written: they test mechanisms, not the pre-registered Phase 0 measurements in `docs/PLAN.md`.

**Note (2026-10-14).** These probes target Jev (`jev-1.13.0`), which the OpenAI Decisions API replaced as Jevson's decision model on 2026-10-14. Porting them (`jevclient.py` and the `probe_*.py` scripts) to the Decisions API is a follow-up ticket, and must land before `docs/PLAN.md` Phase 0r re-runs them.
