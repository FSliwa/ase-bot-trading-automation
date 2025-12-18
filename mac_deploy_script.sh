#!/bin/bash
# 🍎 DEPLOYMENT SCRIPT FOR MAC VNC
# Wykonaj ten skrypt na serwerze VPS

echo "🚀 Trading Bot Deployment Script"
echo "================================"

# Backup existing installation
echo "📦 Creating backup..."
sudo cp -r /opt/trading-bot /opt/trading-bot-backup-$(date +%Y%m%d) 2>/dev/null || echo "No previous installation found"

# Create directory
echo "📁 Creating directory..."
sudo mkdir -p /opt/trading-bot

# Copy files
echo "📋 Copying files..."
sudo cp ~/enhanced_server_gpt5.py \
        ~/user_database.py \
        ~/index.html \
        ~/login.html \
        ~/register.html \
        ~/nginx_8009.conf \
        ~/requirements.txt \
        ~/simple_openai_client.py \
        ~/web_search_tool.py \
        ~/users.json \
        /opt/trading-bot/

# Set permissions
echo "🔧 Setting permissions..."
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x /opt/trading-bot/enhanced_server_gpt5.py

# Install Python packages
echo "🐍 Installing Python packages..."
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install -r /opt/trading-bot/requirements.txt

# Configure nginx
echo "🌐 Configuring nginx..."
sudo cp /opt/trading-bot/nginx_8009.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Create systemd service
echo "⚙️ Creating systemd service..."
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
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# Start service
echo "🚀 Starting service..."
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl stop trading-bot 2>/dev/null || true
sudo systemctl start trading-bot

# Initialize database
echo "💾 Initializing database..."
cd /opt/trading-bot
sudo -u www-data python3 user_database.py

# Check status
echo "✅ Checking status..."
sudo systemctl status trading-bot --no-pager
echo ""
echo "🧪 Testing local connection..."
curl -s http://localhost:8009/login | head -10

echo ""
echo "🎯 DEPLOYMENT COMPLETE!"
echo "Visit: http://185.70.196.214/login"
echo "Registration available at: http://185.70.196.214/register"
