from pydantic import BaseModel, Field
from typing import Literal


class ClassificationResponse(BaseModel):
    """
    A few-shot example of text classification:

    Examples:
    - "Buy cheap watches now!": SPAM
    - "Meeting at 3 PM in the conference room": NOT_SPAM
    - "You've won a free iPhone! Click here": SPAM
    - "Can you pick up some milk on your way home?": NOT_SPAM
    - "Increase your followers by 10000 overnight!": SPAM
    """

    chain_of_thought: str = Field(
        ...,
        description="The chain of thought that led to the prediction.",
    )
    label: Literal["SPAM", "NOT_SPAM"] = Field(
        ...,
        description="The predicted class label.",
    )
