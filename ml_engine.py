# ml_engine.py

import time
import os
from ml.embedding_model import get_embedding as _get_embedding
from ml.storm_detection import is_storm as _is_storm
from ml.storm_detection import create_master_incident as _create_master_incident

from ml.baseline_model import baseline_classify, baseline_urgency_score
from ml.transformer_model import (
    transformer_classify,
    transformer_urgency_score,
)

_last_latency_ms = 0.0


def classify(text: str) -> str:
    global _last_latency_ms

    start = time.perf_counter()

    # Circuit breaker fallback
    if os.getenv("MODEL_FALLBACK"):
        result = baseline_classify(text)
    else:
        result = transformer_classify(text)

    _last_latency_ms = (time.perf_counter() - start) * 1000

    return result


def urgency_score(text: str) -> float:
    global _last_latency_ms

    start = time.perf_counter()

    if os.getenv("MODEL_FALLBACK"):
        score = baseline_urgency_score(text)
    else:
        score = transformer_urgency_score(text)

    _last_latency_ms = (time.perf_counter() - start) * 1000

    return score


def get_model_latency_ms() -> float:
    return _last_latency_ms

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
