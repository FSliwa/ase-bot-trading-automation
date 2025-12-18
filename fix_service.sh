#!/bin/bash
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"

echo "🔧 NAPRAWA USŁUGI SYSTEMD"
echo "=========================="

# Naprawa usługi systemd
ssh -t ${VPS_USER}@${VPS_IP} "
echo 'Naprawa usługi trading-bot.service...'
sudo systemctl unmask trading-bot.service
sudo systemctl daemon-reload
sudo systemctl stop trading-bot.service || true

echo 'Sprawdzanie statusu usługi...'
sudo systemctl status trading-bot.service --no-pager || true

echo 'Sprawdzanie plików aplikacji...'
cd /opt/trading-bot
ls -la

echo 'Test importu...'
sudo -u www-data .venv/bin/python -c \"
import sys
sys.path.insert(0, '/opt/trading-bot')
try:
    import fastapi_app
    print('✅ Import OK')
except Exception as e:
    print(f'❌ Import error: {e}')
    import traceback
    traceback.print_exc()
\"

echo 'Ponowne uruchomienie usługi...'
sudo systemctl enable trading-bot.service
sudo systemctl start trading-bot.service
sleep 3
sudo systemctl status trading-bot.service --no-pager

echo 'Test endpointu...'
curl -s http://127.0.0.1:8009/healthz || echo 'Endpoint niedostępny'
"
