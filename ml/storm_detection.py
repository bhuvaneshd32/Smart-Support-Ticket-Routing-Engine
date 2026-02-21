# ml/storm_detection.py

import numpy as np
import uuid
from shared_types import Ticket


def cosine_similarity(a, b):
    a = np.array(a)
    b = np.array(b)

    if len(a) == 0 or len(b) == 0:
        return 0.0

    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def is_storm(recent_tickets: list[Ticket]) -> bool:
    if len(recent_tickets) <= 10:
        return False

    embeddings = [t.embedding for t in recent_tickets if t.embedding]

    if len(embeddings) <= 10:
        return False

    count_similar = 0

    for i in range(len(embeddings)):
        for j in range(i + 1, len(embeddings)):
            sim = cosine_similarity(embeddings[i], embeddings[j])
            if sim > 0.9:
                count_similar += 1

    return count_similar >= 10


def create_master_incident(tickets: list[Ticket]) -> str:
    master_id = str(uuid.uuid4())

    for ticket in tickets:
        ticket.is_duplicate = True
        ticket.master_incident_id = master_id

    return master_id
