#!/bin/bash

# 🚀 QUICK UPDATE - Trading Bot v2
# Szybka aktualizacja bez zawieszania

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
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo "🚀 Quick Update - Trading Bot v2"
echo "=================================="

# Step 1: Create package
print_status "Tworzenie pakietu..."
cd "$LOCAL_DIR"

tar -czf QUICK_UPDATE.tar.gz \
    fastapi_app.py \
    requirements.txt \
    nginx_8009.conf 2>/dev/null

print_success "Pakiet utworzony: QUICK_UPDATE.tar.gz"

# Step 2: Upload
print_status "Przesyłanie na serwer..."
echo "🔑 Wprowadź hasło SSH:"
scp QUICK_UPDATE.tar.gz $VPS_USER@$VPS_IP:/tmp/

print_success "Pliki przesłane"

# Step 3: Simple update commands
print_status "Wykonywanie aktualizacji (krótkie komendy)..."
echo "🔑 Wprowadź hasło SSH:"

# Stop service
ssh $VPS_USER@$VPS_IP "sudo systemctl stop trading-bot"
print_success "Serwis zatrzymany"

echo "🔑 Wprowadź hasło SSH:"
# Extract files
ssh $VPS_USER@$VPS_IP "cd /opt/trading-bot && sudo tar -xzf /tmp/QUICK_UPDATE.tar.gz"
print_success "Pliki wyodrębnione"

echo "🔑 Wprowadź hasło SSH:"
# Install requirements
ssh $VPS_USER@$VPS_IP "cd /opt/trading-bot && sudo python3 -m pip install --break-system-packages -r requirements.txt"
print_success "Wymagania zainstalowane"

echo "🔑 Wprowadź hasło SSH:"
# Start service
ssh $VPS_USER@$VPS_IP "sudo systemctl start trading-bot"
print_success "Serwis uruchomiony"

# Wait and test
sleep 3
print_status "Testowanie..."

# Test OAuth endpoints
GOOGLE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$VPS_IP/auth/google 2>/dev/null || echo "ERROR")
GITHUB_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://$VPS_IP/auth/github 2>/dev/null || echo "ERROR")

echo ""
echo "🧪 WYNIKI TESTÓW:"
echo "Google OAuth: $GOOGLE_STATUS"
echo "GitHub OAuth: $GITHUB_STATUS"

if [[ "$GOOGLE_STATUS" == "307" || "$GOOGLE_STATUS" == "302" ]] && [[ "$GITHUB_STATUS" == "307" || "$GITHUB_STATUS" == "302" ]]; then
    print_success "✅ OAuth działa poprawnie!"
else
    print_warning "⚠️ OAuth może wymagać konfiguracji credentials"
fi

# Clean up
rm -f QUICK_UPDATE.tar.gz

echo ""
echo "🎉 SZYBKA AKTUALIZACJA ZAKOŃCZONA!"
echo "🌐 Test: http://$VPS_IP/auth/google"
echo "🌐 Test: http://$VPS_IP/auth/github"
