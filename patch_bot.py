import re

with open("telegram_bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Add new imports
imports = """
from app.database import DatabaseManager
from app.utils import parse_date, normalize_symbol
from app.watchlist import WatchlistManager
from app.chart_generator import generate_candlestick_chart
"""
code = code.replace(
    "from app.database import DatabaseManager\nfrom app.utils import parse_date, normalize_symbol",
    imports.strip()
)

# 2. Add watchlist manager instance
wm_init = """
db = DatabaseManager()
watchlist = WatchlistManager()
"""
code = code.replace("db = DatabaseManager()", wm_init.strip())

# 3. Add Watchlist Commands
wl_cmds = """
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
    
    msg = "📋 <b>واچ‌لیست شما:</b>\\n\\n"
    for item in items:
        msg += f"• <b>{item['symbol']}</b>\\n"
    msg += "\\nبرای تحلیل، نام نماد را ارسال کنید."
    await update.message.reply_text(msg, parse_mode=ParseMode.HTML)
"""

# Insert before start()
code = code.replace("@restricted\nasync def start", wl_cmds.strip() + "\n\n@restricted\nasync def start")

# 4. Modify handle_callback "analyze_" block to send chart
old_analyze_end = """
            new_text = query.message.text + (
                f"\\n\\n🔬 <b>Advanced Analysis (Live):</b>\\n"
                f"• <b>Trend (EMA 50):</b> {ema_status}\\n"
                f"• <b>Divergence:</b>\\n  {div_str}\\n"
            )
            
            await query.edit_message_text(text=new_text, parse_mode=ParseMode.HTML)
        except Exception as e:
            await query.edit_message_text(f"❌ Analysis failed: {e}")
"""

new_analyze_end = """
            new_text = query.message.text + (
                f"\\n\\n🔬 <b>Advanced Analysis (Live):</b>\\n"
                f"• <b>Trend (EMA 50):</b> {ema_status}\\n"
                f"• <b>Divergence:</b>\\n  {div_str}\\n"
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
"""
code = code.replace(old_analyze_end, new_analyze_end)

# 5. Add handlers to main
handlers_old = """
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("scans", filters_menu))
"""
handlers_new = """
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("scan", scan))
    app.add_handler(CommandHandler("scans", filters_menu))
    app.add_handler(CommandHandler("watchlist", watchlist_cmd))
    app.add_handler(CommandHandler("add", add_symbol_cmd))
    app.add_handler(CommandHandler("remove", remove_symbol_cmd))
"""
code = code.replace(handlers_old, handlers_new)

with open("telegram_bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("telegram_bot.py updated!")
