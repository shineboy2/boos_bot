import socket
import httpx
import asyncio

old = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in old(*args, **kwargs) if r[0] == socket.AF_INET]

async def run():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get('https://webgw.tse.ir/Web/V2/Home/MarketWatchCash/0/0/0/fa', headers={'User-Agent': 'Mozilla/5.0'})
        data = r.json()
        print(f"Keys: {data.keys() if isinstance(data, dict) else 'Not dict'}")
        if isinstance(data, dict) and 'marketwatch' in data:
            print(f"Items: {len(data['marketwatch'])}")
            print(data['marketwatch'][0])

asyncio.run(run())
