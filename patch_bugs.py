import re

# Fix chart_generator.py
with open("app/chart_generator.py", "r", encoding="utf-8") as f:
    chart_code = f.read()

chart_code = chart_code.replace('fig.write_image(output_path, engine="kaleido", scale=2.0)', 'fig.write_image(output_path, scale=2.0)')

with open("app/chart_generator.py", "w", encoding="utf-8") as f:
    f.write(chart_code)


# Fix telegram_bot.py
with open("telegram_bot.py", "r", encoding="utf-8") as f:
    bot_code = f.read()

# Fix unescaped HTML characters in scan queries
bot_code = bot_code.replace('title = "📉 اختلاف قیمت منفی (< -۳٪)"', 'title = "📉 اختلاف قیمت منفی (کمتر از -۳٪)"')
bot_code = bot_code.replace('title = "📈 اختلاف قیمت مثبت (> ۳٪)"', 'title = "📈 اختلاف قیمت مثبت (بیشتر از ۳٪)"')

# Add -u to python executable in create_subprocess_exec
bot_code = bot_code.replace(
    'process = await asyncio.create_subprocess_exec(\n            sys.executable, str(BASE_DIR / "daily_pipeline.py"),',
    'process = await asyncio.create_subprocess_exec(\n            sys.executable, "-u", str(BASE_DIR / "daily_pipeline.py"),'
)

bot_code = bot_code.replace(
    'process = await asyncio.create_subprocess_exec(\n            sys.executable, str(BASE_DIR / "calculate_signals.py"),',
    'process = await asyncio.create_subprocess_exec(\n            sys.executable, "-u", str(BASE_DIR / "calculate_signals.py"),'
)

with open("telegram_bot.py", "w", encoding="utf-8") as f:
    f.write(bot_code)

print("Patched successfully!")
