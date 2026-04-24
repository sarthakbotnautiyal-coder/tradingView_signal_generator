#!/bin/bash
# Restart script for TradingView listener — called by cron at 9AM EST weekdays

PROJECT_DIR="/Users/ubexbot/.openclaw/workspace-venkat/tradingView_signal_generator"
LOG="${PROJECT_DIR}/listener_restart.log"

echo "$(date '+%Y-%m-%d %H:%M:%S') — restarting listener" >> "$LOG"

# Kill any existing listener process
existing=$(ps aux | grep "[r]un_listener.py" | awk '{print $2}')
if [ -n "$existing" ]; then
    echo "Killing existing listener PID $existing" >> "$LOG"
    kill "$existing" 2>/dev/null
    sleep 2
fi

# Start fresh
cd "$PROJECT_DIR"
/opt/homebrew/bin/python3 run_listener.py >> "$LOG" 2>&1 &
echo "$(date '+%Y-%m-%d %H:%M:%S') — listener started PID $!" >> "$LOG"