# api_server.py  ──  Member B owns this file
# FastAPI server: POST /ticket, GET /health
# Uses import guards so it runs even before Member A / C commit their code.

import os
import json
import uuid
import httpx
import asyncio
from dataclasses import asdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from shared_types import Ticket
from config import (
    REDIS_URL,
    REDIS_QUEUE_KEY,
    URGENCY_WEBHOOK_THRESHOLD,
    WEBHOOK_URL,
)

# ── Import Guards ─────────────────────────────────────────────────────────────
# These allow the API to run solo from Hour 0:30 without waiting for A or C.

try:
    from ml_engine import classify, urgency_score
except ImportError:
    classify = lambda t: "Technical"
    urgency_score = lambda t: 0.5

try:
    from router import enqueue, assign_agent, get_queue_depth
except ImportError:
    enqueue = lambda t: None
    assign_agent = lambda t: "agent-1"
    get_queue_depth = lambda: 0

# ── Redis (optional — only used in Phase 2+) ──────────────────────────────────
try:
    import redis.asyncio as aioredis
    _redis_client: aioredis.Redis | None = None
    REDIS_AVAILABLE = True
except ImportError:
    _redis_client = None
    REDIS_AVAILABLE = False

# ── Circuit Breaker State (shared with worker via module-level state) ──────────
# worker.py manages the actual env var; we just read it here for /health
def _circuit_breaker_state() -> str:
    return "open" if os.getenv("MODEL_FALLBACK") else "closed"

# ── App Lifespan ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_client
    if REDIS_AVAILABLE:
        try:
            _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
            await _redis_client.ping()
            print("✅  Redis connected")
        except Exception as e:
            print(f"⚠️  Redis unavailable ({e}). Running in sync mode.")
            _redis_client = None
    yield
    if _redis_client:
        await _redis_client.aclose()

app = FastAPI(
    title="SmartSupport Routing Engine",
    version="1.0.0",
    lifespan=lifespan,
)

# ── Request / Response Models ─────────────────────────────────────────────────

class TicketRequest(BaseModel):
    id: str | None = None   # auto-generated if omitted
    text: str

class TicketResponse(BaseModel):
    id: str
    text: str
    category: str | None
    urgency_score: float
    is_duplicate: bool
    master_incident_id: str | None
    assigned_agent: str | None = None

class HealthResponse(BaseModel):
    status: str
    queue_depth: int
    circuit_breaker: str

# ── Helper: fire webhook ──────────────────────────────────────────────────────

async def _fire_webhook(ticket: Ticket, agent_id: str) -> None:
    """POST a summary to Slack/Discord if urgency is high."""
    if not WEBHOOK_URL:
        return
    payload = {
        "text": (
            f"🚨 *High-Urgency Ticket* `{ticket.id}`\n"
            f"*Category:* {ticket.category}\n"
            f"*Urgency:* {ticket.urgency_score:.2f}\n"
            f"*Assigned to:* {agent_id}\n"
            f"*Text:* {ticket.text[:200]}"
        )
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(WEBHOOK_URL, json=payload)
    except Exception as e:
        print(f"⚠️  Webhook delivery failed: {e}")

# ── Phase 1: Synchronous processing (fallback when Redis is unavailable) ───────

def _process_ticket_sync(ticket: Ticket) -> str:
    """Classify, score, enqueue, and assign — all in one synchronous call."""
    ticket.category = classify(ticket.text)
    ticket.urgency_score = urgency_score(ticket.text)
    enqueue(ticket)
    agent_id = assign_agent(ticket)
    return agent_id

# ── POST /ticket ──────────────────────────────────────────────────────────────

@app.post("/ticket", status_code=200)
async def create_ticket(req: TicketRequest):
    """
    Phase 1: Returns 200 with fully processed Ticket JSON (sync).
    Phase 2: Returns 202 Accepted immediately; pushes raw payload to Redis.
    """
    ticket_id = req.id or str(uuid.uuid4())
    ticket = Ticket(id=ticket_id, text=req.text)

    # ── Phase 2 path: async broker available ──────────────────────────────────
    if _redis_client is not None:
        payload = json.dumps({"id": ticket_id, "text": req.text})
        await _redis_client.lpush(REDIS_QUEUE_KEY, payload)
        return JSONResponse(
            status_code=202,
            content={
                "status": "accepted",
                "ticket_id": ticket_id,
                "message": "Ticket queued for processing",
            },
        )

    # ── Phase 1 path: synchronous fallback ───────────────────────────────────
    agent_id = _process_ticket_sync(ticket)
    if ticket.urgency_score > URGENCY_WEBHOOK_THRESHOLD:
        asyncio.create_task(_fire_webhook(ticket, agent_id))

    return TicketResponse(
        id=ticket.id,
        text=ticket.text,
        category=ticket.category,
        urgency_score=ticket.urgency_score,
        is_duplicate=ticket.is_duplicate,
        master_incident_id=ticket.master_incident_id,
        assigned_agent=agent_id,
    )

# ── GET /health ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """
    Phase 1: Returns static queue_depth=0.
    Phase 3: Returns real queue_depth from Redis + real circuit_breaker state.
    """
    depth = 0
    if _redis_client is not None:
        try:
            depth = await _redis_client.llen(REDIS_QUEUE_KEY)
        except Exception:
            depth = -1  # Redis error
    else:
        depth = get_queue_depth()

    return HealthResponse(
        status="ok",
        queue_depth=depth,
        circuit_breaker=_circuit_breaker_state(),
    )

# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("api_server:app", host=API_HOST, port=API_PORT, reload=True)
