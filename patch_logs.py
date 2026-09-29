import re

with open("telegram_bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Fix start function
old_start = """    welcome_text = (
        "👋 <b>به ربات تحلیلگر هوشمند بورس خوش آمدید!</b>\\\\n\\\\n"
        "این ربات به شما در پیدا کردن بهترین موقعیت‌های معاملاتی بر اساس واگرایی‌ها و تحلیل‌های تکنیکال کمک می‌کند.\\\\n\\\\n"
        "<b>دستورات اصلی ربات:</b>\\\\n"
        "• /update - فچ کردن دیتای امروز، آپدیت دیتابیس و استخراج سیگنال‌ها\\\\n"
        "• /today - مشاهده بهترین سیگنال‌های واگرایی امروز\\\\n"
        "• /scans - لیست فیلترهای هوشمند بازار\\\\n"
        "• /scan - اجرای اسکنر کامل بازار (زمان‌بر)\\\\n\\\\n"
        "<b>مدیریت واچ‌لیست:</b>\\\\n"
        "• /watchlist - مشاهده نمادهای مورد علاقه شما\\\\n"
        "• <code>/add فولاد</code> - اضافه کردن نماد به واچ‌لیست\\\\n"
        "• <code>/remove فولاد</code> - حذف نماد از واچ‌لیست\\\\n\\\\n"
        "🔎 <b>تحلیل لایو:</b>\\\\n"
        "برای دریافت چارت تکنیکال و وضعیت هر نماد، کافیست نام آن را ارسال کنید (مثلاً بفرستید: <b>شپنا</b>)."
    )"""

new_start = """    welcome_text = (
        "👋 <b>به ربات تحلیلگر هوشمند بورس خوش آمدید!</b>\\n\\n"
        "این ربات به شما در پیدا کردن بهترین موقعیت‌های معاملاتی بر اساس واگرایی‌ها و تحلیل‌های تکنیکال کمک می‌کند.\\n\\n"
        "<b>دستورات اصلی ربات:</b>\\n"
        "• /update - فچ کردن دیتای امروز، آپدیت دیتابیس و استخراج سیگنال‌ها\\n"
        "• /today - مشاهده بهترین سیگنال‌های واگرایی امروز\\n"
        "• /scans - لیست فیلترهای هوشمند بازار\\n"
        "• /scan - اجرای اسکنر کامل بازار (زمان‌بر)\\n\\n"
        "<b>مدیریت واچ‌لیست:</b>\\n"
        "• /watchlist - مشاهده نمادهای مورد علاقه شما\\n"
        "• <code>/add فولاد</code> - اضافه کردن نماد به واچ‌لیست\\n"
        "• <code>/remove فولاد</code> - حذف نماد از واچ‌لیست\\n\\n"
        "🔎 <b>تحلیل لایو:</b>\\n"
        "برای دریافت چارت تکنیکال و وضعیت هر نماد، کافیست نام آن را ارسال کنید (مثلاً بفرستید: <b>شپنا</b>)."
    )"""
code = code.replace(old_start, new_start)


# 2. Add log reading helper and update /update command
run_update_old = """@restricted
async def run_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔄 در حال اجرای آپدیت روزانه و استخراج سیگنال‌ها (اجرای daily_pipeline). این عملیات ممکن است چند دقیقه طول بکشد...", parse_mode=ParseMode.HTML)
    
    import asyncio
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "daily_pipeline.py"),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            await update.message.reply_text("✅ آپدیت دیتابیس و محاسبه سیگنال‌ها با موفقیت انجام شد.\\\\nسیگنال‌ها به زودی ارسال می‌شوند.", parse_mode=ParseMode.HTML)
        else:
            error_msg = stderr.decode('utf-8')[:500] if stderr else "Unknown Error"
            await update.message.reply_text(f"❌ خطا در آپدیت:\\\\n<pre>{error_msg}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"❌ خطای سیستمی هنگام اجرای آپدیت: {e}")"""

run_update_new = """import time
@restricted
async def run_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🔄 در حال اجرای آپدیت روزانه و استخراج سیگنال‌ها...\\n(گزارش لحظه‌ای در زیر نمایش داده می‌شود)\\n\\n<pre>شروع...</pre>", parse_mode=ParseMode.HTML)
    
    import asyncio
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "daily_pipeline.py"),
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
                log_text = "\\n".join(logs)
                try:
                    await status_msg.edit_text(f"🔄 <b>در حال اجرای آپدیت...</b>\\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
                last_edit_time = current_time
                
        await process.wait()
        
        if process.returncode == 0:
            await status_msg.edit_text("✅ آپدیت با موفقیت به پایان رسید.\\nسیگنال‌ها استخراج و در صورت وجود ارسال شدند.", parse_mode=ParseMode.HTML)
        else:
            log_text = "\\n".join(logs)
            await status_msg.edit_text(f"❌ خطا در آپدیت:\\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
    except Exception as e:
        await status_msg.edit_text(f"❌ خطای سیستمی هنگام اجرای آپدیت: {e}")"""
code = code.replace(run_update_old, run_update_new)

# 3. Update /scan command
scan_old = """@restricted
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚀 <b>Starting full market divergence scan...</b>\\nThis will take about 5 minutes.\\nI will notify you when it's done.", parse_mode=ParseMode.HTML)
    
    import asyncio
    try:
        process = await asyncio.create_subprocess_exec(
            BASE_DIR / ".venv" / "bin" / "python", 
            BASE_DIR / "calculate_signals.py",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        await process.communicate()
        
        if process.returncode == 0:
            await update.message.reply_text("✅ <b>Full market scan completed successfully!</b>\\nSend /today to view the new signals.", parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text("❌ An error occurred during the scan. Please check server logs.", parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to run scanner: {e}", parse_mode=ParseMode.HTML)"""

scan_new = """@restricted
async def scan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = await update.message.reply_text("🚀 <b>شروع اسکن کامل بازار...</b>\\nاین فرآیند چند دقیقه زمان می‌برد.\\n\\n<pre>شروع...</pre>", parse_mode=ParseMode.HTML)
    
    import asyncio
    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable, str(BASE_DIR / "calculate_signals.py"),
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
                log_text = "\\n".join(logs)
                try:
                    await status_msg.edit_text(f"🚀 <b>اسکن در حال اجرا...</b>\\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
                except Exception:
                    pass
                last_edit_time = current_time
                
        await process.wait()
        
        if process.returncode == 0:
            await status_msg.edit_text("✅ <b>اسکن کامل بازار با موفقیت انجام شد!</b>\\nبرای مشاهده سیگنال‌های امروز دستور /today را ارسال کنید.", parse_mode=ParseMode.HTML)
        else:
            log_text = "\\n".join(logs)
            await status_msg.edit_text(f"❌ خطا در اسکن:\\n<pre>{log_text}</pre>", parse_mode=ParseMode.HTML)
            
    except Exception as e:
        await status_msg.edit_text(f"❌ خطای سیستمی: {e}")"""
code = code.replace(scan_old, scan_new)


with open("telegram_bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("telegram_bot.py updated!")
