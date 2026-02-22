
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from shared_types import Ticket
from router import enqueue, dequeue, assign_agent, check_storm_window,get_queue_depth

# create tickets
t1 = Ticket(id="1", text="low", category="Billing", urgency_score=0.2)
t2 = Ticket(id="2", text="high", category="Technical", urgency_score=0.9)

enqueue(t1)
enqueue(t2)

print("Queue depth:", get_queue_depth())

first = dequeue()
print("Dequeued first:", first.id)

agent = assign_agent(first)
print("Assigned agent:", agent)

# storm test
for i in range(11):
    storm = check_storm_window(Ticket(id=str(i), text="same", urgency_score=0.5))
print("Storm detected:", storm)