You are grading drafts. The file `items-NNN.jsonl` in this directory holds one item per line. Each item is a JSON object `{"id", "source", "field", "criteria": [{"id", "statement"}], "draft"}`.

For every item, judge each criterion true or false against the item's `source` alone: true if the `draft` meets the criterion statement as the source supports it, false otherwise. You may add a short note.

Paging rule. Read the chunk file with the Read tool. If any Read result says it is a PARTIAL view, keep calling Read with the offset and limit that the result names until every line of the file has been returned. Never label an item whose line you have not been shown. A Grep or Glob result does not count as reading an item.

Labels. As soon as you have judged an item, append its label as one line to `labels-NNN.jsonl` in this directory, in this format and nothing else: `{"id": "<item id>", "criteria": {"<criterion id>": true or false, ...}, "note": "<optional note>"}`. Label every criterion id of the item. Append each label as soon as the item is judged; never write the file once at the end.

Write nothing else, and read nothing outside this directory.
