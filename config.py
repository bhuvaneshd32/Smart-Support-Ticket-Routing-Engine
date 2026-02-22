# config.py  ──  Member B owns this file
# All configuration and environment variables live here.
# No hardcoded values anywhere in api_server.py or worker.py

import os

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379")
REDIS_QUEUE_KEY: str = "tickets_queue"
REDIS_LOCK_TTL_SECONDS: int = 30           # SETNX lock expiry

# ── API ───────────────────────────────────────────────────────────────────────
API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
API_PORT: int = int(os.getenv("API_PORT", "8000"))

# ── Webhook ───────────────────────────────────────────────────────────────────
WEBHOOK_URL: str | None = os.getenv("WEBHOOK_URL")          # Slack/Discord
URGENCY_WEBHOOK_THRESHOLD: float = 0.8

# ── Circuit Breaker ───────────────────────────────────────────────────────────
CIRCUIT_BREAKER_LATENCY_MS: float = 500.0   # open circuit if latency > this
CIRCUIT_BREAKER_OPEN_COUNT: int = 3         # consecutive slow calls to open
CIRCUIT_BREAKER_CLOSE_COUNT: int = 5        # consecutive fast calls to close
CIRCUIT_BREAKER_FAST_MS: float = 200.0      # "fast" threshold to close circuit

# ── Model Fallback ────────────────────────────────────────────────────────────
MODEL_FALLBACK_ENV_VAR: str = "MODEL_FALLBACK"

# ── Storm Detection ───────────────────────────────────────────────────────────
STORM_WINDOW_SECONDS: int = 300             # 5 minutes
STORM_TICKET_THRESHOLD: int = 10
