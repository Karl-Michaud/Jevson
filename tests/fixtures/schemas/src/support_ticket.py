from pydantic import BaseModel, Field
from typing import List, Literal

class SupportTicket(BaseModel):
    """Structured representation of a customer support ticket."""
    ticket_id: str
    severity: Literal["low", "medium", "high", "critical"]
    category: str = Field(description="e.g., billing, technical, account")
    description: str
    affected_services: List[str]
