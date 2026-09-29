import sqlite3
import pandas as pd

DB_FILE = "data/market.db"

def test_query(name, query):
    print(f"--- {name} ---")
    try:
        conn = sqlite3.connect(DB_FILE)
        df = pd.read_sql_query(query, conn)
        conn.close()
        print(f"Rows returned: {len(df)}")
        if len(df) > 0:
            print(df.head())
    except Exception as e:
        print(f"Error: {e}")
    print()

q_pos = """
SELECT i.symbol, o.last, o.close
FROM instruments i
JOIN ohlcv_daily o ON i.id = o.instrument_id
WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
AND o.last > o.close
AND i.market_board NOT LIKE '%صندوق%'
AND i.symbol NOT LIKE '%ح'
LIMIT 5
"""

q_vol = """
WITH Ranked AS (
    SELECT i.symbol, o.volume, o.date,
           AVG(o.volume) OVER (PARTITION BY i.id ORDER BY o.date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) as avg_vol
    FROM instruments i
    JOIN ohlcv_daily o ON i.id = o.instrument_id
    WHERE i.active = 1
)
SELECT symbol, volume, avg_vol FROM Ranked
WHERE date = (SELECT MAX(date) FROM ohlcv_daily)
AND volume > 4 * avg_vol
LIMIT 5
"""

q_candles = """
SELECT i.symbol, o.open, o.high, o.low, o.close
FROM instruments i
JOIN ohlcv_daily o ON i.id = o.instrument_id
WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
AND (
    (o.close > o.open AND o.high - o.close < (o.high - o.low) * 0.05 AND o.open - o.low < (o.high - o.low) * 0.05 AND (o.close - o.open) / o.open > 0.03)
    OR
    (MIN(o.open, o.close) - o.low > 2 * ABS(o.close - o.open) AND o.high - MAX(o.open, o.close) < ABS(o.close - o.open) * 0.2)
)
LIMIT 5
"""

test_query("Positive Diff", q_pos)
test_query("Suspicious Vol", q_vol)
test_query("Candlesticks", q_candles)
