#!/usr/bin/env python3

import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
import concurrent.futures
import time
import sys

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine

def init_db():
    db = DatabaseManager()
    with db.connect() as conn:
        # We clear the previous calculations
        conn.execute("DELETE FROM divergence_signals")
        conn.commit()

def fetch_instruments():
    db = DatabaseManager()
    with db.connect() as conn:
        cur = conn.execute("SELECT id, symbol, ins_code FROM instruments WHERE active = 1")
        instruments = cur.fetchall()
    return instruments

def process_instrument(args):
    instrument_id, symbol, ins_code = args
    
    try:
        db = DatabaseManager()
        with db.connect() as conn:
            query = """
                SELECT date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE instrument_id = ?
                ORDER BY date
            """
            df = pd.read_sql_query(query, conn, params=(instrument_id,))

        if len(df) < 50:
            return instrument_id, []

        indicator_engine = IndicatorEngine()
        df_calc = indicator_engine.calculate_for_symbol(df, symbol=symbol)

        divergence_engine = DivergenceEngine(
            left_bars=3,
            right_bars=3,
            min_bars_between_pivots=5,
            max_bars_between_pivots=60,
            max_calendar_days=120,
            indicator_tolerance_bars=2,
        )

        signals_df = divergence_engine.calculate(df_calc)

        if signals_df.empty:
            return instrument_id, []

        now = datetime.utcnow().isoformat()
        records = []
        
        for _, row in signals_df.iterrows():
            records.append((
                instrument_id,
                row['signal_date'].strftime('%Y-%m-%d'),
                row['indicator'],
                row['divergence_type'],
                
                row['price_pivot_1_date'].strftime('%Y-%m-%d'),
                row['price_pivot_2_date'].strftime('%Y-%m-%d'),
                row['indicator_pivot_1_date'].strftime('%Y-%m-%d'),
                row['indicator_pivot_2_date'].strftime('%Y-%m-%d'),
                
                float(row['price_pivot_1_value']),
                float(row['price_pivot_2_value']),
                float(row['indicator_pivot_1_value']),
                float(row['indicator_pivot_2_value']),
                
                int(row['bars_between']),
                now
            ))

        return instrument_id, records

    except Exception as e:
        # Returning Exception for logging
        return instrument_id, e

def main():
    print("=" * 60)
    print("DIVERGENCE SIGNALS CALCULATOR (Parallel)")
    print("=" * 60)
    
    start_time = time.time()
    init_db()
    instruments = fetch_instruments()
    
    print(f"Total instruments to process: {len(instruments)}")
    
    all_records = []
    success = 0
    failed = 0
    empty = 0
    
    # Batch process
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_instrument, ins): ins for ins in instruments}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            ins_args = futures[future]
            ins_id, symbol, ins_code = ins_args
            
            try:
                res_id, result = future.result()
                if isinstance(result, Exception):
                    print(f"[{i:03d}/{len(instruments)}] {symbol:<15} ERROR: {result}")
                    failed += 1
                else:
                    if not result:
                        empty += 1
                        print(f"[{i:03d}/{len(instruments)}] {symbol:<15} OK | 0 signals")
                    else:
                        all_records.extend(result)
                        success += 1
                        print(f"[{i:03d}/{len(instruments)}] {symbol:<15} OK | {len(result)} signals")
            except Exception as e:
                print(f"[{i:03d}/{len(instruments)}] {symbol:<15} FATAL ERROR: {e}")
                failed += 1
                
    # Bulk insert
    print("\\nInserting records into database...")
    if all_records:
        db = DatabaseManager()
        with db.connect() as conn:
            conn.executemany("""
                INSERT INTO divergence_signals (
                    instrument_id, signal_date, indicator, divergence_type,
                    price_pivot_1_date, price_pivot_2_date,
                    indicator_pivot_1_date, indicator_pivot_2_date,
                    price_pivot_1_value, price_pivot_2_value,
                    indicator_pivot_1_value, indicator_pivot_2_value,
                    bars_between, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, all_records)
            conn.commit()

    elapsed = time.time() - start_time
    print("=" * 60)
    print("FINISHED")
    print("=" * 60)
    print(f"Processed instruments : {success + empty + failed}")
    print(f"Success (w/ signals)  : {success}")
    print(f"Empty (no signals)    : {empty}")
    print(f"Failed instruments    : {failed}")
    print(f"Total signals saved   : {len(all_records)}")
    print(f"Time elapsed          : {elapsed:.2f} seconds")

if __name__ == "__main__":
    main()
