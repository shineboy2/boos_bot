import pandas as pd
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine
from app.indicators.smc_engine import SMCEngine

class AnalysisService:
    """Service to handle high-level technical analysis operations."""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.indicator_engine = IndicatorEngine()
        self.divergence_engine = DivergenceEngine(
            left_bars=3, right_bars=3,
            min_bars_between_pivots=5, max_bars_between_pivots=60,
            max_calendar_days=120, indicator_tolerance_bars=2
        )
        self.smc_engine = SMCEngine()
        
    def analyze_dataframe(self, df: pd.DataFrame, symbol: str = "Unknown") -> pd.DataFrame:
        """Run standard indicator calculations on a dataframe."""
        if df.empty or len(df) < 50:
            return pd.DataFrame()
            
        res = self.indicator_engine.calculate_for_symbol(df, symbol=symbol)
        res = self.smc_engine.calculate_all(res)
        return res
        
    def get_latest_divergence(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate divergences on a dataframe with indicators."""
        if df.empty:
            return pd.DataFrame()
            
        return self.divergence_engine.calculate(df)
        
    def get_latest_smc(self, df: pd.DataFrame) -> dict:
        """Returns the most recent FVGs and OBs found in the last 10 candles."""
        if df.empty or 'fvg_type' not in df.columns:
            return {}
            
        recent = df.tail(10)
        fvg_bullish = recent[recent['fvg_type'] == 'bullish']
        fvg_bearish = recent[recent['fvg_type'] == 'bearish']
        
        ob_bullish = recent[recent['ob_type'] == 'bullish']
        ob_bearish = recent[recent['ob_type'] == 'bearish']
        
        return {
            'has_bullish_fvg': not fvg_bullish.empty,
            'has_bearish_fvg': not fvg_bearish.empty,
            'has_bullish_ob': not ob_bullish.empty,
            'has_bearish_ob': not ob_bearish.empty
        }
