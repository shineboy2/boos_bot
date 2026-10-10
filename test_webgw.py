import asyncio
import httpx

async def test():
    url = "https://webgw.tse.ir/Web/V2/Home/MarketSummary"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
    }
    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
        try:
            resp = await client.get(url, headers=headers)
            print(f"Status: {resp.status_code}")
            print(resp.text[:200])
        except Exception as e:
            print(f"Error: {e}")

asyncio.run(test())
