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

def init_db():
    db = DatabaseManager()
    with db.connect() as conn:
        # We clear the previous calculations
        conn.execute("DELETE FROM backtest_results")
        conn.commit()

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
                SELECT date, open, high, low, close
                FROM ohlcv_daily
                WHERE instrument_id = ?
                ORDER BY date
            """
            ohlc_df = pd.read_sql_query(ohlc_query, conn, params=(instrument_id,))

        if signals_df.empty or ohlc_df.empty:
            return instrument_id, []

        # Create mapping of date to integer index
        ohlc_df['idx'] = range(len(ohlc_df))
        date_to_idx = ohlc_df.set_index('date')['idx'].to_dict()
        
        closes = ohlc_df['close'].values
        highs = ohlc_df['high'].values
        lows = ohlc_df['low'].values
        
        total_rows = len(ohlc_df)
        
        now = datetime.utcnow().isoformat()
        records = []
        
        for _, row in signals_df.iterrows():
            signal_id = row['id']
            sig_date = row['signal_date']
            indicator = row['indicator']
            div_type = row['divergence_type']
            is_bullish = 'bullish' in div_type
            
            if sig_date not in date_to_idx:
                continue
                
            entry_idx = date_to_idx[sig_date]
            entry_price = closes[entry_idx]
            
            if entry_price <= 0:
                continue
            
            # Helper to safely calculate return
            def get_return(forward_days):
                target_idx = entry_idx + forward_days
                if target_idx < total_rows:
                    price = closes[target_idx]
                    if is_bullish:
                        return (price - entry_price) / entry_price
                    else:
                        return (entry_price - price) / entry_price
                return None

            ret_5d = get_return(5)
            ret_10d = get_return(10)
            ret_20d = get_return(20)
            ret_30d = get_return(30)
            
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
                    mfe_30d = (max_high - entry_price) / entry_price
                    mae_30d = (min_low - entry_price) / entry_price
                else:
                    mfe_30d = (entry_price - min_low) / entry_price
                    mae_30d = (entry_price - max_high) / entry_price

            records.append((
                signal_id,
                instrument_id,
                sig_date,
                indicator,
                div_type,
                float(entry_price),
                float(ret_5d) if ret_5d is not None else None,
                float(ret_10d) if ret_10d is not None else None,
                float(ret_20d) if ret_20d is not None else None,
                float(ret_30d) if ret_30d is not None else None,
                float(mfe_30d) if mfe_30d is not None else None,
                float(mae_30d) if mae_30d is not None else None,
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
    init_db()
    instruments = fetch_instruments()
    
    print(f"Total instruments to process: {len(instruments)}")
    
    all_records = []
    success = 0
    failed = 0
    
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
                    all_records.extend(result)
                    success += 1
                    print(f"[{i:03d}/{len(instruments)}] {symbol:<15} OK | {len(result)} backtest rows")
            except Exception as e:
                print(f"[{i:03d}/{len(instruments)}] {symbol:<15} FATAL ERROR: {e}")
                failed += 1
                
    # Bulk insert
    print("\\nInserting backtest records into database...")
    if all_records:
        db = DatabaseManager()
        with db.connect() as conn:
            # Batch insert to handle SQLite limits
            batch_size = 50000
            for i in range(0, len(all_records), batch_size):
                batch = all_records[i:i + batch_size]
                conn.executemany("""
                    INSERT INTO backtest_results (
                        signal_id, instrument_id, signal_date, indicator, divergence_type,
                        entry_price, return_5d, return_10d, return_20d, return_30d,
                        mfe_30d, mae_30d, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, batch)
            
            conn.commit()

    elapsed = time.time() - start_time
    print("=" * 60)
    print("FINISHED")
    print("=" * 60)
    print(f"Success             : {success}")
    print(f"Failed              : {failed}")
    print(f"Total rows saved    : {len(all_records)}")
    print(f"Time elapsed        : {elapsed:.2f} seconds")

if __name__ == "__main__":
    main()
