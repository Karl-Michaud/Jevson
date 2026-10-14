"""The probed fields: class D leaves of the six extraction schemas (tests/fixtures/schemas/), one noun-phrase label
each (the question's {label}, docs/taxonomy.md §1), fixed before any extraction or label exists.

A leaf inside an array is probed as one scoped instance (``x-jevson.source.scope``, DESIGN §5.2), because probes
1-3 measure single-value selection; the scope is part of the label.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    field_id: str
    domain: str
    schema: str
    pointer: str          # JSON pointer into the target instance; [] marks a scoped array item
    label: str            # rendered into the question
    value_type: str       # pattern extractor type (datasets/extract.py)
    guidance: str         # what counts as the value, for the extractor and labellers


FIELDS: tuple[Field, ...] = (
    # receipt: CORD label schema (clovaai/cord README)
    Field("receipt.total_price", "receipt", "receipt", "/total/total_price", "total price of the receipt", "money",
          "the final total the customer has to pay for the purchase"),
    Field("receipt.subtotal_price", "receipt", "receipt", "/subtotal/subtotal_price", "subtotal price of the receipt",
          "money", "the subtotal of the items before tax, service charge, and discounts are applied"),
    Field("receipt.tax_price", "receipt", "receipt", "/subtotal/tax_price", "tax amount on the receipt", "money",
          "the tax amount charged (e.g. PPN, PB1, tax)"),
    Field("receipt.service_price", "receipt", "receipt", "/subtotal/service_price", "service charge on the receipt",
          "money", "the service charge amount"),
    Field("receipt.discount_price", "receipt", "receipt", "/subtotal/discount_price", "discount amount on the receipt",
          "money", "the total discount amount applied to the purchase"),
    Field("receipt.cashprice", "receipt", "receipt", "/total/cashprice", "amount paid in cash", "money",
          "the cash amount handed over by the customer"),
    Field("receipt.changeprice", "receipt", "receipt", "/total/changeprice", "change given to the customer", "money",
          "the change returned to the customer"),
    Field("receipt.menuqty_cnt", "receipt", "receipt", "/total/menuqty_cnt", "total quantity of items purchased",
          "number", "the total count of items purchased, as printed on the receipt"),
    # contract: CUAD categories
    Field("contract.document_name", "contract", "contract", "/document_name", "name of the agreement", "text",
          "the title of the agreement, as the contract names itself"),
    Field("contract.agreement_date", "contract", "contract", "/agreement_date", "date of the agreement", "date",
          "the date the contract was made or signed"),
    Field("contract.effective_date", "contract", "contract", "/effective_date", "effective date of the agreement",
          "date", "the date on which the contract takes effect"),
    Field("contract.expiration_date", "contract", "contract", "/expiration_date",
          "expiration date of the agreement's initial term", "date",
          "the date on which the initial term expires, stated as a date"),
    Field("contract.governing_law", "contract", "contract", "/governing_law", "governing law of the agreement", "text",
          "the state or country whose law governs the contract"),
    Field("contract.renewal_term", "contract", "contract", "/renewal_term", "length of each renewal term", "duration",
          "the length of a renewal term after the initial term expires"),
    Field("contract.notice_period", "contract", "contract", "/notice_period_to_terminate_renewal",
          "notice period to terminate renewal", "duration",
          "how long before expiry notice must be given to prevent renewal"),
    # resume: JSON Resume schema, on FJC judge records
    Field("resume.name", "resume", "resume", "/basics/name", "full name of the person the record is about", "text",
          "the name of the person the biography describes"),
    Field("resume.law_institution", "resume", "resume", "/education/[]/institution",
          "institution where the person earned a law degree", "text", "the school that awarded the J.D. or LL.B."),
    Field("resume.law_year", "resume", "resume", "/education/[]/endDate",
          "year the person earned a law degree", "year", "the year the J.D. or LL.B. was awarded"),
    Field("resume.undergrad_institution", "resume", "resume", "/education/[]/institution",
          "institution where the person earned a bachelor's degree", "text", "the school that awarded the B.A., B.S., or other bachelor's degree"),
    Field("resume.undergrad_year", "resume", "resume", "/education/[]/endDate",
          "year the person earned a bachelor's degree", "year", "the year the bachelor's degree was awarded"),
    Field("resume.first_judgeship_start", "resume", "resume", "/work/[]/startDate",
          "date the commission for the person's first federal judgeship was issued", "date",
          "the commission date of the first federal judicial service listed"),
    Field("resume.latest_position", "resume", "resume", "/work/[]/position",
          "title of the person's most recent federal judicial position", "text",
          "the position title of the latest federal judicial service listed (e.g. 'Judge, U.S. Court of Appeals for the Second Circuit')"),
    # support ticket: LangChain SupportTicket
    Field("ticket.affected_service", "support_ticket", "support_ticket", "/affected_services/[]",
          "main software or service affected by the problem", "text",
          "the product, application, or service the user's problem is about"),
    # medical intake: json-schema.org Health record
    Field("medical.diagnosis", "medical_intake", "medical_intake", "/conditions/[]", "patient's final diagnosis", "text",
          "the condition the patient was finally diagnosed with"),
    Field("medical.treatment_drug", "medical_intake", "medical_intake", "/medications/[]",
          "medication used to treat the patient's final diagnosis", "text",
          "the drug given as treatment for the final diagnosis (the first one named if several)"),
    # product listing: LlamaIndex Product
    Field("product.title", "product_listing", "product_listing", "/title", "title of the item for sale", "text",
          "the name or title of the item or lot being sold"),
    Field("product.inventory", "product_listing", "product_listing", "/inventory", "quantity of items in the lot",
          "number", "how many units the lot contains"),
    Field("product.price", "product_listing", "product_listing", "/price", "price of the item", "money",
          "the asking or sale price of the item"),
)

BY_ID = {f.field_id: f for f in FIELDS}


def for_domain(domain: str) -> list[Field]:
    return [f for f in FIELDS if f.domain == domain]
