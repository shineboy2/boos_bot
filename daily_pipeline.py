import subprocess
import time
from datetime import datetime
import os
import sys
import asyncio
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.logging_config import setup_logging
from app.watchlist import WatchlistManager
from telegram import Bot
from telegram.constants import ParseMode
from dotenv import load_dotenv

logger = setup_logging("daily_pipeline")

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def send_daily_report():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set. Skipping report.")
        return
        
    bot = Bot(token=TOKEN)
    db = DatabaseManager()
    wm = WatchlistManager()
    
    with db.connect() as conn:
        # Get latest signal date
        cur = conn.cursor()
        cur.execute("SELECT MAX(signal_date) FROM divergence_signals")
        latest_date = cur.fetchone()[0]
        
        if not latest_date:
            logger.info("No signals found in db.")
            return
            
        logger.info(f"Sending reports for date: {latest_date}")
        
        # Get unique users from watchlist
        cur.execute("SELECT DISTINCT user_id FROM user_watchlists")
        users = [row['user_id'] for row in cur.fetchall()]
        
        for user_id in users:
            try:
                watchlist_items = wm.get_watchlist(user_id)
                if not watchlist_items:
                    continue
                    
                msg_lines = [f"📊 <b>گزارش روزانه واچ‌لیست ({latest_date})</b>\n"]
                found_signals = False
                
                for item in watchlist_items:
                    instrument_id = item['id']
                    symbol = item['symbol']
                    
                    cur.execute("""
                        SELECT indicator, divergence_type 
                        FROM divergence_signals 
                        WHERE instrument_id = ? AND signal_date = ? AND divergence_type LIKE '%bullish%'
                    """, (instrument_id, latest_date))
                    signals = cur.fetchall()
                    
                    if signals:
                        found_signals = True
                        msg_lines.append(f"🟢 <b>{symbol}:</b>")
                        for sig in signals:
                            ind = sig['indicator'].upper()
                            dt = sig['divergence_type'].replace('_', ' ').title()
                            msg_lines.append(f"  • {ind} - {dt}")
                        msg_lines.append("")
                
                if found_signals:
                    msg = "\n".join(msg_lines)
                    await bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.HTML)
                    logger.info(f"Sent watchlist report to {user_id}")
            except Exception as e:
                logger.error(f"Failed to send report to {user_id}: {e}")

        # Broadcast general best signals to all allowed users
        try:
            allowed_users_str = os.getenv("ALLOWED_USER_IDS", "")
            allowed_users = [int(u.strip()) for u in allowed_users_str.split(",") if u.strip()]
            
            # Find symbols with multiple bullish signals (confluence)
            cur.execute("""
                SELECT i.symbol, COUNT(d.id) as sig_count, GROUP_CONCAT(d.indicator || ' ' || d.divergence_type) as details
                FROM divergence_signals d
                JOIN instruments i ON d.instrument_id = i.id
                WHERE d.signal_date = ? AND d.divergence_type LIKE '%bullish%'
                GROUP BY i.id
                HAVING sig_count >= 2
                ORDER BY sig_count DESC
                LIMIT 10
            """, (latest_date,))
            
            best_signals = cur.fetchall()
            if best_signals:
                msg_lines = [f"🚀 <b>بهترین سیگنال‌های ترکیبی بازار ({latest_date})</b>\n"]
                for b in best_signals:
                    msg_lines.append(f"🔥 <b>{b['symbol']}</b> ({b['sig_count']} سیگنال واگرایی)")
                
                msg = "\n".join(msg_lines)
                for user_id in allowed_users:
                    try:
                        await bot.send_message(chat_id=user_id, text=msg, parse_mode=ParseMode.HTML)
                        logger.info(f"Sent best signals report to {user_id}")
                    except Exception as e:
                        pass
        except Exception as e:
            logger.error(f"Failed to broadcast best signals: {e}")

def main():
    logger.info("Starting Daily Pipeline...")
    start_time = time.time()
    
    # 1. Update Today
    logger.info("Running update_today.py...")
    res = subprocess.run([sys.executable, str(BASE_DIR / "update_today.py")])
    if res.returncode != 0:
        logger.error("update_today.py failed!")
        return
        
    # 2. Calculate Signals
    logger.info("Running calculate_signals.py...")
    res = subprocess.run([sys.executable, str(BASE_DIR / "calculate_signals.py")])
    if res.returncode != 0:
        logger.error("calculate_signals.py failed!")
        return
        
    # 3. Send Telegram Reports
    logger.info("Sending Telegram Reports...")
    asyncio.run(send_daily_report())
    
    elapsed = time.time() - start_time
    logger.info(f"Daily Pipeline finished in {elapsed:.2f} seconds.")

if __name__ == "__main__":
    main()
