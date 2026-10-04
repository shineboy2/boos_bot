#!/usr/bin/env python3

import json
import time
from datetime import datetime, timezone
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import sys
from pathlib import Path
import concurrent.futures
import threading

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
        "yesterday": to_float(row.get("priceYesterday")),
        "volume": to_int(row.get("qTotTran5J")),
        "value": to_int(row.get("qTotCap")),
        "trade_count": to_int(row.get("zTotTran")),
    }

def load_instruments():
    db = DatabaseManager()
    with db.connect() as conn:
        cur = conn.execute("""
            SELECT id, ins_code, ins_id, symbol, name, isin, market, market_board, instrument_type
            FROM instruments
            WHERE active = 1 AND instrument_type IN ('stock', 'etf', 'right')
        """)
        
        instruments = []
        for row in cur.fetchall():
            instruments.append({
                "id": row['id'],
                "ins_code": row['ins_code'],
                "ins_id": row['ins_id'],
                "symbol": row['symbol'],
                "name": row['name'],
                "isin": row['isin'],
                "market": row['market'],
                "market_board": row['market_board'],
                "instrument_type": row['instrument_type']
            })
            
    return instruments


def process_instrument(instrument, thread_local_session):
    time.sleep(0.1)  # Prevent sudden bursts to TSETMC
    ins_code = str(instrument.get("ins_code") or instrument.get("insCode"))
    symbol = (instrument.get("symbol") or instrument.get("lVal18AFC") or instrument.get("lVal18"))
    
    try:
        if not hasattr(thread_local_session, "session"):
            thread_local_session.session = requests.Session()
            thread_local_session.session.headers.update(HEADERS)
            
        rows = fetch_history(thread_local_session.session, ins_code)
        
        parsed_rows = []
        for row in rows:
            parsed_rows.append(map_history_row(row))
            
        return instrument, parsed_rows, None
    except Exception as exc:
        return instrument, None, exc

def upsert_instrument(conn, instrument):
    now = datetime.now(timezone.utc).isoformat()
    ins_code = str(instrument.get("ins_code") or instrument.get("insCode"))
    ins_id = (instrument.get("ins_id") or instrument.get("insID") or instrument.get("instrumentID"))
    symbol = (instrument.get("symbol") or instrument.get("lVal18AFC") or instrument.get("lVal18"))
    symbol = normalize_symbol(symbol)
    name = (instrument.get("name") or instrument.get("lVal30"))
    isin = (instrument.get("isin") or instrument.get("cIsin"))
    market = (instrument.get("market") or instrument.get("flowTitle"))
    market_board = (instrument.get("market_board") or instrument.get("cgrValCotTitle"))
    instrument_type = instrument.get("instrument_type", "stock")

    conn.execute("""
        INSERT INTO instruments (
            ins_code, ins_id, isin, symbol, name, market, market_board, instrument_type, active, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(ins_code) DO UPDATE SET
            ins_id = excluded.ins_id,
            isin = excluded.isin,
            symbol = excluded.symbol,
            name = excluded.name,
            market = excluded.market,
            market_board = excluded.market_board,
            instrument_type = excluded.instrument_type,
            updated_at = excluded.updated_at
    """, (ins_code, ins_id, isin, symbol, name, market, market_board, instrument_type, now, now))
    
    row = conn.execute("SELECT id FROM instruments WHERE ins_code = ?", (ins_code,)).fetchone()
    return row['id']

def save_history(conn, instrument_id, parsed_rows):
    fetched_at = datetime.now(timezone.utc).isoformat()
    records = []
    for parsed in parsed_rows:
        records.append((
            instrument_id, parsed["date"], parsed["open"], parsed["high"], parsed["low"],
            parsed["close"], parsed["last"], parsed["yesterday"], parsed["volume"], parsed["value"],
            parsed["trade_count"], "tsetmc", fetched_at,
        ))

    conn.executemany("""
        INSERT INTO ohlcv_daily (
            instrument_id, date, open, high, low, close, last, yesterday, volume, value, trade_count, source, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id, date) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            last = excluded.last,
            yesterday = excluded.yesterday,
            volume = excluded.volume,
            value = excluded.value,
            trade_count = excluded.trade_count,
            source = excluded.source,
            fetched_at = excluded.fetched_at
    """, records)
    return len(records)

def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    instruments = load_instruments()

    logger.info("=" * 60)
    logger.info("TSETMC DAILY HISTORY COLLECTOR (MULTITHREADED)")
    logger.info("=" * 60)
    logger.info(f"Instrument file : {INSTRUMENTS_FILE}")
    logger.info(f"Total instruments: {len(instruments)}")
    
    db = DatabaseManager()
    
    thread_local = threading.local()

    success = 0
    failed = 0
    total_rows = 0
    
    start_time = time.time()

    # Use 4 workers to avoid TSETMC rate limits/hanging
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_instrument, inst, thread_local): inst for inst in instruments}
        
        with db.connect() as conn:
            for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
                instrument, parsed_rows, exc = future.result()
                symbol = (instrument.get("symbol") or instrument.get("lVal18AFC") or instrument.get("lVal18"))
                ins_code = str(instrument.get("ins_code") or instrument.get("insCode"))

                if exc:
                    failed += 1
                    logger.error(f"[{i:03d}/{len(instruments)}] ERROR {symbol:<15} | {type(exc).__name__}: {exc}")
                else:
                    try:
                        instrument_id = instrument.get("id")
                        count = save_history(conn, instrument_id, parsed_rows)
                        conn.commit()
                        
                        success += 1
                        total_rows += count

                        if parsed_rows:
                            dates = [row["date"] for row in parsed_rows]
                            logger.info(f"[{i:03d}/{len(instruments)}] OK | {symbol:<15} | {count} rows | {min(dates)} -> {max(dates)}")
                        else:
                            logger.info(f"[{i:03d}/{len(instruments)}] OK | {symbol:<15} | 0 rows")

                    except Exception as e:
                        failed += 1
                        logger.error(f"[{i:03d}/{len(instruments)}] DB ERROR {symbol:<15} | {e}")
                        conn.rollback()

    elapsed = time.time() - start_time
    logger.info("=" * 60)
    logger.info("FINISHED")
    logger.info(f"Success instruments : {success}")
    logger.info(f"Failed instruments  : {failed}")
    logger.info(f"Total history rows  : {total_rows}")
    logger.info(f"Time elapsed        : {elapsed:.2f}s")
    
    with db.connect() as conn:
        count_instruments = conn.execute("SELECT COUNT(*) FROM instruments").fetchone()[0]
        count_history = conn.execute("SELECT COUNT(*) FROM ohlcv_daily").fetchone()[0]
        logger.info(f"DB instruments      : {count_instruments}")
        logger.info(f"DB history rows     : {count_history}")

if __name__ == "__main__":
    main()