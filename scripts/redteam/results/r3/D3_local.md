# Red-team round 3: local checks of Revision 5 (D3)

Scope: the technical claims that Revision 5 of `DESIGN.md` introduced (§3.5, §5.6, §5.9, §6.3, §8, §8.4) and PLAN's `pydantic ≥ 2.12` pin. Every verdict below comes from a script run or a cited document. No design docs were edited and the Jev API was not called.

Scripts are in `scripts/redteam/`. Their outputs are in `scripts/redteam/results/r3/outputs/`.
Environment: host Python 3.11.7; Python 3.13.15 and 3.15.0rc2 in Docker; Node v24.10.0; httpx 0.28.1; pydantic 2.12.0, 2.13.5 (latest on PyPI) and, for contrast, 2.8.2, 2.10.6 and 2.11.10; jsonschema 4.26.0.

| # | claim | verdict |
|---|---|---|
| 1 | sync `resolve()` on a private loop, one `AsyncClient`, per-key shared limiter (§8) | **REFUTED as written**; buildable with the fix below |
| 2 | UAX #29 from a vendored ~9 KB table, no dependency (§5.9) | **CONFIRMED** (the table is smaller than claimed), with a caveat about testing |
| 3 | RFC 8785 keys reproducible in any language (§8.4) | **CONFIRMED** with library choice and edge cases pinned |
| 4 | Normalisation table vs Pydantic's `mode="validation"` output (§3.5) | **PARTIAL**: 4 rows need rewording, 1 row is missing, and 2 final-validation divergences exist |
| 5 | Absent/null table (§5.6) | **PARTIAL**: row 1 loses a declared non-null default |
| 6 | `{value: string}` fits every provider's subset (§6.3) | **PARTIAL**: Gemini `parameters` has no `additionalProperties` |
| 7 | pydantic ≥ 2.12 pin | **CONFIRMED**: 2.12.0 output is byte-identical to 2.13.5; 2.11 and earlier differ |

---

## 1. Sync-over-async buildability (DESIGN §8)

**Claim.** "All are async; the synchronous `resolve()` runs them on a private event loop and refuses to run inside an already-running loop … The backend owns one `httpx.AsyncClient`. The rate limiter is per API key, shared across every `JevBackend` in the process through a registry."

**Script.** `check_r3_sync_over_async.py` uses a real local HTTP/1.1 keep-alive server. Outputs: `check_r3_sync_over_async.txt` (Python 3.11) and `check_r3_sync_over_async.py313.txt` (Python 3.13). Both versions give the same verdicts.

**Results**

- **(a) One `AsyncClient` across `asyncio.run()` calls.**
  - The first call returns 200. The second fails with `RuntimeError: Event loop is closed`. The third succeeds only because the dead pooled connection was dropped.
  - With `new_event_loop()` and the loop left open, the second call fails with `RuntimeError: <asyncio.locks.Event …> is bound to a different event loop`.
  - After two threads had used one client, every later `asyncio.run` call failed.
  - A client used by the sync path also fails when the caller's `aresolve()` reuses it on its own loop.
- **(b) Limiter built on asyncio primitives, shared across loops.**
  - Sequential use without contention works.
  - After contention in loop 1, `Semaphore(2)` in loop 2 raises `bound to a different event loop`.
  - Contention across two threads (two loops) gives a **lost wakeup** for both `Lock` and `Semaphore(1)`. The waiter was still blocked after 5 s although the holder released after 0.30 s. With a 3 s timeout, 3.11 returned at 3.00 s and 3.13 raised `TimeoutError`.
- **(c) Sync call inside a running loop.** `asyncio.run` raises "cannot be called from a running event loop", and `run_until_complete` raises "Cannot run the event loop while another loop is running". The refusal is necessary for any design based on `asyncio.run`.
- **(d) Designs that work.**
  - **d1, library-owned loop thread** (`run_coroutine_threadsafe`): 3 sequential sync calls and 4 threads × 3 sync calls all used one client and all returned 200. Called from inside a running loop it also worked, but it blocks the caller's loop.
  - **d2, one client per running loop** (a `WeakKeyDictionary`): 3 × `asyncio.run` all returned 200. Clients left on dead loops need an explicit `aclose`.
  - **d3, token bucket guarded by `threading.Lock`, waiting with `asyncio.sleep`:** 70 acquisitions from 5 loops in 5 threads, at a limit of 20/s with burst 5.
    - Elapsed time was 3.25 s, the theoretical minimum.
    - The effective rate was 20.0/s.
    - The busiest 1 s window held 24 acquisitions, under the bound of 25.

**Unbuildable sentences**

- "runs them on a private event loop", read as a new loop per call, combined with "The backend owns one `httpx.AsyncClient`": the second call fails.
- "shared … through a registry", if built from asyncio primitives: it fails across loops and loses wakeups across threads.
- There is also an unstated consequence: caller-supplied async `LLM` and `Extractor` objects run on whichever loop `resolve()` uses. An SDK client the caller created on their own loop fails in the same way as in (a).

**Fix text (§8)**

> All protocols are async. `resolve()` submits `aresolve()` to one library-owned event loop running in a daemon thread, created lazily once per process, and blocks on the result. When called from a thread whose event loop is running, it raises `RuntimeError` naming `aresolve()`, because blocking there would stall the caller's loop. Loop-bound resources are created lazily per event loop and never shared across loops: `JevBackend` keeps one `httpx.AsyncClient` per running loop (the sync path always uses the library loop, so it reuses one client), and `Jevson.aclose()` / `close()` releases them. Caller-supplied async protocols run on the loop that runs the resolve; under `resolve()` that is the library loop. The per-key rate limiter holds no asyncio objects: it is a token bucket guarded by `threading.Lock`, whose waiters sleep with `asyncio.sleep` in their own loop.

PLAN Phase 3 exit criteria should add three tests:

- two sequential `resolve()` calls on one backend;
- `resolve()` from 4 threads;
- one limiter shared by `resolve()` and `aresolve()` under contention.

## 2. UAX #29 vendored table (DESIGN §5.9)

**Claim.** "vendors a generated boundary table (~9 KB) rather than adding a dependency"; tested against `GraphemeBreakTest.txt`.

**Script.** `check_r3_grapheme_table.py <ucd> <version>`, run on Unicode 15.1.0, 16.0.0 and 17.0.0. Inputs are `GraphemeBreakProperty.txt`, `emoji-data.txt` (Extended_Pictographic) and `DerivedCoreProperties.txt` (InCB) from unicode.org. Generated files are in `grapheme_gen_<v>/`. Also run: `check_r3_uniseg_conformance.py` and `check_r3_py315_graphemes.txt`.

**Table size, conformance, and cross-checks by Unicode version**

| Unicode | classes / ranges | Python literal | packed | packed + zlib | embedded .py (base85) | GraphemeBreakTest |
|---|---|---|---|---|---|---|
| 15.1 | 18 / 1,955 | 21,362 B | 3,979 B | 1,228 B | 1,917 B | 1187/1187 |
| 16.0 | 18 / 1,917 | 21,036 B | 3,905 B | 1,136 B | 1,802 B | 1093/1093 |
| 17.0 | 18 / 2,168 | 23,761 B | 4,409 B | 1,344 B | 2,062 B | 766/766 |

- **Runtime code:** 47 non-blank lines (2.9 KB) using only `bisect`, `zlib` and `base64`. The generator is 45 lines.
- **Cross-checks:**
  - Against `uniseg` (Unicode 16.0): 20,000/20,000 random strings agree at 16.0.
  - Against `regex` `\X`: 20,000/20,000 agree at 17.0, so `regex` 2026.9.29 uses Unicode 17.
  - Python 3.15.0rc2: `unicodedata.unidata_version` is 17.0.0, and `iter_graphemes` passes 766/766 of the 17.0 test.
- **Testing caveat:** my first segmenter let ExtPict ZWJ Extend ZWJ ExtPict join (a GB11 state bug). It still **passed every line of the conformance file at all three versions**. A targeted probe and `uniseg` caught it. Passing `GraphemeBreakTest.txt` is necessary but not sufficient.
- **`uniseg` as an alternative:**
  - 0.10.1, MIT, released 2026-01-09, Unicode 16.0.
  - Passes 15.1 and 16.0, and fails 9/766 lines at 17.0.
  - The wheel is 8.18 MB, because 10 MB of docs are installed.

**Verdict: CONFIRMED.** A vendored table with no dependency is realistic. It is about 2–4 KB, not about 9 KB.

**Fix text (§5.9)**

> … vendors a generated boundary table (~2 KB compressed, ~50 lines of runtime code) **at Unicode 17.0, the version of Python 3.15's `unicodedata`**, so the table can be dropped for `unicodedata.iter_graphemes` when 3.15 is the floor. Conformance is `GraphemeBreakTest.txt` **plus a differential test against `regex` `\X` at the same Unicode version**, because the conformance file does not exercise every rule state.

Also state that `unicodedata` (used for NFC in the normaliser) is Unicode 14.0 on 3.11. `Result.versions` should therefore record both versions.

## 3. RFC 8785 canonical JSON (DESIGN §8.4)

**Script.** `check_r3_jcs_crosslang.py` together with `check_r3_jcs_crosslang.mjs`. Vectors are in `check_r3_jcs_vectors.json`.

**Implementations**

| language | package | licence | status |
|---|---|---|---|
| Python | `rfc8785` 0.1.4 (Trail of Bits) | Apache-2.0 | repo pushed 2026-09-28 |
| Python | `jcs` 0.2.1 | Apache-2.0 | last release 2022 |
| JS | `canonicalize` 5.1.0 (erdtman) | Apache-2.0 | modified 2026-09-18 |
| JS | `json-canonicalize` 3.0.1 | MIT | — |

`canonicaljson` (Matrix) is **not** RFC 8785. There is no npm package named `rfc8785` (404).

**Results**

- **Realistic request** (model id; unicode source with NFC and NFD text, emoji ZWJ sequences, U+2028 and control characters; question keys whose UTF-16 order differs from code-point order):
  - `rfc8785`, `jcs`, `canonicalize` and `json-canonicalize` give the identical SHA-256 (`87ac3c20…`).
  - `canonicaljson` and a naive `json.dumps(sort_keys=True)` differ, because they sort 😀 after U+FB01.
- **Integer-hundredths response:** all six outputs are identical.
- **Float edge cases** (1e21, −0, 5e-324): the four RFC 8785 implementations agree; the naive dump differs.
- **2⁵³+1:** `rfc8785` raises `IntegerDomainError`, while `jcs` and JS silently round it to …992.
- **Lone surrogate:** both Python libraries raise.

**Verdict: CONFIRMED.**

**Fix text (§8.4):** "…canonicalised with `rfc8785` (Python) / `canonicalize` (JS). A request that cannot be canonicalised (an integer beyond ±2⁵³, a lone surrogate) is not cached, and this is counted. The probabilities are *stored values*, not part of the key; the key is reproducible because it contains only strings and small integers."

## 4. Pydantic validation-mode schema vs the normalisation table (DESIGN §3.5)

**Script.** `check_r3_pydantic_rows.py` covers 20 cases with both validation and serialization modes. Outputs: `check_r3_pydantic_rows_<ver>.{json,txt}`.

| row / case | emitted (2.12.0 = 2.13.5) | table as written holds? |
|---|---|---|
| Decimal | validation: `anyOf [{type:number}, {type:string, pattern:…}]`; serialization: `{type:string, pattern}` | yes |
| `Optional[Decimal]` | `anyOf [number, string+pattern, null]`, a flat 3-branch union | **no**: it matches neither the Decimal row nor the `[T, null]` row. Remove the null branch first |
| Decimal `gt`, `max_digits`, `decimal_places` | `exclusiveMinimum` only on the number branch; digits only in the string pattern | **no**: after "→ number" these constraints are lost (see 4b) |
| single-member Enum | `$ref → $defs {enum:["only"], type:string}`, **not `const`** | only after inlining |
| single Literal | `{const:"x", type:string}` | yes |
| flat `allOf` | **Pydantic ≥ 2.10 emits no `allOf` in any of the 20 cases**; 2.8.2 wraps `$ref` in `allOf` whenever siblings exist | the row serves only raw JSON Schema |
| `$ref` + siblings | `{"$ref":…, "description"/"default"/"x-jevson": …}` | inlining must **merge siblings** |
| `Field(json_schema_extra={"x-jevson":…})` on a submodel, Enum, `Optional[Sub]`, `list[Sub]`, or discriminated union | always on the **property**, beside `$ref`, `anyOf`, `oneOf+discriminator` or `items`; never inside `$defs`. Two fields of one def carry different `x-jevson` | yes, if inlining merges siblings per instance |
| `model_config json_schema_extra` | lands **inside `$defs/Model`** | the table does not say whether this is allowed or how it merges with the property-level declaration |
| `gt`/`lt`/`multiple_of` | numeric `exclusiveMinimum` / `exclusiveMaximum`, `multipleOf: 0.01` | yes, but see 4c |
| discriminated union | `oneOf [$ref…]` + `discriminator {propertyName, mapping}` | **missing row** (PLAN Phase 6 relies on it); `discriminator` is OpenAPI, and `jsonschema` ignores it |
| plain union | `anyOf [$ref, $ref]` | covered by §3.2 |
| `Optional[str] = "x"` | `anyOf [string, null]`, `default: "x"` | see check 5 |

**4b.** Decimal with `decimal_places=2` (`check_r3_absent_null.py`, section a): `12.345` and `"12.345"` are **both valid under `jsonschema` but rejected by `model_validate`**. Pydantic's pattern `(?:\d{0,8}|…)` is unanchored in its first alternative. So `satisfies_schema=True` can hold for a value the caller's model rejects.

**4c.** Float `multiple_of=0.01`: over all cent values from 0.00 to 1000.00, **`jsonschema` rejects 11,426 of 100,001; Pydantic rejects 0**. Examples are 0.07, 19.99 and 4.35. `jsonschema` uses float division. This produces false `satisfies_schema=False`.

**Fix text (§3.5)**

- Add these rows:
  - "`$ref` with sibling keywords: inlined per instance, with siblings (`description`, `default`, `x-jevson`) merged over the target; a sibling that conflicts with the target refuses."
  - "`oneOf` + `discriminator` (Pydantic discriminated union): a union whose branches are distinguished by the `const` at `propertyName`."
  - "Remove `{type:null}` from any `anyOf` before matching the other rows."
  - "`x-jevson` inside a `$defs` model applies to every instance; a property-level `x-jevson` overrides it key by key."
- Reword the Decimal row: "`anyOf [number, string]` from Pydantic `Decimal` → number for mapping. The class F parse emits the **string** form, and constraints are checked by the model."
- Reword the single-member Enum row: "single-member `Enum` (a one-value `enum` after inlining)".
- Add to §6: "For Pydantic input, `satisfies_schema` also requires `Model.model_validate(value)` to succeed. `multipleOf` is checked in decimal arithmetic."

## 5. Absent/null semantics (DESIGN §5.6)

**Script.** `check_r3_absent_null.py`. Validation uses Draft 2020-12 against `model_json_schema(mode="validation")` plus `model_validate`.

| model | §5.6 output | jsonschema | model_validate | note |
|---|---|---|---|---|
| (i) `Optional[str] = None` | `{"f": null}` | valid | f=None | ok |
| (ii) `Optional[str]` required | `{"f": null}` | valid | f=None | ok |
| (iii) `str = "default"` | `{}` | valid | f='default' | ok; the default is applied by the consumer, not written into `.value` |
| (iv) `str` required | `{}` | invalid | missing | correct: unresolved |
| (v) `Optional[str] = "x"` | `{"f": null}` | valid | **f=None: DEFAULT LOST** | the alternative rule (omit) gives f='x' |

No row produces an invalid object, but row 1 overrides a declared non-null default with an explicit `null`.

**Fix text (§5.6):**

| field | abstention yields |
|---|---|
| not required (has a default, nullable or not) | key omitted, `Result.absent`; the consumer's default applies |
| required, nullable | `null`, `Result.absent` |
| required, not nullable | key omitted, `Result.unresolved(abstained)` |

Optionally add: "`.value` never writes schema defaults; `Result.absent` names them."

## 6. Generative tool schema `{value: string}` (DESIGN §6.3)

**Script.** `check_r3_tool_schema_providers.py`, run against the live Gemini v1beta discovery document (revision 20260928). Output: `check_r3_tool_schema_providers.txt`.

**Provider requirements**

- **OpenAI**, strict function calling (developers.openai.com/api/docs/guides/function-calling): "additionalProperties must be set to false for each object in the parameters"; "All fields in properties must be marked as required."
- **Anthropic**, strict tool use (platform.claude.com/docs/en/build-with-claude/structured-outputs): `required` and `additionalProperties` "must be set to `false` for objects". `minLength`, `maxLength` and `pattern` are not supported.
- **Gemini** `FunctionDeclaration.parameters`: an OpenAPI Schema whose fields exclude `additionalProperties`, with the type enum in upper case (`STRING`, `OBJECT`). `parametersJsonSchema` accepts full JSON Schema, including `additionalProperties:false`, and "is mutually exclusive with `parameters`". The `google-genai` SDK is reported to reject `additionalProperties` client-side (googleapis/python-genai#1815).

**Result.** The strict rendering `{type:object, properties:{value:{type:string}}, required:[value], additionalProperties:false}` uses one keyword that is not in Gemini's `parameters` Schema: `additionalProperties`.

**Verdict: PARTIAL.** The shape is in every subset, but one literal schema does not fit all providers.

**Fix text (§6.3):** "…a one-field tool schema `{value: string}`, required, whose shape every major provider supports. The `LLM` adapter renders it per provider: `additionalProperties:false` for OpenAI and Anthropic strict modes, and `parametersJsonSchema` or the OpenAPI subset for Gemini. `max_draft_chars` is enforced after the call, never as `maxLength` in the tool schema, which Anthropic strict mode does not support."

## 7. Pydantic pin (≥ 2.12)

**Script.** `check_r3_pydantic_rows.py` under 2.8.2, 2.10.6, 2.11.10, 2.12.0 and 2.13.5.

- The 2.12.0 and 2.13.5 JSON outputs are **byte-identical** across all 20 cases (validation and serialization). That covers `x-jevson` placement, the discriminator/`oneOf`, and the Decimal form.
- 2.10.6 and 2.11.10 emit Decimal as `anyOf [number, {type:string}]` with **no pattern**.
- 2.8.2 wraps every `$ref` that has siblings in `allOf: [{$ref}]`.

**Verdict: CONFIRMED.** The floor is justified. The matcher should still recognise Decimal structurally rather than by its pattern text, and CI should test the floor (2.12.0) and the latest release.
