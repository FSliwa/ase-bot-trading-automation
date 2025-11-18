#!/bin/bash

# 🚀 UPDATE SERVER WITH GEMINI AI - Trading Bot v2.2
# Prosty skrypt do aktualizacji z ręcznym wprowadzaniem hasła sudo

set -e

# --- Konfiguracja ---
VPS_IP="185.70.196.214"
VPS_USER="admin"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"
REMOTE_DIR="/opt/trading-bot"
FILES_TO_UPLOAD=(
    "fastapi_app.py"
    "requirements.txt"
)
ARCHIVE_NAME="gemini_update.tar.gz"
GEMINI_API_KEY="YOUR_NEW_SECURE_GEMINI_API_KEY_HERE"

# --- Kolory ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- Funkcje pomocnicze ---
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# --- Główny skrypt ---
cd "$LOCAL_DIR"

print_status "Tworzenie archiwum z plikami do aktualizacji..."
tar -czf "$ARCHIVE_NAME" "${FILES_TO_UPLOAD[@]}"
print_success "Archiwum '$ARCHIVE_NAME' zostało utworzone."

print_status "Przesyłanie archiwum na serwer $VPS_IP..."
scp "$ARCHIVE_NAME" "$VPS_USER@$VPS_IP:/tmp/"
print_success "Archiwum zostało przesłane do /tmp/ na serwerze."

print_warning "Teraz będziesz musiał wprowadzić hasło SSH, a następnie hasło sudo dla każdej komendy."
print_status "Łączenie z serwerem i uruchamianie aktualizacji..."

ssh -t "$VPS_USER@$VPS_IP" << EOF
echo "🔄 Rozpoczynanie aktualizacji na serwerze..."

echo "🛑 Zatrzymywanie usługi trading-bot..."
sudo systemctl stop trading-bot || true

echo "📂 Rozpakowywanie archiwum w $REMOTE_DIR..."
sudo tar -xzf "/tmp/$ARCHIVE_NAME" -C "$REMOTE_DIR"

echo "🔧 Aktualizowanie zmiennej środowiskowej GEMINI_API_KEY..."
ENV_FILE="$REMOTE_DIR/.env.db"
if sudo grep -q "GEMINI_API_KEY" "\$ENV_FILE"; then
    sudo sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=$GEMINI_API_KEY|" "\$ENV_FILE"
else
    echo "GEMINI_API_KEY=$GEMINI_API_KEY" | sudo tee -a "\$ENV_FILE" > /dev/null
fi

echo "🗑️ Usuwanie starego klucza OpenAI..."
sudo sed -i "/^OPENAI_API_KEY=.*/d" "\$ENV_FILE"

echo "📦 Instalowanie/aktualizowanie zależności Pythona..."
sudo "$REMOTE_DIR/.venv/bin/pip" install -r "$REMOTE_DIR/requirements.txt"

echo "🔐 Ustawianie uprawnień..."
sudo chown -R www-data:www-data "$REMOTE_DIR"
sudo chmod 600 "\$ENV_FILE"

echo "♻️ Przeładowanie demona systemd i restart usługi..."
sudo systemctl daemon-reload
sudo systemctl restart trading-bot

echo "⏳ Oczekiwanie na uruchomienie usługi..."
sleep 5

echo "📊 Sprawdzanie statusu usługi..."
sudo systemctl status trading-bot --no-pager

echo "🧪 Testowanie endpointów..."
curl -s -o /dev/null -w "Healthz: %{http_code}\n" http://localhost:8009/healthz
curl -s -o /dev/null -w "Readyz: %{http_code}\n" http://localhost:8009/readyz
curl -s -o /dev/null -w "Login: %{http_code}\n" http://localhost:8009/login

echo "✅ Aktualizacja zakończona pomyślnie!"
echo "🌐 Sprawdź: http://185.70.196.214/login"
echo "🔧 Nowy endpoint AI: http://185.70.196.214/api/gemini-analyze"
EOF

# --- Sprzątanie ---
rm "$ARCHIVE_NAME"
print_status "Lokalne archiwum zostało usunięte."

print_success "🎉 Aktualizacja z Gemini AI została zakończona!"
print_status "Nowe endpointy:"
print_status "  - /api/gemini-analyze (zastąpił /api/gpt5-analyze)"
print_status "  - /api/web-search-analysis (korzysta teraz z Gemini)"
