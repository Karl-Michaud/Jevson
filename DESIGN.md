# Jevson — design

> **Status:** Design document, 2026-09-28. Pre-implementation.
>
> **One line:** Guaranteed schema-valid JSON from an LLM, by never letting the LLM emit the JSON — bounded fields are decided by [Jev](https://jevapi.dev/), free-form fields are drafted by the LLM and adjudicated by Jev, and the object itself is assembled by ordinary code.

---

## 1. The problem

LLMs can be *instructed* to emit JSON. They cannot be *made* to. Providers offer JSON modes, grammars, and tool schemas that narrow the failure rate without closing it, and every production system ends up with the same defensive layer: parse, validate, retry, repair, give up. The failure is not usually malformed syntax — modern models rarely miss a brace. It is semantic: an enum value that isn't in the enum, a score outside the range, a field invented or omitted, a nested object flattened.

Jev has the opposite property. Its outputs are constrained to a schema declared before the call, so an invalid value is not merely unlikely but unrepresentable. TypeSafe reports a 0% structured-output error rate, which is a claim about the class of outputs the model can produce rather than a benchmark score.

Jev also has a hard limit that shapes everything below: **it answers bounded questions and nothing else.** Its three primitives are a boolean probability (`noul`), a choice among declared options (`choice`), and an ordered rubric score (`score`). It cannot produce free-form text, arrays, or nested objects; it does not read images; it does not reason step by step. So Jev can never extract `"name": "Dana Whitfield"` from a document. That value is not in any declared option set.

The naive framing — *take the LLM's output and convert it to JSON with Jev* — is therefore not achievable as stated, because conversion of an unbounded field requires producing an unbounded value. But the goal behind the framing is achievable, and the route is narrower and better than conversion.

## 2. The idea

**Jev is not a converter. It is the gate on the commit path, and code is the assembler.**

The LLM keeps the work only it can do: reading messy input, reasoning across it, drafting prose. It is never permitted to *emit the result object*. Instead it is handed exactly one tool and forced to use it, and that tool commits one field at a time through Jev.

```text
                 target JSON Schema
                         |
                 schema compiler
                         |
        +----------------+----------------+
        |                |                |
   decidable        generative        structural
   bool, enum,      free-form         objects, arrays,
   0-1 number,      strings           nesting, required
   2-10 ordinal                       fields, defaults
        |                |                |
        v                v                v
  Jev decides      LLM drafts ->      library walks
  the value        Jev adjudicates    and assembles
        |                |                |
        +----------------+----------------+
                         |
                assembled object
                         |
            validate against original schema
                         |
                    return JSON
```

Three field classes, three owners. Nothing crosses.

### 2.1 Decidable fields: the LLM never sees the value

For a field whose legal values are enumerable — a boolean, an enum of up to 255 options, an integer range of 2 to 10 levels, a number bounded to 0–1 — the LLM's tool call does **not** carry the value. It carries evidence:

```jsonc
// the LLM's forced tool call
{
  "field": "sentiment",
  "evidence": "Third paragraph: 'we're actively looking at alternatives' and 'the last two releases were rough'."
}
```

Jevson turns the field's schema into a Jev `choice` over `["positive", "neutral", "negative"]`, passes the evidence as state, and Jev returns the value with a distribution and a confidence. The LLM cannot emit `"mixed"`, because it was never asked for a value at all. This is the strongest guarantee in the library and it costs one bounded question.

### 2.2 Generative fields: the LLM drafts, Jev admits

Only the LLM can produce a `summary` string. So it does — and the draft is not committed until Jev admits it. Each generative field declares criteria, and each criterion becomes a `noul`; an optional rubric becomes a `score`. All of them are evaluated in one batched call, since Jev answers every question on a state in parallel.

```jsonc
// field declaration
{
  "summary": {
    "type": "string",
    "x-jevson": {
      "criteria": [
        "is at most three sentences",
        "mentions no product name absent from the source",
        "states the customer's primary complaint"
      ],
      "rubric": { "levels": ["unusable", "weak", "acceptable", "strong"], "min": "acceptable" }
    }
  }
}
```

On rejection the tool returns the failing criterion, not a generic error, and the LLM redrafts. Retries are bounded; exhaustion is a typed failure, never a silently accepted string.

The honest boundary: Jev adjudicates against the criteria you declare and nothing else. It is not a fact-checker. Criteria quality is the library's real interface.

### 2.3 Structure belongs to code

Objects, nesting, required fields, defaults, and array assembly are walked by the library. No model emits a brace, a comma, or a quote. This is where the syntactic guarantee actually comes from.

## 3. Forcing is not guaranteeing

Both matter, and they are different mechanisms — worth stating plainly because conflating them is how this design would get built wrong.

**Forcing** is available at the provider level: `tool_choice` pinned to a specific tool makes the model call that tool rather than replying with prose. It raises first-pass acceptance and removes a whole class of "the model just answered in Markdown" failures. It is an optimisation.

**Guaranteeing** comes from three structural facts, none of which depend on the model behaving:

1. Decidable values never pass through the LLM — it supplies evidence, Jev supplies the value.
2. Generative payloads are plain strings, the simplest type a tool call can carry, and they are validated before commit.
3. Structure is assembled by code, so there is no step at which a model could produce invalid JSON.

A forced tool call can still arrive with junk arguments, because arguments are generated. Jevson survives that: a junk `evidence` string yields a low-confidence Jev answer that trips a threshold, and a junk `draft` fails adjudication. Neither can corrupt the shape of the result.

### 3.1 The skill layer

Packaging the field list, the criteria, and the commit protocol as a skill or system-prompt block is worth doing: better-instructed models call the tool correctly the first time, which cuts retries and therefore cost and latency. It belongs in the library as a generated prompt artifact. It is not part of the guarantee, and the docs should not imply that it is.

## 4. What this does not solve

Stated up front, because the failure modes are the interesting part of the design.

| Limit | Consequence |
|---|---|
| Jev has no vision | Image-derived fields are generative, drafted by the LLM, adjudicated only against declared criteria |
| Enums cap at 255 options | Larger sets must be narrowed by code first, or the field becomes generative |
| Integer ranges cap at 2–10 levels | Wider numeric ranges must be re-modelled as an ordinal rubric or bucketed |
| Numbers must be bounded 0–1 to map onto `noul` | Other numeric ranges are rescaled by the library, or refused |
| **Arrays have unbounded cardinality** | The hard case. See below. |
| Jev is not a fact-checker | Adjudication is only as good as the declared criteria |
| `anyOf` / `oneOf` / `$ref` | Resolved by the compiler where possible; refused loudly where not |

**Arrays.** Cardinality is itself an unbounded decision, so it cannot be handed to Jev directly. Jevson takes the explicit route: a declared maximum cardinality, then one `noul` per slot asking whether an *n*th item is warranted, then the item's own fields resolved by the rules above. Unbounded lists are refused rather than approximated. This is a real restriction and the docs should lead with it.

**Refusal over invention.** Any schema feature the compiler cannot map is reported before a single API call is made, with the offending JSON pointers. A library in this position must fail at compile time or it is worthless — the whole value proposition is that the output cannot be wrong.

## 5. Prior art, and what is actually new

The space is already occupied. All of it is early-stage, and none of it does what is described above.

| Project | What it does | Relationship |
|---|---|---|
| [`Kiln-AI/jev_jsonschema`](https://github.com/Kiln-AI/jev_jsonschema) | JSON Schema → Jev questions → JSON. Refuses free-form strings, arrays, objects, `anyOf`/`oneOf`/`$ref`. | Closest existing work, and effectively Jevson's **Mode A**. No LLM in the loop; free-form fields are simply out of scope. |
| [`doronp/jevc`](https://github.com/doronp/jevc) | Transpiles prompts and JSON Schemas into Jev decision programs. | Replaces the prompt; does not keep a generative model. |
| [`alexwestco/llm-to-jev`](https://github.com/alexwestco/llm-to-jev) | Classifies prompts as fully / partly / not convertible to Jev primitives. | A useful analysis step, not a runtime. |
| [`eortizs/jev-json-builder`](https://github.com/eortizs/jev-json-builder) | Express middleware producing typed payloads from natural language via Jev. | Same schema-first shape, JS ecosystem. |
| [`0xjba/jev-swap`](https://github.com/0xjba/jev-swap) | Finds LLM calls that are really decisions and costs out the swap. | Adoption tooling. |
| [`nokia-applied-research/AnyJev`](https://github.com/nokia-applied-research/AnyJev), [`kikoncuo/jevfire`](https://github.com/kikoncuo/jevfire) | Jev-style constrained decisions over other models. | Candidate backends for a vendor-independent Jevson. |

Every one of them runs *schema → Jev* and drops the generative model. Jevson's contribution is the hybrid: **keep the LLM for what only it can do, and put Jev on the commit path for everything it touches.** That is the case nobody has built, and it is the case that actually arises in production, where real schemas mix an enum, a score, and a paragraph of prose.

Being differentiated is not the same as being novel. The claim to make publicly is "handles mixed schemas that schema-first converters refuse," not "first of its kind."

## 6. Why Asterion needs this

Jevson is not a detour. It is required at three points in the engine, and building it separately keeps the engine's dependency surface clean.

- **Layer 1 → 2 → 3 boundaries** (SSOT §7). Every handoff between layers is a typed payload. A malformed payload at a layer boundary is an unattributable simulation failure.
- **The execution bus** (SSOT §7.5). Generated content for a trial action must be *validated against the trial's schema* before it enters a simulation. That validator is Jevson.
- **Trial action spaces** (SSOT §6.2). A trial's declared action space is exactly a `choice` over options with criteria — the same compilation step Jevson's schema compiler performs.

Build it because the engine needs it. Publish it because publishing costs almost nothing once it exists.

## 7. Proposed API

Python first, minimal dependencies, matching the existing ecosystem.

```python
from jevson import Jevson, compile_schema

# compile-time: fails loudly on unmappable schema features
plan = compile_schema(schema)          # -> FieldPlan | CompileError with JSON pointers
print(plan.decidable, plan.generative, plan.refused)

jevson = Jevson(jev_key=..., llm=...)

# Mode A — fully decidable schema, no LLM involved
result = jevson.extract(plan, state=document)

# Mode B — mixed schema, LLM forced through the commit tool
result = jevson.build(plan, task="Summarise this ticket and triage it", state=document)

result.value          # dict, guaranteed to validate against the original schema
result.confidence     # per-field confidence from Jev
result.rejections     # adjudication history for generative fields
result.cost           # Jev questions, LLM tokens, retries
```

Design commitments: the schema compiler is usable standalone and has no network dependency; the LLM is injected rather than assumed; Jev is reachable through a backend interface so `AnyJev`-style implementations can be substituted; nothing is logged by default.

## 8. Open decisions

- Array cardinality: fixed maximum, a `noul` per slot, or refuse arrays entirely in v0.
- Whether `evidence` for decidable fields should be LLM-supplied at all, or whether the state should simply be passed whole to Jev and the LLM skipped for those fields (cheaper, but loses the LLM's ability to locate the relevant passage in a long document).
- Retry budget per generative field, and whether to escalate a repeatedly failing field to a typed `null` with a reason instead of raising.
- Whether to batch all decidable fields into one Jev call at plan time, or per commit round. Batching is close to free on latency, so the default should probably be one call.
- Whether the generated skill artifact ships as a prompt string, an Anthropic skill, or both.
- Licence. MIT matches the neighbours.
- Whether v0 supports a JS port or stays Python-only.
