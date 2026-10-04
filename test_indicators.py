import pandas as pd
import numpy as np
from app.indicators.engine import IndicatorEngine

def test_rsi_numeric():
    # Construct a simple series
    # 14 days of up 1, down 0
    # For a perfect 14-day up streak, RSI is 100
    prices = [10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24]
    df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=len(prices)),
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [1000] * len(prices)
    })
    
    engine = IndicatorEngine()
    res = engine.calculate(df)
    
    # After 14 consecutive up days, RSI should be 100
    assert np.isclose(res['rsi'].iloc[-1], 100.0), f"Expected RSI 100, got {res['rsi'].iloc[-1]}"
    print("✅ RSI test passed.")

def test_macd_numeric():
    prices = [10] * 30 + [20] * 10
    df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=len(prices)),
        'open': prices,
        'high': prices,
        'low': prices,
        'close': prices,
        'volume': [1000] * len(prices)
    })
    engine = IndicatorEngine()
    res = engine.calculate(df)
    
    macd_val = res['macd'].iloc[-1]
    # We just ensure MACD isn't NaN and reacted to the jump
    assert not np.isnan(macd_val) and macd_val > 0, "MACD should be positive after a price jump"
    print("✅ MACD test passed.")
    
def main():
    print("Running numerical tests for indicators...")
    test_rsi_numeric()
    test_macd_numeric()
    print("All indicator tests passed.")

if __name__ == "__main__":
    main()
