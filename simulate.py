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