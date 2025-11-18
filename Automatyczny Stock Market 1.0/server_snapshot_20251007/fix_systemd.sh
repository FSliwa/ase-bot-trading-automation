#!/bin/bash
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"

echo "🔧 RĘCZNA NAPRAWA SYSTEMD SERVICE"
echo "================================="

ssh -t ${VPS_USER}@${VPS_IP} "
echo 'Ręczne utworzenie pliku systemd service...'

sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'UNIT'
[Unit]
Description=Trading Bot (FastAPI)
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/trading-bot
EnvironmentFile=/opt/trading-bot/.env.db
ExecStart=/opt/trading-bot/.venv/bin/python -m uvicorn fastapi_app:app --host 127.0.0.1 --port 8009 --workers 2
Restart=always
RestartSec=3
TimeoutStopSec=15
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
UNIT

echo 'Przeładowanie systemd i uruchomienie usługi...'
sudo systemctl unmask trading-bot.service || true
sudo systemctl daemon-reload
sudo systemctl enable trading-bot.service
sudo systemctl start trading-bot.service

echo 'Sprawdzenie statusu usługi...'
sleep 3
sudo systemctl status trading-bot.service --no-pager -l

echo ''
echo 'Test endpoint /healthz:'
curl -s http://127.0.0.1:8009/healthz || echo 'Endpoint lokalny niedostępny'

echo ''
echo 'Test endpoint zewnętrzny:'
curl -s http://185.70.196.214/healthz || echo 'Endpoint zewnętrzny niedostępny'
"
