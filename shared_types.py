# shared_types.py

from dataclasses import dataclass
from typing import Literal, Optional

Category = Literal["Billing", "Technical", "Legal"]

@dataclass
class Ticket:
    id: str
    text: str
    category: Optional[Category] = None
    urgency_score: float = 0.0
    embedding: Optional[list] = None
    is_duplicate: bool = False
    master_incident_id: Optional[str] = None
