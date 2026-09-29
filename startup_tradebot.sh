#!/bin/bash
# Auto-start script for trading telegram bot
LOG_FILE="/home/shahab/api/bot_startup.log"
BOT_DIR="/home/shahab/api"
LOCK_FILE="/tmp/trade_bot_starter.lock"

exec 200>"$LOCK_FILE"
flock -n 200 || exit 0

if pgrep -f "telegram_bot.py" > /dev/null 2>&1; then
    exit 0
fi

echo "=== Trade Bot Startup: $(date) ===" >> "$LOG_FILE"
cd "$BOT_DIR"

export PATH="$BOT_DIR/.venv/bin:$PATH"

nohup python3 telegram_bot.py >> "$LOG_FILE" 2>&1 &
BOT_PID=$!
echo "✅ Bot is running with PID: $BOT_PID" >> "$LOG_FILE"
