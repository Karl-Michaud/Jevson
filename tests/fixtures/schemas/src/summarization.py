from pydantic import BaseModel, Field
from typing import List


class ContentSummary(BaseModel):
    title: str = Field(..., description="The title of the video")
    duration: float = Field(
        ..., description="The total duration of the video in seconds"
    )
    main_topics: List[str] = Field(
        ..., description="A list of main topics covered in the video"
    )
    key_takeaways: List[str] = Field(
        ..., description="The most important points from the entire video"
    )
    target_audience: str = Field(
        ..., description="The intended audience for this content"
    )
