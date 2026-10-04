import socket
import httpx
import asyncio

old = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in old(*args, **kwargs) if r[0] == socket.AF_INET]

async def run():
    async with httpx.AsyncClient(http2=True, timeout=10) as c:
        r = await c.get('https://cdn.tsetmc.com/api/MarketMap/GetMarketMapData/1', headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        print(str(r.json())[:100])

asyncio.run(run())
