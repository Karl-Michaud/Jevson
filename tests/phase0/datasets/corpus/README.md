# Phase 0 corpus

Real documents for the Phase 0 probes (`docs/taxonomy.md` §3), one file per document under `<domain>/<doc_id>.txt`. Every document's source URL, licence, retrieval date (2026-09-29), character count, and SHA-256 of this text is in `manifest.jsonl`; `tests/phase0/datasets/fetch.py` re-fetches the sources.

These texts are not covered by the repository's code licence. Each keeps its own:

| folder | source | licence and attribution |
|---|---|---|
| `contract/` | CUAD v1, The Atticus Project (https://zenodo.org/records/4595826) | CC BY 4.0 |
| `receipt/` | CORD v2, NAVER Clova (https://huggingface.co/datasets/naver-clova-ix/cord-v2), text rebuilt from the annotated OCR words | CC BY 4.0 |
| `resume/` | Federal Judicial Center, Biographical Directory of Article III Federal Judges (fjc.gov) | U.S. Government work, public domain |
| `support_ticket/` | Stack Exchange questions (superuser, askubuntu, es.stackoverflow); the author and link of each are in the manifest | CC BY-SA 4.0: these texts are redistributed under CC BY-SA 4.0 |
| `medical_intake/` | Europe PMC open-access case reports, case-presentation sections; the article and PMCID of each are in the manifest | CC BY 4.0 (per article licence, checked at retrieval) |
| `product_listing/` | GSA Auctions listings by federal agencies (api.gsa.gov) | U.S. Government work, public domain |

The only non-source text used anywhere in Phase 0 is probe 6's injected notes, which are generated at run time (`tests/phase0/probes.py`) and never written into these files.
