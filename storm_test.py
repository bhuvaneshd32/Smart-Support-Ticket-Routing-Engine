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