#!/bin/bash
# Start all bots for specified users

cd "/Users/filipsliwa/Desktop/ASE BOT/ASE BOT - bot tradingowy/Automatyczny Stock Market 1.0/Algorytm Uczenia Kwantowego LLM"

# Kill existing bots
pkill -9 -f auto_trader 2>/dev/null
sleep 2

# Create logs directory
mkdir -p logs

# Start bots for each user
echo "🚀 Starting bots..."

USER1="4177e228-e38e-4a64-b34a-2005a959fcf2"
USER2="e4f7f9e4-1664-4419-aaa2-592f12dc2f2a"
USER3="b812b608-3bdc-4afe-9dbd-9857e65a3bfe"
USER4="1aa87e38-f100-49d1-85dc-292bc58e25f1"
USER5="43e88b0b-d34f-4795-8efa-5507f40426e8"

nohup python3 -m bot.auto_trader --user-id $USER1 --margin >> logs/bot_4177e228.log 2>&1 &
echo "✅ Bot 4177e228 started (PID: $!)"

nohup python3 -m bot.auto_trader --user-id $USER2 --margin >> logs/bot_e4f7f9e4.log 2>&1 &
echo "✅ Bot e4f7f9e4 started (PID: $!)"

nohup python3 -m bot.auto_trader --user-id $USER3 --margin >> logs/bot_b812b608.log 2>&1 &
echo "✅ Bot b812b608 started (PID: $!)"

nohup python3 -m bot.auto_trader --user-id $USER4 --margin >> logs/bot_1aa87e38.log 2>&1 &
echo "✅ Bot 1aa87e38 started (PID: $!)"

nohup python3 -m bot.auto_trader --user-id $USER5 --margin >> logs/bot_43e88b0b.log 2>&1 &
echo "✅ Bot 43e88b0b started (PID: $!)"

sleep 3

echo ""
echo "📊 Running bots:"
ps aux | grep auto_trader | grep -v grep | wc -l
