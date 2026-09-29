"""Claim: PLAN Phase 10 — Python offsets are code points; JS indexes UTF-16. Python half of the
comparison: compute code-point offsets for the same source/targets as check_js_offsets.mjs,
run the node script, and assert the node-computed code-point offsets match Python's while
native UTF-16 indices differ after the first astral character."""
import json, subprocess, pathlib
src = "Paid 👍🏽 to 𝐀cme 東京 José́ — Dana Whitfield"
targets = ["👍🏽", "𝐀cme", "東京", "José́", "Dana Whitfield"]
py = {t: [src.index(t), src.index(t) + len(t)] for t in targets}
for t, (i, j) in py.items():
    u16 = len(src[:i].encode("utf-16-le")) // 2
    print(f"{t!r:18} python_cp=[{i},{j}) utf16_start={u16} differs={u16 != i}")
here = pathlib.Path(__file__).parent
res = subprocess.run(["node", str(here / "check_js_offsets.mjs")], capture_output=True, text=True, check=True)
print(res.stdout)
js = json.loads(res.stdout.strip().splitlines()[-1].split(": ", 1)[1])
print("node code-point offsets == python offsets:", js == py)
