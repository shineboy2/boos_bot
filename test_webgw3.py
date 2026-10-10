import asyncio
import httpx
import traceback

async def test():
    urls = [
        "https://webgw.tse.ir/Web/V2/Home/MarketSummary",
        "http://webgw.tse.ir/Web/V2/Home/MarketSummary",
        "https://webgw.tsetmc.com/Web/V2/Home/MarketSummary",
        "http://web.tsetmc.com/tsev2/data/MarketWatchPlus.aspx"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
    }
    
    for url in urls:
        print(f"Testing {url} ...")
        async with httpx.AsyncClient(timeout=3.0, verify=False) as client:
            try:
                resp = await client.get(url, headers=headers)
                print(f"Status: {resp.status_code}")
                print(resp.text[:100])
            except Exception as e:
                print(f"Error Type: {type(e)}")

asyncio.run(test())
