#!/bin/bash

# 🚀 UPDATE SERVER FILES - Using Admin Access
# Aktualizacja plików na serwerze używając dostępu admin

set -e

# Configuration
VPS_IP="185.70.196.214"
VPS_USER="admin"  # Using admin instead of root
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"
REMOTE_DIR="/opt/trading-bot"

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
print_update() { echo -e "${PURPLE}[UPDATE]${NC} $1"; }

echo "🚀 Aktualizacja plików na serwerze przez admin..."
echo "═══════════════════════════════════════════════════"

# Stop local server
print_status "Zatrzymywanie lokalnego serwera..."
pkill -f enhanced_server_gpt5.py 2>/dev/null || true
sleep 2

# Check SSH connection with admin user
print_status "Sprawdzanie połączenia SSH jako admin@$VPS_IP..."

SSH_SUCCESS=false

# Try SSH key first
if ssh -o ConnectTimeout=10 -o BatchMode=yes $VPS_USER@$VPS_IP exit 2>/dev/null; then
    SSH_SUCCESS=true
    print_success "Połączenie SSH udane (klucz admin)"
else
    # Try with password
    print_status "Próba logowania z hasłem admin..."
    if ssh -o ConnectTimeout=10 $VPS_USER@$VPS_IP exit; then
        SSH_SUCCESS=true
        print_success "Połączenie SSH udane (hasło admin)"
    else
        SSH_SUCCESS=false
    fi
fi

if [ "$SSH_SUCCESS" = false ]; then
    print_error "Nie można połączyć się jako admin@$VPS_IP"
    
    # Try other common usernames
    for user in ubuntu deployer www-data; do
        print_status "Próba połączenia jako $user..."
        if ssh -o ConnectTimeout=5 -o BatchMode=yes $user@$VPS_IP exit 2>/dev/null; then
            print_success "Połączenie udane jako $user"
            VPS_USER="$user"
            SSH_SUCCESS=true
            break
        fi
    done
fi

if [ "$SSH_SUCCESS" = false ]; then
    print_error "Brak dostępu SSH. Tworzenie pakietu do manualnego upload..."
    
    # Create deployment package
    print_status "Tworzenie pakietu deployment..."
    cd "$LOCAL_DIR"
    
    tar -czf TRADING_BOT_V2_ADMIN_UPDATE.tar.gz \
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
    tar -czf TRADING_BOT_V2_ADMIN_UPDATE.tar.gz \
        enhanced_server_gpt5.py \
        user_database.py \
        index.html \
        login.html \
        register.html \
        nginx_8009.conf \
        requirements.txt \
        simple_openai_client.py \
        web_search_tool.py
    
    print_success "Pakiet utworzony: TRADING_BOT_V2_ADMIN_UPDATE.tar.gz"
    
    # Create admin update script
    cat > admin_update_script.sh << 'EOF'
#!/bin/bash

# 📋 ADMIN UPDATE SCRIPT FOR VPS
# Uruchom ten skrypt na serwerze po przesłaniu plików

echo "🔄 Admin Update Script - Trading Bot v2"
echo "═══════════════════════════════════════"

# Check if running as admin/sudo
if [ "$EUID" -eq 0 ]; then
    echo "✅ Running as root/admin"
elif groups | grep -q 'sudo\|admin\|wheel'; then
    echo "✅ Running as user with sudo access"
    SUDO="sudo"
else
    echo "❌ No admin privileges. Please run as admin or with sudo."
    exit 1
fi

# Backup current version
echo "📦 Creating backup..."
cd /opt
$SUDO cp -r trading-bot trading-bot-backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true

# Stop service
echo "🛑 Stopping trading-bot service..."
$SUDO systemctl stop trading-bot 2>/dev/null || true

# Create directory if it doesn't exist
$SUDO mkdir -p /opt/trading-bot

# Extract files
echo "📂 Extracting new files..."
cd /opt/trading-bot
$SUDO tar -xzf /tmp/TRADING_BOT_V2_ADMIN_UPDATE.tar.gz 2>/dev/null || {
    echo "❌ Cannot find /tmp/TRADING_BOT_V2_ADMIN_UPDATE.tar.gz"
    echo "Please upload the file to /tmp/ first"
    exit 1
}

# Set permissions
echo "🔐 Setting permissions..."
$SUDO chown -R www-data:www-data /opt/trading-bot
$SUDO chmod +x enhanced_server_gpt5.py

# Install dependencies
echo "🐍 Installing Python dependencies..."
$SUDO python3 -m pip install --upgrade pip
$SUDO python3 -m pip install -r requirements.txt

# Update Nginx configuration
echo "🌐 Updating Nginx..."
$SUDO cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
$SUDO ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
$SUDO nginx -t && $SUDO systemctl reload nginx

# Initialize user database
echo "🗄️ Initializing user database..."
cd /opt/trading-bot
$SUDO -u www-data python3 user_database.py

# Create/Update systemd service
echo "⚙️ Creating systemd service..."
$SUDO tee /etc/systemd/system/trading-bot.service > /dev/null << 'SYSTEMD_EOF'
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
SYSTEMD_EOF

# Enable and start service
echo "🚀 Starting service..."
$SUDO systemctl daemon-reload
$SUDO systemctl enable trading-bot
$SUDO systemctl start trading-bot

# Wait and check status
echo "⏳ Checking service status..."
sleep 5
$SUDO systemctl status trading-bot --no-pager

echo ""
echo "🧪 Testing endpoints..."
curl -s -o /dev/null -w "Login page: %{http_code}\n" http://localhost:8009/login || echo "Login test failed"
curl -s -o /dev/null -w "Register page: %{http_code}\n" http://localhost:8009/register || echo "Register test failed"

echo ""
echo "✅ ADMIN UPDATE COMPLETED!"
echo "═════════════════════════════════"
echo "🌐 Website: http://185.70.196.214"
echo "🔐 Login: http://185.70.196.214/login"
echo "📝 Register: http://185.70.196.214/register"
echo ""
echo "🔑 Default Admin Login:"
echo "   Username: admin"
echo "   Password: password"
echo ""
echo "📊 Service Commands:"
echo "   sudo systemctl status trading-bot"
echo "   sudo systemctl restart trading-bot"
echo "   sudo journalctl -u trading-bot -f"

# Clean up
rm -f /tmp/TRADING_BOT_V2_ADMIN_UPDATE.tar.gz
EOF

    chmod +x admin_update_script.sh
    
    echo ""
    print_success "Skrypt admin update utworzony: admin_update_script.sh"
    echo ""
    echo "📋 INSTRUKCJE MANUAL DEPLOYMENT:"
    echo "════════════════════════════════════════"
    echo ""
    echo "1. 📁 Prześlij pliki na serwer:"
    echo "   scp TRADING_BOT_V2_ADMIN_UPDATE.tar.gz admin@$VPS_IP:/tmp/"
    echo "   scp admin_update_script.sh admin@$VPS_IP:~/"
    echo ""
    echo "2. 🔐 Zaloguj się na serwer:"
    echo "   ssh admin@$VPS_IP"
    echo ""
    echo "3. 🚀 Uruchom aktualizację:"
    echo "   chmod +x admin_update_script.sh"
    echo "   ./admin_update_script.sh"
    echo ""
    echo "4. 🧪 Przetestuj aplikację:"
    echo "   curl http://localhost:8009/login"
    echo "   curl http://localhost:8009/register"
    echo ""
    
    exit 1
fi

# If SSH works, proceed with automatic update
print_success "Połączenie SSH udane jako $VPS_USER@$VPS_IP"

# Create update package
print_status "Tworzenie pakietu aktualizacji..."
cd "$LOCAL_DIR"

tar -czf TRADING_BOT_V2_ADMIN_UPDATE.tar.gz \
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
tar -czf TRADING_BOT_V2_ADMIN_UPDATE.tar.gz \
    enhanced_server_gpt5.py \
    user_database.py \
    index.html \
    login.html \
    register.html \
    nginx_8009.conf \
    requirements.txt \
    simple_openai_client.py \
    web_search_tool.py

print_success "Pakiet utworzony"

# Upload files
print_update "Przesyłanie plików..."
scp TRADING_BOT_V2_ADMIN_UPDATE.tar.gz $VPS_USER@$VPS_IP:/tmp/

print_success "Pliki przesłane"

# Execute update on server
print_update "Wykonywanie aktualizacji na serwerze..."

ssh $VPS_USER@$VPS_IP << 'ENDSSH'
set -e

echo "🔄 Starting update as admin user..."

# Check sudo access
if sudo -n true 2>/dev/null; then
    echo "✅ Sudo access confirmed"
    SUDO="sudo"
elif [ "$USER" = "root" ]; then
    echo "✅ Running as root"
    SUDO=""
else
    echo "❌ No sudo access. Please ensure admin user has sudo privileges."
    exit 1
fi

# Backup
echo "📦 Creating backup..."
$SUDO mkdir -p /opt
cd /opt
$SUDO cp -r trading-bot trading-bot-backup-$(date +%Y%m%d-%H%M%S) 2>/dev/null || echo "No previous installation found"

# Stop service
echo "🛑 Stopping service..."
$SUDO systemctl stop trading-bot 2>/dev/null || echo "Service not running"

# Create directory and extract
echo "📂 Updating files..."
$SUDO mkdir -p /opt/trading-bot
cd /opt/trading-bot
$SUDO tar -xzf /tmp/TRADING_BOT_V2_ADMIN_UPDATE.tar.gz

# Set permissions
echo "🔐 Setting permissions..."
$SUDO chown -R www-data:www-data /opt/trading-bot
$SUDO chmod +x enhanced_server_gpt5.py

# Install dependencies
echo "🐍 Installing dependencies..."
$SUDO python3 -m pip install --upgrade pip
$SUDO python3 -m pip install -r requirements.txt

# Update Nginx
echo "🌐 Configuring Nginx..."
$SUDO cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
$SUDO ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
$SUDO nginx -t && $SUDO systemctl reload nginx

# Initialize database
echo "🗄️ Initializing database..."
$SUDO -u www-data python3 user_database.py

# Create systemd service
echo "⚙️ Creating service..."
$SUDO tee /etc/systemd/system/trading-bot.service > /dev/null << 'EOF'
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

# Start service
echo "🚀 Starting service..."
$SUDO systemctl daemon-reload
$SUDO systemctl enable trading-bot
$SUDO systemctl start trading-bot

sleep 5
echo "📊 Service status:"
$SUDO systemctl status trading-bot --no-pager

echo "✅ Update completed on server!"

# Clean up
rm -f /tmp/TRADING_BOT_V2_ADMIN_UPDATE.tar.gz
ENDSSH

# Test from outside
print_update "Testowanie z zewnątrz..."
sleep 3

LOGIN_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://$VPS_IP/login)
REGISTER_TEST=$(curl -s -o /dev/null -w "%{http_code}" http://$VPS_IP/register)

if [ "$LOGIN_TEST" = "200" ] && [ "$REGISTER_TEST" = "200" ]; then
    print_success "✅ Wszystkie testy przeszły pomyślnie!"
else
    print_warning "⚠️  Serwer może potrzebować więcej czasu (Login: $LOGIN_TEST, Register: $REGISTER_TEST)"
fi

# Clean up
rm -f TRADING_BOT_V2_ADMIN_UPDATE.tar.gz

echo ""
echo "🎉 AKTUALIZACJA ZAKOŃCZONA POMYŚLNIE!"
echo "═══════════════════════════════════════════════════"
echo "🌐 Website: http://$VPS_IP"
echo "🔐 Login: http://$VPS_IP/login"
echo "📝 Register: http://$VPS_IP/register"
echo "🔧 API: http://$VPS_IP/api/"
echo ""
echo "🔑 Admin Login:"
echo "   Username: admin"
echo "   Password: password"
echo ""
echo "📊 Monitorowanie:"
echo "   ssh $VPS_USER@$VPS_IP"
echo "   sudo systemctl status trading-bot"
echo "   sudo journalctl -u trading-bot -f"
echo ""
print_success "Wszystkie pliki zaktualizowane przez admin!"
