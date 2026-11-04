"""A discriminated union: the decision model picks the branch, and only that branch is built.

Offline, with no API key. By default (`union_fanout=True`) every branch's questions go out in the
same request as the discriminator, which saves a round trip; only the selected branch's answers are
used. With `JevsonConfig(union_fanout=False)` the branch's questions are asked only after the
discriminator is decided. A discriminator inside the tie margin leaves the union `Unresolved(tie)`.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from jevson import Answer, DecisionKind, FakeBackend, Jevson, JevsonConfig, Question


class Card(BaseModel):
    """Paid by payment card."""

    type: Literal["card"]
    network: Literal["visa", "mastercard", "amex"]


class BankTransfer(BaseModel):
    """Paid by bank transfer."""

    type: Literal["bank"]
    speed: Literal["instant", "standard"]


class Payment(BaseModel):
    method: Annotated[Card | BankTransfer, Field(discriminator="type")]
    disputed: bool = Field(description="the customer disputes the payment")


SOURCE = "Paid 18 March by SEPA instant transfer from the customer's bank. No complaint on file."


def stand_in(question: Question) -> Answer:
    """What a decision model might answer for this source."""
    if question.kind is DecisionKind.PREDICATE:
        return FakeBackend.predicate(0.04)(question)
    for option in question.options:
        if option.description.startswith("BankTransfer") or option.description in ('"instant"', '"visa"'):
            return FakeBackend.select(option.id, 0.9)(question)
    raise AssertionError(question)


def main() -> None:
    for fanout in (True, False):
        backend = FakeBackend(default=stand_in)
        with Jevson(backend, config=JevsonConfig(union_fanout=fanout)) as jevson:
            result = jevson.resolve(Payment, SOURCE)
        print(result.value)  # {'disputed': False, 'method': {'speed': 'instant', 'type': 'bank'}}
        asked = sum(len(call.questions) for call in backend.calls)
        print(f"union_fanout={fanout}: {len(backend.calls)} request(s), {asked} questions")


if __name__ == "__main__":
    main()
