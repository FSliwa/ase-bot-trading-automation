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
