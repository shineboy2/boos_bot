import pandas as pd
import json
from app.database import DatabaseManager

def generate_daily_scores(db: DatabaseManager = None):
    if db is None:
        db = DatabaseManager()
        
    print("Generating Daily Confluence Scores...")
    
    with db.connect() as conn:
        # Get latest date
        latest_date = conn.execute("SELECT MAX(date) FROM ohlcv_daily").fetchone()[0]
        if not latest_date:
            print("No data in ohlcv_daily")
            return
            
        # Get active stock instruments
        instruments = pd.read_sql_query("SELECT id, symbol, ins_code FROM instruments WHERE active = 1 AND instrument_type = 'stock'", conn)
        
        scores = []
        
        # 1. Divergence Signals
        div_query = """
            SELECT instrument_id, indicator 
            FROM divergence_signals 
            WHERE signal_date = ? AND divergence_type LIKE '%bullish%'
        """
        div_df = pd.read_sql_query(div_query, conn, params=(latest_date,))
        
        # 2. Suspicious Volume (Volume >= 4x avg_vol)
        vol_query = """
            WITH Ranked AS (
                SELECT i.id as instrument_id, o.volume, o.date,
                       AVG(o.volume) OVER (PARTITION BY i.id ORDER BY o.date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) as avg_vol
                FROM instruments i
                JOIN ohlcv_daily o ON i.id = o.instrument_id
                WHERE i.active = 1 AND i.instrument_type = 'stock'
            )
            SELECT instrument_id, volume, avg_vol
            FROM Ranked
            WHERE date = ?
            AND volume >= 4 * avg_vol
        """
        vol_df = pd.read_sql_query(vol_query, conn, params=(latest_date,))
        
        # 3. Real Money Flow
        money_query = """
            SELECT c.instrument_id, c.real_buy_value, c.real_sell_value, c.real_buy_count, c.real_sell_count
            FROM client_type_daily c
            JOIN ohlcv_daily o ON c.instrument_id = o.instrument_id AND c.date = o.date
            WHERE c.date = ?
            AND c.real_buy_value > c.real_sell_value * 2
            AND c.real_buy_count < c.real_sell_count
        """
        money_df = pd.read_sql_query(money_query, conn, params=(latest_date,))
        
        # 4. Candles
        candle_query = """
            SELECT instrument_id
            FROM ohlcv_daily
            WHERE date = ?
            AND (
                (close > open AND high - close < (high - low) * 0.05 AND open - low < (high - low) * 0.05 AND (close - open) / open > 0.03)
                OR
                ((CASE WHEN open < close THEN open ELSE close END) - low > 2 * ABS(close - open) AND high - (CASE WHEN open > close THEN open ELSE close END) < ABS(close - open) * 0.2)
            )
        """
        candle_df = pd.read_sql_query(candle_query, conn, params=(latest_date,))
        
        # 5. SMC Scan
        try:
            from app.services.scanner import ScannerService
            scanner = ScannerService()
            smc_res = scanner.scan_smc()
            smc_ins_codes = set()
            if smc_res['success'] and not smc_res['data'].empty:
                smc_ins_codes = set(smc_res['data']['ins_code'].tolist())
        except Exception as e:
            print(f"Error running SMC for confluence: {e}")
            smc_ins_codes = set()
            
        # Iterate and score
        for _, row in instruments.iterrows():
            ins_id = row['id']
            ins_code = row['ins_code']
            
            total_score = 0
            d_score = 0
            v_score = 0
            m_score = 0
            s_score = 0
            c_score = 0
            reasons = []
            
            # Divergence check
            ins_divs = div_df[div_df['instrument_id'] == ins_id]
            if not ins_divs.empty:
                inds = ins_divs['indicator'].tolist()
                has_quality = any(i.upper() in ['MACD', 'OBV'] for i in inds)
                if has_quality:
                    d_score = 30
                    reasons.append("واگرایی معتبر (MACD/OBV)")
                else:
                    d_score = 20
                    reasons.append("واگرایی عادی (RSI/Stoch)")
                total_score += d_score
                
            # Volume check
            ins_vol = vol_df[vol_df['instrument_id'] == ins_id]
            if not ins_vol.empty:
                ratio = ins_vol.iloc[0]['volume'] / (ins_vol.iloc[0]['avg_vol'] or 1)
                v_score = 15
                total_score += v_score
                reasons.append(f"حجم مشکوک ({ratio:.1f} برابر)")
                
            # Money Flow check
            ins_money = money_df[money_df['instrument_id'] == ins_id]
            if not ins_money.empty:
                m_score = 20
                total_score += m_score
                reasons.append("ورود پول هوشمند")
                
            # Candle check
            ins_candle = candle_df[candle_df['instrument_id'] == ins_id]
            if not ins_candle.empty:
                c_score = 10
                total_score += c_score
                reasons.append("الگوی کندلی صعودی")
                
            # SMC check
            if ins_code in smc_ins_codes:
                s_score = 15
                total_score += s_score
                reasons.append("الگوی پرایس اکشن (SMC)")
                
            if total_score > 0:
                scores.append({
                    "instrument_id": ins_id,
                    "date": latest_date,
                    "total_score": total_score,
                    "divergence_score": d_score,
                    "volume_score": v_score,
                    "money_flow_score": m_score,
                    "smc_score": s_score,
                    "candle_score": c_score,
                    "reasons": json.dumps(reasons, ensure_ascii=False)
                })
                
        # Insert to DB
        if scores:
            conn.execute("DELETE FROM daily_scores WHERE date = ?", (latest_date,))
            conn.executemany("""
                INSERT INTO daily_scores (
                    instrument_id, date, total_score, divergence_score, 
                    volume_score, money_flow_score, smc_score, candle_score, reasons
                ) VALUES (
                    :instrument_id, :date, :total_score, :divergence_score,
                    :volume_score, :money_flow_score, :smc_score, :candle_score, :reasons
                )
            """, scores)
            conn.commit()
            print(f"✅ Generated confluence scores for {len(scores)} stocks on {latest_date}")
        else:
            print("No stocks scored any points today.")

if __name__ == "__main__":
    generate_daily_scores()
