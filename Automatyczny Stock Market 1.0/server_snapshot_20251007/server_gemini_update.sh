#!/bin/bash

# 🚀 MANUAL GEMINI UPDATE SCRIPT
# Ten skrypt należy uruchomić bezpośrednio na serwerze jako admin

set -e

echo "🔄 Rozpoczynanie aktualizacji Gemini na serwerze..."

# Zatrzymaj usługę
echo "🛑 Zatrzymywanie usługi trading-bot..."
sudo systemctl stop trading-bot

# Rozpakuj nowe pliki
echo "📂 Rozpakowywanie archiwum..."
cd /opt/trading-bot
sudo tar -xzf /tmp/gemini_update.tar.gz

# Zaktualizuj zmienne środowiskowe
echo "🔧 Aktualizowanie zmiennych środowiskowych..."
ENV_FILE="/opt/trading-bot/.env.db"

# Dodaj klucz Gemini
if sudo grep -q "GEMINI_API_KEY" "$ENV_FILE"; then
    sudo sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=YOUR_NEW_SECURE_GEMINI_API_KEY_HERE|" "$ENV_FILE"
else
    echo "GEMINI_API_KEY=YOUR_NEW_SECURE_GEMINI_API_KEY_HERE" | sudo tee -a "$ENV_FILE"
fi

# Usuń stary klucz OpenAI
sudo sed -i "/^OPENAI_API_KEY=.*/d" "$ENV_FILE"

echo "📦 Instalowanie zależności..."
sudo /opt/trading-bot/.venv/bin/pip install -r /opt/trading-bot/requirements.txt

echo "🔐 Ustawianie uprawnień..."
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod 600 "$ENV_FILE"

echo "♻️ Restart usługi..."
sudo systemctl daemon-reload
sudo systemctl restart trading-bot

echo "⏳ Oczekiwanie na uruchomienie..."
sleep 5

echo "📊 Status usługi:"
sudo systemctl status trading-bot --no-pager

echo "🧪 Testowanie endpointów..."
curl -s -o /dev/null -w "Healthz: %{http_code}\n" http://localhost:8009/healthz
curl -s -o /dev/null -w "Readyz: %{http_code}\n" http://localhost:8009/readyz
curl -s -o /dev/null -w "Login: %{http_code}\n" http://localhost:8009/login

echo "✅ Aktualizacja zakończona!"
