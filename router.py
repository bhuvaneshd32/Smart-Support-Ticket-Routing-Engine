# router.py

import heapq
import time
from collections import deque
from typing import Optional
from shared_types import Ticket
from agent_registry import AgentRegistry

# PRIORITY QUEUE
_queue = []
_counter = 0 

def enqueue(ticket: Ticket) -> None:
    global _counter
    heapq.heappush(_queue, (-ticket.urgency_score, _counter, ticket))
    _counter += 1

def dequeue() -> Optional[Ticket]:
    if not _queue:
        return None
    return heapq.heappop(_queue)[2]

def get_queue_depth() -> int:
    return len(_queue)

# AGENT REGISTRY
registry = AgentRegistry()

def assign_agent(ticket: Ticket) -> str:
    return registry.assign(ticket)

# STORM WINDOW DETECTION
_recent_tickets = deque(maxlen=200)
STORM_WINDOW_SECONDS = 300  
STORM_THRESHOLD = 10

def check_storm_window(ticket: Ticket) -> bool:
    now = time.time()
    _recent_tickets.append((now, ticket))

    while _recent_tickets and now - _recent_tickets[0][0] > STORM_WINDOW_SECONDS:
        _recent_tickets.popleft()

    return len(_recent_tickets) > STORM_THRESHOLD