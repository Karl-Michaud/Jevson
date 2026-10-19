"""A generative field: your LLM drafts it, the decision model checks it against declared criteria.

Offline, with no API key. `ScriptedLLM` stands in for your LLM and `Reviewer` for the decision
model: it passes the refund criterion only when the draft states the amount. The first draft leaves
the amount out, is rejected with the failing criterion named, and the one redraft is admitted.
Criteria are about the draft and the source only; the decision model is not a fact-checker.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from jevson import (
    Answer,
    BackendResponse,
    DecisionKind,
    FakeBackend,
    Jevson,
    LLMResponse,
    Message,
    Question,
)


class Reply(BaseModel):
    summary: str = Field(
        json_schema_extra={
            "x-jevson": {
                "generate": {"criteria": ["mentions the refund amount stated in the source", "is a single sentence"]}
            }
        }
    )


SOURCE = "Order 7731 arrived broken. The customer wants the $40 they paid refunded to their card."


class ScriptedLLM:
    """Implements the `LLM` protocol with two canned drafts; use your own provider in real code."""

    def __init__(self) -> None:
        self.drafts = ["The customer wants a refund for a broken order.", "The customer wants their $40 refunded."]
        self.prompts: list[Sequence[Message]] = []

    async def complete(self, messages: Sequence[Message], tool_schema: Mapping[str, object] | None) -> LLMResponse:
        self.prompts.append(messages)
        draft = self.drafts[len(self.prompts) - 1]
        return LLMResponse(arguments={"value": draft}, raw=draft, input_tokens=60, output_tokens=12)


class Reviewer:
    """Implements the `Backend` protocol: the criteria pass, except the amount when the draft omits it."""

    async def ask(self, state: str, questions: Sequence[Question], model: str) -> BackendResponse:
        def verdict(question: Question) -> Answer:
            assert question.kind is DecisionKind.PREDICATE
            omits_amount = "refund amount" in question.instructions and "$40 refunded" not in state
            return FakeBackend.predicate(0.08 if omits_amount else 0.91)(question)

        return await FakeBackend(default=verdict).ask(state, questions, model)


def main() -> None:
    llm = ScriptedLLM()
    with Jevson(Reviewer(), llm=llm) as jevson:
        result = jevson.resolve(Reply, SOURCE)

    print(result.value)  # {'summary': 'The customer wants their $40 refunded.'}
    print(result.decided_by["/summary"])  # llm+decision
    for rejection in result.rejections:
        print("rejected:", rejection.draft, "| failed:", rejection.criteria)
    print(result.cost.redrafts, "redraft;", len(llm.prompts), "LLM calls")


if __name__ == "__main__":
    main()
