#!/bin/bash
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"

echo "🔍 SZCZEGÓŁOWA DIAGNOZA APLIKACJI"
echo "=================================="

ssh -t ${VPS_USER}@${VPS_IP} "
echo 'Status usługi:'
sudo systemctl status trading-bot.service --no-pager

echo ''
echo 'Procesy na porcie 8009:'
sudo ss -ltnp | grep ':8009' || echo 'Brak procesów na porcie 8009'

echo ''
echo 'Wszystkie procesy uvicorn:'
ps aux | grep uvicorn | grep -v grep || echo 'Brak procesów uvicorn'

echo ''
echo 'Test podstawowy HTTP na 127.0.0.1:8009:'
curl -v http://127.0.0.1:8009/ || echo 'Brak odpowiedzi na /'

echo ''
echo 'Test curl z większym timeout:'
curl --connect-timeout 10 -m 10 http://127.0.0.1:8009/healthz || echo 'Brak odpowiedzi na /healthz'

echo ''
echo 'Ostatnie logi aplikacji:'
sudo journalctl -u trading-bot.service -n 20 --no-pager

echo ''
echo 'Test dostępności portu 8009 przez telnet:'
timeout 5s telnet 127.0.0.1 8009 || echo 'Port 8009 nie odpowiada'
"
