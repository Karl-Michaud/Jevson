"""check_r3_pydantic_rows.py — DESIGN §3.5 normalisation table vs what Pydantic actually emits
(and PLAN "pydantic >= 2.12": run under 2.12.0 and the latest; diff the outputs).

Claims (DESIGN §3.5, Rev 5):
  - the compiler reads Pydantic's mode="validation" schema;
  - Decimal emits `anyOf [number, string with pattern]` -> number;
  - `anyOf [T, {type: null}]` -> nullable T; const / single Literal / single-member Enum -> constant;
  - flat allOf of object schemas -> merged, anything else refused;
  - exclusiveMinimum/multipleOf/format kept for final validation only;
  - Pydantic users write Field(json_schema_extra={"x-jevson": {...}}) "so the emitted JSON
    Schema is identical to what a raw-schema user writes";
  - PLAN Phase 6: discriminated unions (`discriminator` keyword) supported.
Method: build one model per table row plus x-jevson placement cases; dump
model_json_schema(mode="validation") and mode="serialization"; record, per case, the exact
emitted form and machine checks (where x-jevson lands; presence of allOf anywhere; siblings
next to $ref; Optional[Decimal] shape; discriminator/oneOf). Writes
out/check_r3_pydantic_rows_<pydantic version>.json and a .txt summary.
"""
import json, sys, enum, datetime, os
from decimal import Decimal
from typing import Optional, Literal, Union, Annotated
import pydantic
from pydantic import BaseModel, Field, ConfigDict

OUTD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
X = {"x-jevson": {"source": {"extractor": "llm"}}}

class One(enum.Enum):
    ONLY = "only"
class Tier(str, enum.Enum):
    GOLD = "gold"; SILVER = "silver"
class Addr(BaseModel):
    street: str
    city: str
class AddrX(BaseModel):
    model_config = ConfigDict(json_schema_extra={"x-jevson": {"question": "model-level"}})
    street: str
class Person(BaseModel):
    kind: Literal["person"]
    name: str
class Org(BaseModel):
    kind: Literal["org"]
    legal_name: str

cases = {}
def case(name, model):
    cases[name] = model

class R_decimal(BaseModel):
    total: Decimal
case("decimal", R_decimal)
class R_decimal_x(BaseModel):
    total: Decimal = Field(json_schema_extra={"x-jevson": {"source": {"extractor": "money"}}})
case("decimal_with_x", R_decimal_x)
class R_decimal_constrained(BaseModel):
    total: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
case("decimal_constrained", R_decimal_constrained)
class R_opt_decimal(BaseModel):
    total: Optional[Decimal] = None
case("optional_decimal", R_opt_decimal)
class R_one_enum(BaseModel):
    e: One
case("single_member_enum", R_one_enum)
class R_one_lit(BaseModel):
    k: Literal["x"]
case("single_literal", R_one_lit)
class R_one_enum_default(BaseModel):
    e: One = One.ONLY
case("single_member_enum_default", R_one_enum_default)
class R_nested_desc(BaseModel):
    addr: Addr = Field(description="billing address")
case("nested_with_description", R_nested_desc)
class R_nested_x(BaseModel):
    billing: Addr = Field(json_schema_extra=X)
    shipping: Addr = Field(json_schema_extra={"x-jevson": {"question": "ship to"}})
case("nested_with_x_two_fields_same_def", R_nested_x)
class R_nested_default(BaseModel):
    addr: Addr = Addr(street="s", city="c")
case("nested_with_model_default", R_nested_default)
class R_opt_nested_x(BaseModel):
    addr: Optional[Addr] = Field(default=None, json_schema_extra=X, description="d")
case("optional_nested_with_x", R_opt_nested_x)
class R_list_nested_x(BaseModel):
    items: list[Addr] = Field(json_schema_extra=X)
case("list_nested_with_x", R_list_nested_x)
class R_enum_x(BaseModel):
    tier: Tier = Field(json_schema_extra={"x-jevson": {"question": "tier?"}})
case("enum_with_x", R_enum_x)
class R_model_level_x(BaseModel):
    a: AddrX
case("submodel_config_x", R_model_level_x)
class R_annot_x(BaseModel):
    vendor: Annotated[str, Field(json_schema_extra=X)]
case("annotated_str_with_x", R_annot_x)
class R_excl(BaseModel):
    price: float = Field(gt=0, lt=100, multiple_of=0.01)
    n: int = Field(ge=1, le=10)
case("exclusive_multipleof", R_excl)
class R_disc(BaseModel):
    party: Union[Person, Org] = Field(discriminator="kind")
case("discriminated_union", R_disc)
class R_disc_x(BaseModel):
    party: Union[Person, Org] = Field(discriminator="kind", json_schema_extra={"x-jevson": {"question": "which?"}})
case("discriminated_union_with_x", R_disc_x)
class R_undisc(BaseModel):
    party: Union[Person, Org]
case("plain_union", R_undisc)
class R_opt_default(BaseModel):
    note: Optional[str] = "x"
case("optional_nonnull_default", R_opt_default)
class R_formats(BaseModel):
    d: datetime.date
    dt: datetime.datetime
case("formats", R_formats)

def walk(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            yield path + "/" + k, k, v, o
            yield from walk(v, path + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}/{i}")

dump, summary = {}, []
summary.append(f"pydantic {pydantic.VERSION} (core {pydantic.version.version_short() if hasattr(pydantic.version,'version_short') else ''})")
for name, m in cases.items():
    v = m.model_json_schema(mode="validation"); s = m.model_json_schema(mode="serialization")
    dump[name] = {"validation": v, "serialization": s}
    allof = [p for p, k, _, _ in walk(v) if k == "allOf"]
    xloc = [p for p, k, _, _ in walk(v) if k == "x-jevson"]
    ref_sibs = sorted({p.rsplit("/", 1)[0] + ": " + ",".join(sorted(k2 for k2 in par if k2 != "$ref")) for p, k, _, par in walk(v) if k == "$ref" and len(par) > 1})
    summary.append(f"\n[{name}]")
    summary.append(f"  validation props: {json.dumps(v.get('properties'), ensure_ascii=False)}")
    if v.get("$defs"): summary.append(f"  $defs: {json.dumps(v['$defs'], ensure_ascii=False)}")
    if s != v: summary.append(f"  serialization props differ: {json.dumps(s.get('properties'), ensure_ascii=False)}")
    summary.append(f"  allOf at: {allof or 'none'}; x-jevson at: {xloc or 'none'}; $ref with siblings: {ref_sibs or 'none'}")
open(f"{OUTD}/check_r3_pydantic_rows_{pydantic.VERSION}.json", "w").write(json.dumps(dump, indent=1, sort_keys=True))
open(f"{OUTD}/check_r3_pydantic_rows_{pydantic.VERSION}.txt", "w").write("\n".join(summary) + "\n")
print("\n".join(summary))
