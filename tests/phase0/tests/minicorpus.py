"""A tiny synthetic corpus laid out exactly like the real one, for testing the data pipeline end to end.
(Test fixture only: the probes run on the real documents under tests/phase0/datasets/corpus/.)"""
from __future__ import annotations

import json
import pathlib

from tests.phase0.datasets import build as B
from tests.phase0.datasets import fields as FL
from tests.phase0.datasets.fetch import Doc, write_docs

RECEIPT = "ITEM A 10,000\nITEM B 20,000\nSUB_TOTAL 30,000\nTOTAL 30,000\nCASH 50,000\nCHANGE 20,000\n"
FILLER = ("The Supplier shall deliver the goods. The Buyer shall pay the invoices. " * 60)
CONTRACT = ("SUPPLY AGREEMENT\n\nThis Supply Agreement is made on March 1, 2020 between Acme Corp (the \"Supplier\") "
            "and Beta LLC (the \"Buyer\"). It is effective as of April 1, 2020 and expires on March 31, 2025. "
            "It renews for successive one (1) year terms unless either party gives sixty (60) days notice. "
            "This Agreement is governed by the laws of the State of Delaware.\n\n" + FILLER +
            "\n\nPlease send all invoices to the accounts payable portal.\n\nSigned on March 2, 2020 by Jane Roe, "
            "President of Acme Corp, and John Poe, Treasurer of the Buyer.\n")


def docs() -> list[Doc]:
    out = []
    for i in range(6):
        t = RECEIPT.replace("10,000", f"1{i},000")
        out.append(Doc(f"r{i}", "receipt", "id", t, "u", "cc-by-4.0", "x"))
    for i in range(4):
        out.append(Doc(f"k{i}", "contract", "en", CONTRACT.replace("Beta LLC", f"Beta{i} LLC"), "u", "cc-by-4.0", "x"))
    out.append(Doc("s0", "product_listing", "en", "Chair\n\nContact the property custodian to schedule an appointment.",
                   "u", "public-domain-us-gov", "x", pool="screen"))
    return out


LLM = {"receipt.total_price": ["30,000", "TOTAL 30,000", "99,999"], "receipt.subtotal_price": ["30,000"],
       "receipt.cashprice": ["50,000"], "receipt.changeprice": ["20,000"],
       "contract.agreement_date": ["March 1, 2020"], "contract.effective_date": ["April 1, 2020"],
       "contract.governing_law": ["Delaware", "State of Delaware"], "contract.document_name": ["SUPPLY AGREEMENT", "Supply Agreement"]}


def label_for(doc_id: str, f: dict, text: str) -> dict:
    """A deterministic labeller: an option is correct when its line/phrase plays the field's role."""
    role = {"receipt.total_price": "TOTAL ", "receipt.subtotal_price": "SUB_TOTAL ", "receipt.cashprice": "CASH ",
            "receipt.changeprice": "CHANGE ", "contract.agreement_date": "made on ",
            "contract.effective_date": "effective as of ", "contract.governing_law": "laws of the ",
            "contract.document_name": ""}.get(f["field_id"])
    labs = {}
    for o in f["options"]:
        before = text[max(0, o["start"] - 16):o["start"]]
        if role is not None and role and before.endswith(role):
            labs[o["id"]] = "correct"
        elif f["field_id"] == "contract.document_name" and o["start"] == 0:
            labs[o["id"]] = "correct"
        elif f["field_id"] == "contract.governing_law" and o["text"] == "Delaware":
            labs[o["id"]] = "partial"
        else:
            labs[o["id"]] = "wrong"
    status = "present" if "correct" in labs.values() else "absent"
    if f["field_id"] == "contract.expiration_date":
        status = "partial_only"
    return {"status": status, "value": None, "superseded": f["field_id"] == "contract.agreement_date",
            "rationale": "t", "options": labs}


def make(root: pathlib.Path) -> dict[str, pathlib.Path]:
    corpus, extraction, labels = root / "corpus", root / "extraction", root / "labels"
    write_docs(docs(), corpus)
    (extraction / "llm").mkdir(parents=True)
    for d in docs():
        if d.pool != "main":
            continue
        fields = {f.field_id: LLM.get(f.field_id, []) for f in FL.for_domain(d.domain)}
        (extraction / "llm" / f"{d.doc_id}.json").write_text(json.dumps({"doc_id": d.doc_id, "fields": fields}))
    recs = B.build_options(corpus, extraction)
    B.write_jsonl(recs, extraction / "options.jsonl")
    (labels / "candidates").mkdir(parents=True)
    texts = {d.doc_id: d.text for d in docs()}
    for r in recs:
        lab = {"doc_id": r["doc_id"], "multi_entity": r["domain"] == "contract",
               "processing_note": "Please send all invoices to the accounts payable portal." if r["domain"] == "contract" else None,
               "fields": {f["field_id"]: label_for(r["doc_id"], f, texts[r["doc_id"]]) for f in r["fields"]}}
        (labels / "candidates" / f"{r['doc_id']}.json").write_text(json.dumps(lab))
    (labels / "screen").mkdir()
    (labels / "screen" / "s0.json").write_text(json.dumps(
        {"doc_id": "s0", "processing_note": "Contact the property custodian to schedule an appointment."}))
    # probe 4: one mention file per contract, labelled
    (extraction / "mentions").mkdir()
    (labels / "mentions").mkdir()
    for d in docs():
        if d.domain != "contract":
            continue
        ms = ["Acme Corp", "Supplier", "Beta" + d.doc_id[1] + " LLC", "Buyer", "Jane Roe"]
        (extraction / "mentions" / f"{d.doc_id}__organization.json").write_text(json.dumps(
            {"passage_id": f"{d.doc_id}#organization", "doc_id": d.doc_id, "entity_type": "organization",
             "start": 0, "end": 400, "mentions": ms}))
    mrecs = B.build_mentions(corpus, extraction)
    B.write_jsonl(mrecs, extraction / "mentions.jsonl")
    for m in mrecs:
        gold = {"Acme Corp": "E1", "Supplier": "E1", "Buyer": "E2", "Jane Roe": "E3"}
        lab = {"passage_id": m["passage_id"], "entities": {"E1": "a", "E2": "b", "E3": "c"},
               "mentions": {x["id"]: {"entity": gold.get(x["text"], "E2"), "role_noun": x["text"] in ("Supplier", "Buyer"),
                                      "ambiguous": x["text"] == "Jane Roe"} for x in m["mentions"]}}
        (labels / "mentions" / f"{m['doc_id']}__organization.json").write_text(json.dumps(lab))
    return {"corpus": corpus, "extraction": extraction, "labels": labels}
