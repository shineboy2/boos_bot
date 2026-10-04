#!/usr/bin/env python3
"""
Backtest calculator for divergence signals.

Key fixes in this version:
- Non-atomic deletion is removed; uses UPSERT to prevent data loss.
- Look-ahead bias fixed: Trades enter on the NEXT session's open.
- Tracks horizon completeness (trading sessions count).
- Added pipeline_runs logging.
"""

import sqlite3
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
from app.engines.adjustment import AdjustmentService

def fetch_instruments():
    db = DatabaseManager()
    with db.connect() as conn:
        cur = conn.execute("SELECT id, symbol FROM instruments WHERE active = 1")
        instruments = cur.fetchall()
    return instruments

def process_instrument(args):
    instrument_id, symbol = args
    
    try:
        db = DatabaseManager()
        with db.connect() as conn:
            # Load signals
            signals_query = """
                SELECT id, signal_date, indicator, divergence_type
                FROM divergence_signals
                WHERE instrument_id = ?
                ORDER BY signal_date
            """
            signals_df = pd.read_sql_query(signals_query, conn, params=(instrument_id,))
            
            # Load OHLC
            ohlc_query = """
                SELECT date, open, high, low, close, yesterday, volume
                FROM ohlcv_daily
                WHERE instrument_id = ?
                ORDER BY date
            """
            ohlc_df = pd.read_sql_query(ohlc_query, conn, params=(instrument_id,))

        if signals_df.empty or ohlc_df.empty:
            return instrument_id, []

        # Adjust prices to prevent fake returns on splits/dividends
        ohlc_df = AdjustmentService.adjust_prices(ohlc_df)
        
        # Use adjusted prices for backtest
        ohlc_df['open'] = ohlc_df['adj_open']
        ohlc_df['high'] = ohlc_df['adj_high']
        ohlc_df['low'] = ohlc_df['adj_low']
        ohlc_df['close'] = ohlc_df['adj_close']

        # Create mapping of date to integer index
        ohlc_df['idx'] = range(len(ohlc_df))
        date_to_idx = ohlc_df.set_index('date')['idx'].to_dict()
        
        dates = ohlc_df['date'].values
        opens = ohlc_df['open'].values
        closes = ohlc_df['close'].values
        highs = ohlc_df['high'].values
        lows = ohlc_df['low'].values
        
        total_rows = len(ohlc_df)
        
        now = datetime.now(timezone.utc).isoformat()
        records = []
        
        for _, row in signals_df.iterrows():
            signal_id = row['id']
            sig_date = row['signal_date']
            indicator = row['indicator']
            div_type = row['divergence_type']
            is_bullish = 'bullish' in div_type
            
            if sig_date not in date_to_idx:
                continue
                
            sig_idx = date_to_idx[sig_date]
            
            # ENTRY ON NEXT SESSION (Fix for look-ahead bias)
            entry_idx = sig_idx + 1
            if entry_idx >= total_rows:
                continue # Signal was on the last day, cannot enter trade yet
                
            entry_date = dates[entry_idx]
            entry_price = opens[entry_idx]
            
            # Fallback if open price is missing/zero (sometimes happens in TSE)
            if pd.isna(entry_price) or entry_price <= 0:
                entry_price = closes[entry_idx]
                
            if pd.isna(entry_price) or entry_price <= 0:
                continue
            
            # Helper to calculate return based on trading sessions forward
            def get_return(forward_days):
                target_idx = entry_idx + forward_days
                is_complete = 1
                
                if target_idx >= total_rows:
                    # Not enough days have passed, calculate based on latest available data
                    target_idx = total_rows - 1
                    is_complete = 0
                    
                if target_idx > entry_idx:
                    price = closes[target_idx]
                    if is_bullish:
                        ret = (price - entry_price) / entry_price
                    else:
                        ret = (entry_price - price) / entry_price
                    return float(ret), is_complete
                return None, 0

            ret_5d, comp_5d = get_return(5)
            ret_10d, comp_10d = get_return(10)
            ret_20d, comp_20d = get_return(20)
            ret_30d, comp_30d = get_return(30)
            
            # Calculate 30-day MFE and MAE
            mfe_30d = None
            mae_30d = None
            
            end_idx = min(entry_idx + 31, total_rows)
            if end_idx > entry_idx + 1:
                window_highs = highs[entry_idx + 1 : end_idx]
                window_lows = lows[entry_idx + 1 : end_idx]
                
                max_high = np.nanmax(window_highs)
                min_low = np.nanmin(window_lows)
                
                if is_bullish:
                    mfe_30d = float((max_high - entry_price) / entry_price)
                    mae_30d = float((min_low - entry_price) / entry_price)
                else:
                    mfe_30d = float((entry_price - min_low) / entry_price)
                    mae_30d = float((entry_price - max_high) / entry_price)

            records.append((
                signal_id,
                instrument_id,
                sig_date,
                indicator,
                div_type,
                entry_date,
                float(entry_price),
                'next_open',
                ret_5d, ret_10d, ret_20d, ret_30d,
                mfe_30d, mae_30d,
                comp_5d, comp_10d, comp_20d, comp_30d,
                0.0, # Transaction cost
                now
            ))

        return instrument_id, records

    except Exception as e:
        return instrument_id, e

def main():
    print("=" * 60)
    print("BACKTEST SIGNALS (Parallel)")
    print("=" * 60)
    
    start_time = time.time()
    
    # Record pipeline run
    run_id = f"backtest_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    db = DatabaseManager()
    with db.connect() as conn:
        conn.execute("""
            INSERT INTO pipeline_runs (run_id, stage, status, started_at)
            VALUES (?, 'backtest', 'running', ?)
        """, (run_id, datetime.now(timezone.utc).isoformat()))
        conn.commit()
        
    instruments = fetch_instruments()
    
    print(f"Total instruments to process: {len(instruments)}")
    
    all_records = []
    success = 0
    failed = 0
    empty = 0
    
    with concurrent.futures.ProcessPoolExecutor() as executor:
        futures = {executor.submit(process_instrument, ins): ins for ins in instruments}
        
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            ins_args = futures[future]
            ins_id, symbol = ins_args
            
            try:
                res_id, result = future.result()
                if isinstance(result, Exception):
                    print(f"[{i:03d}/{len(instruments)}] {symbol:<15} ERROR: {result}")
                    failed += 1
                else:
                    if not result:
                        empty += 1
                        print(f"[{i:03d}/{len(instruments)}] {symbol:<15} OK | 0 rows")
                    else:
                        all_records.extend(result)
                        success += 1
                        print(f"[{i:03d}/{len(instruments)}] {symbol:<15} OK | {len(result)} backtest rows")
            except Exception as e:
                print(f"[{i:03d}/{len(instruments)}] {symbol:<15} FATAL ERROR: {e}")
                failed += 1
                
    inserted_count = 0
    if all_records:
        print(f"\nInserting {len(all_records)} backtest records into database (UPSERT)...")
        with db.connect() as conn:
            # Batch insert to handle SQLite limits, using UPSERT on signal_id
            batch_size = 10000
            try:
                for i in range(0, len(all_records), batch_size):
                    batch = all_records[i:i + batch_size]
                    # We rely on UNIQUE (signal_id) in backtest_results to DO UPDATE
                    cursor = conn.executemany("""
                        INSERT INTO backtest_results (
                            signal_id, instrument_id, signal_date, indicator, divergence_type,
                            entry_date, entry_price, entry_type,
                            return_5d, return_10d, return_20d, return_30d,
                            mfe_30d, mae_30d,
                            horizon_5d_complete, horizon_10d_complete, horizon_20d_complete, horizon_30d_complete,
                            transaction_cost, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_id) DO UPDATE SET
                            entry_date = excluded.entry_date,
                            entry_price = excluded.entry_price,
                            return_5d = excluded.return_5d,
                            return_10d = excluded.return_10d,
                            return_20d = excluded.return_20d,
                            return_30d = excluded.return_30d,
                            mfe_30d = excluded.mfe_30d,
                            mae_30d = excluded.mae_30d,
                            horizon_5d_complete = excluded.horizon_5d_complete,
                            horizon_10d_complete = excluded.horizon_10d_complete,
                            horizon_20d_complete = excluded.horizon_20d_complete,
                            horizon_30d_complete = excluded.horizon_30d_complete,
                            created_at = excluded.created_at
                    """, batch)
                    inserted_count += cursor.rowcount
                
                conn.commit()
                print(f"Upserted records.")
            except Exception as e:
                print(f"ERROR during bulk upsert: {e}")
                failed += 1
                
    # Clean very old backtests (> 180 days) after successful execution
    if inserted_count > 0 or (not all_records and failed == 0):
        with db.connect() as conn:
            old_count = conn.execute(
                "SELECT COUNT(*) FROM backtest_results WHERE signal_date < date('now', '-180 days')"
            ).fetchone()[0]
            if old_count > 0:
                conn.execute("DELETE FROM backtest_results WHERE signal_date < date('now', '-180 days')")
                conn.commit()
                print(f"Cleaned {old_count} backtests older than 180 days.")

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
    print(f"Success               : {success}")
    print(f"Failed                : {failed}")
    print(f"Total rows updated    : {len(all_records)}")
    print(f"Time elapsed          : {elapsed:.2f} seconds")
    print(f"Status                : {status}")

if __name__ == "__main__":
    main()
