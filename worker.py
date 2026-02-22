# worker.py  ──  Member B owns this file
# Background worker: pulls tickets from Redis, processes them, fires webhooks.
# Implements:
#   Phase 2 — async BLPOP loop + SETNX atomic locking + webhook trigger
#   Phase 3 — circuit breaker + storm short-circuit

import os
import json
import asyncio
import httpx

import redis.asyncio as aioredis

from shared_types import Ticket
from config import (
    REDIS_URL,
    REDIS_QUEUE_KEY,
    REDIS_LOCK_TTL_SECONDS,
    URGENCY_WEBHOOK_THRESHOLD,
    WEBHOOK_URL,
    CIRCUIT_BREAKER_LATENCY_MS,
    CIRCUIT_BREAKER_OPEN_COUNT,
    CIRCUIT_BREAKER_CLOSE_COUNT,
    CIRCUIT_BREAKER_FAST_MS,
    MODEL_FALLBACK_ENV_VAR,
)

# ── Import Guards ─────────────────────────────────────────────────────────────

try:
    from ml_engine import (
        classify,
        urgency_score,
        get_model_latency_ms,
        is_storm,
        get_embedding,
        create_master_incident,
    )
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

# ── Circuit Breaker State ─────────────────────────────────────────────────────

_consecutive_slow_calls: int = 0
_consecutive_fast_calls: int = 0

def _update_circuit_breaker(latency_ms: float) -> None:
    """
    Track consecutive slow/fast ML calls and flip MODEL_FALLBACK env var.
    Open  → 3+ consecutive calls > 500ms
    Close → 5+ consecutive calls < 200ms
    """
    global _consecutive_slow_calls, _consecutive_fast_calls

    if latency_ms > CIRCUIT_BREAKER_LATENCY_MS:
        _consecutive_slow_calls += 1
        _consecutive_fast_calls = 0
        if _consecutive_slow_calls >= CIRCUIT_BREAKER_OPEN_COUNT:
            if not os.getenv(MODEL_FALLBACK_ENV_VAR):
                os.environ[MODEL_FALLBACK_ENV_VAR] = "1"
                print(
                    f"⚡ CIRCUIT OPEN — {_consecutive_slow_calls} consecutive calls "
                    f"exceeded {CIRCUIT_BREAKER_LATENCY_MS}ms"
                )
    elif latency_ms < CIRCUIT_BREAKER_FAST_MS:
        _consecutive_fast_calls += 1
        _consecutive_slow_calls = 0
        if _consecutive_fast_calls >= CIRCUIT_BREAKER_CLOSE_COUNT:
            if os.getenv(MODEL_FALLBACK_ENV_VAR):
                del os.environ[MODEL_FALLBACK_ENV_VAR]
                _consecutive_fast_calls = 0
                print(
                    f"✅ CIRCUIT CLOSED — {_consecutive_fast_calls} consecutive fast calls "
                    f"below {CIRCUIT_BREAKER_FAST_MS}ms"
                )
    else:
        # Latency in the middle band — reset counters without changing state
        _consecutive_slow_calls = 0
        _consecutive_fast_calls = 0

# ── Webhook Helper ────────────────────────────────────────────────────────────
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1475144580692447244/EWlitNhR06fGJFRIXuafmbUgQmcO4vRXIhJEinZK-jMTVmbTgBv9nUEq15I9kXPvM3Hl"

async def _fire_webhook(payload: dict) -> None:
    try:
        discord_payload = {
            "content": payload.get("text", ""),
            "username": "SmartSupport Bot",
        }
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(DISCORD_WEBHOOK, json=discord_payload)
            print(f"📣  Webhook fired → HTTP {resp.status_code}")
    except Exception as e:
        print(f"⚠️  Webhook delivery failed: {e}")

# ── Storm batch storage (Phase 3) ─────────────────────────────────────────────

_storm_batch: list[Ticket] = []

async def _handle_storm(ticket: Ticket) -> None:
    """
    When check_storm_window signals a storm, collect the batch,
    create a single master incident, and fire ONE consolidated webhook.
    """
    global _storm_batch
    _storm_batch.append(ticket)

    # We wait a short window to let more storm tickets accumulate
    await asyncio.sleep(0.1)

    if not _storm_batch:
        return  # Already handled by another coroutine

    batch, _storm_batch = _storm_batch, []
    if not batch:
        return

    incident_id = create_master_incident(batch)
    print(
        f"🌊 STORM DETECTED — Master Incident {incident_id} "
        f"created for {len(batch)} tickets. Individual routing suppressed."
    )
    await _fire_webhook(
        {
            "text": (
                f"🌊 *Ticket Storm Detected!*\n"
                f"*Master Incident:* `{incident_id}`\n"
                f"*Tickets suppressed:* {len(batch)}\n"
                f"*Sample:* {batch[0].text[:150]}"
            )
        }
    )

# ── Core Ticket Processor ─────────────────────────────────────────────────────

async def _process_ticket(raw: str, redis: aioredis.Redis) -> None:
    """
    Full processing pipeline for a single ticket:
    1. Parse JSON
    2. Acquire atomic lock (SETNX) to prevent duplicate processing
    3. Phase 3: Storm short-circuit check
    4. Classify + urgency score (with circuit breaker tracking)
    5. Enqueue + assign agent
    6. Fire webhook if urgency > threshold
    7. Release lock
    """
    data = json.loads(raw)
    ticket = Ticket(id=data["id"], text=data["text"])

    # ── Atomic lock (SETNX) ───────────────────────────────────────────────────
    lock_key = f"ticket:{ticket.id}:lock"
    acquired = await redis.set(lock_key, "1", nx=True, ex=REDIS_LOCK_TTL_SECONDS)
    if not acquired:
        print(f"🔒 Duplicate skipped: {ticket.id}")
        return

    try:
        print(f"🎫 Processing ticket {ticket.id}")

        # ── Phase 3: Storm short-circuit ──────────────────────────────────────
        if check_storm_window(ticket):
            await _handle_storm(ticket)
            return  # Skip individual routing for storm tickets

        # ── ML Classification + Urgency ───────────────────────────────────────
        ticket.category = classify(ticket.text)
        ticket.urgency_score = urgency_score(ticket.text)

        # ── Phase 3: Circuit breaker tracking ─────────────────────────────────
        latency = get_model_latency_ms()
        _update_circuit_breaker(latency)

        # ── Route to agent ────────────────────────────────────────────────────
        enqueue(ticket)
        agent_id = assign_agent(ticket)

        print(
            f"✅ Ticket {ticket.id} → category={ticket.category}, "
            f"urgency={ticket.urgency_score:.2f}, agent={agent_id}, "
            f"latency={latency:.1f}ms"
        )

        # ── Webhook for high urgency ───────────────────────────────────────────
        if ticket.urgency_score > URGENCY_WEBHOOK_THRESHOLD:
            await _fire_webhook(
                {
                    "text": (
                        f"🚨 *High-Urgency Ticket* `{ticket.id}`\n"
                        f"*Category:* {ticket.category}\n"
                        f"*Urgency:* {ticket.urgency_score:.2f}\n"
                        f"*Assigned to:* {agent_id}\n"
                        f"*Text:* {ticket.text[:200]}"
                    )
                }
            )

    finally:
        # Lock is intentionally left to expire naturally (idempotency window).
        # Remove it only if you want immediate reprocessability.
        pass

# ── Main Worker Loop ──────────────────────────────────────────────────────────

async def run_worker() -> None:
    """
    Connect to Redis and run an infinite BLPOP loop.
    BLPOP blocks until a ticket arrives — zero CPU spin when idle.
    Multiple worker instances can run in parallel; SETNX prevents double processing.
    """
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    print(f"👷 Worker started — listening on {REDIS_QUEUE_KEY}")

    while True:
        try:
            result = await redis.blpop(REDIS_QUEUE_KEY, timeout=5)
            if result is None:
                continue  # timeout — loop again
            _, raw = result
            # Process each ticket as a separate task so the loop never blocks
            asyncio.create_task(_process_ticket(raw, redis))

        except aioredis.ConnectionError as e:
            print(f"❌ Redis connection lost: {e}. Retrying in 3s…")
            await asyncio.sleep(3)
        except Exception as e:
            print(f"❌ Unexpected error in worker loop: {e}")
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(run_worker())
