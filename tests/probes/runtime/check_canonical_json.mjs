// check_canonical_json.mjs — Node half of check_canonical_json.py (DESIGN §8.4).
// Canonicalises each vector with `canonicalize` (erdtman, Apache-2.0) and
// `json-canonicalize` (MIT), SHA-256 over UTF-8, prints {impl: {case: hex}} as JSON.
// Note: vectors are read with JSON.parse, so 2**53+1 is already rounded by the parser —
// that is the point of the bigint case.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { createRequire } from "node:module";
const require = createRequire(process.cwd() + "/");
const canonicalize = (await import(require.resolve("canonicalize"))).default;
const { canonicalize: jc } = require("json-canonicalize");
const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
const impls = { "js:canonicalize": canonicalize, "js:json-canonicalize": jc };
const out = {};
for (const [name, f] of Object.entries(impls)) {
  out[name] = {};
  for (const [c, o] of Object.entries(cases)) {
    try { out[name][c] = createHash("sha256").update(Buffer.from(f(o), "utf8")).digest("hex"); }
    catch (e) { out[name][c] = "ERROR " + e.message.slice(0, 80); }
  }
}
console.log(JSON.stringify(out));
