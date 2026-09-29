/**
 * Claim: PLAN Phase 10 — "Python offsets are code points; JavaScript strings index UTF-16 code
 * units, so the port converts explicitly and a fixture with astral-plane characters proves it."
 *
 * Method: run the same source through node, computing the Python-style code point offset
 * (via Array.from / for..of) and the native JS UTF-16 index, and show slice() disagreement.
 * Also check whether combining/BMP content (é, CJK) differs (it should not), and whether a
 * lone-surrogate split is possible in JS but not in Python. Python side is run by the companion
 * check_js_offsets_py.py and the outputs are compared.
 */
const src = "Paid 👍🏽 to 𝐀cme 東京 José́ — Dana Whitfield";
const targets = ["👍🏽", "𝐀cme", "東京", "José́", "Dana Whitfield"];
const cpOf = (s, u16) => Array.from(s.slice(0, u16)).length; // UTF-16 index -> code point index
const u16Of = (s, cp) => Array.from(s).slice(0, cp).join("").length; // code point -> UTF-16
const out = {};
for (const t of targets) {
  const i16 = src.indexOf(t), j16 = i16 + t.length;
  const icp = cpOf(src, i16), jcp = cpOf(src, j16);
  out[t] = [icp, jcp];
  const naive = src.slice(icp, jcp); // using Python offsets directly in JS
  console.log(JSON.stringify(t).padEnd(20), `utf16=[${i16},${j16})`, `codepoint=[${icp},${jcp})`,
    `naive_js_slice_with_py_offsets_ok=${naive === t}`,
    `converted_ok=${src.slice(u16Of(src, icp), u16Of(src, jcp)) === t}`);
}
const lone = "👍".slice(0, 1);
console.log("JS can slice a lone surrogate:", JSON.stringify(lone), "length", lone.length,
  "encodes to UTF-8 as", Buffer.from(lone, "utf8").toString("hex"), "(EF BF BD = U+FFFD replacement)");
console.log("JSON offsets for Python comparison:", JSON.stringify(out));
