import os
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from dotenv import load_dotenv

from app.database import DatabaseManager

load_dotenv()
ALLOWED_USER_IDS = set(
    int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()
)

db = DatabaseManager()

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id if update.effective_user else None
        if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
            print(f"Unauthorized access denied for user_id: {user_id}")
            if update.message:
                await update.message.reply_text("⛔ شما دسترسی استفاده از این ربات را ندارید.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ عدم دسترسی.", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def get_latest_signals():
    """Fetch and aggregate the latest bullish signals from the database."""
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT MAX(signal_date) FROM divergence_signals")
            latest_date = cur.fetchone()[0]
            
            if not latest_date:
                return None, {}
                
            query = """
                SELECT i.symbol, d.indicator, d.divergence_type
                FROM divergence_signals d
                JOIN instruments i ON d.instrument_id = i.id
                WHERE d.signal_date = ? AND d.divergence_type LIKE '%bullish%'
            """
            cur.execute(query, (latest_date,))
            rows = cur.fetchall()
        
        signals_by_symbol = {}
        for symbol, indicator, div_type in rows:
            if symbol not in signals_by_symbol:
                signals_by_symbol[symbol] = set()
            
            ind = indicator.upper()
            if ind == "STOCH_K":
                ind = "STOCH"
                
            dt = div_type.replace('_', ' ').title()
            signals_by_symbol[symbol].add(f"<i>{ind}</i> ({dt})")
            
        return latest_date, signals_by_symbol
    except Exception as e:
        print(f"Database error: {e}")
        return None, {}

def format_signals_message(latest_date, signals_by_symbol):
    if not latest_date or not signals_by_symbol:
        return "No bullish signals found."
        
    confluence_signals = {}
    quality_signals = {}
    other_signals = {}
    
    for symbol, indicators_set in signals_by_symbol.items():
        indicators = sorted(list(indicators_set))
        
        if len(indicators) >= 2:
            confluence_signals[symbol] = indicators
        elif "MACD" in indicators[0] or "OBV" in indicators[0]:
            quality_signals[symbol] = indicators
        else:
            other_signals[symbol] = indicators
            
    msg = [f"📅 <b>Latest Signals for {latest_date}</b>\n"]
    
    if confluence_signals:
        msg.append("⭐⭐⭐ <b>High Probability (Confluence)</b>")
        msg.append("<i>(Multiple indicators triggered on the same day)</i>")
        for symbol, indicators in confluence_signals.items():
            inds_str = ", ".join(indicators)
            msg.append(f"🟢 <b>{symbol}</b>: {inds_str}")
        msg.append("\n")
        
    if quality_signals:
        msg.append("⭐ <b>Quality Bullish Signals</b>")
        msg.append("<i>(Strong individual indicators: MACD & OBV)</i>")
        for symbol, indicators in quality_signals.items():
            msg.append(f"🔹 <b>{symbol}</b>: {indicators[0]}")
        msg.append("\n")
        
    if not confluence_signals and not quality_signals and not other_signals:
        msg.append("No bullish signals found today.\n")
        
    if other_signals:
        msg.append("⚪ <b>Other Signals</b>")
        msg.append("<i>(Single RSI/Stochastic signals)</i>")
        for symbol, indicators in other_signals.items():
            msg.append(f"🔸 <b>{symbol}</b>: {indicators[0]}")
        msg.append("\n")
        
    return "\n".join(msg)
