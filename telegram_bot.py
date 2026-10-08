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
from app.utils import normalize_symbol
from app.watchlist import WatchlistManager
from app.chart_generator import generate_candlestick_chart
from app.handlers.fetch_handlers import update_menu, handle_fetch_callback
from app.handlers.commands import start, today, scan, filters_menu, watchlist_cmd, add_symbol_cmd, remove_symbol_cmd, marketmap_cmd, portfolio_cmd, close_trade_cmd, top_cmd
from app.data.provider import DataProvider
from app.services.scanner import ScannerService
from app.services.analysis import AnalysisService

# Load environment variables
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

from app.utils_bot import restricted, get_latest_signals, format_signals_message

db = DatabaseManager()
watchlist = WatchlistManager()

async def fetch_api_data(ins_code):
    provider = DataProvider()
    # Min rows required for indicators is around 50
    df = await provider.get_ohlcv(ins_code, min_rows=50)
    return df


@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("/"):
        return
        
    status_msg = await update.message.reply_text(f"Searching for <b>{text}</b> (fetching from API)...", parse_mode=ParseMode.HTML)
    
    try:
        with db.connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT ins_code, symbol, sector_name FROM instruments")
            all_instruments = cur.fetchall()
        
        qt = normalize_symbol(text)
        
        row = None
        for r_code, r_sym, r_sec in all_instruments:
            norm_sym = r_sym.replace('ك', 'ک').replace('ي', 'ی')
            if norm_sym == qt:
                row = (r_code, r_sym, r_sec)
                break
                
        if not row:
            for r_code, r_sym, r_sec in all_instruments:
                norm_sym = normalize_symbol(r_sym)
                if qt in norm_sym:
                    row = (r_code, r_sym, r_sec)
                    break
        
        if not row:
            # Maybe it's a sector name?
            sectors = list(set([r[2] for r in all_instruments if r[2] and r[2] != "ناشناخته"]))
            matched_sec = None
            for sec in sectors:
                if qt in normalize_symbol(sec) or normalize_symbol(sec) in qt:
                    matched_sec = sec
                    break
            
            if matched_sec:
                from app.services.sector_analysis import SectorAnalysisService
                svc = SectorAnalysisService()
                market_df = svc.get_market_returns()
                if market_df.empty:
                    await status_msg.edit_text("❌ No return data available.")
                    return
                sec_stocks = market_df[market_df['sector_name'] == matched_sec].sort_values('1m_ret', ascending=False).head(90)
                
                keyboard = []
                row_btns = []
                for _, r in sec_stocks.iterrows():
                    sym_text = f"{r['symbol']} | {r['1m_ret']*100:+.1f}%"
                    row_btns.append(InlineKeyboardButton(sym_text, callback_data=f"analyze_{r['ins_code']}"))
                    if len(row_btns) == 3:
                        keyboard.append(row_btns)
                        row_btns = []
                if row_btns:
                    keyboard.append(row_btns)
                    
                reply_markup = InlineKeyboardMarkup(keyboard)
                await status_msg.edit_text(f"🏢 <b>گروه: {matched_sec}</b>\nلیست نمادها به ترتیب بازدهی یک‌ماهه:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)
                return

            await status_msg.edit_text(f"❌ Symbol or Sector <b>{text}</b> not found in database.", parse_mode=ParseMode.HTML)
            return
                
        ins_code, symbol, r_sec = row
        
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
        
        if price_yesterday > 0:
            yesterday_close = price_yesterday
        elif len(df) > 1:
            from datetime import timezone, timedelta
            tehran_tz = timezone(timedelta(hours=3, minutes=30))
            today_str = datetime.now(tehran_tz).strftime('%Y-%m-%d')
            last_date = str(df.iloc[-1]['date']).split(' ')[0]
            if last_date == today_str:
                yesterday_close = float(df.iloc[-2]['close'])
            else:
                yesterday_close = float(df.iloc[-1]['close'])
        else:
            yesterday_close = close_price
        
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
        
        sector_str = ""
        if r_sec and r_sec != "ناشناخته":
            try:
                from app.services.sector_analysis import SectorAnalysisService
                svc = SectorAnalysisService()
                comp = svc.get_stock_comparison(ins_code)
                if comp and comp.get('sector'):
                    st = comp['stock']
                    sc = comp['sector']
                    s_ret = st['1m_ret'] * 100
                    c_ret = sc['1m_ret'] * 100
                    diff = s_ret - c_ret
                    status = "🟢 بهتر از گروه" if diff > 0 else "🔴 ضعیف‌تر از گروه"
                    sector_str = (
                        f"\nــــــــــــــــــــــــــــــــــــــــ\n"
                        f"🏢 <b>گروه:</b> {r_sec}\n"
                        f"📈 <b>بازدهی یک‌ماهه سهم:</b> %{s_ret:+.1f}\n"
                        f"📊 <b>بازدهی یک‌ماهه گروه:</b> %{c_ret:+.1f}\n"
                        f"✅ <b>وضعیت (نسبت به گروه):</b> %{diff:+.1f} ({status})"
                    )
            except Exception as e:
                print(f"Sector error: {e}")
                pass

        msg = (
            f"🏢 <b>نماد:</b> {symbol}\n"
            f"📅 <b>تاریخ:</b> {date_str}\n"
            f"ــــــــــــــــــــــــــــــــــــــــ\n"
            f"💰 <b>قیمت پایانی:</b> {close_price:,} ريال ({close_str})\n"
            f"🏷️ <b>آخرین معامله:</b> {last_price:,} ريال ({last_str})\n"
            f"📦 <b>حجم معاملات:</b> {volume:,}{vol_alert}\n"
            f"📉 <b>میانگین حجم ماهانه:</b> {avg_vol_str}\n"
            f"ــــــــــــــــــــــــــــــــــــــــ\n"
            f"📈 <b>وضعیت اندیکاتورها:</b>\n"
            f"🔸 <b>RSI (14):</b> {rsi}\n"
            f"🔸 <b>MACD Hist:</b> {macd_hist}\n"
            f"🔸 <b>Stoch %K:</b> {stoch_k}\n"
            f"🔸 <b>OBV:</b> {obv}"
            f"{sector_str}"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Analyze", callback_data=f"analyze_{ins_code}")],
            [InlineKeyboardButton("🛒 خرید مجازی (Paper Trade)", callback_data=f"buy_{ins_code}")]
        ]
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
        
        scanner = ScannerService()
        result = {}
        
        if data == "scan_pos_diff":
            result = scanner.scan_positive_diff()
        elif data == "scan_neg_diff":
            result = scanner.scan_negative_diff()
        elif data == "scan_golden":
            result = scanner.scan_golden()
        elif data == "scan_smc":
            result = scanner.scan_smc()
        elif data == "scan_sus_vol":
            result = scanner.scan_suspicious_volume()
        elif data == "scan_queue":
            result = scanner.scan_queue()
        elif data == "scan_rights":
            result = scanner.scan_rights()
        elif data == "scan_etfs":
            result = scanner.scan_etfs()
        elif data == "scan_candles":
            result = scanner.scan_candles()
        elif data == "scan_real_money_flow":
            result = scanner.scan_real_money_flow()
        elif data == "scan_top_sectors":
            result = scanner.scan_top_sectors()
        elif data == "scan_lagging_stocks":
            result = scanner.scan_lagging_stocks()
            
        if not result.get("success"):
            await query.edit_message_text(f"❌ خطا در اجرای فیلتر: {result.get('error')}", parse_mode=ParseMode.HTML)
            return
            
        df = result.get("data")
        title = result.get("title")
            
        if df is None or df.empty:
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
    elif data.startswith("buy_"):
        await query.answer("ثبت خرید مجازی...")
        ins_code = data.split("_")[1]
        user_id = update.effective_user.id
        from app.portfolio import PortfolioManager
        portfolio = PortfolioManager()
        # Default buy 10,000 shares
        success, msg = portfolio.buy_virtual(user_id, ins_code, volume=10000)
        await query.message.reply_text(msg)
            
    elif data.startswith("analyze_"):
        await query.answer("Running live analysis...")
        ins_code = data.split("_")[1]
        
        try:
            df = await fetch_api_data(ins_code)
            if df.empty:
                await query.edit_message_text("❌ No data for analysis.")
                return
                
            analyzer = AnalysisService()
            df = analyzer.analyze_dataframe(df)
            signals_df = analyzer.get_latest_divergence(df)
            
            latest = df.iloc[-1]
            close = latest['close']
            latest_date = latest['date']
            
            # EMA check
            df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
            ema50 = df.iloc[-1]['ema50']
            ema_status = f"🟢 قیمت ({int(close):,}) بالاتر از میانگین ۵۰ روزه ({int(ema50):,})" if close > ema50 else f"🔴 قیمت ({int(close):,}) پایین‌تر از میانگین ۵۰ روزه ({int(ema50):,})"
            
            # Divergence string
            div_str = "⚪ واگرایی صعودی یافت نشد."
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
                
            smc_data = analyzer.get_latest_smc(df)
            smc_str = ""
            if smc_data:
                if smc_data.get('has_bullish_fvg'):
                    smc_str += "🟢 گپ صعودی (FVG)  "
                if smc_data.get('has_bearish_fvg'):
                    smc_str += "🔴 گپ نزولی (FVG)  "
                if smc_data.get('has_bullish_ob'):
                    smc_str += "🟩 اوردر بلاک صعودی (OB)  "
                if smc_data.get('has_bearish_ob'):
                    smc_str += "🟥 اوردر بلاک نزولی (OB)  "
            
            if not smc_str:
                smc_str = "⚪ الگوی اسمارت مانی یافت نشد."
                
            new_text = query.message.text + (
                f"\nــــــــــــــــــــــــــــــــــــــــ\n"
                f"🔬 <b>تحلیل پیشرفته (لایو):</b>\n\n"
                f"📌 <b>روند (EMA 50):</b>\n  {ema_status}\n\n"
                f"🎯 <b>واگرایی‌ها:</b>\n  {div_str}\n\n"
                f"🐋 <b>اسمارت مانی (SMC):</b>\n  {smc_str}\n"
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
    app.add_handler(CommandHandler("top", top_cmd))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("portfolio", portfolio_cmd))
    app.add_handler(CommandHandler("add", add_symbol_cmd))
    app.add_handler(CommandHandler("remove", remove_symbol_cmd))
    app.add_handler(CommandHandler("update", update_menu))
    app.add_handler(CommandHandler("marketmap", marketmap_cmd))
    app.add_handler(MessageHandler(filters.Regex(r'^/close_\d+$'), close_trade_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_fetch_callback, pattern="^fetch:"))
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Bot is polling. Press Ctrl+C to stop.")
    app.run_polling()
