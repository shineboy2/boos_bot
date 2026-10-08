import os
import sys
import asyncio
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.database import DatabaseManager
from app.utils import normalize_symbol
from app.watchlist import WatchlistManager
from app.utils_bot import restricted, get_latest_signals, format_signals_message

db = DatabaseManager()
watchlist = WatchlistManager()

@restricted
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "👋 <b>به ربات تحلیلگر هوشمند بورس خوش آمدید!</b>\n\n"
        "این ربات به شما در پیدا کردن بهترین موقعیت‌های معاملاتی بر اساس واگرایی‌ها و تحلیل‌های تکنیکال کمک می‌کند.\n\n"
        "<b>دستورات اصلی ربات:</b>\n"
        "• /update - منوی دریافت داده و بروزرسانی قیمت‌ها\n"
        "• /today - مشاهده بهترین سیگنال‌های واگرایی امروز\n"
        "• /scans - لیست فیلترهای هوشمند بازار\n"
        "• /scan - اجرای اسکنر کامل بازار (محاسبات سنگین)\n"
        "• /marketmap - رسم نقشه زنده بازار\n\n"
        "<b>مدیریت واچ‌لیست و پورتفو:</b>\n"
        "• /portfolio - مشاهده پوزیشن‌های باز و سود/زیان\n"
        "• /watchlist - مشاهده نمادهای مورد علاقه شما\n"
        "• <code>/add فولاد</code> - اضافه کردن نماد به واچ‌لیست\n"
        "• <code>/remove فولاد</code> - حذف نماد از واچ‌لیست\n\n"
        "🔎 <b>تحلیل لایو:</b>\n"
        "برای دریافت چارت تکنیکال و وضعیت هر نماد، کافیست نام آن را ارسال کنید (مثلاً بفرستید: <b>شپنا</b>)."
    )
    await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)

@restricted
async def filters_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📈 اختلاف قیمت مثبت", callback_data="scan_pos_diff")],
        [InlineKeyboardButton("📉 اختلاف قیمت منفی", callback_data="scan_neg_diff")],
        [InlineKeyboardButton("🌟 سیگنال طلایی (SMC + تابلو)", callback_data="scan_golden")],
        [InlineKeyboardButton("👁️ پرایس‌اکشن نهنگ‌ها (SMC)", callback_data="scan_smc")],
        [InlineKeyboardButton("💰 ورود پول حقیقی سنگین", callback_data="scan_real_money_flow")],
        [InlineKeyboardButton("⚠️ حجم معاملات مشکوک", callback_data="scan_sus_vol")],
        [InlineKeyboardButton("🚀 مستعد صف خرید فردا", callback_data="scan_queue")],
        [InlineKeyboardButton("⚖️ لیست حق تقدم‌ها", callback_data="scan_rights")],
        [InlineKeyboardButton("💼 صندوق‌های قابل معامله", callback_data="scan_etfs")],
        [InlineKeyboardButton("🕯️ کندل‌های مستعد رشد (چکش/ماروبوزو)", callback_data="scan_candles")],
        [InlineKeyboardButton("🏆 صنایع پیشتاز (یک ماهه)", callback_data="scan_top_sectors")],
        [InlineKeyboardButton("📊 جامانده‌های گروه‌های پیشتاز", callback_data="scan_lagging_stocks")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🔎 <b>فیلترهای هوشمند بازار</b>\nیک مورد را انتخاب کنید:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

@restricted
async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Fetching latest signals from database...", parse_mode=ParseMode.HTML)
    latest_date, signals_by_symbol = get_latest_signals()
    message = format_signals_message(latest_date, signals_by_symbol)
    
    # Split message if it exceeds 4096 chars (Telegram limit)
    chunk_size = 4000
    if len(message) <= chunk_size:
        await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    else:
        # Split safely by newline
        parts = []
        current_part = ""
        for line in message.split('\n'):
            if len(current_part) + len(line) + 1 > chunk_size:
                parts.append(current_part)
                current_part = line + '\n'
            else:
                current_part += line + '\n'
        if current_part:
            parts.append(current_part)
            
        for i, part in enumerate(parts):
            if i == 0:
                await update.message.reply_text(part, parse_mode=ParseMode.HTML)
            else:
                await update.message.reply_text(f"(ادامه...)\n\n{part}", parse_mode=ParseMode.HTML)

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

from app.portfolio import PortfolioManager
portfolio = PortfolioManager()

@restricted
async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    trades = portfolio.get_open_trades(user_id)
    
    if not trades:
        await update.message.reply_text("💼 <b>پورتفوی مجازی شما خالی است.</b>\nهیچ پوزیشن بازی ندارید.", parse_mode=ParseMode.HTML)
        return
        
    msg = "💼 <b>پورتفوی مجازی (پوزیشن‌های باز):</b>\n\n"
    total_pnl = 0
    for t in trades:
        emoji = "🟢" if t['pnl_percent'] > 0 else ("🔴" if t['pnl_percent'] < 0 else "⚪")
        msg += (
            f"🔹 <b>{t['symbol']}</b>\n"
            f"   خرید: {int(t['buy_price']):,} | حجم: {t['volume']}\n"
            f"   فعلی: {int(t['current_price']):,} | بازدهی: %{t['pnl_percent']:.2f} {emoji}\n"
            f"   بستن: /close_{t['id']}\n\n"
        )
        total_pnl += t['pnl_percent']
        
    avg_pnl = total_pnl / len(trades)
    overall_emoji = "🟢" if avg_pnl > 0 else "🔴"
    msg += f"📊 <b>میانگین بازدهی کل:</b> %{avg_pnl:.2f} {overall_emoji}"
    
@restricted
async def close_trade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Text could be /close_123
    text = update.message.text
    try:
        trade_id = int(text.split("_")[1])
    except (IndexError, ValueError):
        await update.message.reply_text("❌ فرمت دستور اشتباه است. (مثال: /close_123)")
        return
        
    success, msg = portfolio.close_trade(user_id, trade_id)
    await update.message.reply_text(msg)
