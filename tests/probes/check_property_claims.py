"""Claims: PLAN §4.3 property invariants — "Assembly of a fully resolved graph always validates against the
original schema" and "Cost is monotonic: retries only increase it"; PLAN §3 / Phase 3 determinism
("Same schema, source, and backend produce the same result"; "Same input resolves to the same output").

Method: (1) build 'fully resolved' assemblies in which every decision node has an answer, using values the
design says are legal (verified spans, accepted memberships, score answers), and validate them with
jsonschema against schemas carrying constraints no decision node owns (maxLength, pattern, minItems,
uniqueItems, dependentRequired, format, integer type vs weighted score). (2) model Cost as the §8.1 record
and show wall_clock_by_component differs across two identical runs, so a Result containing it cannot be
byte-identical run to run, and 'monotonic' needs a stated order (componentwise on counters only).
"""
import time
from dataclasses import dataclass, field, astuple
import jsonschema
from jsonschema import Draft202012Validator, FormatChecker

cases = [
    ("verified span vs maxLength", {"type": "object", "properties": {"code": {"type": "string", "maxLength": 5}}},
     {"code": "Dana Whitfield"}),
    ("verified span vs pattern", {"type": "object", "properties": {"email": {"type": "string", "pattern": "^[^@]+@[^@]+$"}}},
     {"email": "dana at acme dot com"}),
    ("membership accepted 1 < minItems 2", {"type": "object", "properties": {"attendees": {"type": "array", "minItems": 2, "items": {"type": "string"}}}},
     {"attendees": ["Dana"]}),
    ("entity split -> duplicates vs uniqueItems", {"type": "object", "properties": {"orgs": {"type": "array", "uniqueItems": True, "items": {"type": "string"}}}},
     {"orgs": ["Acme", "Acme"]}),
    ("cross-field dependentRequired", {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "string"}}, "dependentRequired": {"a": ["b"]}},
     {"a": "x"}),
    ("score weighted value into integer", {"type": "object", "properties": {"rating": {"type": "integer", "minimum": 1, "maximum": 5}}},
     {"rating": 3.2}),
    ("span vs format:date (format asserted only with FormatChecker)", {"type": "object", "properties": {"d": {"type": "string", "format": "date"}}},
     {"d": "March 3rd, 2026"}),
]
for name, schema, inst in cases:
    v1 = Draft202012Validator(schema)
    v2 = Draft202012Validator(schema, format_checker=FormatChecker())
    e1 = [e.message for e in v1.iter_errors(inst)]; e2 = [e.message for e in v2.iter_errors(inst)]
    print(f"{name:55} valid(default)={not e1!s:5} valid(format)={not e2!s:5} {e2[:1]}")

@dataclass
class Cost:
    jev_questions: int = 0; jev_input_tokens: int = 0; llm_input_tokens: int = 0
    llm_output_tokens: int = 0; retries: int = 0
    wall_clock_by_component: dict = field(default_factory=dict)

def run(retry_budget):
    c = Cost(); t0 = time.perf_counter()
    c.jev_questions += 3; c.jev_input_tokens += 900
    for _ in range(retry_budget):
        c.retries += 1; c.jev_questions += 3; c.jev_input_tokens += 900
    sum(range(20000))
    c.wall_clock_by_component["executor"] = time.perf_counter() - t0
    return c
a, b = run(0), run(0)
print("\nidentical runs: counters equal:", astuple(a)[:5] == astuple(b)[:5], "| whole Cost equal:", a == b,
      "| wall clocks:", a.wall_clock_by_component, b.wall_clock_by_component)
r0, r1 = run(0), run(1)
print("retry 0 vs 1 counters componentwise <=:", all(x <= y for x, y in zip(astuple(r0)[:5], astuple(r1)[:5])))
