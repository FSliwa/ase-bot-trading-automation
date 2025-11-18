#!/bin/bash

# Skrypt do naprawy i konfiguracji OpenAI na serwerze
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"
OPENAI_API_KEY="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"

echo "🔧 Konfiguracja OpenAI na serwerze..."

ssh -t $VPS_USER@$VPS_IP "
set -e

echo '--- Aktualizacja pliku .env.db ---'
DB_PASSWORD=\$(sudo grep DB_PASSWORD /opt/trading-bot/.env.db 2>/dev/null | cut -d= -f2 || echo \"default_password\")

sudo bash -c 'cat > /opt/trading-bot/.env.db << EOF
# OpenAI Configuration
OPENAI_API_KEY=$OPENAI_API_KEY
ALLOW_PUBLIC_GPT_ENDPOINTS=true

# PostgreSQL Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_bot_user
DB_PASSWORD=\$DB_PASSWORD
USE_POSTGRESQL=true

# JWT Configuration
JWT_SECRET=\$(openssl rand -hex 32)
JWT_ISSUER=trading-bot
JWT_EXPIRE_MIN=120

# OAuth Configuration (dodaj swoje klucze tutaj)
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
EOF'

echo '--- Ustawianie uprawnień dla .env.db ---'
sudo chown root:root /opt/trading-bot/.env.db
sudo chmod 600 /opt/trading-bot/.env.db

echo '--- Instalowanie zależności Pythona ---'
sudo python3 -m pip install --break-system-packages -q openai duckduckgo_search

echo '--- Restartowanie usługi ---'
sudo systemctl restart trading-bot

echo '--- Oczekiwanie na uruchomienie usługi ---'
sleep 5

echo '--- Testowanie endpointów AI ---'
echo \"Testing GPT-5 analyze...\"
curl -X POST http://localhost:8009/api/gpt5-analyze \\
  -H \"Content-Type: application/json\" \\
  -d '{\"prompt\":\"Analyze Bitcoin market trend\"}' \\
  -s | python3 -m json.tool | head -15

echo \"\"
echo \"Testing Web Search analysis...\"
curl -X POST http://localhost:8009/api/web-search-analysis \\
  -H \"Content-Type: application/json\" \\
  -d '{\"query\":\"Bitcoin price prediction 2025\",\"symbol\":\"BTC\"}' \\
  -s | python3 -m json.tool | head -15

echo \"\"
echo \"✅ Konfiguracja zakończona!\"
"

echo "✅ Konfiguracja OpenAI została zaktualizowana na serwerze!"
echo "🌐 Przetestuj: curl -X POST http://$VPS_IP/api/gpt5-analyze -H \"Content-Type: application/json\" -d '{\"prompt\":\"test\"}'"
