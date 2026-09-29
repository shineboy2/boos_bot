#!/usr/bin/env python3

import os
import sqlite3
import asyncio
import socket
import httpx
from datetime import datetime
from pathlib import Path

# --- Force IPv4 Patch (Fix for Proton VPN IPv6 blackhole) ---
old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(*args, **kwargs):
    responses = old_getaddrinfo(*args, **kwargs)
    return [response for response in responses if response[0] == socket.AF_INET]
socket.getaddrinfo = new_getaddrinfo
# -------------------------------------------------------------

import sys
import pandas as pd
from functools import wraps

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

BASE_DIR = Path(__file__).resolve().parent

# Add project root to sys.path so we can import app modules
sys.path.append(str(BASE_DIR))
from app.indicators.engine import IndicatorEngine
from app.divergence.engine import DivergenceEngine
from app.database import DatabaseManager
from app.utils import parse_date, normalize_symbol
from app.watchlist import WatchlistManager
from app.chart_generator import generate_candlestick_chart

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_IDS = set(
    int(uid.strip()) for uid in os.getenv("ALLOWED_USER_IDS", "").split(",") if uid.strip()
)

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

db = DatabaseManager()
watchlist = WatchlistManager()

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
    other_signals_count = 0
    
    for symbol, indicators_set in signals_by_symbol.items():
        indicators = sorted(list(indicators_set))
        
        if len(indicators) >= 2:
            confluence_signals[symbol] = indicators
        elif "MACD" in indicators[0] or "OBV" in indicators[0]:
            quality_signals[symbol] = indicators
        else:
            other_signals_count += 1
            
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
        
    if not confluence_signals and not quality_signals:
        msg.append("No confluence or quality MACD/OBV signals found today.\n")
        
    if other_signals_count > 0:
        msg.append(f"<i>Plus {other_signals_count} other symbols with single RSI/Stochastic signals (hidden for brevity).</i>")
        
    return "\n".join(msg)

async def fetch_api_data(ins_code):
    url_info = f"http://cdn.tsetmc.com/api/ClosingPrice/GetClosingPriceInfo/{ins_code}"
    
    from app.database import DatabaseManager
    import pandas as pd
    from datetime import datetime, timezone, timedelta
    
    # 1. Fetch History from local DB
    db = DatabaseManager()
    with db.connect() as conn:
        df = pd.read_sql_query(
            "SELECT date, open, high, low, close, last, volume FROM ohlcv_daily "
            "WHERE instrument_id = (SELECT id FROM instruments WHERE ins_code = ?) "
            "ORDER BY date ASC", conn, params=(ins_code,)
        )
        
    # 2. Fetch Live data from API
    info_data = {}
    try:
        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            r_info = await client.get(url_info, headers={"User-Agent": "Mozilla/5.0"})
            if r_info.status_code == 200:
                info_data = r_info.json().get("closingPriceInfo", {})
    except Exception as e:
        print(f"Error fetching live info: {e}")
            
    # 3. Append Live data if available and market is open
    if info_data:
        live_vol = int(info_data.get("qTotTran5J") or 0)
        # TSETMC sets volume to 0 at night/closed market.
        if live_vol > 0:
            live_open = float(info_data.get("priceFirst") or 0)
            live_high = float(info_data.get("priceMax") or 0)
            live_low = float(info_data.get("priceMin") or 0)
            live_close = float(info_data.get("pClosing") or 0)
            live_last = float(info_data.get("pDrCotVal") or 0)
            
            now_iran = datetime.now(timezone(timedelta(hours=3, minutes=30)))
            today_date = now_iran.strftime('%Y-%m-%d')
            
            # Check if we don't already have today's date in DB
            if not df.empty and today_date not in df['date'].values:
                new_row = pd.DataFrame([{
                    "date": today_date, "open": live_open, "high": live_high, 
                    "low": live_low, "close": live_close, "last": live_last, "volume": live_vol
                }])
                df = pd.concat([df, new_row], ignore_index=True)

    if not df.empty:
        df = df.tail(150).reset_index(drop=True)
        df.attrs['info_data'] = info_data
        
    return df


@restricted
async def marketmap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🗺️ در حال دریافت اطلاعات بازار و رسم نقشه (این عملیات ممکن است چند ثانیه طول بکشد)...")
    try:
        from app.market_map import generate_market_map
        import asyncio
        loop = asyncio.get_event_loop()
        output_path = await loop.run_in_executor(None, generate_market_map, None)
        
        with open(output_path, 'rb') as f:
            await update.message.reply_photo(photo=f, caption="✅ نقشه زنده بازار (بورس و فرابورس)")
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ خطا در رسم نقشه بازار: {e}")

import time
@restricted
async def run_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 در حال اجرای آپدیت روزانه و استخراج سیگنال‌ها...\n(گزارش لحظه‌ای در زیر نمایش داده می‌شود)\n\n<pre>شروع...</pre>", parse_mode=ParseMode.HTML)
    
    import asyncio
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, "-u", str(BASE_DIR / "daily_pipeline.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        
        logs = []
        last_edit_time = time.time()
        
        while True:
            line = await process.stdout.readline()
            if not line:
                break
                
            decoded_line = line.decode('utf-8').strip()
            if decoded_line:
                logs.append(decoded_line)
                if len(logs) > 10:
                    logs.pop(0)
            
            current_time = time.time()
            if current_time - last_edit_time > 2.0:
                log_text = "\n".join(logs)
                try:
                    await status_msg.edit_text(f"🔄 <b>در حال اجرای آپدیت...</b>\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
                last_edit_time = current_time
                
        await process.wait()
        
        if process.returncode == 0:
            await status_msg.edit_text("✅ آپدیت با موفقیت به پایان رسید.\nسیگنال‌ها استخراج و در صورت وجود ارسال شدند.", parse_mode=ParseMode.HTML)
        else:
            log_text = "\n".join(logs)
            await status_msg.edit_text(f"❌ خطا در آپدیت:\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(f"❌ خطای سیستمی هنگام اجرای آپدیت: {e}")

@restricted
async def add_symbol_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /add <symbol>")
        return
    symbol = " ".join(context.args)
    symbol = normalize_symbol(symbol)
    user_id = update.effective_user.id
    success, msg = watchlist.add_to_watchlist(user_id, symbol)
    await update.message.reply_text(msg)

@restricted
async def remove_symbol_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /remove <symbol>")
        return
    symbol = " ".join(context.args)
    symbol = normalize_symbol(symbol)
    user_id = update.effective_user.id
    success, msg = watchlist.remove_from_watchlist(user_id, symbol)
    await update.message.reply_text(msg)

@restricted
async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    items = watchlist.get_watchlist(user_id)
    if not items:
        await update.message.reply_text("واچ‌لیست شما خالی است. با دستور /add نمادها را اضافه کنید.")
        return
    
    msg = "📋 <b>واچ‌لیست شما:</b>\n\n"
    for item in items:
        msg += f"• <b>{item['symbol']}</b>\n"
    msg += "\nبرای تحلیل، نام نماد را ارسال کنید."
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>به ربات تحلیلگر هوشمند بورس خوش آمدید!</b>\n\n"
        "این ربات به شما در پیدا کردن بهترین موقعیت‌های معاملاتی بر اساس واگرایی‌ها و تحلیل‌های تکنیکال کمک می‌کند.\n\n"
        "<b>دستورات اصلی ربات:</b>\n"
        "• /update - فچ کردن دیتای امروز، آپدیت دیتابیس و استخراج سیگنال‌ها\n"
        "• /today - مشاهده بهترین سیگنال‌های واگرایی امروز\n"
        "• /scans - لیست فیلترهای هوشمند بازار\n"
        "• /scan - اجرای اسکنر کامل بازار (زمان‌بر)\n\n"
        "<b>مدیریت واچ‌لیست:</b>\n"
        "• /watchlist - مشاهده نمادهای مورد علاقه شما\n"
        "• <code>/add فولاد</code> - اضافه کردن نماد به واچ‌لیست\n"
        "• <code>/remove فولاد</code> - حذف نماد از واچ‌لیست\n\n"
        "🔎 <b>تحلیل لایو:</b>\n"
        "برای دریافت چارت تکنیکال و وضعیت هر نماد، کافیست نام آن را ارسال کنید (مثلاً بفرستید: <b>شپنا</b>)."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

@restricted
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest signals from database...", parse_mode=ParseMode.HTML)
    latest_date, signals_by_symbol = get_latest_signals()
    
    message = format_signals_message(latest_date, signals_by_symbol)
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)

@restricted
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 <b>Starting full market divergence scan...</b>\nThis will take about 5 minutes.\nI will notify you when it's done.", parse_mode=ParseMode.HTML)
    
    try:
        process = await asyncio.create_subprocess_exec(
            BASE_DIR / ".venv" / "bin" / "python", 
            BASE_DIR / "calculate_signals.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode == 0:
            await update.message.reply_text("✅ <b>Full market scan completed successfully!</b>\nSend /today to view the new signals.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ An error occurred during the scan. Please check server logs.", parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to run scanner: {e}", parse_mode=ParseMode.HTML)

@restricted
async def filters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 اختلاف قیمت مثبت", callback_data="scan_pos_diff")],
        [InlineKeyboardButton("📉 اختلاف قیمت منفی", callback_data="scan_neg_diff")],
        [InlineKeyboardButton("⚠️ حجم معاملات مشکوک", callback_data="scan_sus_vol")],
        [InlineKeyboardButton("🚀 مستعد صف خرید فردا", callback_data="scan_queue")],
        [InlineKeyboardButton("⚖️ لیست حق تقدم‌ها", callback_data="scan_rights")],
        [InlineKeyboardButton("💼 صندوق‌های قابل معامله", callback_data="scan_etfs")],
        [InlineKeyboardButton("🕯️ کندل‌های مستعد رشد (چکش/ماروبوزو)", callback_data="scan_candles")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔎 <b>فیلترهای هوشمند بازار</b>\nیک مورد را انتخاب کنید:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/"):
        return
        
    status_msg = await update.message.reply_text(f"Searching for <b>{text}</b> (fetching from API)...", parse_mode=ParseMode.HTML)
    
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ins_code, symbol FROM instruments")
            all_instruments = cur.fetchall()
        
        qt = normalize_symbol(text)
        
        row = None
        for r_code, r_sym in all_instruments:
            norm_sym = r_sym.replace('ك', 'ک').replace('ي', 'ی')
            if norm_sym == qt:
                row = (r_code, r_sym)
                break
                
        if not row:
            for r_code, r_sym in all_instruments:
                norm_sym = normalize_symbol(r_sym)
                if qt in norm_sym:
                    row = (r_code, r_sym)
                    break
        
        if not row:
            await status_msg.edit_text(f"❌ Symbol <b>{text}</b> not found in database.", parse_mode=ParseMode.HTML)
            return
                
        ins_code, symbol = row
        
        try:
            df = await fetch_api_data(ins_code)
        except Exception as api_exc:
            await status_msg.edit_text(
                f"❌ <b>API Connection Failed</b> for {symbol}.\n\n"
                f"Error: <code>{type(api_exc).__name__}: {api_exc}</code>\n\n"
                f"<i>Note: TSETMC API blocks foreign IPs. Please check if your VPN (ProtonVPN) is active and blocking access to TSETMC.</i>",
                parse_mode=ParseMode.HTML
            )
            return
        
        if df.empty:
            await status_msg.edit_text(f"❌ No historical data returned by API for {symbol}.", parse_mode=ParseMode.HTML)
            return
            
        engine = IndicatorEngine()
        res = engine.calculate(df)
        
        if res.empty:
            await status_msg.edit_text(f"❌ Could not calculate indicators for {symbol}.", parse_mode=ParseMode.HTML)
            return
            
        latest = res.iloc[-1]
        date_str = latest['date'].strftime('%Y-%m-%d') if hasattr(latest['date'], 'strftime') else str(latest['date']).split(' ')[0]
        
        close_price = int(latest['close'])
        last_price = int(latest['last'])
        volume = int(latest['volume'])
        
        # Try to use priceYesterday from live data if available, otherwise fallback to history
        info_data = df.attrs.get('info_data', {})
        price_yesterday = float(info_data.get("priceYesterday") or 0)
        
        yesterday_close = price_yesterday if price_yesterday > 0 else (df.iloc[-2]['close'] if len(df) > 1 else close_price)
        
        close_diff = ((close_price - yesterday_close) / yesterday_close) * 100 if yesterday_close else 0
        last_diff = ((last_price - yesterday_close) / yesterday_close) * 100 if yesterday_close else 0
        
        close_str = f"{close_diff:+.2f}%"
        last_str = f"{last_diff:+.2f}%"
        
        avg_volume_30d = df['volume'].tail(30).mean()
        suspicious_volume = volume > (3 * avg_volume_30d)
        
        rsi = f"{latest['rsi']:.1f}" if pd.notna(latest['rsi']) else "N/A"
        macd_hist = f"{latest['macd_histogram']:.1f}" if pd.notna(latest['macd_histogram']) else "N/A"
        obv = f"{latest['obv']:,.0f}" if pd.notna(latest['obv']) else "N/A"
        stoch_k = f"{latest['stoch_k']:.1f}" if pd.notna(latest['stoch_k']) else "N/A"
        
        vol_alert = " 🚨 <b>(Suspicious Volume!)</b>" if suspicious_volume else ""
        avg_vol_str = f"{int(avg_volume_30d):,}"
        
        msg = (
            f"📊 <b>{symbol}</b> (Date: {date_str})\n\n"
            f"💰 <b>Close:</b> {close_price:,} ({close_str})\n"
            f"🏷️ <b>Last:</b> {last_price:,} ({last_str})\n"
            f"📦 <b>Volume:</b> {volume:,}{vol_alert}\n"
            f"📉 <b>30d Avg Vol:</b> {avg_vol_str}\n\n"
            f"📈 <b>Indicators:</b>\n"
            f"• <b>RSI (14):</b> {rsi}\n"
            f"• <b>MACD Hist:</b> {macd_hist}\n"
            f"• <b>Stoch %K:</b> {stoch_k}\n"
            f"• <b>OBV:</b> {obv}"
        )
        
        keyboard = [[InlineKeyboardButton("📊 Analyze", callback_data=f"analyze_{ins_code}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await status_msg.edit_text(msg, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error processing {text}: {e}", parse_mode=ParseMode.HTML)


@restricted
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    if data.startswith("scan_"):
        await query.answer("در حال اسکن بازار...")
        
        query_sql = ""
        title = ""
        
        if data == "scan_pos_diff":
            title = "📈 اختلاف قیمت مثبت (بیشتر از ۳٪)"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND o.close > 0
            AND (o.last - o.close) / o.close >= 0.03
            AND IFNULL(i.market_board, '') NOT LIKE '%صندوق%'
            AND i.symbol NOT LIKE '%ح'
            ORDER BY ((o.last - o.close) / o.close) DESC
            LIMIT 45
            """
        elif data == "scan_neg_diff":
            title = "📉 اختلاف قیمت منفی (کمتر از -۳٪)"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND o.close > 0
            AND (o.last - o.close) / o.close <= -0.03
            AND IFNULL(i.market_board, '') NOT LIKE '%صندوق%'
            AND i.symbol NOT LIKE '%ح'
            ORDER BY ((o.last - o.close) / o.close) ASC
            LIMIT 45
            """
        elif data == "scan_sus_vol":
            title = "⚠️ حجم معاملات مشکوک"
            query_sql = """
            WITH Ranked AS (
                SELECT i.ins_code, i.symbol, o.volume, o.date,
                       AVG(o.volume) OVER (PARTITION BY i.id ORDER BY o.date ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) as avg_vol
                FROM instruments i
                JOIN ohlcv_daily o ON i.id = o.instrument_id
                WHERE i.active = 1
                AND IFNULL(i.market_board, '') NOT LIKE '%صندوق%'
                AND i.symbol NOT LIKE '%ح'
            )
            SELECT ins_code, symbol FROM Ranked
            WHERE date = (SELECT MAX(date) FROM ohlcv_daily)
            AND volume > 4 * avg_vol
            ORDER BY (volume / avg_vol) DESC
            LIMIT 45
            """
        elif data == "scan_queue":
            title = "🚀 مستعد صف خرید فردا"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND o.close > 0
            AND (o.last - o.close) / o.close >= 0.015
            AND IFNULL(i.market_board, '') NOT LIKE '%صندوق%'
            AND i.symbol NOT LIKE '%ح'
            ORDER BY ((o.last - o.close) / o.close) DESC
            LIMIT 45
            """
        elif data == "scan_rights":
            title = "⚖️ لیست حق تقدم‌ها"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND (i.symbol LIKE '%ح' OR IFNULL(i.market_board, '') LIKE '%حق تقدم%')
            ORDER BY o.volume DESC
            LIMIT 45
            """
        elif data == "scan_etfs":
            title = "💼 صندوق‌های قابل معامله"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND (IFNULL(i.market_board, '') LIKE '%صندوق%' OR IFNULL(i.market, '') LIKE '%صندوق%')
            ORDER BY o.volume DESC
            LIMIT 45
            """
        elif data == "scan_candles":
            title = "🕯️ کندل‌های مستعد رشد (چکش/ماروبوزو)"
            query_sql = """
            SELECT i.ins_code, i.symbol FROM instruments i
            JOIN ohlcv_daily o ON i.id = o.instrument_id
            WHERE o.date = (SELECT MAX(date) FROM ohlcv_daily)
            AND IFNULL(i.market_board, '') NOT LIKE '%صندوق%'
            AND i.symbol NOT LIKE '%ح'
            AND (
                (o.close > o.open AND o.high - o.close < (o.high - o.low) * 0.05 AND o.open - o.low < (o.high - o.low) * 0.05 AND (o.close - o.open) / o.open > 0.03)
                OR
                (MIN(o.open, o.close) - o.low > 2 * ABS(o.close - o.open) AND o.high - MAX(o.open, o.close) < ABS(o.close - o.open) * 0.2)
            )
            ORDER BY o.volume DESC
            LIMIT 45
            """
            
        try:
            with db.connect() as conn:
                df = pd.read_sql_query(query_sql, conn)
            
            if df.empty:
                await query.edit_message_text(f"❌ هیچ نمادی برای فیلتر <b>{title}</b> یافت نشد.", parse_mode=ParseMode.HTML)
                return
                
            keyboard = []
            row = []
            for _, r in df.iterrows():
                row.append(InlineKeyboardButton(r['symbol'], callback_data=f"analyze_{r['ins_code']}"))
                if len(row) == 3:
                    keyboard.append(row)
                    row = []
            if row:
                keyboard.append(row)
                
            reply_markup = InlineKeyboardMarkup(keyboard)
            msg = f"✅ <b>{title}</b>\nتعداد یافت شده: {len(df)}\nبرای تحلیل لایو روی هر نماد کلیک کنید:"
            await query.edit_message_text(msg, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            await query.edit_message_text(f"❌ خطا در اجرای فیلتر: {e}", parse_mode=ParseMode.HTML)
            
    elif data.startswith("analyze_"):
        await query.answer("Running live analysis...")
        ins_code = data.split("_")[1]
        
        try:
            df = await fetch_api_data(ins_code)
            if df.empty:
                await query.edit_message_text("❌ No data for analysis.")
                return
                
            engine = IndicatorEngine()
            df = engine.calculate(df)
            
            div_engine = DivergenceEngine()
            signals_df = div_engine.calculate(df)
            
            latest = df.iloc[-1]
            close = latest['close']
            latest_date = latest['date']
            
            # EMA check
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            ema50 = df.iloc[-1]['ema50']
            ema_status = f"🟢 Price ({int(close):,}) > EMA 50 ({int(ema50):,})" if close > ema50 else f"🔴 Price ({int(close):,}) < EMA 50 ({int(ema50):,})"
            
            # Divergence string
            div_str = "⚪ No bullish divergence detected today."
            if not signals_df.empty:
                today_signals = signals_df[signals_df['signal_date'] == latest_date]
                bullish_signals = today_signals[today_signals['divergence_type'].str.contains('bullish', case=False, na=False)]
                
                if not bullish_signals.empty:
                    divs = []
                    for _, row in bullish_signals.iterrows():
                        ind = row['indicator'].upper()
                        dt = row['divergence_type'].replace('_', ' ').title()
                        divs.append(f"{ind} ({dt})")
                    div_str = "🟢 " + ", ".join(divs)
                
            new_text = query.message.text + (
                f"\n\n🔬 <b>Advanced Analysis (Live):</b>\n"
                f"• <b>Trend (EMA 50):</b> {ema_status}\n"
                f"• <b>Divergence:</b>\n  {div_str}\n"
            )
            
            await query.edit_message_text(text=new_text, parse_mode=ParseMode.HTML)
            
            # Generate and send chart
            symbol = df.iloc[-1].get('symbol', 'Symbol') # Might need to fetch symbol if not in df
            try:
                # Need to find symbol name from DB for the chart title
                with db.connect() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT symbol FROM instruments WHERE ins_code = ?", (ins_code,))
                    s_row = cur.fetchone()
                    real_symbol = s_row['symbol'] if s_row else "Chart"
                
                chart_path = generate_candlestick_chart(df, real_symbol)
                with open(chart_path, 'rb') as f:
                    await query.message.reply_photo(photo=f)
            except Exception as chart_exc:
                print(f"Chart error: {chart_exc}")
                await query.message.reply_text("❌ Failed to generate chart.")
                
        except Exception as e:
            await query.edit_message_text(f"❌ Analysis failed: {e}")


if __name__ == '__main__':
    if not TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in .env")
        exit(1)
        
    print("Starting Telegram Bot...")
    proxy_url = os.getenv("PROXY_URL")
    
    if proxy_url:
        print(f"Using proxy: {proxy_url}")
        app = ApplicationBuilder().token(TOKEN).proxy_url(proxy_url).get_updates_proxy_url(proxy_url).read_timeout(30).write_timeout(30).connect_timeout(30).build()
    else:
        app = ApplicationBuilder().token(TOKEN).read_timeout(30).write_timeout(30).connect_timeout(30).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("scans", filters_menu))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("add", add_symbol_cmd))
    app.add_handler(CommandHandler("remove", remove_symbol_cmd))
    app.add_handler(CommandHandler("update", run_update))
    app.add_handler(CommandHandler("marketmap", marketmap_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot is polling. Press Ctrl+C to stop.")
    app.run_polling()
