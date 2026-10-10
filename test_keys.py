import requests
import json
from config import DEFAULT_HEADERS

url = 'https://cdn.tsetmc.com/api/ClosingPrice/GetMarketWatch?market=0&paperTypes[0]=1&withBestLimits=false&hEven=0&RefID=0'

print("Fetching MarketWatch...")
r = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
data = r.json()
if 'marketwatch' in data and len(data['marketwatch']) > 0:
    item = data['marketwatch'][0]
    print("Keys:", list(item.keys()))
    print("Item:", json.dumps(item, ensure_ascii=False))
else:
    print("No data")
