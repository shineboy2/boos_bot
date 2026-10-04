import pandas as pd
from typing import List, Dict
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager

class ScannerService:
    """Handles market scanning based on technical and statistical conditions."""
    
    def __init__(self):
        self.db = DatabaseManager()
        
    def _execute_query(self, sql: str, title: str) -> Dict:
        """Execute scanner query and format results."""
        try:
            with self.db.connect() as conn:
                df = pd.read_sql_query(sql, conn)
            
            return {
                "success": True,
                "title": title,
                "data": df
            }
        except Exception as e:
            return {
                "success": False,
                "title": title,
                "error": str(e)
            }
            
    def scan_positive_diff(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND o.close > 0
        AND (o.last - o.close) / o.close >= 0.03
        AND i.instrument_type = 'stock'
        ORDER BY ((o.last - o.close) / o.close) DESC
        LIMIT 45
        """
        return self._execute_query(sql, "📈 اختلاف قیمت مثبت (بیشتر از ۳٪)")
        
    def scan_negative_diff(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND o.close > 0
        AND (o.last - o.close) / o.close <= -0.03
        AND i.instrument_type = 'stock'
        ORDER BY ((o.last - o.close) / o.close) ASC
        LIMIT 45
        """
        return self._execute_query(sql, "📉 اختلاف قیمت منفی (کمتر از -۳٪)")
        
    def scan_suspicious_volume(self) -> Dict:
        sql = """
        WITH Ranked AS (
            SELECT i.ins_code, i.symbol, o.volume, o.date,
                   AVG(o.volume) OVER (PARTITION BY i.id ORDER BY o.date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) as avg_vol
            FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE i.active = 1
            AND i.instrument_type = 'stock'
        )
        SELECT ins_code, symbol FROM Ranked
        WHERE date = (SELECT MAX(date) FROM ohlcv_daily)
        AND volume > 4 * avg_vol
        ORDER BY (volume / avg_vol) DESC
        LIMIT 45
        """
        return self._execute_query(sql, "⚠️ حجم معاملات مشکوک")

    def scan_candles(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND i.instrument_type = 'stock'
        AND (
            (o.close > o.open AND o.high - o.close < (o.high - o.low) * 0.05 AND o.open - o.low < (o.high - o.low) * 0.05 AND (o.close - o.open) / o.open > 0.03)
            OR
            ((CASE WHEN o.open < o.close THEN o.open ELSE o.close END) - o.low > 2 * ABS(o.close - o.open) AND o.high - (CASE WHEN o.open > o.close THEN o.open ELSE o.close END) < ABS(o.close - o.open) * 0.2)
        )
        ORDER BY o.volume DESC
        LIMIT 45
        """
        return self._execute_query(sql, "🕯️ کندل‌های مستعد رشد")

    def scan_queue(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND o.close > 0
        AND (o.last - o.close) / o.close >= 0.015
        AND i.instrument_type = 'stock'
        ORDER BY ((o.last - o.close) / o.close) DESC
        LIMIT 45
        """
        return self._execute_query(sql, "🚀 مستعد صف خرید فردا")
        
    def scan_rights(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND i.instrument_type = 'right'
        ORDER BY o.volume DESC
        LIMIT 45
        """
        return self._execute_query(sql, "⚖️ لیست حق تقدم‌ها")
        
    def scan_etfs(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN ohlcv_daily o ON i.id = o.instrument_id
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND i.instrument_type = 'etf'
        ORDER BY o.volume DESC
        LIMIT 45
        """
        return self._execute_query(sql, "💼 صندوق‌های قابل معامله")
        
    def scan_smc(self) -> Dict:
        """Scan all active stocks for recent SMC patterns using pandas."""
        try:
            with self.db.connect() as conn:
                # Fetch last 10 days for all active stocks
                sql = """
                SELECT i.ins_code, i.symbol, o.date, o.open, o.high, o.low, o.close
                FROM instruments i
                JOIN ohlcv_daily o ON i.id = o.instrument_id
                WHERE i.active = 1 AND i.instrument_type = 'stock'
                AND o.date >= date('now', '-20 days')
                ORDER BY i.ins_code, o.date
                """
                df = pd.read_sql_query(sql, conn)
                
            if df.empty:
                return {"success": False, "title": "SMC Scan", "error": "No data found"}
                
            # We need SMCEngine
            from app.indicators.smc_engine import SMCEngine
            engine = SMCEngine()
            
            results = []
            grouped = df.groupby('ins_code')
            
            for ins_code, group in grouped:
                if len(group) < 10:
                    continue
                    
                calc = engine.calculate_all(group)
                latest = calc.iloc[-1]
                
                # Check if FVG or OB formed today (or yesterday if no data today yet)
                # Just checking the last row
                has_pattern = False
                pattern_name = ""
                
                if latest['fvg_type'] == 'bullish':
                    pattern_name = "🟢 شکاف ارزش صعودی (Bullish FVG)"
                    has_pattern = True
                elif latest['fvg_type'] == 'bearish':
                    pattern_name = "🔴 شکاف ارزش نزولی (Bearish FVG)"
                    has_pattern = True
                elif latest['ob_type'] == 'bullish':
                    pattern_name = "🟩 اردر بلاک صعودی (Bullish OB)"
                    has_pattern = True
                elif latest['ob_type'] == 'bearish':
                    pattern_name = "🟥 اردر بلاک نزولی (Bearish OB)"
                    has_pattern = True
                    
                if has_pattern:
                    results.append({
                        'ins_code': ins_code,
                        'symbol': latest['symbol'] + f" ({pattern_name})"
                    })
                    
            res_df = pd.DataFrame(results)
            # Take top 45
            if not res_df.empty:
                res_df = res_df.head(45)
                
            return {
                "success": True,
                "title": "👁️ اسکن پول هوشمند (SMC)",
                "data": res_df
            }
            
        except Exception as e:
            return {
                "success": False,
                "title": "SMC Scan",
                "error": str(e)
            }

    def scan_golden(self) -> Dict:
        """Scan for Golden Signal: SMC Pattern + Real Money Flow Inflow."""
        # 1. Get money flow symbols first (since it's a fast SQL query)
        sql = """
        SELECT i.ins_code, c.real_buy_value, c.real_sell_value 
        FROM instruments i
        JOIN client_type_daily c ON i.id = c.instrument_id
        JOIN ohlcv_daily o ON i.id = o.instrument_id AND o.date = c.date
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND c.real_buy_value > c.real_sell_value * 2
        AND c.real_buy_count < c.real_sell_count
        AND i.instrument_type = 'stock'
        """
        try:
            with self.db.connect() as conn:
                money_df = pd.read_sql_query(sql, conn)
                
            if money_df.empty:
                return {"success": True, "title": "🌟 سیگنال طلایی", "data": pd.DataFrame()}
                
            # 2. Get SMC results
            smc_res = self.scan_smc()
            if not smc_res['success'] or smc_res['data'].empty:
                return {"success": True, "title": "🌟 سیگنال طلایی", "data": pd.DataFrame()}
                
            smc_df = smc_res['data']
            
            # 3. Intersection
            # money_df has ins_code, smc_df has ins_code and symbol
            # We want rows in smc_df that have ins_code in money_df
            golden_df = smc_df[smc_df['ins_code'].isin(money_df['ins_code'])].copy()
            
            if not golden_df.empty:
                golden_df['symbol'] = golden_df['symbol'].apply(lambda x: "⭐ " + x)
                
            return {
                "success": True,
                "title": "🌟 سیگنال طلایی (SMC + تابلو)",
                "data": golden_df
            }
        except Exception as e:
            return {
                "success": False,
                "title": "Golden Scan",
                "error": str(e)
            }

    def scan_real_money_flow(self) -> Dict:
        sql = """
        SELECT i.ins_code, i.symbol FROM instruments i
        JOIN client_type_daily c ON i.id = c.instrument_id
        JOIN ohlcv_daily o ON i.id = o.instrument_id AND o.date = c.date
        WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
        AND c.real_buy_value > c.real_sell_value * 2
        AND c.real_buy_count < c.real_sell_count
        AND i.instrument_type = 'stock'
        ORDER BY (c.real_buy_value - c.real_sell_value) DESC
        LIMIT 45
        """
        return self._execute_query(sql, "💰 ورود پول حقیقی هوشمند")
