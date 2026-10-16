# Redraft-bar labelling set, run 1 (ASTERION-36)

- `items.jsonl`: the 444 drafts as the labeller saw them (no role, no verdict).
- `labels.jsonl`: the labels. **Model-labelled, not human-labelled**: the owner did not label them, and a separate
  Claude session labelled every item blind from `items.jsonl` alone (PLAN Phase 4, stated deviation).
- `key.jsonl` and `sampling.json`: held back during labelling, committed with the verdict.
- `report.json`: the scored verdict, pooled and per domain.

Rescore:

```bash
uv run --frozen python -m tests.j4b.labelling.score tests/j4b/labelling/run1/key.jsonl tests/j4b/labelling/run1/labels.jsonl --sampling tests/j4b/labelling/run1/sampling.json
```

For a human relabel, open `../label.html`, load `items.jsonl`, label every criterion, and score the download the same way.
