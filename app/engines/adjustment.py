import pandas as pd
import numpy as np
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

class AdjustmentService:
    """Handles price adjustment based on corporate actions (capital increase, dividends)."""
    
    @staticmethod
    def adjust_prices(df: pd.DataFrame) -> pd.DataFrame:
        """
        Adjust OHLCV dataframe backward using 'yesterday' and 'close' gap.
        TSETMC provides 'yesterday' which is the theoretical previous close adjusted for corporate actions.
        If yesterday_t != close_{t-1}, it indicates a corporate action (split, dividend).
        """
        df = df.copy()
        
        if df.empty:
            return df
            
        if 'yesterday' not in df.columns:
            # Fallback if no yesterday column exists (e.g. before fetching data again)
            df['adj_close'] = df.get('close', pd.Series(dtype=float))
            df['adj_open'] = df.get('open', pd.Series(dtype=float))
            df['adj_high'] = df.get('high', pd.Series(dtype=float))
            df['adj_low'] = df.get('low', pd.Series(dtype=float))
            df['adj_factor'] = 1.0
            return df
            
        df = df.sort_values('date').reset_index(drop=True)
        
        n = len(df)
        adj_factors = np.ones(n)
        
        closes = df['close'].values
        yesterdays = df['yesterday'].values
        
        current_adj = 1.0
        
        for i in range(n-1, 0, -1):
            c_prev = closes[i-1]
            y_curr = yesterdays[i]
            
            # If y_curr is valid and c_prev is valid and they differ
            if c_prev > 0 and y_curr > 0:
                # We calculate the ratio. 
                # TSETMC rounds to 0 decimals for stocks, but let's just use float ratio.
                # If the difference is extremely small (e.g., < 0.1%), it might just be a rounding glitch, 
                # but mathematically applying it is harmless and maintains the exact shape.
                # However, to avoid noise, we only apply adjustments if the gap is > 1% or > 50 Rials.
                # Actually, dividends can be small (e.g. 10 Rials on a 5000 Rial stock is 0.2%).
                # So we should always apply it if they differ.
                ratio = y_curr / c_prev
                
                # To prevent garbage data from ruining the entire series, 
                # we cap extreme ratios if they are clearly errors (e.g. ratio > 1000)
                if 0.001 < ratio < 1000.0 and abs(y_curr - c_prev) > 1.0:
                    current_adj *= ratio
                
            adj_factors[i-1] = current_adj
            
        df['adj_close'] = df['close'] * adj_factors
        df['adj_open'] = df['open'] * adj_factors
        df['adj_high'] = df['high'] * adj_factors
        df['adj_low'] = df['low'] * adj_factors
        df['adj_factor'] = adj_factors
        
        return df
