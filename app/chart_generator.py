import pandas as pd
import mplfinance as mpf
import os
from pathlib import Path

def generate_candlestick_chart(df: pd.DataFrame, symbol: str, output_path: str = None) -> str:
    """
    Generates an advanced static PNG candlestick chart for the given symbol using mplfinance.
    """
    if df.empty:
        raise ValueError("DataFrame is empty. Cannot generate chart.")
        
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df['date']):
        df['date'] = pd.to_datetime(df['date'])
        
    # Drop rows where 'open', 'high', 'low', 'close', 'volume' are missing to avoid mplfinance errors
    df.dropna(subset=['open', 'high', 'low', 'close', 'volume'], inplace=True)
        
    df.set_index('date', inplace=True)
    df = df.tail(150)
    
    # Required by mplfinance: columns must be capitalized properly
    # The existing DataFrame might have lower case columns 'open', 'high', etc.
    df.rename(columns={
        'open': 'Open',
        'high': 'High',
        'low': 'Low',
        'close': 'Close',
        'volume': 'Volume'
    }, inplace=True)
    
    # Check for indicators
    has_rsi = 'rsi' in df.columns and not df['rsi'].isna().all()
    has_macd = 'macd' in df.columns and not df['macd'].isna().all()
    has_ema = 'ema_50' in df.columns and not df['ema_50'].isna().all()
    has_supertrend = 'supertrend' in df.columns and not df['supertrend'].isna().all()
    
    addplots = []
    panel_ratios = [1, 0.3] # Main price chart, Volume chart (panel 1)
    
    current_panel = 2
    
    if has_ema:
        addplots.append(mpf.make_addplot(df['ema_50'], color='orange', width=1.5, panel=0))
        
    if has_supertrend:
        addplots.append(mpf.make_addplot(df['supertrend'], color='dodgerblue', width=1.5, linestyle=':', panel=0))
        
    if has_rsi:
        addplots.append(mpf.make_addplot(df['rsi'], color='mediumorchid', width=1.5, panel=current_panel, ylabel='RSI'))
        # Overbought/oversold lines
        addplots.append(mpf.make_addplot([70]*len(df), color='red', linestyle='--', panel=current_panel, secondary_y=False))
        addplots.append(mpf.make_addplot([30]*len(df), color='green', linestyle='--', panel=current_panel, secondary_y=False))
        panel_ratios.append(0.3)
        current_panel += 1
        
    if has_macd:
        colors = ['#26a69a' if val >= 0 else '#ef5350' for val in df['macd_histogram']]
        addplots.append(mpf.make_addplot(df['macd'], color='dodgerblue', width=1.5, panel=current_panel, ylabel='MACD'))
        addplots.append(mpf.make_addplot(df['macd_signal'], color='orange', width=1.5, panel=current_panel))
        addplots.append(mpf.make_addplot(df['macd_histogram'], type='bar', color=colors, panel=current_panel))
        panel_ratios.append(0.3)
        current_panel += 1

    if not output_path:
        base_dir = Path(__file__).resolve().parent.parent / "data" / "charts"
        base_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(base_dir / f"{symbol}_chart.png")
        
    mc = mpf.make_marketcolors(
        up='#26a69a', down='#ef5350',
        edge='inherit',
        wick='inherit',
        volume='inherit'
    )
    # Using 'mike' style for a nice dark theme
    s = mpf.make_mpf_style(
        marketcolors=mc, 
        base_mpf_style='nightclouds', 
        gridstyle=':', 
        rc={'axes.titlesize': 14, 'axes.labelsize': 10, 'ytick.labelsize': 10}
    )
    
    # Re-verify that df is not empty after drops
    if df.empty:
        raise ValueError("DataFrame is empty after cleaning. Cannot generate chart.")
        
    mpf.plot(
        df,
        type='candle',
        volume=True,
        title=f'\n{symbol} Advanced Analysis',
        style=s,
        addplot=addplots,
        panel_ratios=panel_ratios,
        figsize=(12, 8),
        datetime_format='%Y-%m-%d',
        xrotation=0,
        tight_layout=True,
        savefig=dict(fname=output_path, dpi=120, bbox_inches='tight')
    )
    
    return output_path
