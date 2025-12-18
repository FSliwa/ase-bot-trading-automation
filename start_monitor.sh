#!/bin/bash
# Start monitor_group.py with live output
cd "/Users/filipsliwa/Desktop/ASE BOT/ASE BOT - bot tradingowy/Automatyczny Stock Market 1.0/Algorytm Uczenia Kwantowego LLM"

echo "🛑 Zatrzymuję stary monitor..."
pkill -f "monitor_group.py" 2>/dev/null
sleep 1

echo "🚀 Uruchamiam monitor_group.py..."
echo "📺 Logi LIVE (Ctrl+C aby wyjść):"
echo ""

/usr/bin/python3 monitor_group.py
