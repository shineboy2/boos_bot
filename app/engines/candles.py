import pandas as pd
import numpy as np

class CandleEngine:
    """Detects candlestick patterns in OHLCV data."""
    
    @staticmethod
    def detect_hammer(df: pd.DataFrame) -> pd.Series:
        """
        Detect Hammer or Hanging Man pattern.
        Condition: Lower shadow is at least twice the real body, upper shadow is very small.
        """
        body = abs(df['close'] - df['open'])
        lower_shadow = np.minimum(df['open'], df['close']) - df['low']
        upper_shadow = df['high'] - np.maximum(df['open'], df['close'])
        
        # Prevent division by zero
        body = body.replace(0, 0.001)
        
        is_hammer = (lower_shadow > 2 * body) & (upper_shadow < body * 0.2)
        return is_hammer

    @staticmethod
    def detect_marubozu(df: pd.DataFrame) -> pd.Series:
        """
        Detect Bullish Marubozu pattern.
        Condition: Strong bullish body with very little or no shadows.
        """
        body = df['close'] - df['open']
        high_low = df['high'] - df['low']
        
        # Bullish only (close > open)
        is_bullish = df['close'] > df['open']
        
        upper_shadow = df['high'] - df['close']
        lower_shadow = df['open'] - df['low']
        
        # Shadows are less than 5% of the total range, and body is at least 3%
        is_marubozu = is_bullish & (upper_shadow < high_low * 0.05) & (lower_shadow < high_low * 0.05) & ((df['close'] - df['open']) / df['open'] > 0.03)
        return is_marubozu
        
    def find_patterns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Appends pattern columns to dataframe."""
        df = df.copy()
        df['is_hammer'] = self.detect_hammer(df)
        df['is_marubozu'] = self.detect_marubozu(df)
        return df
