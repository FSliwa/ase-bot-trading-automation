#!/bin/bash

# Prosty skrypt aktualizacji serwera - bez zawieszania się
set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"

echo "🚀 Prosty skrypt aktualizacji serwera"
echo "======================================"

# Krok 1: Utwórz pakiet
echo "📦 Tworzenie pakietu..."
cd "$LOCAL_DIR"
tar -czf update.tar.gz \
    fastapi_app.py \
    user_database.py \
    requirements.txt \
    login.html \
    register.html \
    index.html \
    setup_postgresql.sh

# Krok 2: Prześlij na serwer
echo "📤 Przesyłanie na serwer..."
scp -o ConnectTimeout=30 -o StrictHostKeyChecking=no update.tar.gz $VPS_USER@$VPS_IP:/tmp/

# Krok 3: Wykonaj proste polecenia aktualizacji
echo "🔧 Uruchamianie aktualizacji na serwerze..."
ssh -t -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP "
set -e
cd /opt/trading-bot

echo '--- Rozpakowywanie aktualizacji ---'
sudo tar -xzf /tmp/update.tar.gz --no-same-owner

echo '--- Ustawianie uprawnień ---'
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x setup_postgresql.sh

echo '--- Konfiguracja PostgreSQL ---'
sudo ./setup_postgresql.sh

echo '--- Instalowanie zależności ---'
sudo python3 -m pip install --break-system-packages -r requirements.txt

echo '--- Restartowanie usługi ---'
sudo systemctl restart trading-bot

echo '✅ Gotowe'
"

echo "✅ Aktualizacja zakończona!"
echo "🌐 Test: http://$VPS_IP/register"
