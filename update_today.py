#!/usr/bin/env python3

import time
from datetime import datetime
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.utils import parse_date, to_int, to_float, normalize_symbol
from app.logging_config import setup_logging

logger = setup_logging("update_today")

TSETMC_BASE_URL = "https://cdn.tsetmc.com/api"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.08

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

def map_info_row(row):
    return {
        "date": parse_date(row["dEven"]),
        "open": to_float(row.get("priceFirst")),
        "high": to_float(row.get("priceMax")),
        "low": to_float(row.get("priceMin")),
        "close": to_float(row.get("pClosing")),
        "last": to_float(row.get("pDrCotVal")),
        "volume": to_int(row.get("qTotTran5J")),
        "value": to_int(row.get("qTotCap")),
        "trade_count": to_int(row.get("zTotTran")),
    }

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True
)
def fetch_today_info(session, ins_code):
    url = f"{TSETMC_BASE_URL}/ClosingPrice/GetClosingPriceInfo/{ins_code}"
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    if response.status_code == 303:
        # TSETMC sometimes redirects to HTTPS manually
        url_https = response.headers.get("Location")
        if url_https:
            response = session.get(url_https, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()

def main():
    logger.info("=" * 60)
    logger.info("TSETMC DAILY FAST UPDATER (TODAY ONLY)")
    logger.info("=" * 60)
    
    db = DatabaseManager()
    
    with db.connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, ins_code, symbol FROM instruments WHERE active = 1")
        instruments = cursor.fetchall()
        
        session = requests.Session()
        session.headers.update(HEADERS)
        
        success = 0
        failed = 0
        
        for index, row in enumerate(instruments, start=1):
            inst_id = row['id']
            ins_code = row['ins_code']
            symbol = row['symbol']
            
            logger.info(f"[{index:03d}/{len(instruments)}] {symbol:<15} {ins_code}")
            
            try:
                data = fetch_today_info(session, ins_code)
                info = data.get("closingPriceInfo")
                
                if not info or not info.get("dEven") or info.get("dEven") == 0:
                    logger.info("SKIP | No data for today")
                    success += 1
                    continue
                    
                if to_int(info.get("qTotTran5J")) == 0 or to_int(info.get("qTotCap")) == 0:
                    logger.info("SKIP | Market closed or zero volume")
                    success += 1
                    continue
                    
                parsed = map_info_row(info)
                fetched_at = datetime.utcnow().isoformat()
                
                conn.execute("""
                    INSERT INTO ohlcv_daily (
                        instrument_id, date, open, high, low, close, last, 
                        volume, value, trade_count, source, fetched_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instrument_id, date) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        last = excluded.last,
                        volume = excluded.volume,
                        value = excluded.value,
                        trade_count = excluded.trade_count,
                        source = excluded.source,
                        fetched_at = excluded.fetched_at
                """, (
                    inst_id, parsed["date"], parsed["open"], parsed["high"], parsed["low"],
                    parsed["close"], parsed["last"], parsed["volume"], parsed["value"],
                    parsed["trade_count"], "tsetmc_fast", fetched_at
                ))
                conn.commit()
                
                success += 1
                logger.info(f"OK | Date: {parsed['date']}")
                
            except Exception as exc:
                failed += 1
                logger.error(f"ERROR | {type(exc).__name__}: {exc}")
                
            time.sleep(SLEEP_BETWEEN_REQUESTS)
            
        logger.info("FINISHED")
        logger.info(f"Successfully updated: {success}")
        logger.info(f"Failed: {failed}")

if __name__ == "__main__":
    main()
