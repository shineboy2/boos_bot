import socket
import sys
old = socket.getaddrinfo
socket.getaddrinfo = lambda *args, **kwargs: [r for r in old(*args, **kwargs) if r[0] == socket.AF_INET]
import app.market_map
try:
    print(app.market_map.generate_market_map())
except Exception as e:
    print(f"Error: {e}")
