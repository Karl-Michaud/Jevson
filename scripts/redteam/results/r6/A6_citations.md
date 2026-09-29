# A6: Citation audit of Revision 8 (red-team round 6)

**Scope.** `DESIGN.md` (813 lines), `PLAN.md` (911), `README.md` (49), `docs/REDTEAM.md` (123), `results/r5/*`. No design doc was edited. There is no git history, so the changed text was found from the DESIGN §13 "Revision 8" table, from each A5 fix text, and from grepping the changed tags (P19, P22, P23, L17, L18, L19, L22, V-confidence).

**Method.**
- P23 was recomputed from `results/r5/raw/r5_sum_largek.json`.
- L22 was re-run locally (`check_r5_weakkey_clients.py`, Python 3.11.7, httpx 0.28.1). The output is saved as `results/r6/check_r5_weakkey_clients.rerun.txt`.
- P19 was recomputed from `results/r3/raw/r3_mixed_desc.json`.
- V-confidence was re-read in `jevdocs/confidence.md`.
- Tags were counted with a regex over `**[...]**` groups.
- Line refs: `D` = DESIGN.md, `P` = PLAN.md, `RT` = docs/REDTEAM.md.

**Key scan.** 231 files were scanned (excluding `.env` and `.git`), and the key was found in **0**. Only the count was printed.

## Summary

- **Tag counts.** DESIGN has 223 tag elements and PLAN has 117. Three are example tags, which leaves **337 claim tags**. That is 8 more than Revision 7: P23 ×2, L22 ×3, L18 at D243, P22 at D398, and one more.
- **Definitions.** All 66 tags used are defined in RT, and every named script exists. L5, L6 and L8 are defined but unused, which is harmless.

| verdict | count | instances |
|---|---|---|
| SUPPORTED | 336 | — |
| OVERSTATED | 1 | D398 P22 (new) |
| WRONG / UNSUPPORTED | 0 | — |

**0 blockers, 0 majors. CONVERGED: yes.**

## 1. Changed tags

| tag / where | recomputed | verdict |
|---|---|---|
| **P23**: D71, D737, RT41 | K = 51: 10 answers, max dev 0, argmax = `choice` 10/10, correct 10/10. K = 255: the same. Option counts are K − 1 addresses plus `none_of_these`, which is correct. Request count 20 matches `request_count.txt` and RT16 | **S**. Caveat (minor): the raw file keeps only `dev`, not `probabilities`, so the sums cannot be re-derived and max p is unknown. On easy one-correct questions the mass is likely concentrated, and rounding deviation arises only when mass is spread. "Confirmed" (D737) holds for the tested regime only. Fix: save `probabilities` in the raw file; D737 "confirmed on 20 easy answers at K = 51 and 255 (0 deviation)" |
| **L22**: D540, D734, P374, RT72 | The re-run reproduces the claim: no-close 5/5 survive, aclose 0/5 | **S**. Nit: a client that was created but never made a request is freed (0/5), so "open client" should read "a client that has made a request". **The output was not saved under `results/r5/`** (hygiene, minor), and RT48 names no round-5 location |
| **P19**: RT38, D318, D720, P869 | UA_MIX: abstain 47/48, 1 rep-distractor, mean p on context options 0.098 (BARE 0.0). Repeated-text answers MIX 48/48, CTX 47/48, BARE 20/48; unique answers 48/48 | **S**. P868 → P869 now matches D720 (A5 O fixed). Nit: UA_CTX also committed 1/48, so the effect is not specific to mixing |
| **P22**: D489, D757, RT42 | Wording is scoped to the `none_of_these` key, with the 120 P5 choices excluded (2.5% with them). This is the A5 fix | **S** |
| **P22**: D398 (new, membership ties) | P22 measures multi-option candidate *choices*, but membership is a per-candidate *noul* (D221, D518). The closest evidence is P12: ~1.1% of bool answers fall in 0.45–0.55. Membership nouls themselves are unmeasured | **O, minor.** The qualitative "long arrays will often be incomplete" still holds at 1–3% per mention. Fix: "with ~1.1% of pilot yes/no answers and 2.6% of candidate choices inside the margin **[P12, P22]** (membership nouls not measured), long arrays…" |
| **L17 + P23**: D71 sum-tolerance sentence | "at most 1 observed at K ≤ 11" is confirmed by a re-run of `check_r5_sum_tolerance_largek.py` (n = 4,794, max 1). The "0 across 20 at K = 51/255" is as above | **S**. Nit: the bound "at most ⌈K/2⌉" is loose, since integer deviation ≤ ⌊K/2⌋. It remains true |
| **V-confidence**: D70, RT88 | `confidence.md:138`: "(3 × largest probability − 1) / 2 to approximate confidence for three options" | **S**. "Written in terms of the option count" is a fair reading. Carried nit: the "also call it calibrated" aside is V-cookbooks |
| **L19**: P274 | "real GB11 bug in a first draft" | **S** (A5 O fixed) |
| **L18**: D243 | x-jevson placed beside `$ref` on the property | **S** (A5 U1 fixed) |

No untagged new factual claims were found in the Revision 8 text. The object-absence, defaulted-leaf, fork, close, extractor, `locale` and timeout rules are design decisions. **README is unchanged and states nothing DESIGN doesn't.**

## 2. A5 traceability

**The five overstated items are all addressed:**
- D71 L17;
- D489 P22;
- D742 (now D757) P22;
- P274 L19;
- P868 (now P869) P19.

**Also addressed:**
- A5 U1 (D243);
- RT38, RT41 (now RT42) and RT86 (now RT88);
- the PLAN residues P418, P466 (now P467), P473 (now P474), P315 and P438 (now P439, the paired interval, E4 m14).

**Not addressed and not recorded as declined (all minor):**
- RT32 P13: name the rounding convention for run 2 (5/60 half-even, 6/60 half-up).
- RT68 L17: add "observed at 1–11 options".
- RT73 L21: "silently rounded elsewhere" should be "by `jcs` and both JS packages".
- `r4/raw/` is still empty.
- The `28/60` nit at P203, P477 and P833.
- `Agents/CLAUDE.md:60` (Infisical vs `.env`), which is outside Jevson.

## 3. RT hygiene (minor)

- **Ordering.**
  - P23 precedes P22, and L22 precedes L21.
  - The round-log row for round 5 precedes round 4.
- **Stale range.** P150 "[P1–P22]" should be [P1–P23].
- **Missing output.** The L22 output file is missing from `results/r5/`.

## Verdict

- 1 new overstated tag (minor).
- 4 carried RT and PLAN nits that were neither fixed nor declined.
- Hygiene items only.

**No blocker, no major. CONVERGED: yes.**
