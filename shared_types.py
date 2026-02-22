# shared_types.py  ──  the only file all three members share
from dataclasses import dataclass
from typing import Literal, Optional

Category = Literal['Billing', 'Technical', 'Legal']

@dataclass
class Ticket:
    id: str
    text: str
    category: Optional[Category]  = None
    urgency_score: float          = 0.0   # S ∈ [0,1]
    embedding: Optional[list]     = None   # filled by Member A
    is_duplicate: bool            = False
    master_incident_id: Optional[str] = None
