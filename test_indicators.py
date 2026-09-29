import sqlite3

import pandas as pd

from app.indicators.engine import IndicatorEngine


DB_FILE = "data/market.db"


def main():
    conn = sqlite3.connect(DB_FILE)

    query = """
        SELECT
            i.symbol,
            o.date,
            o.open,
            o.high,
            o.low,
            o.close,
            o.volume
        FROM ohlcv_daily o
        JOIN instruments i
            ON i.id = o.instrument_id
        WHERE i.symbol = ?
        ORDER BY o.date ASC
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=("فولاد",),
    )

    conn.close()

    print(f"Rows loaded: {len(df)}")
    print(f"Date range : {df['date'].min()} -> {df['date'].max()}")

    engine = IndicatorEngine()

    result = engine.calculate_for_symbol(
        df,
        symbol="فولاد",
    )

    columns = [
        "date",
        "close",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "stoch_k",
        "stoch_d",
        "ema_20",
        "ema_50",
        "ema_200",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "bb_width",
        "obv",
        "atr",
        "supertrend",
        "supertrend_direction",
    ]

    print()
    print(result[columns].tail(10).to_string(index=False))

    print()
    print("Indicator columns:")
    for column in columns:
        if column in result.columns:
            print(f"  OK  {column}")


if __name__ == "__main__":
    main()
