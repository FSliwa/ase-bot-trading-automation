#!/bin/bash

# 🚀 Trading Bot v2 - Deployment Script with Registration System
# Kompilacja i wdrożenie aplikacji na serwer VPS

set -e

# Configuration
VPS_IP="185.70.196.214"
VPS_USER="root"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"
REMOTE_DIR="/opt/trading-bot"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "🚀 Rozpoczynanie kompilacji i wdrożenia Trading Bot v2..."

# Check SSH connection
print_status "Sprawdzanie połączenia SSH z $VPS_IP..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes $VPS_USER@$VPS_IP exit 2>/dev/null; then
    print_error "Nie można połączyć się z serwerem. Sprawdź:"
    echo "1. Czy serwer jest dostępny"
    echo "2. Czy klucz SSH jest skonfigurowany"
    echo "3. Czy IP i użytkownik są poprawne"
    exit 1
fi
print_success "Połączenie SSH udane"

# Create deployment package
print_status "Tworzenie pakietu deployment..."
cd "$LOCAL_DIR"

# Stop local server
print_status "Zatrzymywanie lokalnego serwera..."
pkill -f enhanced_server_gpt5.py 2>/dev/null || true

# Create archive with all necessary files
print_status "Tworzenie archiwum z plikami aplikacji..."
tar -czf trading_bot_complete.tar.gz \
    enhanced_server_gpt5.py \
    user_database.py \
    index.html \
    login.html \
    register.html \
    nginx_8009.conf \
    requirements.txt \
    simple_openai_client.py \
    web_search_tool.py \
    users.json \
    2>/dev/null || true

print_success "Pakiet deployment utworzony: trading_bot_complete.tar.gz"

# Upload to server
print_status "Przesyłanie plików na serwer..."
scp trading_bot_complete.tar.gz $VPS_USER@$VPS_IP:/tmp/

# Deploy on server
print_status "Instalowanie aplikacji na serwerze..."
ssh $VPS_USER@$VPS_IP << 'ENDSSH'
set -e

echo "📦 Rozpakowywanie aplikacji..."
cd /opt
rm -rf trading-bot-old 2>/dev/null || true
mv trading-bot trading-bot-old 2>/dev/null || true
mkdir -p trading-bot
cd trading-bot

tar -xzf /tmp/trading_bot_complete.tar.gz
rm /tmp/trading_bot_complete.tar.gz

echo "🐍 Instalowanie Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

echo "🔧 Konfigurowanie Nginx..."
cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

echo "🗄️ Inicjalizowanie bazy danych użytkowników..."
python3 user_database.py

echo "🔒 Ustawianie uprawnień..."
chown -R www-data:www-data /opt/trading-bot
chmod +x enhanced_server_gpt5.py

echo "📊 Tworzenie systemd service..."
cat > /etc/systemd/system/trading-bot.service << 'EOF'
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

systemctl daemon-reload
systemctl enable trading-bot
systemctl stop trading-bot 2>/dev/null || true
systemctl start trading-bot

echo "🔍 Sprawdzanie statusu..."
sleep 3
systemctl status trading-bot --no-pager
ENDSSH

# Check deployment
print_status "Sprawdzanie wdrożenia..."
sleep 5

# Test server response
if curl -s -o /dev/null -w "%{http_code}" http://$VPS_IP/login | grep -q "200"; then
    print_success "✅ Serwer odpowiada poprawnie!"
else
    print_warning "⚠️  Serwer może potrzebować więcej czasu na uruchomienie"
fi

# Display final information
echo ""
echo "🎉 DEPLOYMENT COMPLETED!"
echo "═══════════════════════════════════════"
echo "🌐 Website: http://$VPS_IP"
echo "🔐 Login: http://$VPS_IP/login"
echo "📝 Register: http://$VPS_IP/register"
echo "🔧 API Base: http://$VPS_IP/api/"
echo ""
echo "📊 Default Admin Account:"
echo "   Username: admin"
echo "   Password: password"
echo ""
echo "🔧 System Commands on VPS:"
echo "   sudo systemctl status trading-bot"
echo "   sudo systemctl restart trading-bot"
echo "   sudo journalctl -u trading-bot -f"
echo ""
echo "📁 Application Path: $REMOTE_DIR"
echo "🗄️ User Database: $REMOTE_DIR/users.json"
echo ""

# Clean up local files
rm -f trading_bot_complete.tar.gz

print_success "Deployment zakończony pomyślnie!"
echo ""
echo "🚀 Aplikacja jest gotowa do użycia z pełnym systemem rejestracji!"
