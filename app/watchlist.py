from app.database import DatabaseManager

class WatchlistManager:
    def __init__(self):
        self.db = DatabaseManager()

    def get_watchlist(self, user_id: int):
        """Returns a list of (instrument_id, ins_code, symbol) for the user."""
        with self.db.connect() as conn:
            query = """
                SELECT i.id, i.ins_code, i.symbol 
                FROM user_watchlists w
                JOIN instruments i ON w.instrument_id = i.id
                WHERE w.user_id = ?
            """
            cur = conn.cursor()
            cur.execute(query, (user_id,))
            return cur.fetchall()

    def add_to_watchlist(self, user_id: int, symbol: str) -> tuple[bool, str]:
        """
        Adds a symbol to the user's watchlist.
        Returns (success, message).
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            # Find the instrument
            cur.execute("SELECT id FROM instruments WHERE symbol = ?", (symbol,))
            row = cur.fetchone()
            
            if not row:
                # Try finding it with partial match
                cur.execute("SELECT id, symbol FROM instruments WHERE symbol LIKE ?", (f"%{symbol}%",))
                results = cur.fetchall()
                if not results:
                    return False, f"نماد '{symbol}' در دیتابیس یافت نشد."
                
                # If multiple or one, let's just use the exact or first match.
                # It's better if user gives exact symbol. Let's just return error if not exact.
                return False, f"نماد '{symbol}' یافت نشد. آیا منظور شما {results[0]['symbol']} بود؟"
                
            instrument_id = row['id']
            
            try:
                from datetime import datetime
                now = datetime.utcnow().isoformat()
                cur.execute(
                    "INSERT INTO user_watchlists (user_id, instrument_id, created_at) VALUES (?, ?, ?)",
                    (user_id, instrument_id, now)
                )
                conn.commit()
                return True, f"✅ نماد '{symbol}' با موفقیت به واچ‌لیست شما اضافه شد."
            except Exception as e:
                if "UNIQUE constraint failed" in str(e):
                    return False, f"⚠️ نماد '{symbol}' قبلاً در واچ‌لیست شما وجود دارد."
                return False, f"❌ خطای پایگاه داده: {e}"

    def remove_from_watchlist(self, user_id: int, symbol: str) -> tuple[bool, str]:
        """
        Removes a symbol from the user's watchlist.
        Returns (success, message).
        """
        with self.db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id FROM instruments WHERE symbol = ?", (symbol,))
            row = cur.fetchone()
            
            if not row:
                return False, f"نماد '{symbol}' در دیتابیس یافت نشد."
                
            instrument_id = row['id']
            
            cur.execute(
                "DELETE FROM user_watchlists WHERE user_id = ? AND instrument_id = ?",
                (user_id, instrument_id)
            )
            
            if cur.rowcount > 0:
                conn.commit()
                return True, f"✅ نماد '{symbol}' از واچ‌لیست حذف شد."
            else:
                return False, f"⚠️ نماد '{symbol}' در واچ‌لیست شما وجود نداشت."
