import sqlite3

import pandas as pd

from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine


DB_PATH = "data/market.db"

INS_CODE = "46348559193224090"


def load_history():
    conn = sqlite3.connect(DB_PATH)

    query = """
        SELECT
            date,
            open,
            high,
            low,
            close,
            volume
        FROM ohlcv_daily
        WHERE instrument_id = (
            SELECT id
            FROM instruments
            WHERE ins_code = ?
        )
        ORDER BY date
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=[INS_CODE],
    )

    conn.close()

    return df


def main():

    df = load_history()

    print("Rows loaded:", len(df))

    indicator_engine = IndicatorEngine()

    df = indicator_engine.calculate_for_symbol(
        df,
        symbol="فولاد",
    )

    divergence_engine = DivergenceEngine(
        left_bars=3,
        right_bars=3,
        min_bars_between_pivots=5,
        max_bars_between_pivots=60,
    )

    signals = divergence_engine.calculate(df)

    print()
    print("Divergence signals:", len(signals))
    print()

    if signals.empty:
        print("No divergence detected.")
        return

    print(
        signals[
            [
                "signal_date",
                "indicator",
                "divergence_type",
                "price_pivot_1_date",
                "price_pivot_2_date",
                "price_pivot_1_value",
                "price_pivot_2_value",
                "indicator_pivot_1_value",
                "indicator_pivot_2_value",
                "bars_between",
            ]
        ].tail(30).to_string(index=False)
    )


if __name__ == "__main__":
    main()
