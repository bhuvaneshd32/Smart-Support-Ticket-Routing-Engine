# test_full_system.py
import os
import time
import redis
import json
import uuid
from shared_types import Ticket
from router import assign_agent

# --- CONFIG ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
QUEUE_KEY = "tickets_queue"
WEBHOOK_URL = os.getenv("WEBHOOK_URL")  # can be None for test

# Connect to Redis
r = redis.from_url(REDIS_URL)

def push_ticket_to_queue(text: str):
    ticket_id = str(uuid.uuid4())
    ticket = Ticket(id=ticket_id, text=text)
    # Push raw JSON to Redis
    r.lpush(QUEUE_KEY, json.dumps(ticket.__dict__))
    print(f"[API TEST] Ticket queued: {ticket_id}")
    return ticket

def simulate_worker_processing():
    """Simulate what worker.py does, printing urgency & agent assigned"""
    while True:
        item = r.blpop(QUEUE_KEY, timeout=2)  # block until a ticket arrives
        if not item:
            break
        _, raw_ticket = item
        data = json.loads(raw_ticket)
        ticket = Ticket(**data)

        # --- ML simulation (replace with real imports if available) ---
        try:
            from ml_engine import classify, urgency_score
        except ImportError:
            classify = lambda t: 'Technical'
            urgency_score = lambda t: 0.5

        ticket.category = classify(ticket.text)
        ticket.urgency_score = urgency_score(ticket.text)

        # --- Router simulation ---
        agent_id = assign_agent(ticket)  # uses your router.py logic

        print(f"[WORKER] Ticket: {ticket.id}")
        print(f"         Text: {ticket.text}")
        print(f"         Category: {ticket.category}")
        print(f"         Urgency Score: {ticket.urgency_score:.2f}")
        print(f"         Assigned Agent: {agent_id}")
        print("-" * 50)

if __name__ == "__main__":
    # Step 1: Push some tickets
    tickets_texts = [
        "My billing is wrong and I need help ASAP!",
        "Technical system is broken, cannot login",
        "Legal question about terms and conditions",
        "Urgent! System crashed during payment",
        "Just a minor technical question",
        "Billing discrepancy noticed",
        "System not responding, broken workflow",
        "Urgent legal notice received",
        "App broken, cannot proceed",
        "Request for refund ASAP"
    ]

    for text in tickets_texts:
        push_ticket_to_queue(text)

    time.sleep(1)  # give Redis a moment

    # Step 2: Simulate worker processing
    simulate_worker_processing()