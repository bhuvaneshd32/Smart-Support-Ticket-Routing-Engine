# tests/test_router.py

from shared_types import Ticket
from router import enqueue, dequeue, get_queue_depth, assign_agent

def test_priority_queue():
    t1 = Ticket(id="1", text="Low", urgency_score=0.2)
    t2 = Ticket(id="2", text="High", urgency_score=0.9)

    enqueue(t1)
    enqueue(t2)

    first = dequeue()
    assert first.id == "2"

def test_agent_assignment():
    t = Ticket(id="3", text="Billing issue", category="Billing", urgency_score=0.5)
    agent = assign_agent(t)
    assert agent in ["agent-1", "agent-2", "agent-3"]