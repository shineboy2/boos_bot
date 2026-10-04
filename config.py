import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "market.db"

# Data Provider Configuration
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds
CONCURRENT_LIMIT = 5

# TSETMC URLs
CDN_BASE_URL = "https://cdn.tsetmc.com/api"
WEBGW_BASE_URL = "https://webgw.tse.ir"

# Headers
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9,fa;q=0.8",
}
