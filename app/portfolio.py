from datetime import datetime
from app.database import DatabaseManager

class PortfolioManager:
    def __init__(self):
        self.db = DatabaseManager()

    def buy_virtual(self, user_id: int, ins_code: str, volume: int = 1000) -> tuple[bool, str]:
        """Buy a stock virtually."""
        with self.db.connect() as conn:
            cur = conn.cursor()
            
            # Find instrument
            cur.execute("SELECT id, symbol FROM instruments WHERE ins_code = ?", (ins_code,))
            row = cur.fetchone()
            if not row:
                return False, "نماد یافت نشد."
                
            instrument_id = row['id']
            symbol = row['symbol']
            
            # Get latest price
            cur.execute("""
                SELECT close, date FROM ohlcv_daily 
                WHERE instrument_id = ? 
                ORDER BY date DESC LIMIT 1
            """, (instrument_id,))
            price_row = cur.fetchone()
            
            if not price_row:
                return False, "سابقه قیمتی برای این نماد یافت نشد."
                
            buy_price = price_row['close']
            buy_date = price_row['date']
            now = datetime.utcnow().isoformat()
            
            # Insert trade
            cur.execute("""
                INSERT INTO paper_trades (user_id, instrument_id, buy_date, buy_price, volume, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, instrument_id, buy_date, buy_price, volume, now))
            
            conn.commit()
            
            return True, f"✅ خرید مجازی انجام شد.\nنماد: {symbol}\nقیمت: {int(buy_price):,}\nحجم: {volume}"

    def get_open_trades(self, user_id: int) -> list:
        """Returns all open trades with current PnL calculated based on latest prices."""
        with self.db.connect() as conn:
            cur = conn.cursor()
            
            query = """
                SELECT p.id, i.symbol, p.buy_date, p.buy_price, p.volume, p.status,
                       (SELECT close FROM ohlcv_daily o WHERE o.instrument_id = i.id ORDER BY date DESC LIMIT 1) as current_price
                FROM paper_trades p
                JOIN instruments i ON p.instrument_id = i.id
                WHERE p.user_id = ? AND p.status = 'open'
                ORDER BY p.buy_date DESC
            """
            cur.execute(query, (user_id,))
            rows = cur.fetchall()
            
            results = []
            for r in rows:
                trade = dict(r)
                if trade['current_price'] and trade['buy_price']:
                    trade['pnl_percent'] = ((trade['current_price'] - trade['buy_price']) / trade['buy_price']) * 100
                else:
                    trade['pnl_percent'] = 0.0
                results.append(trade)
                
            return results

    def close_trade(self, user_id: int, trade_id: int) -> tuple[bool, str]:
        """Close an open paper trade."""
        with self.db.connect() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                SELECT p.instrument_id, p.buy_price, i.symbol
                FROM paper_trades p
                JOIN instruments i ON p.instrument_id = i.id
                WHERE p.id = ? AND p.user_id = ? AND p.status = 'open'
            """, (trade_id, user_id))
            trade = cur.fetchone()
            
            if not trade:
                return False, "پوزیشن یافت نشد یا از قبل بسته شده است."
                
            instrument_id = trade['instrument_id']
            buy_price = trade['buy_price']
            symbol = trade['symbol']
            
            cur.execute("""
                SELECT close, date FROM ohlcv_daily 
                WHERE instrument_id = ? 
                ORDER BY date DESC LIMIT 1
            """, (instrument_id,))
            price_row = cur.fetchone()
            
            if not price_row:
                return False, "قیمت فعلی یافت نشد."
                
            sell_price = price_row['close']
            sell_date = price_row['date']
            pnl_percent = ((sell_price - buy_price) / buy_price) * 100
            
            cur.execute("""
                UPDATE paper_trades
                SET status = 'closed', sell_price = ?, sell_date = ?, pnl_percent = ?
                WHERE id = ?
            """, (sell_price, sell_date, pnl_percent, trade_id))
            
            conn.commit()
            
            emoji = "🟢" if pnl_percent > 0 else "🔴"
            return True, f"✅ پوزیشن با موفقیت بسته شد.\nنماد: {symbol}\nبازدهی: {pnl_percent:.2f}% {emoji}"
