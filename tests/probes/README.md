# Probes

The scripts behind every evidence tag in [`docs/EVIDENCE.md`](../../docs/EVIDENCE.md). They are the starting material for Jevson's test suite, not tests yet: they print measurements rather than assert.

- `probe_*.py` call the live Jev API (`jev-1.13.0`). They read `TYPESAFE_API_KEY` from the repository's gitignored `.env` (template: `.env.example`), never print it, and cost money: check the request count in each docstring before running.
- `check_*.py` / `.mjs` run locally with no API key.
- Every script writes to `out/` beside it (gitignored). A few checks (`check_r2_rounding.py`, `check_r3_calibration_bar_empirical.py`, `check_r4_tie_margin_pooled.py`, `check_r5_sum_tolerance_largek.py`) analyse saved live answers, so run the probes first.
- `fetch_vendor_docs.sh` snapshots TypeSafe's documentation into `jevdocs/` (gitignored) for the checks that read it.
- `jevclient.py` is the shared HTTP client for the probes.

Each script's docstring names the claim it tests and its method. Pilot datasets are synthetic and author-written: they test mechanisms, not the pre-registered Phase 0 measurements in `docs/PLAN.md`.
