from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(BASE_DIR))

from app.services.data_fetcher import DataFetcherService
from app.data.provider import DataProvider

async def update_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show data update options as inline buttons."""
    keyboard = [
        [InlineKeyboardButton("📥 آپدیت قیمت امروز", callback_data="fetch:today")],
        [InlineKeyboardButton("📊 فچ تاریخچه کامل", callback_data="fetch:history")],
        [InlineKeyboardButton("🔄 آپدیت لیست نمادها", callback_data="fetch:instruments")],
        [InlineKeyboardButton("👥 آپدیت حقیقی/حقوقی", callback_data="fetch:clienttype")],
        [InlineKeyboardButton("🔗 وضعیت اتصال", callback_data="fetch:status")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📡 <b>مدیریت داده‌ها</b>\n\nیکی از گزینه‌ها را انتخاب کنید:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def handle_fetch_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data.split(":")[1]
    
    if action == "status":
        provider = DataProvider()
        status = await provider.check_connectivity()
        cdn_icon = "✅" if status["cdn"] else "❌"
        webgw_icon = "✅" if status["webgw"] else "❌"
        
        warn = "⚠️ VPN شما فعال است! برای فچ داده VPN را خاموش کنید." if not status["cdn"] else "✅ آماده دریافت داده"
        
        await query.edit_message_text(
            f"🔗 <b>وضعیت اتصال</b>\n\n"
            f"{cdn_icon} CDN (cdn.tsetmc.com)\n"
            f"{webgw_icon} WebGW (webgw.tse.ir)\n"
            f"📅 آخرین آپدیت DB: {status['db_last_update']}\n\n{warn}",
            parse_mode=ParseMode.HTML
        )
        return
        
    fetcher = DataFetcherService()
    
    if action == "today":
        await query.edit_message_text("⏳ در حال آپدیت قیمت‌های امروز...")
        count = await fetcher.update_today_prices()
        await query.edit_message_text(f"✅ آپدیت انجام شد!\n📊 {count} نماد بروزرسانی شد")
        
    elif action == "history":
        await query.edit_message_text("⏳ در حال فچ تاریخچه... (ممکن است چند دقیقه طول بکشد)")
        
        async def progress(done, total):
            try:
                await query.edit_message_text(f"⏳ فچ تاریخچه: {done}/{total} نماد")
            except:
                pass # Ignore 'Message is not modified' error
                
        total, done = await fetcher.fetch_all_history(progress_callback=progress)
        await query.edit_message_text(f"✅ تاریخچه {done}/{total} نماد فچ شد")
        
    elif action == "instruments":
        await query.edit_message_text("⏳ در حال آپدیت لیست نمادها...")
        count = await fetcher.update_instruments()
        await query.edit_message_text(f"✅ {count} نماد آپدیت شد")
        
    elif action == "clienttype":
        await query.edit_message_text("⏳ در حال آپدیت اطلاعات حقیقی/حقوقی...")
        count = await fetcher.update_client_types()
        await query.edit_message_text(f"✅ حقیقی/حقوقی {count} نماد آپدیت شد")
