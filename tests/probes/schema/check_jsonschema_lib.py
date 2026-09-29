"""Claim: PLAN Phase 8 dependency `jsonschema` validates "against the original schema" (DESIGN §3, §6);
pydantic v2 emits JSON Schema draft 2020-12. Which drafts does the installed jsonschema support, does
validator_for pick 2020-12 for a schema without $schema, is `format` asserted by default, and are
$ref/$defs from pydantic resolved by the validator?

Method: introspect jsonschema; validate pydantic output; check format behaviour with/without FormatChecker.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
from importlib.metadata import version
import jsonschema
from jsonschema import validators, FormatChecker, Draft202012Validator
from pydantic import BaseModel

print("jsonschema", version("jsonschema"), "| pydantic", version("pydantic"))
print("validators:", sorted(n for n in dir(jsonschema) if n.startswith("Draft") and n.endswith("Validator")))
print("validator_for(schema without $schema) ->", validators.validator_for({}).__name__)

class Addr(BaseModel):
    city: str
class M(BaseModel):
    a: Addr
    email: str
s = M.model_json_schema()
print("pydantic emits $schema key?", "$schema" in s)
v = Draft202012Validator(s)
print("pydantic $ref resolves; invalid instance errors:", [e.message for e in v.iter_errors({"a": {"city": 1}, "email": "x"})])
Draft202012Validator.check_schema(s); print("pydantic schema passes 2020-12 metaschema check")

fs = {"type": "string", "format": "email"}
print("format 'email' on 'not-an-email': default valid =", Draft202012Validator(fs).is_valid("not-an-email"),
      "| with FormatChecker valid =", Draft202012Validator(fs, format_checker=FormatChecker()).is_valid("not-an-email"))
print("jsonschema.validate() default format checking for 'date' 'garbage':", end=" ")
try:
    jsonschema.validate("garbage", {"type": "string", "format": "date"}); print("valid (format NOT asserted)")
except jsonschema.ValidationError as e:
    print("invalid:", e.message)
print("formats checked by bare FormatChecker():", sorted(FormatChecker().checkers)[:40])
