from abc import ABC, abstractmethod
import pandas as pd
from typing import List

class FilterRule(ABC):
    @abstractmethod
    def apply(self, df: pd.DataFrame) -> pd.Series:
        """
        Returns a boolean mask of the same length as the dataframe.
        True means the row passes the filter.
        """
        pass

class FilterEngine:
    """
    Applies a chain of rules to a DataFrame.
    Returns the filtered DataFrame.
    """
    def __init__(self, rules: List[FilterRule] = None):
        self.rules = rules or []

    def add_rule(self, rule: FilterRule):
        self.rules.append(rule)

    def filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or not self.rules:
            return df
            
        mask = pd.Series(True, index=df.index)
        for rule in self.rules:
            mask = mask & rule.apply(df)
            
        return df[mask].copy()

# ---- Pre-defined common rules ----

class MinVolumeRule(FilterRule):
    def __init__(self, min_vol: int):
        self.min_vol = min_vol

    def apply(self, df: pd.DataFrame) -> pd.Series:
        if 'volume' not in df.columns:
            return pd.Series(True, index=df.index)
        return df['volume'] >= self.min_vol

class MinValueRule(FilterRule):
    def __init__(self, min_value: int):
        self.min_value = min_value

    def apply(self, df: pd.DataFrame) -> pd.Series:
        if 'value' not in df.columns:
            return pd.Series(True, index=df.index)
        return df['value'] >= self.min_value

class RsiRangeRule(FilterRule):
    def __init__(self, min_rsi: float, max_rsi: float):
        self.min_rsi = min_rsi
        self.max_rsi = max_rsi

    def apply(self, df: pd.DataFrame) -> pd.Series:
        if 'rsi' not in df.columns:
            return pd.Series(True, index=df.index)
        return (df['rsi'] >= self.min_rsi) & (df['rsi'] <= self.max_rsi)

class TrendRule(FilterRule):
    def __init__(self, indicator: str, trend: str):
        self.indicator = indicator
        self.trend = trend # "bullish" or "bearish"

    def apply(self, df: pd.DataFrame) -> pd.Series:
        if self.indicator not in df.columns or 'close' not in df.columns:
            return pd.Series(True, index=df.index)
            
        if self.trend == "bullish":
            return df['close'] > df[self.indicator]
        else:
            return df['close'] < df[self.indicator]
