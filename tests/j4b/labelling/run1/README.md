# Redraft-bar labelling set, run 1 (ASTERION-36)

`items.jsonl` holds 444 drafts to label blind. The key that joins items to roles and verdicts, and `sampling.json`
(the seeds, the stopping rule and which instances were admitted and sampled), are held back outside the repository
until labelling ends (PLAN Phase 4); both are committed with the scored verdict.

To label: open `../label.html` in a browser, enter your initials, choose this folder's `items.jsonl`, answer Yes/No for
every criterion of every draft from the source and the draft alone, then **Download labels** and save the file as
`labels.jsonl` in this folder. You can stop at any point: progress stays in the browser, and a downloaded
`labels.jsonl` can be loaded again under *Resume*.
