# tests/test_api.py  ──  Member B owns this file
# Tests run entirely against mocked stubs — no dependency on A or C.
# Run: pytest tests/test_api.py -v

import os
import sys
import json
import asyncio
import pytest
import pytest_asyncio

# Add parent dir to path so we can import our modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Patch Redis BEFORE importing the app ─────────────────────────────────────
# This forces the API into Phase 1 (sync) mode during tests,
# so no real Redis is needed.
import unittest.mock as mock
mock_redis = None  # We'll set this per-test if needed

from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

# Force sync mode (no Redis) for most tests
import api_server
api_server._redis_client = None  # type: ignore

from api_server import app

# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 TESTS — Sync API behaviour
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_ticket_returns_200():
    """POST /ticket should return 200 with a complete Ticket JSON in sync mode."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/ticket", json={"text": "My invoice is wrong"})
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert "category" in data
    assert "urgency_score" in data
    assert isinstance(data["urgency_score"], float)


@pytest.mark.asyncio
async def test_post_ticket_uses_provided_id():
    """If an id is supplied in the request, it must appear in the response."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/ticket", json={"id": "ticket-abc-123", "text": "Server is down ASAP!"})
    assert resp.status_code == 200
    assert resp.json()["id"] == "ticket-abc-123"


@pytest.mark.asyncio
async def test_post_ticket_autogenerates_id():
    """If no id is supplied, the API should generate one (UUID)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/ticket", json={"text": "Need legal advice"})
    assert resp.status_code == 200
    ticket_id = resp.json()["id"]
    assert ticket_id is not None
    assert len(ticket_id) > 0


@pytest.mark.asyncio
async def test_get_health_returns_ok():
    """GET /health must return {status: ok, queue_depth: int, circuit_breaker: str}."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "queue_depth" in data
    assert data["circuit_breaker"] in ("open", "closed")


@pytest.mark.asyncio
async def test_get_health_circuit_breaker_closed_by_default():
    """Circuit breaker should be 'closed' when MODEL_FALLBACK is not set."""
    os.environ.pop("MODEL_FALLBACK", None)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.json()["circuit_breaker"] == "closed"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 TESTS — Async broker mode
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_post_ticket_returns_202_when_redis_available():
    """When Redis is available, POST /ticket should return 202 Accepted."""
    mock_redis_instance = mock.AsyncMock()
    mock_redis_instance.lpush = mock.AsyncMock(return_value=1)
    api_server._redis_client = mock_redis_instance

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/ticket", json={"text": "Billing issue urgent"})
    assert resp.status_code == 202
    data = resp.json()
    assert data["status"] == "accepted"
    assert "ticket_id" in data

    # Restore sync mode for other tests
    api_server._redis_client = None


@pytest.mark.asyncio
async def test_202_response_calls_redis_lpush():
    """When Redis is active, the ticket payload must be pushed to Redis."""
    mock_redis_instance = mock.AsyncMock()
    mock_redis_instance.lpush = mock.AsyncMock(return_value=1)
    api_server._redis_client = mock_redis_instance

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        await ac.post("/ticket", json={"id": "t-redis-01", "text": "Test ticket"})

    mock_redis_instance.lpush.assert_called_once()
    call_args = mock_redis_instance.lpush.call_args
    queue_key = call_args[0][0]
    raw_payload = call_args[0][1]
    assert queue_key == "tickets_queue"
    payload = json.loads(raw_payload)
    assert payload["id"] == "t-redis-01"

    api_server._redis_client = None


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 TESTS — Stress test (concurrency)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_15_concurrent_requests_all_accepted():
    """
    Launch 15 simultaneous POST /ticket requests.
    All should succeed (200 in sync mode).
    No request should be dropped.
    """
    api_server._redis_client = None  # sync mode

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        tasks = [
            ac.post("/ticket", json={"text": f"Concurrent ticket #{i}"})
            for i in range(15)
        ]
        responses = await asyncio.gather(*tasks)

    statuses = [r.status_code for r in responses]
    assert all(s == 200 for s in statuses), f"Some requests failed: {statuses}"
    ids = [r.json()["id"] for r in responses]
    assert len(set(ids)) == 15, "All ticket IDs must be unique"


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 TESTS — Circuit breaker state reflected in /health
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_reports_open_circuit_when_env_set():
    """When MODEL_FALLBACK=1 is set, /health must report circuit_breaker=open."""
    os.environ["MODEL_FALLBACK"] = "1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
    assert resp.json()["circuit_breaker"] == "open"
    os.environ.pop("MODEL_FALLBACK")


# ─────────────────────────────────────────────────────────────────────────────
# WORKER UNIT TESTS — Circuit breaker logic
# ─────────────────────────────────────────────────────────────────────────────

def test_circuit_breaker_opens_after_3_slow_calls():
    """Three consecutive slow calls should open the circuit."""
    import worker
    os.environ.pop("MODEL_FALLBACK", None)
    worker._consecutive_slow_calls = 0
    worker._consecutive_fast_calls = 0

    worker._update_circuit_breaker(600)  # slow
    worker._update_circuit_breaker(700)  # slow
    worker._update_circuit_breaker(800)  # slow — should open

    assert os.getenv("MODEL_FALLBACK") == "1"
    os.environ.pop("MODEL_FALLBACK")
    worker._consecutive_slow_calls = 0


def test_circuit_breaker_closes_after_5_fast_calls():
    """Five consecutive fast calls should close an open circuit."""
    import worker
    os.environ["MODEL_FALLBACK"] = "1"
    worker._consecutive_slow_calls = 0
    worker._consecutive_fast_calls = 0

    for _ in range(5):
        worker._update_circuit_breaker(100)  # fast

    assert os.getenv("MODEL_FALLBACK") is None


def test_circuit_breaker_resets_on_mid_band_latency():
    """A mid-band latency (200–500ms) should reset counters without changing state."""
    import worker
    os.environ.pop("MODEL_FALLBACK", None)
    worker._consecutive_slow_calls = 2  # almost open
    worker._consecutive_fast_calls = 0

    worker._update_circuit_breaker(350)  # mid-band

    assert worker._consecutive_slow_calls == 0
    assert os.getenv("MODEL_FALLBACK") is None
