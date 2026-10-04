import socket
import httpx
import asyncio

old = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in old(*args, **kwargs) if r[0] == socket.AF_INET]

async def run():
    try:
        async with httpx.AsyncClient(timeout=10, verify=False) as c:
            r = await c.get('https://webgw.tse.ir/Web/V2/Home/MarketWatchCash/0/0/0/fa', headers={'User-Agent': 'Mozilla/5.0'})
            print(f"Status: {r.status_code}")
            print(f"Content: {r.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(run())
