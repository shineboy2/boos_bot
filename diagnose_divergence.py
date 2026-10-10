import pandas as pd
import numpy as np
from datetime import datetime
from app.database import DatabaseManager
from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine, Pivot
from app.engines.adjustment import AdjustmentService

class DiagnosticDivergenceEngine(DivergenceEngine):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stats = {}
    
    def calculate_diagnostics(self, df: pd.DataFrame, price_column: str = "close") -> dict:
        self.stats = {
            "price_low_pivots": 0,
            "price_high_pivots": 0,
            "indicators": {},
        }
        
        data = self._prepare_dataframe(df=df, price_column=price_column)
        if data.empty:
            return self.stats
            
        price_low_pivots = self._find_pivots(
            values=data[price_column].to_numpy(dtype=float),
            dates=data["date"].to_numpy(),
            pivot_type="low",
        )
        self.stats["price_low_pivots"] = len(price_low_pivots)
        
        price_high_pivots = self._find_pivots(
            values=data[price_column].to_numpy(dtype=float),
            dates=data["date"].to_numpy(),
            pivot_type="high",
        )
        self.stats["price_high_pivots"] = len(price_high_pivots)
        
        for indicator in self.indicators:
            if indicator not in data.columns:
                continue
                
            indicator_data = data[["date", price_column, indicator]].copy()
            if indicator_data.empty:
                continue
                
            indicator_values = indicator_data[indicator].to_numpy(dtype=float)
            
            indicator_low_pivots = self._find_pivots(
                values=indicator_values, dates=indicator_data["date"].to_numpy(), pivot_type="low"
            )
            indicator_high_pivots = self._find_pivots(
                values=indicator_values, dates=indicator_data["date"].to_numpy(), pivot_type="high"
            )
            
            ind_stats = {
                "low_pivots": len(indicator_low_pivots),
                "high_pivots": len(indicator_high_pivots),
                "rejected_distance": 0,
                "rejected_tolerance": 0,
                "rejected_invalid": 0,
                "bullish_found": 0,
                "bearish_found": 0
            }
            
            # Analyze bullish
            bul_found, bul_rej_dist, bul_rej_tol, bul_rej_inv = self._diagnose_divergences(
                price_pivots=price_low_pivots, indicator_pivots=indicator_low_pivots, 
                indicator=indicator, is_bullish=True
            )
            
            # Analyze bearish
            bea_found, bea_rej_dist, bea_rej_tol, bea_rej_inv = self._diagnose_divergences(
                price_pivots=price_high_pivots, indicator_pivots=indicator_high_pivots, 
                indicator=indicator, is_bullish=False
            )
            
            ind_stats["bullish_found"] = bul_found
            ind_stats["bearish_found"] = bea_found
            ind_stats["rejected_distance"] = bul_rej_dist + bea_rej_dist
            ind_stats["rejected_tolerance"] = bul_rej_tol + bea_rej_tol
            ind_stats["rejected_invalid"] = bul_rej_inv + bea_rej_inv
            
            self.stats["indicators"][indicator] = ind_stats
            
        return self.stats

    def _diagnose_divergences(self, price_pivots, indicator_pivots, indicator, is_bullish):
        found = 0
        rej_dist = 0
        rej_tol = 0
        rej_inv = 0
        
        if len(price_pivots) < 2 or len(indicator_pivots) < 2:
            return found, rej_dist, rej_tol, rej_inv
            
        for p1_idx in range(len(price_pivots) - 1):
            p1 = price_pivots[p1_idx]
            for p2_idx in range(p1_idx + 1, len(price_pivots)):
                p2 = price_pivots[p2_idx]
                bars_between = p2.index - p1.index
                
                if bars_between < self.min_bars_between_pivots:
                    rej_dist += 1
                    continue
                if bars_between > self.max_bars_between_pivots:
                    rej_dist += 1
                    break
                    
                matched = self._match_indicator_pivots(p1, p2, indicator_pivots)
                if matched is None:
                    rej_tol += 1
                    continue
                    
                i1, i2 = matched
                
                div_types = ["regular_bullish", "hidden_bullish"] if is_bullish else ["regular_bearish", "hidden_bearish"]
                valid = False
                for dt in div_types:
                    if self._is_valid_divergence(p1, p2, i1, i2, dt):
                        valid = True
                        break
                
                if not valid:
                    rej_inv += 1
                else:
                    found += 1
                    
        return found, rej_dist, rej_tol, rej_inv


def get_sample_symbols(limit=5):
    db = DatabaseManager()
    with db.connect() as conn:
        cur = conn.execute("SELECT id, symbol FROM instruments WHERE active = 1 LIMIT ?", (limit,))
        return [(row['id'], row['symbol']) for row in cur.fetchall()]

def fetch_data(instrument_id):
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
        return pd.DataFrame()
        
    df = AdjustmentService.adjust_prices(df)
    df['close'] = df['adj_close']
    df['open'] = df['adj_open']
    df['high'] = df['adj_high']
    df['low'] = df['adj_low']
    return df

def run_diagnostics():
    symbols = get_sample_symbols(limit=3)
    indicator_engine = IndicatorEngine()
    
    for instrument_id, symbol in symbols:
        print(f"\n{'='*50}\nDiagnostic Report for: {symbol}\n{'='*50}")
        df = fetch_data(instrument_id)
        if df.empty:
            print("Not enough data.")
            continue
            
        df_calc = indicator_engine.calculate_for_symbol(df, symbol=symbol)
        
        # P0: Diagnostic Report with default settings
        engine_default = DiagnosticDivergenceEngine(
            left_bars=3, right_bars=3, 
            min_bars_between_pivots=5, max_bars_between_pivots=60, 
            indicator_tolerance_bars=2
        )
        stats_default = engine_default.calculate_diagnostics(df_calc, price_column="close")
        
        print("\n--- P0: Diagnostic Results (Price Column: close) ---")
        print(f"Price Low Pivots: {stats_default['price_low_pivots']}")
        print(f"Price High Pivots: {stats_default['price_high_pivots']}")
        for ind, st in stats_default['indicators'].items():
            print(f"  Indicator: {ind}")
            print(f"    Low Pivots: {st['low_pivots']}, High Pivots: {st['high_pivots']}")
            print(f"    Pairs Rejected by Distance (min/max bars): {st['rejected_distance']}")
            print(f"    Pairs Rejected by Tolerance (no ind pivot match): {st['rejected_tolerance']}")
            print(f"    Pairs Rejected by Invalid Shape: {st['rejected_invalid']}")
            print(f"    Confirmed Bullish: {st['bullish_found']}, Confirmed Bearish: {st['bearish_found']}")

        # P1: Compare close with low/high
        # For bullish, we use 'low' column for price. For bearish, we use 'high'.
        # To do this cleanly, we'll run it twice: once with price_column='low' for bullish stats, 
        # once with price_column='high' for bearish stats.
        engine_low = DiagnosticDivergenceEngine(
            left_bars=3, right_bars=3, 
            min_bars_between_pivots=5, max_bars_between_pivots=60, 
            indicator_tolerance_bars=2
        )
        stats_low = engine_low.calculate_diagnostics(df_calc, price_column="low")
        
        engine_high = DiagnosticDivergenceEngine(
            left_bars=3, right_bars=3, 
            min_bars_between_pivots=5, max_bars_between_pivots=60, 
            indicator_tolerance_bars=2
        )
        stats_high = engine_high.calculate_diagnostics(df_calc, price_column="high")
        
        print("\n--- P1: Compare 'close' vs 'low'/'high' ---")
        
        for ind in stats_default['indicators'].keys():
            bul_close = stats_default['indicators'][ind]['bullish_found']
            bul_low = stats_low['indicators'][ind]['bullish_found']
            
            bea_close = stats_default['indicators'][ind]['bearish_found']
            bea_high = stats_high['indicators'][ind]['bearish_found']
            
            print(f"  Indicator: {ind}")
            print(f"    Bullish Signals -> Using 'close': {bul_close} | Using 'low': {bul_low}")
            print(f"    Bearish Signals -> Using 'close': {bea_close} | Using 'high': {bea_high}")


if __name__ == "__main__":
    run_diagnostics()
