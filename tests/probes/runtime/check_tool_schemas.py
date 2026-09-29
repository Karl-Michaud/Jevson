"""check_tool_schemas.py — DESIGN §6.3: the one-field tool schema {value: string}
"is inside every provider's supported subset [X1]".

Method: render the schema in the strict form OpenAI and Anthropic require
({type: object, properties: {value: {type: string}}, required: [value], additionalProperties: false})
and check each keyword against Gemini's FunctionDeclaration.parameters Schema object, read from
the live Gemini API discovery document (v1beta), and against parametersJsonSchema.
OpenAI/Anthropic requirements are cited from their docs (see D3_local.md; web fetch 2026-09-29).
Usage: python check_tool_schemas.py <gemini discovery json>
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import json, sys
d = json.load(open(sys.argv[1])); s = d["schemas"]
fields = set(s["Schema"]["properties"])
strict = {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"], "additionalProperties": False}
def keys(o):
    out = set()
    if isinstance(o, dict):
        for k, v in o.items():
            out.add(k)
            if k == "properties": [out.update(keys(x)) for x in v.values()]
    return out
print("discovery revision:", d.get("revision"))
print("Gemini Schema (for FunctionDeclaration.parameters) fields:", sorted(fields))
print("Gemini Schema.type enum:", s["Schema"]["properties"]["type"].get("enum"))
print("strict tool schema keywords:", sorted(keys(strict)))
print("keywords NOT in Gemini `parameters` Schema:", sorted(keys(strict) - fields))
print("parametersJsonSchema:", s["FunctionDeclaration"]["properties"]["parametersJsonSchema"]["description"][:400].replace("\n", " "))
