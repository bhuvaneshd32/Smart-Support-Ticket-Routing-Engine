# api_server.py  ──  Member B owns this file
import os
import json
import uuid
import httpx
import asyncio
from dataclasses import asdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel

from shared_types import Ticket
from config import (
    REDIS_URL,
    REDIS_QUEUE_KEY,
    URGENCY_WEBHOOK_THRESHOLD,
    WEBHOOK_URL,
)

# ── Import Guards ─────────────────────────────────────────────────────────────
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

# ── Redis ─────────────────────────────────────────────────────────────────────
try:
    import redis.asyncio as aioredis
    _redis_client = None
    REDIS_AVAILABLE = True
except ImportError:
    _redis_client = None
    REDIS_AVAILABLE = False

RECENT_TICKETS_KEY = "recent_tickets"
RECENT_TICKETS_MAX = 20

def _circuit_breaker_state() -> str:
    return "open" if os.getenv("MODEL_FALLBACK") else "closed"

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

app = FastAPI(title="SmartSupport Routing Engine", version="1.0.0", lifespan=lifespan)

class TicketRequest(BaseModel):
    id: str | None = None
    text: str

class HealthResponse(BaseModel):
    status: str
    queue_depth: int
    circuit_breaker: str

# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_path = Path(__file__).parent / "dashboard.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text())
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)

# ── POST /ticket ──────────────────────────────────────────────────────────────
@app.post("/ticket")
async def create_ticket(req: TicketRequest):
    ticket_id = req.id or str(uuid.uuid4())
    ticket = Ticket(id=ticket_id, text=req.text)

    if _redis_client is not None:
        payload = json.dumps({"id": ticket_id, "text": req.text})
        await _redis_client.lpush(REDIS_QUEUE_KEY, payload)
        return JSONResponse(status_code=202, content={
            "status": "accepted",
            "ticket_id": ticket_id,
            "message": "Ticket queued for processing",
        })

    ticket.category = classify(ticket.text)
    ticket.urgency_score = urgency_score(ticket.text)
    enqueue(ticket)
    agent_id = assign_agent(ticket)
    result = {
        "id": ticket.id, "text": ticket.text,
        "category": ticket.category,
        "urgency_score": ticket.urgency_score,
        "is_duplicate": ticket.is_duplicate,
        "master_incident_id": ticket.master_incident_id,
        "assigned_agent": agent_id,
    }
    return JSONResponse(status_code=200, content=result)

# ── GET /health ───────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    depth = 0
    if _redis_client is not None:
        try:
            depth = await _redis_client.llen(REDIS_QUEUE_KEY)
        except Exception:
            depth = -1
    else:
        depth = get_queue_depth()
    return HealthResponse(status="ok", queue_depth=depth, circuit_breaker=_circuit_breaker_state())

# ── GET /tickets/recent ───────────────────────────────────────────────────────
@app.get("/tickets/recent")
async def recent_tickets():
    if _redis_client is None:
        return JSONResponse(content=[])
    try:
        raw_list = await _redis_client.lrange(RECENT_TICKETS_KEY, 0, RECENT_TICKETS_MAX - 1)
        tickets = [json.loads(r) for r in raw_list if r]
        return JSONResponse(content=tickets)
    except Exception:
        return JSONResponse(content=[])

if __name__ == "__main__":
    import uvicorn
    from config import API_HOST, API_PORT
    uvicorn.run("api_server:app", host=API_HOST, port=API_PORT, reload=True)
