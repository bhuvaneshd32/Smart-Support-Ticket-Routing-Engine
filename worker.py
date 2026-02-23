# worker.py  ──  Member B owns this file
import os, json, asyncio, httpx
import redis.asyncio as aioredis

from shared_types import Ticket
from config import (
    REDIS_URL, REDIS_QUEUE_KEY, REDIS_LOCK_TTL_SECONDS,
    URGENCY_WEBHOOK_THRESHOLD, WEBHOOK_URL,
    CIRCUIT_BREAKER_LATENCY_MS, CIRCUIT_BREAKER_OPEN_COUNT,
    CIRCUIT_BREAKER_CLOSE_COUNT, CIRCUIT_BREAKER_FAST_MS,
    MODEL_FALLBACK_ENV_VAR,
)

# ── Import Guards ─────────────────────────────────────────────────────────────
try:
    from ml_engine import classify, urgency_score, get_model_latency_ms, is_storm, get_embedding, create_master_incident
except ImportError:
    classify = lambda t: "Technical"
    urgency_score = lambda t: 0.5
    get_model_latency_ms = lambda: 100.0
    is_storm = lambda tickets: False
    get_embedding = lambda t: [0.0] * 384
    create_master_incident = lambda tickets: "stub-incident-id"

try:
    from router import enqueue, assign_agent, check_storm_window, get_queue_depth
except ImportError:
    enqueue = lambda t: None
    assign_agent = lambda t: "agent-1"
    check_storm_window = lambda t: False
    get_queue_depth = lambda: 0

# ── Circuit Breaker ───────────────────────────────────────────────────────────
_consecutive_slow_calls: int = 0
_consecutive_fast_calls: int = 0

def _update_circuit_breaker(latency_ms: float) -> None:
    global _consecutive_slow_calls, _consecutive_fast_calls
    if latency_ms > CIRCUIT_BREAKER_LATENCY_MS:
        _consecutive_slow_calls += 1
        _consecutive_fast_calls = 0
        if _consecutive_slow_calls >= CIRCUIT_BREAKER_OPEN_COUNT:
            if not os.getenv(MODEL_FALLBACK_ENV_VAR):
                os.environ[MODEL_FALLBACK_ENV_VAR] = "1"
                print(f"⚡ CIRCUIT OPEN — {_consecutive_slow_calls} consecutive calls exceeded {CIRCUIT_BREAKER_LATENCY_MS}ms")
    elif latency_ms < CIRCUIT_BREAKER_FAST_MS:
        _consecutive_fast_calls += 1
        _consecutive_slow_calls = 0
        if _consecutive_fast_calls >= CIRCUIT_BREAKER_CLOSE_COUNT:
            if os.getenv(MODEL_FALLBACK_ENV_VAR):
                del os.environ[MODEL_FALLBACK_ENV_VAR]
                _consecutive_fast_calls = 0
                print(f"✅ CIRCUIT CLOSED — {_consecutive_fast_calls} consecutive fast calls below {CIRCUIT_BREAKER_FAST_MS}ms")
    else:
        _consecutive_slow_calls = 0
        _consecutive_fast_calls = 0

# ── Webhook (original — untouched) ───────────────────────────────────────────
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1475144580692447244/EWlitNhR06fGJFRIXuafmbUgQmcO4vRXIhJEinZK-jMTVmbTgBv9nUEq15I9kXPvM3Hl"

async def _fire_webhook(payload: dict) -> None:
    """POST a JSON payload to Slack/Discord webhook."""
    if not WEBHOOK_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(WEBHOOK_URL, json=payload)
            print(f"📣  Webhook fired → HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Webhook delivery failed: {e}")

async def _fire_discord(payload: dict) -> None:
    """Fire to hardcoded Discord webhook."""
    try:
        discord_payload = {
            "content": payload.get("text", ""),
            "username": "SmartSupport Bot",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(DISCORD_WEBHOOK, json=discord_payload)
            print(f"📣  Discord webhook fired → HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Discord webhook failed: {e}")

# ── Store in Redis for dashboard feed ─────────────────────────────────────────
RECENT_TICKETS_KEY = "recent_tickets"

async def _store_recent(redis: aioredis.Redis, ticket: Ticket, agent_id: str) -> None:
    try:
        record = json.dumps({
            "id": ticket.id,
            "text": ticket.text[:120],
            "category": ticket.category,
            "urgency_score": round(ticket.urgency_score, 3),
            "is_duplicate": ticket.is_duplicate,
            "master_incident_id": ticket.master_incident_id,
            "assigned_agent": agent_id,
        })
        await redis.lpush(RECENT_TICKETS_KEY, record)
        await redis.ltrim(RECENT_TICKETS_KEY, 0, 29)
    except Exception as e:
        print(f"⚠️  Could not store recent ticket: {e}")

# ── Storm batch ───────────────────────────────────────────────────────────────
_storm_batch: list[Ticket] = []

async def _handle_storm(ticket: Ticket, redis: aioredis.Redis) -> None:
    global _storm_batch
    _storm_batch.append(ticket)
    await asyncio.sleep(0.1)
    if not _storm_batch:
        return
    batch, _storm_batch = _storm_batch, []
    if not batch:
        return
    incident_id = create_master_incident(batch)
    print(f"🌊 STORM DETECTED — Master Incident {incident_id} created for {len(batch)} tickets. Individual routing suppressed.")
    msg = {"text": f"🌊 *Ticket Storm Detected!*\n*Master Incident:* `{incident_id}`\n*Tickets suppressed:* {len(batch)}\n*Sample:* {batch[0].text[:150]}"}
    await _fire_webhook(msg)
    await _fire_discord(msg)
    # Store storm event for dashboard
    storm_ticket = Ticket(
        id=incident_id,
        text=f"[STORM] {len(batch)} near-identical tickets suppressed → Master Incident",
        category="Technical",
        urgency_score=0.99,
        is_duplicate=True,
        master_incident_id=incident_id,
    )
    await _store_recent(redis, storm_ticket, "storm-handler")

# ── Core processor ────────────────────────────────────────────────────────────
async def _process_ticket(raw: str, redis: aioredis.Redis) -> None:
    data = json.loads(raw)
    ticket = Ticket(id=data["id"], text=data["text"])

    # Atomic lock — prevent duplicate processing
    lock_key = f"ticket:{ticket.id}:lock"
    acquired = await redis.set(lock_key, "1", nx=True, ex=REDIS_LOCK_TTL_SECONDS)
    if not acquired:
        print(f"🔒 Duplicate skipped: {ticket.id}")
        return

    try:
        print(f"🎫 Processing ticket {ticket.id}")

        # Storm check first (fast gate)
        if check_storm_window(ticket):
            await _handle_storm(ticket, redis)
            return

        # ML classification
        ticket.category = classify(ticket.text)
        ticket.urgency_score = urgency_score(ticket.text)

        # Circuit breaker tracking
        latency = get_model_latency_ms()
        _update_circuit_breaker(latency)

        # Route to agent
        enqueue(ticket)
        agent_id = assign_agent(ticket)

        print(f"✅ Ticket {ticket.id} → category={ticket.category}, urgency={ticket.urgency_score:.2f}, agent={agent_id}, latency={latency:.1f}ms")

        # Store for dashboard feed
        await _store_recent(redis, ticket, agent_id)

        # Webhook for high urgency
        if ticket.urgency_score > URGENCY_WEBHOOK_THRESHOLD:
            msg = {
                "text": (
                    f"🚨 *High-Urgency Ticket* `{ticket.id[:8]}`\n"
                    f"*Category:* {ticket.category}\n"
                    f"*Urgency:* {ticket.urgency_score:.2f}\n"
                    f"*Assigned to:* {agent_id}\n"
                    f"*Text:* {ticket.text[:200]}"
                )
            }
            await _fire_webhook(msg)
            await _fire_discord(msg)

    finally:
        pass  # Lock expires naturally

# ── Main loop ─────────────────────────────────────────────────────────────────
async def run_worker() -> None:
    redis = aioredis.from_url(REDIS_URL, decode_responses=True, ssl_cert_reqs=None)
    print(f"👷 Worker started — listening on {REDIS_QUEUE_KEY}")
    while True:
        try:
            result = await redis.blpop(REDIS_QUEUE_KEY, timeout=5)
            if result is None:
                continue
            _, raw = result
            asyncio.create_task(_process_ticket(raw, redis))
        except aioredis.ConnectionError as e:
            print(f"❌ Redis connection lost: {e}. Retrying in 3s…")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"❌ Unexpected worker error: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run_worker())
