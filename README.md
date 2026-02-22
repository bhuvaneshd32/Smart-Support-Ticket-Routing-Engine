
# Smart-Support Ticket Routing Engine

A scalable, fault-tolerant support ticket routing system built using FastAPI, Redis, and Transformer-based NLP models.

This system classifies support tickets, computes urgency, assigns the most suitable agent, detects semantic ticket storms, and automatically fails over under high latency conditions.

---

## Overview

Modern SaaS platforms receive thousands of support tickets daily. Manual triage becomes inefficient during high traffic and outage scenarios.

### This system provides:

- Automated ticket classification (Billing / Technical / Legal)
- Continuous urgency scoring ∈ [0,1]
- Asynchronous queue-based processing with Redis
- Skill-based agent routing
- Semantic duplicate storm detection
- Circuit breaker model failover
- Dockerized deployment

---

# Milestone 1 – Minimum Viable Router (MVR)

## Objective

Establish a working end-to-end ticket processing pipeline.

## Implemented Features

- Baseline text classification using TF-IDF + Logistic Regression
- Regex-based urgency scoring
- In-memory priority queue (heap-based)
- Skill-based agent assignment
- Synchronous processing mode
- REST API:
  - `POST /ticket`
  - `GET /health`

## Behavior

If Redis is unavailable:

- Tickets are processed synchronously
- API returns `200 OK`
- Classification, urgency scoring, and agent assignment occur immediately

---

# Milestone 2 – Intelligent Queue

## Objective

Upgrade to asynchronous, scalable, production-style architecture.

## Implemented Features

- Redis-based asynchronous broker
- Background worker service
- API returns `202 Accepted` immediately
- Transformer-based classification (DistilBERT)
- Zero-shot urgency scoring (BART)
- Atomic Redis locking (`SETNX`) to prevent duplicate processing
- Webhook trigger for high-urgency tickets (urgency > 0.8)

## Asynchronous Flow

```

Client → FastAPI → Redis Queue → Worker → ML Engine → Router

````

---

# Milestone 3 – Autonomous Orchestrator

## Objective

Introduce semantic intelligence, system resilience, and self-healing mechanisms to handle traffic spikes and ticket storms.

---

## 1. Semantic Storm Detection

To prevent alert flooding during outages, the system performs semantic deduplication using sentence embeddings (`all-MiniLM-L6-v2`) and cosine similarity.

### Cosine Similarity Formula

similarity = (A · B) / (||A|| × ||B||)
Where:

A · B → Dot product of the two embedding vectors

||A|| → Magnitude (L2 norm) of vector A

||B|| → Magnitude (L2 norm) of vector B 

### Storm Condition

If:

- Similarity > 0.9  
- More than 10 tickets within a 5-minute window  

Then:

- A **Master Incident** is created
- Duplicate tickets are marked
- Individual routing and alerting are suppressed

### Configurable Parameters (config.py)

```python
STORM_WINDOW_SECONDS = 300
STORM_TICKET_THRESHOLD = 10
````

This ensures system stability during outage spikes.

---

## 2. Circuit Breaker

To protect the system under high latency conditions, a circuit breaker mechanism is implemented.

### Open Circuit Condition

If:

* Model inference latency > 500ms
* For 3 consecutive calls

Then:

```bash
MODEL_FALLBACK=1
```

The system switches to the lightweight baseline model.

### Close Circuit Condition

If:

* Latency < 200ms
* For 5 consecutive calls

Then:

* Circuit closes automatically
* Transformer model is restored

### Configurable Parameters

```python
CIRCUIT_BREAKER_LATENCY_MS = 500
CIRCUIT_BREAKER_OPEN_COUNT = 3
CIRCUIT_BREAKER_CLOSE_COUNT = 5
CIRCUIT_BREAKER_FAST_MS = 200
```

This enables self-healing under load.

---

# Testing

The system includes comprehensive unit and integration tests.

## Run All Tests

```bash
pytest
```

## Run Full System Simulation

```bash
python test_full_system.py
```

### Tests Cover

* Classification correctness
* Urgency scoring validation
* Queue behavior
* Agent assignment logic
* Circuit breaker switching
* Storm detection logic
* End-to-end flow validation

---

# Configuration

All environment variables and system thresholds are centralized in `config.py`.

## Key Variables

* `REDIS_URL`
* `REDIS_QUEUE_KEY`
* `WEBHOOK_URL`
* `URGENCY_WEBHOOK_THRESHOLD`
* `MODEL_FALLBACK`
* Circuit breaker thresholds
* Storm detection window parameters

No infrastructure-specific values are hardcoded inside business logic.

---

# Project Structure

```
SMART-SUPPORT-TICKET-ROUTING-ENGINE/
│
├── api_server.py
├── worker.py
├── router.py
├── agent_registry.py
├── ml_engine.py
├── shared_types.py
├── config.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
│
├── ml/
│   ├── baseline_model.py
│   ├── transformer_model.py
│   ├── embedding_model.py
│   └── storm_detection.py
│
├── tests/
│   ├── test_ml.py
│   ├── test_api.py
│   └── test_router.py
│
└── test_full_system.py
```

---

# Tech Stack

## Backend & Infrastructure

* Python
* FastAPI
* Redis
* Docker
* Uvicorn

## Machine Learning

* scikit-learn
* Transformers (HuggingFace)
* PyTorch
* Sentence-Transformers
* NumPy

## Testing

* Pytest
* Pytest-asyncio

---

# Capabilities Delivered

* Asynchronous ticket ingestion
* Transformer-based NLP classification
* Continuous urgency scoring
* Skill-based agent routing optimization
* Semantic duplicate suppression
* Circuit breaker failover mechanism
* Horizontal worker scalability
* Dockerized deployment
* Config-driven system tuning
* Fully tested modular architecture
