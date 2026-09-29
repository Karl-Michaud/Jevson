"""Claim (DESIGN §3, §4.2, §10; PLAN Phase 2): the Phase 2 normaliser (inline static acyclic $ref/$defs,
nullable-T from anyOf[T,null] / type[T,"null"], const and single-value Literal -> constant, Enum) plus the mapping
(bool -> noul, enum -> choice, integer range 2-10 -> score, bounded numbers not probabilities, unbounded numerics
and undeclared unbounded strings refused, unions with >= 2 non-null branches refused until Phase 6, recursive $ref
refused) handles idiomatic Pydantic.

Method: emit pydantic v2 model_json_schema() in validation AND serialization mode for 30+ shapes beyond round 1's 14.
Walk each schema and collect every JSON Schema keyword used (keys of schema objects; property names excluded).
Classify each keyword by what DESIGN.md / PLAN.md say about it:
  NORMALISED  - rewritten by the Phase 2 normaliser
  MAPPED      - routed by mapping.py rules
  VALIDATED   - mentioned only as checked by final jsonschema validation (PLAN §4.3 / L9 / L10)
  REFUSED     - named refusal
  ANNOTATION  - harmless metadata, but the docs never say it is ignored
  GAP         - the keyword appears nowhere in DESIGN.md or PLAN.md
For every keyword the script prints the doc lines that mention it (word-boundary grep), so the classification is
auditable. Also validates every emitted schema against the draft 2020-12 metaschema, and flags validation vs
serialization divergence.
"""
import datetime as dt
import decimal
import enum
import json
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Dict, FrozenSet, Generic, List, Literal, Optional, Set, Tuple, TypeVar, Union

import jsonschema
import pydantic
from pydantic import (BaseModel, ConfigDict, EmailStr, Field, HttpUrl, computed_field, conint, confloat, conlist,
                      constr)

ROOT = Path(__file__).resolve().parents[2]
DOCS = {"DESIGN": (ROOT / "DESIGN.md").read_text(), "PLAN": (ROOT / "PLAN.md").read_text()}


# ------------------------------------------------------------------ shapes
class Leaf(BaseModel):
    x: int


class DictM(BaseModel):
    tags: Dict[str, int]


class DictModel(BaseModel):
    by_name: Dict[str, Leaf]


class Cat(BaseModel):
    kind: Literal["cat"]
    meows: bool


class Dog(BaseModel):
    kind: Literal["dog"]
    barks: bool


class Disc(BaseModel):
    pet: Union[Cat, Dog] = Field(discriminator="kind")


class Formats(BaseModel):
    when: dt.datetime
    day: dt.date
    at: dt.time
    span: dt.timedelta
    uid: uuid.UUID
    email: EmailStr
    url: HttpUrl


class ConStr(BaseModel):
    code: constr(pattern=r"^[A-Z]{3}$", min_length=3, max_length=3)


class ConNum(BaseModel):
    a: conint(ge=1, le=5)
    b: conint(gt=0, lt=6)
    c: confloat(ge=0, le=1)
    d: confloat(gt=0, lt=1)
    e: conint(ge=0, le=100, multiple_of=5)


class ConList(BaseModel):
    xs: conlist(str, min_length=1, max_length=3)


class Sets(BaseModel):
    s: Set[str]
    f: FrozenSet[int]


class Tup(BaseModel):
    t: Tuple[int, str]
    v: Tuple[int, ...]


class Ann(BaseModel):
    rating: Annotated[int, Field(ge=1, le=5, description="1-5 stars")]
    name: Annotated[str, Field(max_length=40)]


class DefFactory(BaseModel):
    items: List[str] = Field(default_factory=list)
    n: int = 3


class Computed(BaseModel):
    w: int
    h: int

    @computed_field
    @property
    def area(self) -> int:
        return self.w * self.h


class Forbid(BaseModel):
    model_config = ConfigDict(extra="forbid")
    a: int


class Tree(BaseModel):
    value: int
    children: List["Tree"] = []


T = TypeVar("T")


class Box(BaseModel, Generic[T]):
    content: T


class UsesGeneric(BaseModel):
    a: Box[int]
    b: Box[str]


class OptNested(BaseModel):
    leaf: Optional[Leaf] = None


class A_(BaseModel):
    a: int


class B_(BaseModel):
    b: str


class UnionModels(BaseModel):
    ab: Union[A_, B_]


class Pri(enum.Enum):
    low = 1
    mid = 2
    high = 3


class PriI(enum.IntEnum):
    low = 1
    high = 2


class Solo(str, enum.Enum):
    only = "only"


class Enums(BaseModel):
    p: Pri
    q: PriI
    s: Solo


class LitMulti(BaseModel):
    k: Literal["a", "b", "c"]
    mixed: Literal[1, "one"]
    lb: Literal[True]


class BytesM(BaseModel):
    blob: bytes


class DecM(BaseModel):
    amount: decimal.Decimal
    amount_c: Annotated[decimal.Decimal, Field(max_digits=10, decimal_places=2)]


class OptBool(BaseModel):
    flag: Optional[bool]


class JevsonExtra(BaseModel):
    summary: str = Field(json_schema_extra={"jevson": {"generate": {"criteria": ["mentions refund"]}}})


class AnyM(BaseModel):
    blob: Any
    d: dict


class StrEnumDefault(BaseModel):
    s: Solo = Solo.only


SHAPES = {
    "dict[str,int] (additionalProperties)": DictM,
    "dict[str,Model]": DictModel,
    "discriminated union": Disc,
    "datetime/date/time/timedelta/UUID/EmailStr/HttpUrl": Formats,
    "constr(pattern,min,max)": ConStr,
    "conint/confloat ge/le, gt/lt, multiple_of": ConNum,
    "conlist(min,max)": ConList,
    "set / frozenset": Sets,
    "tuple[int,str] / tuple[int,...]": Tup,
    "Annotated[..., Field(ge,le,max_length)]": Ann,
    "default_factory": DefFactory,
    "computed_field": Computed,
    "extra='forbid'": Forbid,
    "recursive model": Tree,
    "generic model Box[int], Box[str]": UsesGeneric,
    "Optional[nested]": OptNested,
    "Union[A,B] of models": UnionModels,
    "Enum int values / IntEnum / 1-member Enum": Enums,
    "Literal multi / mixed / Literal[True]": LitMulti,
    "bytes": BytesM,
    "Decimal": DecM,
    "Optional[bool] (required nullable)": OptBool,
    "json_schema_extra jevson": JevsonExtra,
    "Any / bare dict": AnyM,
    "1-member Enum with default": StrEnumDefault,
}

# ------------------------------------------------------------------ classification (with doc evidence)
STATUS = {
    "$ref": "NORMALISED", "$defs": "NORMALISED", "const": "NORMALISED",
    "anyOf": "NORMALISED(nullable) / REFUSED(>=2 non-null, Phase 6)",
    "oneOf": "REFUSED until Phase 6",
    "allOf": "REFUSED beyond flat merge (PLAN §9)",
    "type": "MAPPED", "enum": "MAPPED", "properties": "MAPPED", "required": "MAPPED", "items": "MAPPED (Phase 7)",
    "minimum": "MAPPED (bounded numeric / score range)", "maximum": "MAPPED (bounded numeric / score range)",
    "default": "MAPPED (defaulted field is class A)", "maxItems": "VALIDATED + cardinality/overflow (R8)",
    "minItems": "VALIDATED (PLAN §4.3)", "uniqueItems": "VALIDATED (PLAN §4.3)", "maxLength": "VALIDATED (PLAN §4.3)",
    "pattern": "VALIDATED (PLAN §4.3)", "format": "VALIDATED-unchecked (L10)",
    "title": "ANNOTATION", "description": "ANNOTATION",
}
GAP_NOTES = {
    "additionalProperties": "dict[str,X] and extra='forbid' both emit it; not in either doc: no rule for open-keyed objects (unbounded key set) nor for additionalProperties:false",
    "discriminator": "OpenAPI keyword, ignored by jsonschema 2020-12; Phase 6 plans a Jev 'discrimination choice' but never says a declared discriminator (const tag) makes the branch deterministic class A",
    "exclusiveMinimum": "gt/lt bounds; 'bounded' / 'integer range of 2-10 values' only speak of minimum/maximum",
    "exclusiveMaximum": "as above",
    "multipleOf": "conint(multiple_of=5) 0..100 has 21 values: a 'range' test on min/max alone says >10 levels -> refuse; with multipleOf it is 21 levels; no rule",
    "minLength": "HttpUrl/constr emit it; only maxLength is named in PLAN §4.3",
    "prefixItems": "tuple[...] emits it; fixed-arity positional arrays have no mapping rule (and are an R13 position reference risk if placed in state)",
    "readOnly": "computed_field emits it in serialization mode only; the docs never say which mode is 'its emitted JSON Schema'",
    "jevson": "Pydantic json_schema_extra={'jevson': ...} emits a bare 'jevson' keyword, while raw JSON Schema uses 'x-jevson-generate'; two spellings, compiler must accept both",
    "contentEncoding": "", "contentMediaType": "",
}


def keywords(schema, acc=None, path=""):
    acc = acc if acc is not None else {}
    if isinstance(schema, dict):
        for k, v in schema.items():
            acc.setdefault(k, set()).add(path or "/")
            if k in ("properties", "$defs", "patternProperties", "dependentRequired"):
                for pk, pv in v.items():
                    keywords(pv, acc, f"{path}/{k}/{pk}")
            elif k in ("enum", "const", "default", "examples", "required", "discriminator"):
                continue
            else:
                keywords(v, acc, f"{path}/{k}")
    elif isinstance(schema, list):
        for i, x in enumerate(schema):
            keywords(x, acc, f"{path}/{i}")
    return acc


def doc_hits(kw):
    pat = re.compile(r"(?<![A-Za-z_$-])" + re.escape(kw) + r"(?![A-Za-z_])")
    out = []
    for name, text in DOCS.items():
        for i, line in enumerate(text.splitlines(), 1):
            if pat.search(line):
                out.append(f"{name}:{i}")
    return out


def classify(kw):
    if kw in STATUS:
        return STATUS[kw]
    return "GAP"


def main():
    print("pydantic", pydantic.VERSION, "jsonschema", __import__("importlib.metadata").metadata.version("jsonschema"))
    meta = jsonschema.Draft202012Validator(jsonschema.Draft202012Validator.META_SCHEMA)
    all_kw = {}
    for name, model in SHAPES.items():
        print("=" * 110)
        print(name)
        v = model.model_json_schema(mode="validation")
        s = model.model_json_schema(mode="serialization")
        errs = list(meta.iter_errors(v))
        print("  metaschema-valid:", not errs)
        print("  validation schema:", json.dumps(v, sort_keys=True)[:900])
        if v != s:
            print("  SERIALIZATION DIFFERS:", json.dumps(s, sort_keys=True)[:600])
        kv = keywords(v)
        ks = keywords(s)
        for k in sorted(set(kv) | set(ks)):
            where = "both" if k in kv and k in ks else ("validation-only" if k in kv else "serialization-only")
            all_kw.setdefault(k, set()).add(name)
            print(f"    {k:22s} {classify(k):45s} [{where}]")
    print("=" * 110)
    print("KEYWORD SUMMARY (status, shapes emitting it, doc mentions by word-boundary grep)")
    for k in sorted(all_kw):
        hits = doc_hits(k)
        st = classify(k)
        if st == "GAP" and hits:
            st = "GAP? (word appears; check context)"
        print(f"  {k:22s} {st:48s} shapes={len(all_kw[k]):2d} docs={','.join(hits[:8]) or '-'}")
        if classify(k) == "GAP":
            print(f"      note: {GAP_NOTES.get(k, '')}  | emitted by: {sorted(all_kw[k])}")

    # specific semantic probes
    print("=" * 110)
    print("SEMANTIC PROBES")
    print("  1-member Enum emits:", Enums.model_json_schema()["$defs"]["Solo"],
          "-> 'enum < 2 values' refusal (PLAN Phase 2) fires, but Literal['x'] emits const and is normalised: inconsistent")
    print("  Literal[True] emits:", LitMulti.model_json_schema()["properties"]["lb"])
    print("  Literal[1,'one'] emits:", LitMulti.model_json_schema()["properties"]["mixed"])
    print("  Decimal emits:", DecM.model_json_schema()["properties"]["amount"],
          "-> anyOf with 2 non-null branches = a 'union' under Phase 2 rules -> not_yet_supported / Phase 6 Jev discrimination between number and string")
    print("  Decimal serialization:", DecM.model_json_schema(mode="serialization")["properties"]["amount"])
    print("  default_factory field in schema:", DefFactory.model_json_schema()["properties"]["items"],
          "required:", DefFactory.model_json_schema().get("required"))
    print("  conint(ge=0,le=100,multiple_of=5):", ConNum.model_json_schema()["properties"]["e"])
    print("  jsonschema ignores 'discriminator': valid instance with wrong tag?",
          jsonschema.Draft202012Validator(Disc.model_json_schema()).is_valid({"pet": {"kind": "cat", "meows": True}}))
    print("  Tree schema top-level:", {k: v for k, v in Tree.model_json_schema().items() if k != "$defs"})
    print("  Box generic $defs names:", list(UsesGeneric.model_json_schema()["$defs"]))


if __name__ == "__main__":
    main()
