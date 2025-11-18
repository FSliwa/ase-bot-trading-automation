#!/bin/bash

# 🚀 UPDATE SERVER WITH GEMINI AI - Trading Bot v2.2
# Prosty skrypt do aktualizacji plików na serwerze, instalacji zależności i restartu usługi.

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

print_status "Uruchamianie skryptu aktualizacyjnego na serwerze..."
ssh -tt "$VPS_USER@$VPS_IP" "bash -s" << EOF
set -e

# --- Prime sudo by asking for password upfront ---
echo "Wprowadź hasło sudo dla użytkownika 'admin', aby kontynuować..."
sudo -v
# Keep-alive: update existing sudo time stamp if set, otherwise do nothing.
while true; do sudo -n true; sleep 60; kill -0 "$$" || exit; done 2>/dev/null &

REMOTE_DIR="$REMOTE_DIR"
ARCHIVE_NAME="$ARCHIVE_NAME"
GEMINI_API_KEY="$GEMINI_API_KEY"

echo -e "${BLUE}[INFO]${NC} Zatrzymywanie usługi trading-bot..."
sudo systemctl stop trading-bot || true

echo -e "${BLUE}[INFO]${NC} Rozpakowywanie archiwum w \$REMOTE_DIR..."
sudo tar -xzf "/tmp/\$ARCHIVE_NAME" -C "\$REMOTE_DIR"

echo -e "${BLUE}[INFO]${NC} Aktualizowanie zmiennej środowiskowej GEMINI_API_KEY..."
ENV_FILE="\$REMOTE_DIR/.env.db"
if sudo grep -q "GEMINI_API_KEY" "\$ENV_FILE"; then
    sudo sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=\${GEMINI_API_KEY}|" "\$ENV_FILE"
else
    echo "GEMINI_API_KEY=\${GEMINI_API_KEY}" | sudo tee -a "\$ENV_FILE" > /dev/null
fi
# Usuwanie starego klucza OpenAI, jeśli istnieje
sudo sed -i "/^OPENAI_API_KEY=.*/d" "\$ENV_FILE"

echo -e "${BLUE}[INFO]${NC} Instalowanie/aktualizowanie zależności Pythona..."
sudo "\$REMOTE_DIR/.venv/bin/pip" install -r "\$REMOTE_DIR/requirements.txt"

echo -e "${BLUE}[INFO]${NC} Ustawianie uprawnień..."
sudo chown -R www-data:www-data "\$REMOTE_DIR"
sudo chmod 600 "\$ENV_FILE"

echo -e "${BLUE}[INFO]${NC} Przeładowanie demona systemd i restart usługi..."
sudo systemctl daemon-reload
sudo systemctl restart trading-bot

echo -e "${GREEN}[SUCCESS]${NC} Usługa została zrestartowana. Sprawdzanie statusu..."
sleep 3
sudo systemctl status trading-bot --no-pager

echo -e "${GREEN}[SUCCESS]${NC} Aktualizacja zakończona pomyślnie!"
EOF

print_success "Proces aktualizacji na serwerze został zakończony."

# --- Sprzątanie ---
rm "$ARCHIVE_NAME"
print_status "Lokalne archiwum zostało usunięte."
