import pandas as pd
import numpy as np
from app.divergence.engine import DivergenceEngine

def test_regular_bullish():
    # Regular Bullish: Price makes lower low, Indicator makes higher low
    prices = [
        100, 90, 80, 90, 100,  # Pivot 1 at 80 (idx 2)
        100, 100,
        90, 70, 90, 100,       # Pivot 2 at 70 (idx 8)
        100, 100, 100
    ]
    rsi = [
        50, 40, 30, 40, 50,    # Pivot 1 at 30 (idx 2)
        50, 50,
        40, 40, 50, 60,        # Pivot 2 at 40 (idx 8) -> Higher low!
        60, 60, 60
    ]
    
    df = pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=len(prices)),
        'close': prices,
        'rsi': rsi,
        'volume': [1000] * len(prices)
    })
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    bullish = res[res['divergence_type'] == 'regular_bullish']
    assert not bullish.empty, "Failed to detect regular bullish divergence"
    
    sig = bullish.iloc[0]
    # Pivot 2 is at index 8 (date 2023-01-09). Right bars is 2. So it's confirmed at index 10 (2023-01-11)
    # Both price and indicator are confirmed at index 10.
    expected_signal_date = pd.Timestamp('2023-01-11')
    
    assert sig['signal_date'] == expected_signal_date, f"Expected signal date {expected_signal_date}, got {sig['signal_date']}"
    assert sig['price_pivot_1_value'] == 80.0
    assert sig['price_pivot_2_value'] == 70.0
    assert sig['indicator_pivot_1_value'] == 30.0
    assert sig['indicator_pivot_2_value'] == 40.0
    print("✅ Regular Bullish Divergence test passed.")

def main():
    print("Running numerical tests for divergence...")
    test_regular_bullish()
    print("All divergence tests passed.")

if __name__ == "__main__":
    main()
