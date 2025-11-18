#!/bin/bash
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"

echo "🚀 DEPLOYMENT POPRAWIONEGO KODU"
echo "================================"

ssh -t ${VPS_USER}@${VPS_IP} "
echo 'Uruchamianie skryptu deployment...'
chmod +x /tmp/run_on_server.sh && /tmp/run_on_server.sh

echo ''
echo '🧪 Test działania aplikacji...'
sleep 5

echo 'Status usługi:'
sudo systemctl status trading-bot.service --no-pager -l

echo ''
echo 'Test endpoint /healthz:'
curl -s http://127.0.0.1:8009/healthz || echo 'Endpoint niedostępny'

echo ''
echo 'Test endpoint zewnętrzny:'
curl -s http://185.70.196.214/healthz || echo 'Endpoint zewnętrzny niedostępny'
"
