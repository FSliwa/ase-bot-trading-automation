#!/bin/bash
cd "/Users/filipsliwa/Desktop/ASE BOT/ASE BOT - bot tradingowy/Automatyczny Stock Market 1.0/Algorytm Uczenia Kwantowego LLM"

echo "🛑 Zatrzymuję istniejące procesy..."
pkill -f "run_single_user.py" 2>/dev/null
pkill -f "monitor_group.py" 2>/dev/null
sleep 2

echo "🚀 Uruchamiam 6 botów..."
/usr/bin/python3 run_single_user.py 2dc2d6d0-1aba-4689-8217-0206d7ebee62 >> logs/bot_2dc2d6d0.log 2>&1 &
/usr/bin/python3 run_single_user.py 43e88b0b-d34f-4795-8efa-5507f40426e8 >> logs/bot_43e88b0b.log 2>&1 &
/usr/bin/python3 run_single_user.py e4f7f9e4-1664-4419-aaa2-592f12dc2f2a >> logs/bot_e4f7f9e4.log 2>&1 &
/usr/bin/python3 run_single_user.py 4177e228-e38e-4a64-b34a-2005a959fcf2 >> logs/bot_4177e228.log 2>&1 &
/usr/bin/python3 run_single_user.py b812b608-3bdc-4afe-9dbd-9857e65a3bfe >> logs/bot_b812b608.log 2>&1 &
/usr/bin/python3 run_single_user.py 1aa87e38-f100-49d1-85dc-292bc58e25f1 >> logs/bot_1aa87e38.log 2>&1 &

echo "📊 Uruchamiam monitor..."
/usr/bin/python3 monitor_group.py >> logs/monitor_group.log 2>&1 &

sleep 3
echo "✅ Wszystkie boty uruchomione!"
echo ""
echo "📋 Procesy:"
ps aux | grep -E "run_single_user|monitor_group" | grep -v grep
echo ""
echo "📺 Logi LIVE (Ctrl+C aby wyjść):"
tail -f logs/bot_*.log
