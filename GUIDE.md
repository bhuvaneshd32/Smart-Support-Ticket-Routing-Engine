# SmartSupport — Complete End-to-End Run & Test Guide

---

## PRE-FLIGHT CHECKLIST

Before anything, confirm these are all in your root folder:

```
Smart-Support-Ticket-Routing-Engine/
├── shared_types.py
├── stubs.py
├── config.py
├── api_server.py
├── worker.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── ml_engine.py          ← Member A
├── router.py             ← Member C
├── agent_registry.py     ← Member C
├── ml/                   ← Member A's subfolder
│   ├── baseline_model.py
│   ├── transformer_model.py
│   ├── embedding_model.py
│   └── storm_detection.py
├── data/                 ← Member A's training data
│   └── training_samples.py
└── tests/
    └── test_api.py
```

If any file is missing — get it from your teammate before proceeding.

---

## STEP 1 — UPDATE YOUR DOCKERFILE

Open Dockerfile and replace everything with this.
This bakes the ML models into the image so they never re-download on startup:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download models ONCE during build — never again on startup
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='distilbert-base-uncased-finetuned-sst-2-english')"
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

COPY . .

EXPOSE 8000
```

---

## STEP 2 — UPDATE docker-compose.yml

Add PYTHONUNBUFFERED=1 to worker so logs appear instantly.
Open docker-compose.yml and make sure the worker section looks like this:

```yaml
worker:
  build:
    context: .
    dockerfile: Dockerfile
  container_name: smartsupport-worker
  command: python worker.py
  environment:
    - REDIS_URL=redis://redis:6379
    - WEBHOOK_URL=${WEBHOOK_URL:-}
    - PYTHONUNBUFFERED=1        ← THIS LINE IS CRITICAL
  depends_on:
    redis:
      condition: service_healthy
  volumes:
    - .:/app
  restart: on-failure
```

---

## STEP 3 — UPDATE requirements.txt

Make sure it has ALL of these:

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
redis>=5.0.0
pydantic>=2.0.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
anyio>=4.0.0
scikit-learn>=1.4.0
transformers>=4.40.0
torch>=2.2.0
sentence-transformers>=2.7.0
numpy>=1.26.0
```

---

## STEP 4 — BUILD THE SYSTEM

Open a terminal in your project folder and run:

```bash
docker-compose down
docker-compose up --build
```

⏳ First build takes 10-15 minutes (downloading PyTorch + models).
Every build after this will be fast (under 1 minute).

You know it's ready when you see ALL of these:

```
✅ Container smartsupport-redis     Running
✅ Container smartsupport-api       Recreated
✅ Container smartsupport-worker    Recreated
smartsupport-api    | ✅ Redis connected
smartsupport-api    | INFO: Application startup complete.
smartsupport-worker | 👷 Worker started — listening on tickets_queue
```

DO NOT close this terminal. Keep it running.

---

## STEP 5 — RUN TESTS (No Docker Needed)

Open a SECOND terminal and activate your venv:

```bash
source venv/bin/activate
pytest tests/test_api.py -v
```

Expected output — all 11 passing:

```
test_api.py::test_post_ticket_returns_200                    PASSED
test_api.py::test_post_ticket_uses_provided_id               PASSED
test_api.py::test_post_ticket_autogenerates_id               PASSED
test_api.py::test_get_health_returns_ok                      PASSED
test_api.py::test_get_health_circuit_breaker_closed_by_default PASSED
test_api.py::test_post_ticket_returns_202_when_redis_available PASSED
test_api.py::test_202_response_calls_redis_lpush             PASSED
test_api.py::test_15_concurrent_requests_all_accepted        PASSED
test_api.py::test_health_reports_open_circuit_when_env_set   PASSED
test_api.py::test_circuit_breaker_opens_after_3_slow_calls   PASSED
test_api.py::test_circuit_breaker_closes_after_5_fast_calls  PASSED

11 passed in 2.31s
```

---

## STEP 6 — LIVE API TESTS

Keep Docker terminal open. In your second terminal, run these one by one:

### Test 1 — Basic Ticket
```bash
curl -X POST http://localhost:8000/ticket \
  -H "Content-Type: application/json" \
  -d '{"text": "Server is completely down ASAP!"}'
```
Expected response:
```json
{"status":"accepted","ticket_id":"xxxx-xxxx","message":"Ticket queued for processing"}
```

### Test 2 — Health Check
```bash
curl http://localhost:8000/health
```
Expected response:
```json
{"status":"ok","queue_depth":0,"circuit_breaker":"closed"}
```

### Test 3 — Billing Ticket
```bash
curl -X POST http://localhost:8000/ticket \
  -H "Content-Type: application/json" \
  -d '{"text": "My invoice was charged twice this month"}'
```

### Test 4 — Legal Ticket
```bash
curl -X POST http://localhost:8000/ticket \
  -H "Content-Type: application/json" \
  -d '{"text": "We need legal review of our enterprise contract"}'
```

After each curl, look at your Docker terminal.
You should see the worker processing it:

```
smartsupport-worker | 🎫 Processing ticket xxxx-xxxx
smartsupport-worker | ✅ category=Billing, urgency=0.91, agent=agent-2, latency=145ms
```

---

## STEP 7 — STRESS TEST (15 Concurrent Tickets)

Create a file called simulate.py in your project folder:

```python
import asyncio
import httpx

URL = "http://localhost:8000/ticket"

TICKETS = [
    "My invoice was charged twice!",
    "Server is completely down ASAP!",
    "Need legal advice on our contract",
    "Cannot login to my account",
    "Billing portal is broken",
    "Database keeps crashing",
    "Urgent legal review needed",
    "Payment failed three times",
    "Server unreachable since morning",
    "Need refund for duplicate charge",
    "App crashes on every login",
    "Contract terms need review",
    "Server down nothing works",
    "Invoice amount is wrong",
    "Legal help needed urgently",
]

async def send_ticket(client, i, text):
    resp = await client.post(URL, json={"text": text})
    print(f"Ticket {i+1:02d} → HTTP {resp.status_code} | {text[:40]}")

async def main():
    print("🚀 Firing 15 concurrent tickets...\n")
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [send_ticket(client, i, t) for i, t in enumerate(TICKETS)]
        await asyncio.gather(*tasks)
    print("\n✅ All tickets sent! Check Docker logs for worker processing.")

asyncio.run(main())
```

Run it:
```bash
python simulate.py
```

Watch Docker logs simultaneously — you'll see all 15 being processed:
```
smartsupport-worker | 🎫 Processing ticket 01
smartsupport-worker | 🎫 Processing ticket 02
smartsupport-worker | 🔒 Duplicate skipped: (if any duplicates sneak in)
smartsupport-worker | ✅ category=Technical, urgency=0.87, agent=agent-3
...
```

---

## STEP 8 — STORM DETECTION TEST

Create storm_test.py:

```python
import asyncio
import httpx

URL = "http://localhost:8000/ticket"

# 11 near-identical tickets — triggers storm detection
STORM_TICKETS = [
    "Server is completely down",
    "Server is totally down",
    "The server is down and not working",
    "Server down nothing works",
    "Everything is down server unreachable",
    "Server is not responding at all",
    "Server has been down since an hour",
    "Our server is down please fix",
    "Server completely unreachable",
    "Nothing is working server is down",
    "Server down ASAP please help",
]

async def main():
    print("🌊 Simulating ticket storm — 11 near-identical tickets...\n")
    async with httpx.AsyncClient(timeout=10) as client:
        tasks = [
            client.post(URL, json={"id": f"storm-{i}", "text": text})
            for i, text in enumerate(STORM_TICKETS)
        ]
        await asyncio.gather(*tasks)
    print("✅ Storm tickets sent! Watch Docker logs for storm detection.")

asyncio.run(main())
```

Run it:
```bash
python storm_test.py
```

Watch Docker logs for:
```
smartsupport-worker | 🌊 STORM DETECTED — Master Incident xxxxx created for 11 tickets
```

---

## STEP 9 — VERIFY EVERYTHING IS WORKING

Run this full checklist:

```bash
# 1. All containers running?
docker-compose ps

# 2. Redis receiving and clearing tickets?
docker-compose exec redis redis-cli LLEN tickets_queue
# Should return 0 (worker is consuming instantly)

# 3. Worker logs clean?
docker-compose logs worker --tail=20

# 4. API logs clean?
docker-compose logs api --tail=20

# 5. All tests passing?
pytest tests/test_api.py -v
```

---

## QUICK REFERENCE — COMMON COMMANDS

| What you want to do | Command |
|---|---|
| Start everything | `docker-compose up --build` |
| Stop everything | `docker-compose down` |
| See worker logs live | `docker-compose logs -f worker` |
| See all logs live | `docker-compose logs -f` |
| Check containers | `docker-compose ps` |
| Check Redis queue depth | `docker-compose exec redis redis-cli LLEN tickets_queue` |
| Run tests | `pytest tests/test_api.py -v` |
| Send one ticket | `curl -X POST http://localhost:8000/ticket -H "Content-Type: application/json" -d '{"text": "test"}'` |
| Check health | `curl http://localhost:8000/health` |
| Run stress test | `python simulate.py` |
| Run storm test | `python storm_test.py` |

---

## WHAT GOOD OUTPUT LOOKS LIKE

### Docker Terminal (keep open always):
```
smartsupport-redis  | Ready to accept connections
smartsupport-api    | ✅ Redis connected
smartsupport-api    | INFO: Application startup complete.
smartsupport-worker | 👷 Worker started — listening on tickets_queue
smartsupport-worker | 🎫 Processing ticket xxxx
smartsupport-worker | ✅ category=Technical, urgency=0.91, agent=agent-2, latency=145ms
smartsupport-worker | 📣 Webhook fired → HTTP 200
```

### Health endpoint:
```json
{"status":"ok","queue_depth":0,"circuit_breaker":"closed"}
```

### Ticket endpoint:
```json
{"status":"accepted","ticket_id":"xxxx","message":"Ticket queued for processing"}
```

If you see all of the above — your system is fully working. Ship it! 🚀