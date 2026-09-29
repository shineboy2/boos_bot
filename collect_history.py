#!/usr/bin/env python3

import json
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

logger = setup_logging("collect_history")

DATA_DIR = BASE_DIR / "data"
INSTRUMENTS_FILE = DATA_DIR / "instruments.json"

TSETMC_BASE_URL = "https://cdn.tsetmc.com/api"
REQUEST_TIMEOUT = 30
SLEEP_BETWEEN_REQUESTS = 0.05

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    reraise=True
)
def fetch_history(session: requests.Session, ins_code: str):
    url = f"{TSETMC_BASE_URL}/ClosingPrice/GetClosingPriceDailyList/{ins_code}/0"
    response = session.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    rows = data.get("closingPriceDaily")
    if rows is None:
        raise ValueError(f"Unexpected response for {ins_code}: missing 'closingPriceDaily'")
    return rows

def map_history_row(row):
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

def load_instruments():
    if not INSTRUMENTS_FILE.exists():
        raise FileNotFoundError(f"Instrument file not found:\n{INSTRUMENTS_FILE}")
    with open(INSTRUMENTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "instruments" in data:
            instruments = data["instruments"]
        elif "data" in data:
            instruments = data["data"]
        else:
            raise ValueError("JSON must contain 'instruments' or 'data'")
    elif isinstance(data, list):
        instruments = data
    else:
        raise ValueError("Invalid instruments.json format")
    return instruments

def upsert_instrument(conn, instrument):
    now = datetime.utcnow().isoformat()
    ins_code = str(instrument.get("ins_code") or instrument.get("insCode"))
    ins_id = (instrument.get("ins_id") or instrument.get("insID") or instrument.get("instrumentID"))
    symbol = (instrument.get("symbol") or instrument.get("lVal18AFC") or instrument.get("lVal18"))
    symbol = normalize_symbol(symbol)
    name = (instrument.get("name") or instrument.get("lVal30"))
    isin = (instrument.get("isin") or instrument.get("cIsin"))
    market = (instrument.get("market") or instrument.get("flowTitle"))
    market_board = (instrument.get("market_board") or instrument.get("cgrValCotTitle"))

    if not ins_code or ins_code == "None":
        raise ValueError(f"Invalid ins_code: {instrument}")
    if not ins_id:
        raise ValueError(f"Invalid ins_id: {instrument}")
    if not symbol:
        raise ValueError(f"Invalid symbol: {instrument}")

    conn.execute("""
        INSERT INTO instruments (
            ins_code, ins_id, isin, symbol, name, market, market_board, active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(ins_code) DO UPDATE SET
            ins_id = excluded.ins_id,
            isin = excluded.isin,
            symbol = excluded.symbol,
            name = excluded.name,
            market = excluded.market,
            market_board = excluded.market_board,
            updated_at = excluded.updated_at
    """, (ins_code, ins_id, isin, symbol, name, market, market_board, now, now))
    
    row = conn.execute("SELECT id FROM instruments WHERE ins_code = ?", (ins_code,)).fetchone()
    return row['id']

def save_history(conn, instrument_id, rows):
    fetched_at = datetime.utcnow().isoformat()
    records = []
    for row in rows:
        parsed = map_history_row(row)
        records.append((
            instrument_id, parsed["date"], parsed["open"], parsed["high"], parsed["low"],
            parsed["close"], parsed["last"], parsed["volume"], parsed["value"],
            parsed["trade_count"], "tsetmc", fetched_at,
        ))

    conn.executemany("""
        INSERT INTO ohlcv_daily (
            instrument_id, date, open, high, low, close, last, volume, value, trade_count, source, fetched_at
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
    """, records)
    conn.commit()
    return len(records)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    instruments = load_instruments()

    logger.info("=" * 60)
    logger.info("TSETMC DAILY HISTORY COLLECTOR")
    logger.info("=" * 60)
    logger.info(f"Instrument file : {INSTRUMENTS_FILE}")
    logger.info(f"Total instruments: {len(instruments)}")
    
    db = DatabaseManager()

    with db.connect() as conn:
        session = requests.Session()
        session.headers.update(HEADERS)

        success = 0
        failed = 0
        total_rows = 0

        for index, instrument in enumerate(instruments, start=1):
            symbol = (instrument.get("symbol") or instrument.get("lVal18AFC") or instrument.get("lVal18"))
            ins_code = str(instrument.get("ins_code") or instrument.get("insCode"))

            logger.info(f"[{index:03d}/{len(instruments)}] {symbol:<15} {ins_code}")

            try:
                instrument_id = upsert_instrument(conn, instrument)
                rows = fetch_history(session, ins_code)
                count = save_history(conn, instrument_id, rows)

                success += 1
                total_rows += count

                if rows:
                    dates = [parse_date(row["dEven"]) for row in rows]
                    logger.info(f"OK | {count} rows | {min(dates)} -> {max(dates)}")
                else:
                    logger.info("OK | 0 rows")

            except Exception as exc:
                failed += 1
                logger.error(f"ERROR | {type(exc).__name__}: {exc}")

            time.sleep(SLEEP_BETWEEN_REQUESTS)

        logger.info("=" * 60)
        logger.info("FINISHED")
        logger.info(f"Success instruments : {success}")
        logger.info(f"Failed instruments  : {failed}")
        logger.info(f"Total history rows  : {total_rows}")

        count_instruments = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
        count_history = conn.execute("SELECT COUNT(*) FROM ohlcv_daily").fetchone()[0]
        logger.info(f"DB instruments      : {count_instruments}")
        logger.info(f"DB history rows     : {count_history}")

if __name__ == "__main__":
    main()