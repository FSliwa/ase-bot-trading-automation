#!/bin/bash
# Skrypt aktualizacji z hasłem
echo '🔧 Aktualizacja z sudo...'
echo 'admin' | sudo -S systemctl stop trading-bot
echo 'admin' | sudo -S cp /tmp/app.py /opt/trading-bot/web/
echo 'admin' | sudo -S cp /tmp/gemini_analysis.py /opt/trading-bot/bot/
echo 'admin' | sudo -S cp /tmp/requirements.txt /opt/trading-bot/
echo 'admin' | sudo -S cp /tmp/fastapi_app.py /opt/trading-bot/
echo 'admin' | sudo -S chown -R www-data:www-data /opt/trading-bot/
echo 'admin' | sudo -S chmod +x /opt/trading-bot/*.py
echo 'admin' | sudo -S systemctl start trading-bot
echo '✅ Aktualizacja zakończona'
