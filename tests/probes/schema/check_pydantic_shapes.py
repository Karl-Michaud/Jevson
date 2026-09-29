"""Claim: PLAN Phase 2 — "Pydantic model acceptance, converting to JSON Schema"; "Nested object support";
"A Pydantic model and its emitted JSON Schema compile to identical graphs"; while unions (anyOf/oneOf)
and `$ref` resolution are Phase 6 and Phase 2 must refuse what it cannot map.
Also DESIGN §9 mapping: number bounded 0–1, integer 2–10 levels, bool, enum.

Method: emit pydantic v2 model_json_schema() for common field shapes and report which JSON Schema
keywords appear ($ref/$defs, anyOf, const, oneOf+discriminator, exclusiveMinimum ...). Any model using
a nested submodel, Optional, Literal[one], or Enum class emits $ref or anyOf — keywords that Phase 2
cannot compile until Phase 6. Also checks mode='validation' vs 'serialization' divergence (which of the
two is "its emitted JSON Schema"?) and title/description noise that could leak into node ids.
"""
import pathlib as _pl, sys as _sys
PROBES = _pl.Path(__file__).resolve().parents[1]
_sys.path.insert(0, str(PROBES))
(PROBES / "out").mkdir(exist_ok=True)
import json
from enum import Enum
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field, conint, confloat

class Tier(str, Enum):
    gold = "gold"; silver = "silver"

class Address(BaseModel):
    city: str

class Nested(BaseModel):
    address: Address

class Opt(BaseModel):
    nickname: Optional[str] = None

class OptReq(BaseModel):
    tier: Optional[Tier]            # required but nullable

class EnumM(BaseModel):
    tier: Tier

class Lit(BaseModel):
    kind: Literal["a", "b", "c"]

class Lit1(BaseModel):
    kind: Literal["invoice"]

class Uni(BaseModel):
    v: Union[int, str]

class Cint(BaseModel):
    rating: conint(ge=1, le=5)

class Cfloat(BaseModel):
    p: confloat(ge=0, le=1)
    q: Annotated[float, Field(gt=0, lt=1)]

class Lst(BaseModel):
    items: list[str] = Field(max_length=5)

class Rec(BaseModel):
    name: str
    children: list["Rec"] = []

class Dflt(BaseModel):
    flag: bool = False
    tier: Tier = Tier.gold

class Cat(BaseModel):
    pet_type: Literal["cat"]; meows: int
class Dog(BaseModel):
    pet_type: Literal["dog"]; barks: float
class Disc(BaseModel):
    pet: Union[Cat, Dog] = Field(discriminator="pet_type")

class Deep(BaseModel):
    class L2(BaseModel):
        class L3(BaseModel):
            ok: bool
        l3: "Deep.L2.L3"
    l2: L2

def keywords(obj, acc=None):
    acc = set() if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            acc.add(k); keywords(v, acc)
    elif isinstance(obj, list):
        for v in obj: keywords(v, acc)
    return acc

PHASE6 = {"$ref", "$defs", "anyOf", "oneOf", "allOf", "discriminator", "const"}
models = [Nested, Opt, OptReq, EnumM, Lit, Lit1, Uni, Cint, Cfloat, Lst, Rec, Dflt, Disc, Deep]
summary = []
for m in models:
    s = m.model_json_schema()
    kws = keywords(s) & PHASE6
    print(f"=== {m.__name__}: Phase-6-only keywords present: {sorted(kws) or 'none'}")
    print(json.dumps(s, indent=None, ensure_ascii=False))
    ser = m.model_json_schema(mode="serialization")
    if ser != s:
        print("   !! serialization-mode schema differs:", json.dumps(ser, ensure_ascii=False))
    summary.append((m.__name__, sorted(kws)))
print("\nSUMMARY (model -> keywords Phase 2 cannot handle per PLAN scope):")
for n, k in summary:
    print(f"  {n:8} {k}")
print(f"{sum(1 for _, k in summary if k)}/{len(summary)} models need $ref/anyOf/const handling")

print("\n=== shared $def: two fields of one submodel type -> one schema location ===")
class Invoice(BaseModel):
    billing: Address
    shipping: Address
s = Invoice.model_json_schema()
print(json.dumps(s))
print("schema pointer for both cities: #/$defs/Address/properties/city ; instance pointers: /billing/city, /shipping/city")
print("=> node ids must derive from INSTANCE pointers after $ref inlining, not schema pointers, or the two fields collide")

print("\n=== Optional[bool] / Optional[conint] : anyOf with null wraps the mappable type ===")
class OB(BaseModel):
    paid: Optional[bool] = None
    rating: Optional[conint(ge=1, le=5)] = None
print(json.dumps(OB.model_json_schema()))
