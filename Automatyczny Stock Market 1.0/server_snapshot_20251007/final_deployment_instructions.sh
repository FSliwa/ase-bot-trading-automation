#!/bin/bash

# 🔐 FINAL DEPLOYMENT - Interactive Session
# Finalne wdrożenie przez interaktywną sesję

VPS_IP="185.70.196.214"
USER="admin"

echo "🚀 FINALNE WDROŻENIE - Trading Bot v2"
echo "═══════════════════════════════════════"
echo ""
echo "✅ Status aktualizacji:"
echo "✅ Pliki przesłane na serwer"
echo "✅ Archiwum rozpakowane w katalogu domowym"
echo "⏳ Wymagane: uruchomienie komend z sudo"
echo ""

echo "📋 INSTRUKCJE FINALNE:"
echo "═══════════════════════════════════════"
echo ""
echo "1. 🔐 Zaloguj się na serwer manualnie:"
echo "   ssh admin@185.70.196.214"
echo ""
echo "2. 🚀 Skopiuj i wklej te komendy jedna po drugiej:"
echo ""

# Create single mega command
echo "# MEGA KOMENDA - Skopiuj całość i wklej:"
cat << 'MEGA_COMMAND'
sudo cp -r /opt/trading-bot /opt/trading-bot-backup-$(date +%Y%m%d) 2>/dev/null || true && \
sudo mkdir -p /opt/trading-bot && \
sudo cp ~/enhanced_server_gpt5.py ~/user_database.py ~/index.html ~/login.html ~/register.html ~/nginx_8009.conf ~/requirements.txt ~/simple_openai_client.py ~/web_search_tool.py ~/users.json /opt/trading-bot/ && \
sudo chown -R www-data:www-data /opt/trading-bot && \
sudo chmod +x /opt/trading-bot/enhanced_server_gpt5.py && \
sudo python3 -m pip install --upgrade pip && \
sudo python3 -m pip install -r /opt/trading-bot/requirements.txt && \
sudo cp /opt/trading-bot/nginx_8009.conf /etc/nginx/sites-available/trading-bot && \
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/ && \
sudo nginx -t && sudo systemctl reload nginx && \
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'EOF'
[Unit]
Description=Trading Bot Server with Registration
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trading-bot
ExecStart=/usr/bin/python3 enhanced_server_gpt5.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
MEGA_COMMAND

echo ""
echo "# Następnie uruchom serwis:"
echo "sudo systemctl daemon-reload && sudo systemctl enable trading-bot && sudo systemctl stop trading-bot 2>/dev/null || true && sudo systemctl start trading-bot"

echo ""
echo "# Inicjalizuj bazę danych:"
echo "cd /opt/trading-bot && sudo -u www-data python3 user_database.py"

echo ""
echo "# Sprawdź status:"
echo "sudo systemctl status trading-bot"

echo ""
echo "# Test lokalny:"
echo "curl http://localhost:8009/login"

echo ""
echo "3. 🧪 Przetestuj aplikację:"
echo "   Otwórz: http://185.70.196.214/login"
echo ""

# Try to check current server status
echo "📊 Aktualny status serwera:"
SERVER_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://$VPS_IP/login 2>/dev/null || echo "000")
if [ "$SERVER_CHECK" = "200" ]; then
    echo "✅ Serwer już działa! http://$VPS_IP/login"
elif [ "$SERVER_CHECK" = "502" ]; then
    echo "⚠️  Serwer proxy działa, backend wymaga uruchomienia (502)"
elif [ "$SERVER_CHECK" = "000" ]; then
    echo "❌ Brak połączenia z serwerem"
else
    echo "⚠️  Status: $SERVER_CHECK - wymaga konfiguracji"
fi

echo ""
echo "📁 Wszystkie pliki są gotowe w katalogu domowym admin na serwerze"
echo "🔧 Potrzebne tylko uruchomienie powyższych komend z sudo"
echo ""
echo "🎯 CEL: http://185.70.196.214/login z systemem rejestracji"
