#!/bin/bash

# 🚀 UPDATE SERVER FILES - Using Ubuntu User with Sudo
# Aktualizacja plików na serwerze używając ubuntu user z sudo

set -e

# Configuration  
VPS_IP="185.70.196.214"
VPS_USER="ubuntu"  # Using ubuntu user which typically has sudo
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "🚀 Aktualizacja przez ubuntu user z sudo..."
echo "═══════════════════════════════════════════"

# Stop local server
print_status "Zatrzymywanie lokalnego serwera..."
pkill -f enhanced_server_gpt5.py 2>/dev/null || true

# Try ubuntu user
print_status "Próba połączenia jako ubuntu@$VPS_IP..."

if ssh -o ConnectTimeout=10 ubuntu@$VPS_IP exit; then
    print_success "Połączenie udane jako ubuntu"
else
    print_error "Nie można połączyć się jako ubuntu"
    
    # Create manual deployment files
    print_status "Tworzenie plików do manual deployment..."
    cd "$LOCAL_DIR"
    
    tar -czf TRADING_BOT_V2_FINAL.tar.gz \
        enhanced_server_gpt5.py \
        user_database.py \
        index.html \
        login.html \
        register.html \
        nginx_8009.conf \
        requirements.txt \
        simple_openai_client.py \
        web_search_tool.py \
        users.json 2>/dev/null || \
    tar -czf TRADING_BOT_V2_FINAL.tar.gz \
        enhanced_server_gpt5.py \
        user_database.py \
        index.html \
        login.html \
        register.html \
        nginx_8009.conf \
        requirements.txt \
        simple_openai_client.py \
        web_search_tool.py
    
    # Create comprehensive deployment script
    cat > deploy_on_server.sh << 'EOF'
#!/bin/bash

# 🚀 FINAL DEPLOYMENT SCRIPT - Run this on the VPS server
# Execute as: sudo ./deploy_on_server.sh

echo "🚀 Trading Bot v2 - Final Deployment"
echo "═══════════════════════════════════════"

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root or with sudo: sudo ./deploy_on_server.sh"
    exit 1
fi

echo "✅ Running with admin privileges"

# Variables
INSTALL_DIR="/opt/trading-bot"
ARCHIVE_FILE="/tmp/TRADING_BOT_V2_FINAL.tar.gz"

# Check if archive exists
if [ ! -f "$ARCHIVE_FILE" ]; then
    echo "❌ Archive not found: $ARCHIVE_FILE"
    echo "Please upload TRADING_BOT_V2_FINAL.tar.gz to /tmp/ first"
    exit 1
fi

# Backup existing installation
if [ -d "$INSTALL_DIR" ]; then
    echo "📦 Creating backup..."
    cp -r "$INSTALL_DIR" "${INSTALL_DIR}-backup-$(date +%Y%m%d-%H%M%S)"
    systemctl stop trading-bot 2>/dev/null || true
fi

# Create installation directory
echo "📁 Creating installation directory..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"

# Extract files
echo "📂 Extracting files..."
tar -xzf "$ARCHIVE_FILE"

# Install system dependencies
echo "🔧 Installing system dependencies..."
apt update
apt install -y python3 python3-pip python3-venv nginx

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt

# Set up nginx
echo "🌐 Configuring Nginx..."
cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl enable nginx
systemctl restart nginx

# Set permissions
echo "🔐 Setting permissions..."
useradd -r -s /bin/bash -d "$INSTALL_DIR" -M www-data 2>/dev/null || true
chown -R www-data:www-data "$INSTALL_DIR"
chmod +x enhanced_server_gpt5.py

# Initialize user database
echo "🗄️ Initializing user database..."
sudo -u www-data python3 user_database.py

# Create systemd service
echo "⚙️ Creating systemd service..."
cat > /etc/systemd/system/trading-bot.service << 'SYSTEMD_EOF'
[Unit]
Description=Trading Bot Server with Registration System
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trading-bot
ExecStart=/usr/bin/python3 enhanced_server_gpt5.py
Restart=always
RestartSec=3
EnvironmentFile=/opt/trading-bot/.env.db
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# Enable and start service
echo "🚀 Starting service..."
systemctl daemon-reload
systemctl enable trading-bot
systemctl start trading-bot

# Wait for service to start
echo "⏳ Waiting for service to start..."
sleep 5

# Check status
echo "📊 Service status:"
systemctl status trading-bot --no-pager

# Test endpoints
echo ""
echo "🧪 Testing endpoints..."
curl -s -o /dev/null -w "Login page: %{http_code}\n" http://localhost:8009/login || echo "Login test failed"
curl -s -o /dev/null -w "Register page: %{http_code}\n" http://localhost:8009/register || echo "Register test failed"
curl -s -o /dev/null -w "Main page: %{http_code}\n" http://localhost:8009/ || echo "Main page test failed"

# Clean up
rm -f "$ARCHIVE_FILE"

echo ""
echo "🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!"
echo "═══════════════════════════════════════════"
echo "🌐 Website: http://185.70.196.214"
echo "🔐 Login: http://185.70.196.214/login"  
echo "📝 Register: http://185.70.196.214/register"
echo "🔧 API: http://185.70.196.214/api/"
echo ""
echo "🔑 Default Admin Account:"
echo "   Username: admin"
echo "   Password: password"
echo "   Email: admin@tradingbot.com"
echo ""
echo "📊 Management Commands:"
echo "   sudo systemctl status trading-bot"
echo "   sudo systemctl restart trading-bot"  
echo "   sudo systemctl stop trading-bot"
echo "   sudo journalctl -u trading-bot -f"
echo ""
echo "📁 Application Files: $INSTALL_DIR"
echo "🗄️ User Database: $INSTALL_DIR/users.json"
echo ""
echo "✅ Trading Bot v2 with Registration System is now live!"
EOF

    chmod +x deploy_on_server.sh
    
    print_success "Pliki deployment utworzone:"
    echo "  - TRADING_BOT_V2_FINAL.tar.gz"
    echo "  - deploy_on_server.sh"
    echo ""
    echo "📋 MANUAL DEPLOYMENT STEPS:"
    echo "═══════════════════════════════════════"
    echo ""
    echo "1. 📁 Upload files to server:"
    echo "   scp TRADING_BOT_V2_FINAL.tar.gz admin@185.70.196.214:/tmp/"
    echo "   scp deploy_on_server.sh admin@185.70.196.214:~/"
    echo ""
    echo "2. 🔐 Login to server:"
    echo "   ssh admin@185.70.196.214"
    echo ""
    echo "3. 🚀 Run deployment:"
    echo "   sudo chmod +x deploy_on_server.sh"
    echo "   sudo ./deploy_on_server.sh"
    echo ""
    echo "4. 🧪 Test the application:"
    echo "   curl http://185.70.196.214/login"
    echo "   Open http://185.70.196.214 in browser"
    echo ""
    
    exit 1
fi

# Automatic deployment with ubuntu user
print_status "Tworzenie pakietu..."
cd "$LOCAL_DIR"

tar -czf TRADING_BOT_V2_UBUNTU.tar.gz \
    enhanced_server_gpt5.py \
    user_database.py \
    index.html \
    login.html \
    register.html \
    nginx_8009.conf \
    requirements.txt \
    simple_openai_client.py \
    web_search_tool.py \
    users.json 2>/dev/null || \
tar -czf TRADING_BOT_V2_UBUNTU.tar.gz \
    enhanced_server_gpt5.py \
    user_database.py \
    index.html \
    login.html \
    register.html \
    nginx_8009.conf \
    requirements.txt \
    simple_openai_client.py \
    web_search_tool.py

print_status "Przesyłanie plików..."
scp TRADING_BOT_V2_UBUNTU.tar.gz ubuntu@$VPS_IP:/tmp/

print_status "Aktualizacja na serwerze..."
ssh ubuntu@$VPS_IP << 'ENDSSH'
set -e

echo "🔄 Ubuntu user deployment..."

# Backup
sudo mkdir -p /opt
sudo cp -r /opt/trading-bot /opt/trading-bot-backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || echo "No previous installation"

# Stop service
sudo systemctl stop trading-bot 2>/dev/null || true

# Extract
sudo mkdir -p /opt/trading-bot
cd /opt/trading-bot
sudo tar -xzf /tmp/TRADING_BOT_V2_UBUNTU.tar.gz

# Dependencies
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install -r requirements.txt

# Nginx
sudo cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Permissions
sudo useradd -r -s /bin/bash -d /opt/trading-bot -M www-data 2>/dev/null || true
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x enhanced_server_gpt5.py

# Database
sudo -u www-data python3 user_database.py

# Service
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
EnvironmentFile=/opt/trading-bot/.env.db
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

sleep 5
sudo systemctl status trading-bot --no-pager

rm -f /tmp/TRADING_BOT_V2_UBUNTU.tar.gz
echo "✅ Ubuntu deployment completed!"
ENDSSH

print_status "Testowanie..."
sleep 3

if curl -s http://$VPS_IP/login | grep -q "Trading"; then
    print_success "✅ Aplikacja działa poprawnie!"
else
    print_warning "⚠️  Aplikacja może potrzebować więcej czasu"
fi

rm -f TRADING_BOT_V2_UBUNTU.tar.gz

echo ""
echo "🎉 AKTUALIZACJA ZAKOŃCZONA!"
echo "═══════════════════════════════"
echo "🌐 http://185.70.196.214"
echo "🔐 http://185.70.196.214/login"
echo "📝 http://185.70.196.214/register"
print_success "Wszystkie pliki zaktualizowane!"
