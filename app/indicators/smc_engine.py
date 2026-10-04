import pandas as pd
import numpy as np

class SMCEngine:
    """
    Smart Money Concepts Engine.
    Identifies FVGs (Fair Value Gaps), Order Blocks, and BOS/CHOCH.
    """
    def __init__(self, fvg_min_size: float = 0.005):
        # Minimum gap size relative to price (e.g. 0.5%)
        self.fvg_min_size = fvg_min_size

    def detect_fvg(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detects Fair Value Gaps.
        Returns the dataframe with new columns: 'fvg_type', 'fvg_top', 'fvg_bottom'
        """
        df = df.copy()
        
        # We need at least 3 candles to detect an FVG
        if len(df) < 3:
            return df
            
        df['fvg_type'] = None
        df['fvg_top'] = np.nan
        df['fvg_bottom'] = np.nan
        
        # Bullish FVG: Low[i] > High[i-2]
        bullish_fvg = (df['low'] > df['high'].shift(2)) & ((df['low'] - df['high'].shift(2)) / df['low'] >= self.fvg_min_size)
        
        # Bearish FVG: High[i] < Low[i-2]
        bearish_fvg = (df['high'] < df['low'].shift(2)) & ((df['low'].shift(2) - df['high']) / df['high'] >= self.fvg_min_size)
        
        df.loc[bullish_fvg, 'fvg_type'] = 'bullish'
        df.loc[bullish_fvg, 'fvg_bottom'] = df['high'].shift(2)[bullish_fvg]
        df.loc[bullish_fvg, 'fvg_top'] = df['low'][bullish_fvg]
        
        df.loc[bearish_fvg, 'fvg_type'] = 'bearish'
        df.loc[bearish_fvg, 'fvg_top'] = df['low'].shift(2)[bearish_fvg]
        df.loc[bearish_fvg, 'fvg_bottom'] = df['high'][bearish_fvg]
        
        return df
        
    def detect_order_blocks(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Detects basic Order Blocks based on FVGs.
        A Bullish OB is the last bearish candle before a bullish FVG.
        """
        if 'fvg_type' not in df.columns:
            df = self.detect_fvg(df)
            
        df['ob_type'] = None
        df['ob_top'] = np.nan
        df['ob_bottom'] = np.nan
        
        # Find indices where bullish FVG occurs
        bullish_fvg_idx = df[df['fvg_type'] == 'bullish'].index
        
        for idx in bullish_fvg_idx:
            # We look backwards from idx-2 for the last bearish candle
            # (since idx is the 3rd candle of the FVG pattern, idx-2 is the 1st candle.
            # Usually the OB is the 1st candle or immediately preceding it)
            loc = df.index.get_loc(idx)
            if loc >= 2:
                # Candle 1 of the FVG pattern is at loc - 2
                c1_loc = loc - 2
                # Check if c1 was bearish
                if df.iloc[c1_loc]['close'] < df.iloc[c1_loc]['open']:
                    df.loc[df.index[c1_loc], 'ob_type'] = 'bullish'
                    df.loc[df.index[c1_loc], 'ob_top'] = df.iloc[c1_loc]['high']
                    df.loc[df.index[c1_loc], 'ob_bottom'] = df.iloc[c1_loc]['low']
                    
        # Find bearish FVGs
        bearish_fvg_idx = df[df['fvg_type'] == 'bearish'].index
        for idx in bearish_fvg_idx:
            loc = df.index.get_loc(idx)
            if loc >= 2:
                c1_loc = loc - 2
                if df.iloc[c1_loc]['close'] > df.iloc[c1_loc]['open']:
                    df.loc[df.index[c1_loc], 'ob_type'] = 'bearish'
                    df.loc[df.index[c1_loc], 'ob_top'] = df.iloc[c1_loc]['high']
                    df.loc[df.index[c1_loc], 'ob_bottom'] = df.iloc[c1_loc]['low']
                    
        return df

    def calculate_all(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.detect_fvg(df)
        df = self.detect_order_blocks(df)
        return df
