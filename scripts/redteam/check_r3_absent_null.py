"""check_r3_absent_null.py — DESIGN §5.6 absent/null table vs JSON Schema and Pydantic, plus
two "kept for final validation" divergences from DESIGN §3.5 (Decimal, multipleOf).

Claim (DESIGN §5.6, Rev 5): on abstention,
    nullable (Optional[T], with or without a default) -> null, Result.absent
    optional, not nullable                           -> key omitted, Result.absent
    required, not nullable                           -> key omitted, Result.unresolved
and satisfies_schema means ".value validates against the original schema".
Method: models (i) Optional[str]=None, (ii) Optional[str] required, (iii) str="default",
(iv) str required, (v) Optional[str]="x". Apply the table; validate the produced object with
jsonschema (Draft 2020-12, against model_json_schema(mode="validation")) and with
Model.model_validate; report what value the caller finally sees for the field and whether the
declared default survives. Compare with the alternative rule "not required -> omit; required
and nullable -> null". Then: (a) Decimal(decimal_places=2) with 12.345 emitted as number;
(b) float multiple_of=0.01 with common money values — jsonschema vs Pydantic verdicts.
Output: results/r3/outputs/check_r3_absent_null.txt
"""
import json
from decimal import Decimal
from typing import Optional
import pydantic, jsonschema
from pydantic import BaseModel, Field, ValidationError

OUT = []
def log(*a):
    s = " ".join(str(x) for x in a); print(s); OUT.append(s)
log(f"pydantic {pydantic.VERSION}, jsonschema {jsonschema.__version__ if hasattr(jsonschema,'__version__') else ''}")

class M1(BaseModel): f: Optional[str] = None
class M2(BaseModel): f: Optional[str]
class M3(BaseModel): f: str = "default"
class M4(BaseModel): f: str
class M5(BaseModel): f: Optional[str] = "x"
rows = [("(i) Optional[str] = None", M1), ("(ii) Optional[str] required", M2), ("(iii) str = 'default'", M3),
        ("(iv) str required", M4), ("(v) Optional[str] = 'x'", M5)]

def nullable(p): return any(b.get("type") == "null" for b in p.get("anyOf", [])) or p.get("type") == "null" or "null" in (p.get("type") if isinstance(p.get("type"), list) else [])
def design_rule(schema):
    p = schema["properties"]["f"]; req = "f" in schema.get("required", [])
    if nullable(p): return {"f": None}, "null -> absent"
    if not req: return {}, "omitted -> absent"
    return {}, "omitted -> unresolved"
def alt_rule(schema):
    p = schema["properties"]["f"]; req = "f" in schema.get("required", [])
    if not req: return {}, "omitted -> absent"
    if nullable(p): return {"f": None}, "null -> absent"
    return {}, "omitted -> unresolved"

def check(m, obj):
    s = m.model_json_schema(mode="validation")
    js = not list(jsonschema.Draft202012Validator(s).iter_errors(obj))
    try: pv = m.model_validate(obj); pyd = f"ok, f={pv.f!r}"
    except ValidationError as e: pyd = "INVALID (" + e.errors()[0]["type"] + ")"
    return js, pyd

for label, m in rows:
    s = m.model_json_schema(mode="validation")
    log(f"\n{label}: schema f={json.dumps(s['properties']['f'])} required={s.get('required', [])}")
    for rname, rule in (("DESIGN §5.6", design_rule), ("alternative", alt_rule)):
        obj, what = rule(s); js, pyd = check(m, obj)
        dflt = s["properties"]["f"].get("default", "<none>")
        lost = ("DEFAULT LOST (declared %r, caller gets None)" % dflt) if (obj == {"f": None} and dflt not in (None, "<none>")) else ""
        log(f"  {rname:12s} -> {json.dumps(obj):12s} [{what}]  jsonschema valid={js}; model_validate: {pyd} {lost}")

log("\n== (a) Decimal(decimal_places=2): class F parse emitted as number vs string ==")
class D(BaseModel): total: Decimal = Field(max_digits=10, decimal_places=2)
sd = D.model_json_schema(mode="validation")
for v in (1204.5, "1204.50", 12.345, "12.345", 0.1):
    js = not list(jsonschema.Draft202012Validator(sd).iter_errors({"total": v}))
    try: pv = D.model_validate({"total": v}); pyd = f"ok -> {pv.total!r}"
    except ValidationError as e: pyd = "INVALID (" + e.errors()[0]["type"] + ")"
    log(f"  total={v!r:10}  jsonschema valid={js}; model_validate: {pyd}")
log("  (json.dumps of the number branch: ", json.dumps({"total": 1204.50}), ")")

log("\n== (b) float multiple_of=0.01 ('kept for final validation only') ==")
class P(BaseModel): price: float = Field(multiple_of=0.01)
sp = P.model_json_schema(mode="validation")
vals = [0.07, 0.29, 1.1, 19.99, 1204.5, 0.57, 4.35, 2.675]
bad_js = 0
for v in vals:
    js = not list(jsonschema.Draft202012Validator(sp).iter_errors({"price": v}))
    try: P.model_validate({"price": v}); pyd = "ok"
    except ValidationError as e: pyd = "INVALID"
    bad_js += (not js)
    log(f"  price={v:<8} jsonschema valid={js}; pydantic {pyd}")
n = 0; nbad_js = 0; nbad_py = 0
for cents in range(0, 100001):
    v = cents / 100; n += 1
    if list(jsonschema.Draft202012Validator(sp).iter_errors({"price": v})): nbad_js += 1
    try: P.model_validate({"price": v})
    except ValidationError: nbad_py += 1
log(f"  all cents 0.00..1000.00 ({n} values): jsonschema rejects {nbad_js}, pydantic rejects {nbad_py}")
open("/Users/karlosins/project-asterion/Jevson/scripts/redteam/results/r3/outputs/check_r3_absent_null.txt", "w").write("\n".join(OUT) + "\n")
