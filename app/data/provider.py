import pandas as pd
from typing import Optional, List, Dict
import sys
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.data.providers.cdn_provider import CDNProvider
from app.data.providers.webgw_provider import WebGWProvider
from app.data.normalizer import Normalizer

class DataProvider:
    """Single entry point for all data access."""
    
    def __init__(self):
        self.db = DatabaseManager()
        self.cdn = CDNProvider()
        self.webgw = WebGWProvider()
        self.normalizer = Normalizer()
    
    async def get_ohlcv(self, ins_code: str, min_rows: int = 50) -> pd.DataFrame:
        """Smart data retrieval with fallback."""
        # Check DB freshness
        with self.db.connect() as conn:
            # We assume ohlcv_daily is accessible by instrument_id
            query = """
                SELECT date, open, high, low, close, volume, last, yesterday
                FROM ohlcv_daily o
                JOIN instruments i ON i.id = o.instrument_id
                WHERE i.ins_code = ?
                ORDER BY date
            """
            df = pd.read_sql_query(query, conn, params=(ins_code,))
            
            
        # 1. Ensure we have minimum historical rows
        if len(df) < min_rows:
            if await self.cdn.is_available():
                raw_data = await self.cdn.get_daily_history(ins_code)
                if raw_data:
                    canonical = self.normalizer.normalize_ohlcv(raw_data)
                    self._upsert_ohlcv_batch(ins_code, canonical)
                    
                    with self.db.connect() as conn:
                        df = pd.read_sql_query(query, conn, params=(ins_code,))

        # 2. Fetch live data for today
        live_info = await self.cdn.get_closing_info(ins_code)
        if live_info:
            live_vol = int(live_info.get("qTotTran5J") or 0)
            if live_vol > 0:
                now_iran = datetime.now() # Simplified for phase 2
                today_date = now_iran.strftime('%Y-%m-%d')
                
                if not df.empty and today_date not in df['date'].values:
                    new_row = pd.DataFrame([{
                        "date": today_date,
                        "open": float(live_info.get("priceFirst") or 0),
                        "high": float(live_info.get("priceMax") or 0),
                        "low": float(live_info.get("priceMin") or 0),
                        "close": float(live_info.get("pClosing") or 0),
                        "last": float(live_info.get("pDrCotVal") or 0),
                        "volume": live_vol
                    }])
                    df = pd.concat([df, new_row], ignore_index=True)
                    
            df.attrs['info_data'] = live_info
        
        return df

    def _upsert_ohlcv_batch(self, ins_code: str, canonical_rows: List[Dict]):
        """Upsert records into the database."""
        with self.db.connect() as conn:
            cur = conn.execute("SELECT id FROM instruments WHERE ins_code = ?", (ins_code,))
            res = cur.fetchone()
            if not res:
                return # Instrument doesn't exist
            
            instrument_id = res['id']
            now = datetime.utcnow().isoformat()
            
            records = []
            for row in canonical_rows:
                records.append((
                    instrument_id, row['date'], row['open'], row['high'], row['low'],
                    row['close'], row['last'], row['volume'], row['value'], row['trade_count'],
                    'cdn', now
                ))
            
            conn.executemany("""
                INSERT OR IGNORE INTO ohlcv_daily (
                    instrument_id, date, open, high, low, close, last, volume, value, trade_count, source, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()

    async def check_connectivity(self) -> Dict:
        """Check all providers and return status."""
        return {
            "cdn": await self.cdn.is_available(),
            "webgw": await self.webgw.is_available(),
            "db_last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S") # Placeholder
        }
