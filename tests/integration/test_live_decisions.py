"""One real call to `/v1/decisions` (PLAN §4.4): opt-in, billed, never in CI.

Not in pyproject's `testpaths`, so a plain `pytest` never collects it. Run it on demand with the
key in the environment (the library never reads `.env`):

    OPENAI_API_KEY=... uv run --frozen pytest tests/integration -m integration -s
"""

from __future__ import annotations

import asyncio
import os

import pytest

from jevson import BackendResponse, ChoiceAnswer, DecisionKind, DecisionsBackend, Option, PredicateAnswer, Question

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY"),
]


def test_one_live_request() -> None:
    questions = (
        Question("paid", DecisionKind.PREDICATE, "The invoice says it has been paid in full."),
        Question("currency", DecisionKind.CHOICE, "Which currency is the total in?",
                 (Option("c0", "US dollars"), Option("c1", "Euros"))),
    )  # fmt: skip

    async def run() -> BackendResponse:
        async with DecisionsBackend() as backend:
            return await backend.ask("Invoice 12. Total: EUR 40.00. Status: PAID IN FULL.", questions, "gpt-6-luna")

    response = asyncio.run(run())
    paid, currency = response.answers
    print(f"model={response.model!r} input_tokens={response.input_tokens}")  # recorded, R15
    assert isinstance(paid, PredicateAnswer)
    assert paid.probability > 0.5
    assert isinstance(currency, ChoiceAnswer)
    assert currency.choice == "c1"
