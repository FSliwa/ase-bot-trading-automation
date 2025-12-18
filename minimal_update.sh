#!/bin/bash

# 🚀 MINIMAL UPDATE - Trading Bot v2  
# Minimalna aktualizacja z sudo -S

set -e

VPS_IP="185.70.196.214"
VPS_USER="admin"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

echo "🚀 Minimal Update - Trading Bot v2"
echo "=================================="

# Get sudo password once
echo -n "🔑 Wprowadź hasło sudo dla serwera: "
read -s SUDO_PASS
echo ""

# Step 1: Create package
print_status "Tworzenie pakietu..."
cd "$LOCAL_DIR"

tar -czf MINIMAL_UPDATE.tar.gz fastapi_app.py requirements.txt 2>/dev/null

print_success "Pakiet utworzony"

# Step 2: Upload
print_status "Przesyłanie na serwer..."
echo "🔑 Wprowadź hasło SSH:"
scp MINIMAL_UPDATE.tar.gz $VPS_USER@$VPS_IP:/tmp/

print_success "Pliki przesłane"

# Step 3: Update with one command
print_status "Wykonywanie aktualizacji..."
echo "🔑 Wprowadź hasło SSH:"

ssh $VPS_USER@$VPS_IP "echo '$SUDO_PASS' | sudo -S bash -c '
echo \"🛑 Stopping service...\"
systemctl stop trading-bot
echo \"📂 Extracting files...\"
cd /opt/trading-bot
tar -xzf /tmp/MINIMAL_UPDATE.tar.gz
echo \"📦 Installing requirements...\"
python3 -m pip install --break-system-packages -r requirements.txt > /dev/null 2>&1
echo \"🚀 Starting service...\"
systemctl start trading-bot
echo \"✅ Update completed!\"
'"

print_success "Aktualizacja zakończona"

# Wait and test
print_status "Testowanie OAuth po 3 sekundach..."
sleep 3

GOOGLE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$VPS_IP/auth/google 2>/dev/null || echo "ERROR")
GITHUB_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$VPS_IP/auth/github 2>/dev/null || echo "ERROR")

echo ""
echo "🧪 WYNIKI TESTÓW:"
echo "Google OAuth: $GOOGLE_STATUS (powinno być 307/302)"
echo "GitHub OAuth: $GITHUB_STATUS (powinno być 307/302)"

if [[ "$GOOGLE_STATUS" == "307" || "$GOOGLE_STATUS" == "302" ]] && [[ "$GITHUB_STATUS" == "307" || "$GITHUB_STATUS" == "302" ]]; then
    echo ""
    print_success "✅ SUKCES! OAuth działa poprawnie - problem rozwiązany!"
else
    echo ""
    print_status "OAuth może wymagać konfiguracji credentials w .env.db"
fi

# Clean up
rm -f MINIMAL_UPDATE.tar.gz

echo ""
echo "🎉 MINIMALNA AKTUALIZACJA ZAKOŃCZONA!"
echo "🌐 Test: http://$VPS_IP/auth/google"
echo "🌐 Test: http://$VPS_IP/auth/github"
