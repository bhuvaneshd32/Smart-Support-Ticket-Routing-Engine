# stubs.py  ──  mock implementations for all cross-member functions
# Everyone uses these until the real modules are ready

from shared_types import Ticket, Category
from typing import Optional
import uuid

# ── Member A stubs (ml_engine.py) ─────────────────────────────────────────────

def classify(text: str) -> Category:
    """Stub: always returns 'Technical'"""
    return 'Technical'

def urgency_score(text: str) -> float:
    """Stub: always returns 0.5"""
    return 0.5

def get_embedding(text: str) -> list[float]:
    """Stub: returns a zero vector of length 384"""
    return [0.0] * 384

def is_storm(recent_tickets: list) -> bool:
    """Stub: always returns False"""
    return False

def get_model_latency_ms() -> float:
    """Stub: returns 100ms"""
    return 100.0

def create_master_incident(tickets: list) -> str:
    """Stub: returns a new UUID and marks tickets as duplicates"""
    incident_id = str(uuid.uuid4())
    for t in tickets:
        t.is_duplicate = True
        t.master_incident_id = incident_id
    return incident_id

# ── Member C stubs (router.py) ────────────────────────────────────────────────

def enqueue(ticket: Ticket) -> None:
    """Stub: no-op"""
    pass

def assign_agent(ticket: Ticket) -> str:
    """Stub: always returns 'agent-1'"""
    return 'agent-1'

def get_queue_depth() -> int:
    """Stub: always returns 0"""
    return 0

def check_storm_window(ticket: Ticket) -> bool:
    """Stub: always returns False"""
    return False
