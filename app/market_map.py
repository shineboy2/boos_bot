import pandas as pd
import requests
import matplotlib.pyplot as plt
import squarify
import matplotlib.colors as mcolors
import numpy as np
from pathlib import Path

def generate_market_map(output_path: str = None) -> str:
    """
    Generates a treemap representing the TSETMC market map based on trade value and price change.
    """
    url_bourse = "https://cdn.tsetmc.com/api/MarketMap/GetMarketMapData/1"
    url_fara = "https://cdn.tsetmc.com/api/MarketMap/GetMarketMapData/2"
    
    from config import DEFAULT_HEADERS
    
    from tenacity import retry, stop_after_attempt, wait_exponential
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    def fetch_data(url):
        r = requests.get(url, headers=DEFAULT_HEADERS, timeout=15)
        if r.status_code != 200:
            raise RuntimeError(f"TSETMC returned status {r.status_code}")
        try:
            return r.json()
        except Exception:
            raise RuntimeError(f"TSETMC returned invalid JSON. Possibly blocked by Cloudflare. Response length: {len(r.text)}")
        
    try:
        r1 = fetch_data(url_bourse)
        r2 = fetch_data(url_fara)
        data = r1 + r2
    except Exception as e:
        raise RuntimeError(f"خطا در ارتباط با سرور TSETMC (ممکن است IP مسدود شده باشد): {e}")

    records = []
    for item in data:
        sec = item.get("sec", {})
        if not sec:
            sec = item.get("sector", {})
        
        sector_name = sec.get("lSecVal", "ناشناخته") if isinstance(sec, dict) else "ناشناخته"
        
        symbol = item.get("lVal18AFC", "")
        # value is usually qTotCap or similar in TSETMC api, often returned as 'value' or 'v'
        val = float(item.get("v", 0) or item.get("qTotCap", 0) or 0) 
        change_pct = float(item.get("pc", 0) or item.get("color", 0) or item.get("percent", 0) or 0)
        
        if val > 0:
            records.append({
                "symbol": symbol,
                "sector": sector_name,
                "value": val,
                "change": change_pct
            })
            
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("No valid data found for market map.")
        
    # Group by sector to get sector sizes and colors
    sector_group = df.groupby("sector").agg(
        total_value=("value", "sum"),
        avg_change=("change", "mean")
    ).reset_index()
    
    # Sort and take top 20 sectors to avoid clutter
    sector_group = sector_group.sort_values("total_value", ascending=False).head(20)
    
    sizes = sector_group["total_value"].values
    labels = [f"{row['sector']}\n{row['avg_change']:.1f}%" for _, row in sector_group.iterrows()]
    
    # Custom colormap for green/red
    cmap = mcolors.LinearSegmentedColormap.from_list("rg", ["#ef5350", "#1e1e1e", "#26a69a"], N=256)
    norm = mcolors.TwoSlopeNorm(vmin=-5, vcenter=0, vmax=5)
    colors = [cmap(norm(val)) for val in sector_group["avg_change"]]
    
    # Plot
    plt.style.use('dark_background')
    fig, ax = plt.subplots(1, 1, figsize=(14, 10))
    fig.patch.set_facecolor('#121212')
    ax.set_facecolor('#121212')
    
    # Font setup for Persian (if available, otherwise fallback)
    plt.rcParams['font.sans-serif'] = ['Tahoma', 'Arial', 'sans-serif']
    
    squarify.plot(
        sizes=sizes, 
        label=labels, 
        color=colors, 
        alpha=0.9, 
        ax=ax,
        text_kwargs={'fontsize': 10, 'color': 'white', 'weight': 'bold'}
    )
    
    ax.set_title("نقشه بازار بورس و فرابورس", fontsize=18, color='white', pad=20)
    plt.axis('off')
    
    if not output_path:
        base_dir = Path(__file__).resolve().parent.parent / "data" / "charts"
        base_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(base_dir / "market_map.png")
        
    plt.savefig(output_path, dpi=120, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    
    return output_path
