"""Quickstart: triage a support ticket into bounded fields, offline, with no API key.

`FakeBackend` stands in for the decision model: each question is answered by `stand_in` below, so
the example spends nothing. Swap in `DecisionsBackend()` (it reads `OPENAI_API_KEY`) to make real,
billed decisions; nothing else changes.
"""

from typing import Literal

from pydantic import BaseModel, Field

from jevson import Answer, DecisionKind, FakeBackend, InMemoryCostSink, Jevson, Question


class Ticket(BaseModel):
    category: Literal["billing", "bug", "feature_request"] = Field(description="the ticket's topic")
    refund_requested: bool = Field(description="the customer asks for a refund")
    severity: int = Field(
        ge=1, le=4, description="severity of the problem", json_schema_extra={"x-jevson": {"ordinal": True}}
    )
    tags: list[Literal["urgent", "enterprise", "churn_risk"]] = Field(description="labels that apply to the ticket")


SOURCE = (
    "Subject: charged twice. Our company account was billed twice for October. Please refund the "
    "duplicate charge today, or we will move to another provider."
)


def stand_in(question: Question) -> Answer:
    """What a decision model might answer for this source; a real backend decides this itself."""
    text = question.instructions
    if question.kind is DecisionKind.PREDICATE:
        yes = any(word in text for word in ("refund", '"urgent"', '"churn_risk"'))
        return FakeBackend.predicate(0.93 if yes else 0.06)(question)
    wanted = '"billing"' if "topic" in text else '"3"'
    option = next(option for option in question.options if option.description == wanted)
    return FakeBackend.select(option.id, 0.88)(question)


def main() -> None:
    sink = InMemoryCostSink()
    with Jevson(FakeBackend(default=stand_in), cost_sink=sink) as jevson:
        result = jevson.resolve(Ticket, SOURCE)

    print(result.value)
    # {'category': 'billing', 'refund_requested': True, 'severity': 3, 'tags': ['urgent', 'churn_risk']}
    print(result.complete, result.satisfies_schema)  # True True
    for key, decision in result.decisions.items():  # every decision, with its full distribution
        print(key, decision.selected, decision.distribution_hundredths)
    print(Ticket.model_validate(result.value))
    print(len(sink.events), "decision request(s);", result.cost.decision_input_tokens, "input tokens")


if __name__ == "__main__":
    main()
