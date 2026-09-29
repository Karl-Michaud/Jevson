"""0a: the taxonomy of the sampled schemas (docs/taxonomy.md §5).

Every node of every schema in tests/fixtures/schemas/ is classified by DESIGN §4. The only human judgement is the
recorded annotation of each node (tests/fixtures/schemas/annotations.json): the operation the field needs
(``origin``) and how damaging a wrong-but-valid value would be (``importance``). Everything else in the table is
derived from the origin by the fixed rules below, which restate DESIGN §4, §4.2, §5, §6.3, §10 and PLAN §9.

    uv run python -m tests.phase0.taxonomy      # writes tests/phase0/results/taxonomy.json
"""
from __future__ import annotations

import json
import pathlib
import statistics
import sys
from collections import Counter
from dataclasses import asdict, dataclass

HERE = pathlib.Path(__file__).resolve().parent
SCHEMAS = HERE.parents[0] / "fixtures" / "schemas"
RESULTS = HERE / "results"

D_SPAN_DEP = "after its extract step: one decision level"
LEVEL0 = "none: decided in the first decision level"

# origin -> (class, construct, primitive, option source, none_of_these, dependency, provenance, batching,
#            existing alternatives, existing Jev implementations, v0 candidate)
RULES: dict[str, tuple[str, ...]] = {
    "structure": ("A", "object (structure)", "none", "—", "n/a", "none", "none (assembled by code)", "n/a",
                  "plain code", "n/a", "yes"),
    "caller": ("A", "value supplied by the caller or program", "none", "—", "n/a", "none",
               "none (`decided_by: caller` via `known=`)", "n/a", "plain code", "n/a", "yes"),
    "constant": ("A", "constant", "none", "—", "n/a", "none", "none", "n/a", "plain code", "n/a", "yes"),
    "span": ("D", "string selected verbatim from the source", "choice", "candidate spans", "yes (R1)", D_SPAN_DEP,
             "SOURCE_SPAN", "one keyed call per level, with every other decision of that level",
             "grounding checks: LangExtract, Instructor quote validation [X2]; constrained decoding cannot see provenance [X1]",
             "TypeSafe pre-parsed value extraction cookbook [V-preparsed]; typesafe-playground, jev-extract, jev-reviewer [X3]",
             "yes, if probes 1-3 are not stop (Phase 5)"),
    "span_parse": ("D", "value selected from the source, then parsed (class F on the span)", "choice",
                   "candidate spans (pattern extractors: money, date, number)", "yes (R1)", D_SPAN_DEP,
                   "SOURCE_SPAN (parsed value keeps the span)",
                   "one keyed call per level, with every other decision of that level",
                   "as for a verbatim span, then parsing in plain code",
                   "pre-parsed value extraction cookbook (regex candidates) [V-preparsed]; date-extraction cookbook [V-cookbooks]",
                   "yes, if probes 1-3 are not stop (Phase 5)"),
    "enum": ("C", "enum", "choice", "schema enum", "no (v0; PLAN §9)", LEVEL0, "DECLARED_OPTION",
             "one keyed call per level", "constrained decoding enforces membership but not correctness [X1]",
             "jev_jsonschema choice [X3]", "yes (Phases 2-3)"),
    "bool": ("C", "boolean predicate", "noul", "predicate", "n/a (tie band 0.45-0.55)", LEVEL0, "DECLARED_OPTION",
             "one keyed call per level", "constrained decoding [X1]", "jev_jsonschema noul [X3]", "yes (Phases 2-3)"),
    "ordinal": ("C", "ordinal rating (integer range)", "score", "schema rubric (levels)", "no (v0)", LEVEL0,
                "DECLARED_OPTION", "one keyed call per level", "constrained decoding (integer range) [X1]",
                "jev_jsonschema score [X3]", "yes, when declared `ordinal: true` (Phases 2-3)"),
    "generate": ("E", "free text synthesised by an LLM", "noul per criterion (+ optional score)", "declared criteria",
                 "n/a", "generate step, then criterion nouls: two stages", "none (adjudicated, or listed in `ungated`)",
                 "all criteria of a field in one call; drafts keyed by node id",
                 "an LLM with structured outputs [X1]; per-field scores (Cleanlab TLM, LlamaExtract) [X2]",
                 "citation-check and SDE-cascade cookbooks (claim support, absent-from-source nouls) [V-cookbooks]",
                 "yes (Phase 4)"),
    "classify_free": ("E", "classification with no declared enum (free string as published)",
                      "noul per criterion (+ optional score)", "declared criteria", "n/a",
                      "generate step, then criterion nouls: two stages", "none (adjudicated, or listed in `ungated`)",
                      "as a generated field; declaring an enum would make it class C",
                      "an LLM with structured outputs [X1]; adding an enum to the schema",
                      "none as a free string (jev_jsonschema refuses free strings) [X3]",
                      "yes as class E (Phase 4); class C if the schema declares the options"),
    "compute": ("F", "value computed from other values", "none", "—", "n/a", "after the values it is computed from",
                "none: derived provenance is out of v0 (R9)", "n/a", "plain code", "n/a",
                "no, except parsing one selected span (R9)"),
    "unsupported": ("G", "construct Jevson cannot map (free-form dict, unbounded number with no source, empty enum)",
                    "none", "—", "n/a", "refused at compile time", "none", "n/a", "none",
                    "jev_jsonschema refuses these too [X3]", "no (refused, PLAN §9)"),
    "array_objects": ("G", "array of objects (records)", "none", "—", "n/a", "refused at compile time", "none", "n/a",
                      "an LLM with structured outputs [X1]", "jev-extract (fixed record types, not schema-compiled) [X3]",
                      "no (arrays of objects, PLAN §9)"),
    "array_spans": ("D", "array of source spans (membership)", "noul per candidate",
                    "candidate spans", "n/a (membership noul per candidate)", D_SPAN_DEP,
                    "SOURCE_SPAN per element", "one membership noul per candidate, in one level (R5)",
                    "span extraction: LangExtract, GLiNER [X2]",
                    "jev-span (span NER), jev-extract; entity-alignment cookbook [X3, V-cookbooks]",
                    "yes, if Phase 5 ships (Phase 7), without deduplication: pairwise entity resolution is post-v0 [Z4]"),
    "array_generated": ("G", "list generated by an LLM", "none", "—", "n/a", "refused at compile time", "none", "n/a",
                        "an LLM with structured outputs [X1]", "none", "no (generative lists, DESIGN §10)"),
    "array_caller": ("A", "array supplied by the caller or program", "none", "—", "n/a", "none", "none", "n/a",
                     "plain code", "n/a", "yes"),
}
IMPORTANCE = ("high", "medium", "low")
KIND = {"array_objects": "array", "array_spans": "array", "array_generated": "array", "array_caller": "array",
        "structure": "object"}


@dataclass(frozen=True)
class Row:
    schema: str
    group: str
    pointer: str
    kind: str                 # object | array | leaf
    json_type: str
    origin: str
    cls: str
    construct: str
    primitive: str
    option_source: str
    none_of_these: str
    dependency: str
    provenance: str
    batching: str
    importance: str
    alternatives: str
    jev_implementations: str
    v0: str
    note: str


def _resolve(s: dict, root: dict, ext: dict) -> tuple[dict, dict]:
    while "$ref" in s:
        ref = s["$ref"]
        rest = {k: v for k, v in s.items() if k != "$ref"}
        if ref in ext:
            root = ext[ref]
            s = {**ext[ref], **rest}
            continue
        t = root
        for part in ref.lstrip("#/").split("/"):
            t = t[part]
        s = {**t, **rest}
    return s, root


def nodes(schema: dict, ext: dict | None = None) -> list[tuple[str, str, str]]:
    """(pointer, kind, json type) for every node; nullable anyOf collapsed; arrays of X recurse into /[]."""
    ext = ext or {}
    out: list[tuple[str, str, str]] = []

    def walk(s: dict, ptr: str, root: dict) -> None:
        s, root = _resolve(s, root, ext)
        if "anyOf" in s:
            nn = [b for b in s["anyOf"] if b.get("type") != "null"]
            if len(nn) == 1:
                s, root = _resolve({**nn[0], **{k: v for k, v in s.items() if k != "anyOf"}}, root, ext)
            else:
                out.append((ptr or "/", "leaf", "union"))
                return
        t = s.get("type")
        if t == "object" or "properties" in s:
            out.append((ptr or "/", "object", "object"))
            for k, v in s.get("properties", {}).items():
                walk(v, f"{ptr}/{k}", root)
        elif t == "array":
            out.append((ptr, "array", "array"))
            walk(s.get("items", {}), f"{ptr}/[]", root)
        else:
            out.append((ptr, "leaf", "enum" if "enum" in s else str(t)))

    walk(schema, "", schema)
    return out


def classify(schema_id: str, group: str, schema: dict, annotations: dict, ext: dict | None = None) -> list[Row]:
    rows = []
    ann = annotations[schema_id]
    under_g: list[str] = []
    for ptr, kind, jt in nodes(schema, ext):
        a = ann.get(ptr)
        if a is None:
            raise ValueError(f"{schema_id}{ptr}: no annotation")
        if a["origin"] not in RULES or a["importance"] not in IMPORTANCE:
            raise ValueError(f"{schema_id}{ptr}: bad annotation {a}")
        if a["origin"] not in ("unsupported", "caller") and KIND.get(a["origin"], "leaf") != kind:
            raise ValueError(f"{schema_id}{ptr}: origin {a['origin']} does not fit a {kind}")
        r = RULES[a["origin"]]
        v0 = r[10]
        container = next((g for g in under_g if ptr.startswith(g + "/")), None)
        if container:
            v0 = f"no: inside an array of objects ({container}, class G)"
        if a["origin"] == "array_objects":
            under_g.append(ptr)
        rows.append(Row(schema_id, group, ptr, kind, jt, a["origin"], r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7],
                        a["importance"], r[8], r[9], v0, a.get("note", "")))
    extra = set(ann) - {p for p, _, _ in nodes(schema, ext)}
    if extra:
        raise ValueError(f"{schema_id}: annotations for unknown pointers {sorted(extra)}")
    return rows


def load_all(root: pathlib.Path = SCHEMAS) -> list[Row]:
    prov = json.loads((root / "provenance.json").read_text())
    ann = json.loads((root / "annotations.json").read_text())["annotations"]
    ext = {"https://example.com/user-profile.schema.json":
           json.loads((root / "src" / "medical_intake.user-profile.schema.json").read_text())}
    rows = []
    for p in prov:
        rows += classify(p["id"], p["group"], json.loads((root / f"{p['id']}.schema.json").read_text()), ann, ext)
    return rows


def summary(rows: list[Row]) -> dict:
    groups = sorted({r.group for r in rows})
    leaves = [r for r in rows if r.kind == "leaf"]
    by = {g: dict(Counter(r.cls for r in leaves if r.group == g)) for g in groups}
    by_nodes = {g: dict(Counter(r.cls for r in rows if r.group == g)) for g in groups}
    schemas = sorted({(r.schema, r.group) for r in rows})
    share_cd = {s: sum(r.cls in "CD" for r in leaves if r.schema == s) / max(1, sum(r.schema == s for r in leaves))
                for s, _ in schemas}
    ext_leaves = [r for r in leaves if r.group == "extraction"]
    a_share = sum(r.cls == "A" for r in rows) / len(rows)
    de_share = sum(r.cls in "DE" for r in ext_leaves) / len(ext_leaves)
    med_all = statistics.median(share_cd.values())
    med_core = statistics.median(v for (s, g) in schemas for v in [share_cd[s]] if g != "additional")
    pred = {"a_A_share_of_all_nodes": a_share, "a_holds": a_share > 0.5,
            "b_DE_share_of_extraction_leaves": de_share, "b_holds": de_share > 0.5,
            "c_median_CD_share_per_schema": med_all, "c_holds": med_all < 0.5,
            "c_median_without_additional_fixtures": med_core}
    pred["verdict"] = "CONFIRMED" if pred["a_holds"] and pred["b_holds"] and pred["c_holds"] else "WRONG"
    constructs = Counter((r.group, r.cls, r.construct) for r in rows)
    return {"schemas": len(schemas), "schemas_by_group": dict(Counter(g for _, g in schemas)),
            "nodes": len(rows), "leaves": len(leaves), "leaves_by_group": dict(Counter(r.group for r in leaves)),
            "leaf_classes_by_group": by, "node_classes_by_group": by_nodes, "cd_share_by_schema": share_cd,
            "v0_leaves": dict(Counter(r.v0.split(",")[0].split(" (")[0].split(":")[0] for r in leaves)),
            "construct_frequency": [{"group": g, "class": c, "construct": k, "count": n}
                                    for (g, c, k), n in sorted(constructs.items())],
            "importance_by_class": {c: dict(Counter(r.importance for r in leaves if r.cls == c)) for c in "ABCDEFG"},
            "prediction": pred}


def main(argv: list[str], root: pathlib.Path = SCHEMAS, out: pathlib.Path = RESULTS) -> int:
    rows = load_all(root)
    out.mkdir(exist_ok=True)
    (out / "taxonomy.json").write_text(json.dumps({"summary": summary(rows), "rows": [asdict(r) for r in rows]},
                                                  indent=1, ensure_ascii=False) + "\n")
    s = summary(rows)
    print(json.dumps({k: s[k] for k in ("schemas", "schemas_by_group", "nodes", "leaves", "leaf_classes_by_group",
                                        "prediction")}, indent=1))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
