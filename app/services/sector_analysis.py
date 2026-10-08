import pandas as pd
from typing import Dict, List
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager

class SectorAnalysisService:
    def __init__(self):
        self.db = DatabaseManager()
        
    def get_market_returns(self) -> pd.DataFrame:
        """
        Calculate weekly, monthly, 3-monthly, and yearly returns for all stocks.
        Returns a DataFrame with columns: ins_code, symbol, sector_name, 1w_ret, 1m_ret, 3m_ret, 1y_ret
        """
        sql = """
            SELECT i.ins_code, i.symbol, i.sector_name, o.date, o.close
            FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE i.instrument_type = 'stock' AND i.active = 1
            AND o.date >= date('now', '-400 days')
            ORDER BY i.ins_code, o.date
        """
        with self.db.connect() as conn:
            df = pd.read_sql_query(sql, conn)
            
        if df.empty:
            return pd.DataFrame()
            
        # Group by instrument and calculate periods
        # 1w = 5 days, 1m = 21 days, 3m = 63 days, 1y = 252 days
        results = []
        
        for ins_code, group in df.groupby('ins_code'):
            if len(group) < 2:
                continue
                
            group = group.sort_values('date').reset_index(drop=True)
            latest_close = group.iloc[-1]['close']
            symbol = group.iloc[-1]['symbol']
            sector_name = group.iloc[-1]['sector_name']
            
            def safe_return(n_days: int) -> float:
                if len(group) > n_days:
                    old_close = group.iloc[-(n_days + 1)]['close']
                else:
                    old_close = group.iloc[0]['close']
                if old_close and old_close > 0:
                    return (latest_close - old_close) / old_close
                return 0.0
                
            results.append({
                'ins_code': ins_code,
                'symbol': symbol,
                'sector_name': sector_name,
                '1w_ret': safe_return(5),
                '1m_ret': safe_return(21),
                '3m_ret': safe_return(63),
                '1y_ret': safe_return(252),
            })
            
        return pd.DataFrame(results)

    def get_sector_returns(self) -> pd.DataFrame:
        """
        Calculate equally weighted average returns for each sector.
        """
        df = self.get_market_returns()
        if df.empty:
            return pd.DataFrame()
            
        # Group by sector_name
        # Note: We filter out sectors with less than 2 valid stocks
        sector_df = df.groupby('sector_name').agg({
            '1w_ret': 'mean',
            '1m_ret': 'mean',
            '3m_ret': 'mean',
            '1y_ret': 'mean',
            'ins_code': 'count'
        }).rename(columns={'ins_code': 'stock_count'}).reset_index()
        
        return sector_df[sector_df['stock_count'] > 1]
        
    def get_stock_comparison(self, ins_code: str) -> Dict:
        """
        Compare a specific stock with its sector.
        """
        df = self.get_market_returns()
        if df.empty:
            return {}
            
        stock_row = df[df['ins_code'] == ins_code]
        if stock_row.empty:
            return {}
            
        stock_data = stock_row.iloc[0]
        sector_name = stock_data['sector_name']
        
        sector_df = self.get_sector_returns()
        sector_row = sector_df[sector_df['sector_name'] == sector_name]
        
        if sector_row.empty:
            return {'stock': stock_data.to_dict(), 'sector': None}
            
        return {
            'stock': stock_data.to_dict(),
            'sector': sector_row.iloc[0].to_dict()
        }
