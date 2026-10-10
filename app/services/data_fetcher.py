import asyncio
import sys
from pathlib import Path
from typing import Callable, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.data.provider import DataProvider
from app.database import DatabaseManager

class DataFetcherService:
    """Service to handle high-level fetch operations from the Telegram Bot."""
    
    def __init__(self):
        self.provider = DataProvider()
        self.db = DatabaseManager()
    
    async def update_today_prices(self) -> int:
        """Update closing info for all active instruments."""
        from datetime import datetime
        now_iran = datetime.now() 
        today_date = now_iran.strftime('%Y-%m-%d')
        
        with self.db.connect() as conn:
            cur = conn.execute("SELECT ins_code FROM instruments WHERE active = 1")
            ins_codes = [row['ins_code'] for row in cur.fetchall()]
            
        if not await self.provider.cdn.is_available():
            return 0
            
        success_count = 0
        
        # Batch requests
        chunk_size = self.provider.cdn.CONCURRENT_LIMIT
        for i in range(0, len(ins_codes), chunk_size):
            chunk = ins_codes[i:i+chunk_size]
            tasks = [self.provider.cdn.get_closing_info(code) for code in chunk]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for code, result in zip(chunk, results):
                if isinstance(result, dict) and result:
                    live_vol = int(result.get("qTotTran5J") or 0)
                    if live_vol > 0:
                        canonical_row = {
                            "date": today_date,
                            "open": float(result.get("priceFirst") or 0),
                            "high": float(result.get("priceMax") or 0),
                            "low": float(result.get("priceMin") or 0),
                            "close": float(result.get("pClosing") or 0),
                            "last": float(result.get("pDrCotVal") or 0),
                            "volume": live_vol,
                            "value": float(result.get("qTotCap") or 0),
                            "trade_count": int(result.get("zTotTran") or 0),
                        }
                        self.provider._upsert_ohlcv_batch(code, [canonical_row])
                        success_count += 1
                        
        return success_count
        
    async def fetch_all_history(self, progress_callback: Callable[[int, int], None] = None) -> Tuple[int, int]:
        """Fetch history for all instruments."""
        with self.db.connect() as conn:
            cur = conn.execute("SELECT ins_code FROM instruments WHERE active = 1")
            ins_codes = [row['ins_code'] for row in cur.fetchall()]
            
        total = len(ins_codes)
        done = 0
        
        if not await self.provider.cdn.is_available():
            return total, 0

        chunk_size = self.provider.cdn.CONCURRENT_LIMIT
        for i in range(0, len(ins_codes), chunk_size):
            chunk = ins_codes[i:i+chunk_size]
            tasks = [self.provider.get_ohlcv(code, min_rows=99999) for code in chunk]
            await asyncio.gather(*tasks, return_exceptions=True)
            
            done += len(chunk)
            if progress_callback:
                # We need to make sure the callback is awaited if it's an async function
                res = progress_callback(done, total)
                if asyncio.iscoroutine(res):
                    await res
                    
        return total, done
        
    async def update_instruments(self) -> int:
        """Fetch instrument master list."""
        # For phase 2, stub.
        return 0
        
    async def update_client_types(self) -> int:
        """Fetch real/legal info."""
        # For phase 2, stub.
        return 0
