# ml_engine.py

import time
import os
from shared_types import Category

from ml.baseline_model import baseline_classify, baseline_urgency_score
from ml.transformer_model import (
    transformer_classify,
    transformer_urgency_score,
)
from ml.embedding_model import get_embedding as _get_embedding
from ml.storm_detection import (
    is_storm as _is_storm,
    create_master_incident as _create_master_incident,
)

_last_latency_ms = 0.0

VALID_CATEGORIES = {"Billing", "Technical", "Legal"}


def classify(text: str) -> Category:
    global _last_latency_ms

    start = time.perf_counter()

    if os.getenv("MODEL_FALLBACK"):
        result = baseline_classify(text)
    else:
        result = transformer_classify(text)

    _last_latency_ms = (time.perf_counter() - start) * 1000

    if result not in VALID_CATEGORIES:
        return "Technical"

    return result


def urgency_score(text: str) -> float:
    global _last_latency_ms

    start = time.perf_counter()

    if os.getenv("MODEL_FALLBACK"):
        score = baseline_urgency_score(text)
    else:
        score = transformer_urgency_score(text)

    _last_latency_ms = (time.perf_counter() - start) * 1000

    score = max(0.0, min(1.0, float(score)))
    return score


def get_embedding(text: str) -> list:
    global _last_latency_ms

    start = time.perf_counter()
    embedding = _get_embedding(text)
    _last_latency_ms = (time.perf_counter() - start) * 1000

    return embedding


def is_storm(recent_tickets):
    return _is_storm(recent_tickets)


def create_master_incident(tickets):
    return _create_master_incident(tickets)


def get_model_latency_ms() -> float:
    return _last_latency_ms
