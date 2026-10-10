import pandas as pd
import numpy as np
from app.divergence.engine import DivergenceEngine

def _create_df(prices, rsi):
    return pd.DataFrame({
        'date': pd.date_range('2023-01-01', periods=len(prices)),
        'close': prices,
        'rsi': rsi,
        'volume': [1000] * len(prices)
    })

def test_regular_bullish():
    # Regular Bullish: Price makes lower low, Indicator makes higher low
    prices = [100, 90, 80, 90, 100, 100, 100, 90, 70, 90, 100, 100, 100, 100]
    rsi    = [50,  40, 30, 40, 50,  50,  50,  40, 40, 50, 60,  60,  60,  60]
    df = _create_df(prices, rsi)
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    bullish = res[res['divergence_type'] == 'regular_bullish']
    assert not bullish.empty, "Failed to detect regular bullish divergence"
    
    sig = bullish.iloc[0]
    assert sig['signal_date'] == pd.Timestamp('2023-01-11')
    assert sig['price_pivot_1_value'] == 80.0
    assert sig['price_pivot_2_value'] == 70.0
    assert sig['indicator_pivot_1_value'] == 30.0
    assert sig['indicator_pivot_2_value'] == 40.0
    print("✅ Regular Bullish test passed.")

def test_regular_bearish():
    # Regular Bearish: Price makes higher high, Indicator makes lower high
    prices = [100, 110, 120, 110, 100, 100, 100, 110, 130, 110, 100, 100, 100, 100]
    rsi    = [50,  60,  70,  60,  50,  50,  50,  60,  60,  50,  40,  40,  40,  40]
    df = _create_df(prices, rsi)
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    bearish = res[res['divergence_type'] == 'regular_bearish']
    assert not bearish.empty, "Failed to detect regular bearish divergence"
    print("✅ Regular Bearish test passed.")

def test_hidden_bullish():
    # Hidden Bullish: Price makes higher low, Indicator makes lower low
    prices = [100, 90, 80, 90, 100, 100, 100, 100, 90, 100, 110, 110, 110, 110]
    rsi    = [50,  40, 30, 40, 50,  50,  50,  40,  20, 40,  50,  50,  50,  50]
    df = _create_df(prices, rsi)
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    h_bullish = res[res['divergence_type'] == 'hidden_bullish']
    assert not h_bullish.empty, "Failed to detect hidden bullish divergence"
    print("✅ Hidden Bullish test passed.")

def test_hidden_bearish():
    # Hidden Bearish: Price makes lower high, Indicator makes higher high
    prices = [100, 110, 120, 110, 100, 100, 100, 100, 110, 100, 90, 90, 90, 90]
    rsi    = [50,  60,  70,  60,  50,  50,  50,  60,  80,  60,  50, 50, 50, 50]
    df = _create_df(prices, rsi)
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    h_bearish = res[res['divergence_type'] == 'hidden_bearish']
    assert not h_bearish.empty, "Failed to detect hidden bearish divergence"
    print("✅ Hidden Bearish test passed.")

def test_no_divergence():
    # No Divergence: Price and indicator move in tandem
    prices = [100, 90, 80, 90, 100, 100, 100, 90, 70, 90, 100, 100, 100, 100]
    rsi    = [50,  40, 30, 40, 50,  50,  50,  40, 20, 40, 50,  50,  50,  50]
    df = _create_df(prices, rsi)
    
    engine = DivergenceEngine(left_bars=2, right_bars=2, min_bars_between_pivots=3)
    res = engine.calculate(df)
    
    assert res.empty, "Engine generated a signal when there should be no divergence"
    print("✅ No Divergence test passed.")

def main():
    print("Running numerical tests for divergence...")
    test_regular_bullish()
    test_regular_bearish()
    test_hidden_bullish()
    test_hidden_bearish()
    test_no_divergence()
    print("All divergence tests passed.")

if __name__ == "__main__":
    main()
