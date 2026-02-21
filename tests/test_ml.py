# tests/test_ml.py

import os
from ml_engine import (
    classify,
    urgency_score,
    get_model_latency_ms,
    get_embedding,
    is_storm,
    create_master_incident,
)
from shared_types import Ticket


# --------------------------
# Classification Tests
# --------------------------

def test_billing_classification():
    result = classify("Please refund my subscription payment")
    assert result in ["Billing", "Technical", "Legal"]


def test_technical_classification():
    result = classify("Server is down and not working")
    assert result in ["Billing", "Technical", "Legal"]


def test_legal_classification():
    result = classify("I need a copy of the privacy policy")
    assert result in ["Billing", "Technical", "Legal"]


def test_empty_input_classification():
    result = classify("")
    assert isinstance(result, str)


def test_category_type():
    result = classify("Refund my invoice")
    assert isinstance(result, str)


# --------------------------
# Urgency Tests
# --------------------------

def test_urgency_high():
    score = urgency_score("This is urgent and the system is down immediately")
    assert 0 <= score <= 1
    assert score > 0.5  # should detect urgency


def test_urgency_zero():
    score = urgency_score("I have a general question")
    assert 0 <= score < 0.2  # transformer returns small probability


def test_urgency_type():
    score = urgency_score("ASAP fix this issue")
    assert isinstance(score, float)


# --------------------------
# Latency Tests
# --------------------------

def test_latency_positive():
    classify("Test message")
    latency = get_model_latency_ms()
    assert latency > 0


def test_multiple_calls_latency():
    classify("Another test")
    latency1 = get_model_latency_ms()
    classify("Yet another test")
    latency2 = get_model_latency_ms()
    assert latency2 >= 0


# --------------------------
# Embedding & Storm Tests
# --------------------------

def test_storm_detection_true():
    tickets = []
    for i in range(11):
        t = Ticket(id=str(i), text="Server is down urgent")
        t.embedding = get_embedding(t.text)
        tickets.append(t)

    assert is_storm(tickets) is True


def test_storm_detection_false():
    tickets = []
    texts = [f"Different message {i}" for i in range(11)]

    for i, text in enumerate(texts):
        t = Ticket(id=str(i), text=text)
        t.embedding = get_embedding(t.text)
        tickets.append(t)

    assert is_storm(tickets) is False


def test_master_incident_creation():
    tickets = [Ticket(id=str(i), text="Test") for i in range(3)]

    master_id = create_master_incident(tickets)

    for t in tickets:
        assert t.is_duplicate is True
        assert t.master_incident_id == master_id


# --------------------------
# Fallback Test
# --------------------------

def test_model_fallback():
    os.environ["MODEL_FALLBACK"] = "1"

    result = classify("Please refund my payment")
    score = urgency_score("urgent issue")

    assert isinstance(result, str)
    assert 0 <= score <= 1

    del os.environ["MODEL_FALLBACK"]
