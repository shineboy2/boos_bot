#!/usr/bin/env python3
"""
Divergence signal calculator.

Key changes from original:
- No longer deletes old signals before confirming new ones succeed.
- Uses INSERT OR IGNORE with UNIQUE constraint to avoid duplicates.
- Records pivot_occurrence_date and confirmation_date separately.
- Failed computation does not destroy valid previous output.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timezone
import concurrent.futures
import time
import sys

BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine
from app.engines.adjustment import AdjustmentService


def fetch_instruments():
    db = DatabaseManager()
    with db.connect() as conn:
        cur = conn.execute("SELECT id, symbol, ins_code FROM instruments WHERE active = 1")
        # Convert sqlite3.Row to regular tuple for multiprocessing pickling
        instruments = [(row['id'], row['symbol'], row['ins_code']) for row in cur.fetchall()]
    return instruments


def process_instrument(args):
    instrument_id, symbol, ins_code = args
    
    try:
        db = DatabaseManager()
        with db.connect() as conn:
            query = """
                SELECT date, open, high, low, close, yesterday, volume
                FROM ohlcv_daily
                WHERE instrument_id = ?
                ORDER BY date
            """
            df = pd.read_sql_query(query, conn, params=(instrument_id,))

        if len(df) < 50:
            return instrument_id, []

        # Adjust prices for corporate actions
        df = AdjustmentService.adjust_prices(df)
        
        # Replace raw OHLC with adjusted OHLC for indicators and divergence
        df['close'] = df['adj_close']
        df['open'] = df['adj_open']
        df['high'] = df['adj_high']
        df['low'] = df['adj_low']

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

        now = datetime.now(timezone.utc).isoformat()
        records = []
        
        for _, row in signals_df.iterrows():
            # pivot_occurrence_date = date of second price pivot (the structure)
            # confirmation_date = signal_date (when both pivots are confirmed)
            pivot_occurrence_date = row['price_pivot_2_date'].strftime('%Y-%m-%d')
            confirmation_date = row['signal_date'].strftime('%Y-%m-%d')
            
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
                pivot_occurrence_date,
                confirmation_date,
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
    
    # Record pipeline run
    run_id = f"signals_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    db = DatabaseManager()
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO pipeline_runs (run_id, stage, status, started_at)
            VALUES (?, 'calculate_signals', 'running', ?)
        """, (run_id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    
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
                
    # Bulk insert using INSERT OR IGNORE (relies on UNIQUE constraint)
    # This preserves existing valid signals and only adds new ones.
    inserted_count = 0
    if all_records:
        print(f"\nInserting {len(all_records)} records into database (INSERT OR IGNORE)...")
        db = DatabaseManager()
        with db.connect() as conn:
            try:
                cursor = conn.executemany("""
                    INSERT OR IGNORE INTO divergence_signals (
                        instrument_id, signal_date, indicator, divergence_type,
                        price_pivot_1_date, price_pivot_2_date,
                        indicator_pivot_1_date, indicator_pivot_2_date,
                        price_pivot_1_value, price_pivot_2_value,
                        indicator_pivot_1_value, indicator_pivot_2_value,
                        bars_between, pivot_occurrence_date, confirmation_date,
                        created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, all_records)
                inserted_count = conn.total_changes
                conn.commit()
                print(f"Inserted {inserted_count} new records (skipped duplicates).")
            except Exception as e:
                print(f"ERROR during bulk insert: {e}")
                # Don't delete old data - just report the error
                failed += 1
    
    # Optionally clean very old signals (> 180 days) that are unlikely to be useful
    # But only AFTER successful insertion
    if inserted_count > 0 or (not all_records and failed == 0):
        with db.connect() as conn:
            old_count = conn.execute(
                "SELECT COUNT(*) FROM divergence_signals WHERE signal_date < date('now', '-180 days')"
            ).fetchone()[0]
            if old_count > 0:
                conn.execute("DELETE FROM divergence_signals WHERE signal_date < date('now', '-180 days')")
                conn.commit()
                print(f"Cleaned {old_count} signals older than 180 days.")

    # Update pipeline run record
    with db.connect() as conn:
        status = 'success' if failed == 0 else ('partial' if success > 0 else 'failed')
        conn.execute("""
            UPDATE pipeline_runs SET 
                status = ?, finished_at = ?,
                total_instruments = ?, success_count = ?, 
                failed_count = ?, skipped_count = ?,
                records_created = ?
            WHERE run_id = ?
        """, (
            status, datetime.now(timezone.utc).isoformat(),
            success + empty + failed, success, failed, empty,
            inserted_count, run_id
        ))
        conn.commit()

    elapsed = time.time() - start_time
    print("=" * 60)
    print("FINISHED")
    print("=" * 60)
    print(f"Processed instruments : {success + empty + failed}")
    print(f"Success (w/ signals)  : {success}")
    print(f"Empty (no signals)    : {empty}")
    print(f"Failed instruments    : {failed}")
    print(f"Total signals saved   : {inserted_count}")
    print(f"Time elapsed          : {elapsed:.2f} seconds")
    print(f"Status                : {status}")

if __name__ == "__main__":
    main()
