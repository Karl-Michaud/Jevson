# LLM extractor prompts (Phase 0)

Recorded verbatim. The LLM extractor is a Claude Code subagent (model recorded in each output file). It sees only
the document text and the field list below; it never sees labels or any Jev output.

## Candidate extraction (probes 1-3, 6, 8) — prompt version 1

> You are the LLM candidate extractor of a document-extraction pipeline. You propose candidates; you do not decide
> answers.
>
> For each document and each field listed for it, return every span of the document text that could plausibly be
> the value of that field:
> - the value itself, if the document states it;
> - every other value of the same kind that appears in the document in some other role (other dates, other amounts,
>   other names of the same kind of thing, other titles, other places, other durations), because a later step
>   chooses among them;
> - shorter or longer forms of those values, where they appear in the text as such.
>
> Rules:
> - Copy each span exactly as it appears in the document text, character for character (same case, punctuation,
>   spacing). Never paraphrase, normalise, translate, or join text from different places.
> - A span is a value, not a sentence: keep it as short as the value itself.
> - At most 15 spans per field. Order does not matter.
> - If nothing in the document could be the field, return an empty list for it.

Output per document: `{"doc_id", "extractor": "llm", "prompt_version": "1", "model", "fields": {field_id: [span, ...]}}`.

## Mention extraction (probe 4) — prompt version 1

> You are the mention extractor of an entity-resolution pipeline. For the passage given (a character range of a
> document) and the entity type given (`person` or `organization`), list every distinct string in the passage that
> refers to a specific entity of that type: names, names with titles, abbreviations, defined terms, and role nouns
> that denote a specific entity ("the Company", "Licensee", "the patient", "the property custodian"). Exclude
> pronouns ("he", "it", "they", "its"). Copy each string exactly as it appears, character for character; list each
> distinct string once. At most 20 strings.

Output per passage: `{"passage_id", "doc_id", "entity_type", "start", "end", "prompt_version": "1", "model", "mentions": [string, ...]}`.
