#!/usr/bin/env python3

import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_FILE = BASE_DIR / "data" / "market.db"
ARTIFACT_PATH = "/home/shahab/.gemini/antigravity-ide/brain/3f76fd18-3f27-4946-83df-07135ec465ec/backtest_report.md"

def generate_report(conn, title, date_filter=""):
    query = f"""
        SELECT 
            indicator, 
            divergence_type,
            return_20d,
            mfe_30d,
            mae_30d
        FROM backtest_results
        {date_filter}
    """
    df = pd.read_sql_query(query, conn)
    
    if df.empty:
        return f"## {title}\\nNo data found.\\n"
        
    df['is_win'] = df['return_20d'] > 0
    
    # Calculate metrics
    agg_df = df.groupby(['indicator', 'divergence_type']).agg(
        total_signals=('return_20d', 'count'),
        win_rate=('is_win', 'mean'),
        median_return=('return_20d', 'median'),
        mean_mfe=('mfe_30d', 'mean'),
        mean_mae=('mae_30d', 'mean')
    ).reset_index()
    
    # Format columns
    agg_df['win_rate'] = (agg_df['win_rate'] * 100).round(2).astype(str) + "%"
    agg_df['median_return'] = (agg_df['median_return'] * 100).round(2).astype(str) + "%"
    agg_df['mean_mfe'] = (agg_df['mean_mfe'] * 100).round(2).astype(str) + "%"
    agg_df['mean_mae'] = (agg_df['mean_mae'] * 100).round(2).astype(str) + "%"
    
    # Sort for better readability (by indicator, then win rate descending)
    agg_df = agg_df.sort_values(by=['indicator', 'win_rate'], ascending=[True, False])
    
    # Generate markdown table
    md = [f"## {title}"]
    md.append("| Indicator | Divergence Type | Signals | Win Rate (20d) | Median Ret (20d) | Mean MFE (30d) | Mean MAE (30d) |")
    md.append("|-----------|-----------------|---------|----------------|------------------|----------------|----------------|")
    
    for _, row in agg_df.iterrows():
        md.append(f"| {row['indicator'].upper()} | {row['divergence_type']} | {row['total_signals']} | {row['win_rate']} | {row['median_return']} | {row['mean_mfe']} | {row['mean_mae']} |")
        
    return "\\n".join(md) + "\\n"

def main():
    conn = sqlite3.connect(DB_FILE)
    
    full_report = generate_report(conn, "All Time Backtest Results (2007 - 2026)")
    summer_report = generate_report(conn, "Summer 2026 Results (June 21 - Present)", "WHERE signal_date >= '2026-06-21'")
    
    conn.close()
    
    content = "# Backtest Results Report\\n\\n" + full_report + "\\n" + summer_report
    
    with open(ARTIFACT_PATH, "w", encoding="utf-8") as f:
        f.write(content)
        
    print(f"Report generated at {ARTIFACT_PATH}")

if __name__ == "__main__":
    main()
