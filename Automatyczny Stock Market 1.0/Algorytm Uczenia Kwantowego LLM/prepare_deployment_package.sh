#!/bin/bash

# 🎯 PRZYGOTOWANIE DEPLOYMENT PACKAGE
# Przygotowuje pełny pakiet do manual deployment na VPS

set -e

echo "🎯 TWORZENIE PAKIETU DEPLOYMENT'U"
echo "=================================="

# Create deployment package
DEPLOY_DIR="vps_deployment_package"
rm -rf $DEPLOY_DIR
mkdir -p $DEPLOY_DIR

echo "📦 Kopiowanie plików projektu..."

# Copy essential files
cp -r bot/ $DEPLOY_DIR/
cp -r web/ $DEPLOY_DIR/
cp requirements.txt $DEPLOY_DIR/
cp *.py $DEPLOY_DIR/ 2>/dev/null || true
cp *.sh $DEPLOY_DIR/ 2>/dev/null || true
cp *.md $DEPLOY_DIR/ 2>/dev/null || true
cp docker-compose.yml $DEPLOY_DIR/ 2>/dev/null || true
cp Dockerfile $DEPLOY_DIR/ 2>/dev/null || true
cp nginx.conf $DEPLOY_DIR/ 2>/dev/null || true

# Create deployment script for VPS
cat > $DEPLOY_DIR/deploy_on_vps.sh << 'EOF'
#!/bin/bash

# 🚀 DEPLOYMENT SCRIPT - EXECUTE ON VPS
# Run this script on VPS after uploading files

set -e

echo "🚀 STARTING DEPLOYMENT ON VPS"
echo "=============================="

VPS_IP=$(hostname -I | awk '{print $1}')
echo "VPS IP: $VPS_IP"

# 1. Update system
echo "📦 Updating system..."
apt update && apt upgrade -y

# 2. Install dependencies
echo "🔧 Installing dependencies..."
apt install -y curl wget git unzip python3.11 python3.11-dev python3.11-venv python3-pip nodejs npm redis-server nginx ufw

# 3. Setup Redis
echo "🔄 Configuring Redis..."
systemctl enable redis-server
systemctl start redis-server

# 4. Setup user
echo "👤 Creating system user..."
useradd -r -s /bin/bash -d /opt/trading-bot -m tradingbot || true
mkdir -p /opt/trading-bot/{logs,data,backups}

# 5. Copy files to proper location
echo "📂 Setting up project files..."
rsync -av . /opt/trading-bot/
chown -R tradingbot:tradingbot /opt/trading-bot

# 6. Setup Python environment
echo "🐍 Setting up Python environment..."
cd /opt/trading-bot
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 7. Setup database
echo "🗃️  Initializing database..."
python3 -c "
from bot.db import get_db_connection, init_database
init_database()
print('Database initialized successfully')
"

# 8. Create systemd service
echo "⚙️  Creating systemd service..."
cat > /etc/systemd/system/trading-bot-api.service << 'EOL'
[Unit]
Description=Trading Bot API
After=network.target

[Service]
Type=simple
User=tradingbot
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/venv/bin
ExecStart=/opt/trading-bot/venv/bin/python start_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# 9. Setup Nginx
echo "🌐 Configuring Nginx..."
cp nginx.conf /etc/nginx/sites-available/trading-bot
ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t

# 10. Setup firewall
echo "🛡️  Configuring firewall..."
ufw --force enable
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp

# 11. Start services
echo "🚀 Starting services..."
systemctl daemon-reload
systemctl enable trading-bot-api
systemctl start trading-bot-api
systemctl reload nginx

# 12. Test deployment
echo "✅ Testing deployment..."
sleep 5

if curl -s http://localhost:8000/health > /dev/null; then
    echo "✅ API is running!"
else
    echo "❌ API test failed"
fi

if curl -s http://localhost/ > /dev/null; then
    echo "✅ Nginx is serving content!"
else
    echo "❌ Nginx test failed"
fi

echo ""
echo "🎉 DEPLOYMENT COMPLETE!"
echo "======================="
echo "📱 Trading Bot: http://$VPS_IP"
echo "📊 API Docs: http://$VPS_IP/docs"
echo "❤️  Health Check: http://$VPS_IP/health"
echo ""
echo "🔧 Service management:"
echo "  systemctl status trading-bot-api"
echo "  systemctl restart trading-bot-api" 
echo "  systemctl logs -f trading-bot-api"
EOF

chmod +x $DEPLOY_DIR/deploy_on_vps.sh

# Create upload instructions
cat > $DEPLOY_DIR/UPLOAD_INSTRUCTIONS.md << 'EOF'
# 📤 INSTRUKCJE UPLOAD'U NA VPS

## 🔧 Krok 1: Upload plików

### Opcja A: SCP (jeśli masz hasło)
```bash
scp -r vps_deployment_package/* root@185.70.196.214:/tmp/trading-bot/
```

### Opcja B: SFTP
```bash
sftp root@185.70.196.214
put -r vps_deployment_package/* /tmp/trading-bot/
```

### Opcja C: Manual upload przez panel VPS
1. Spakuj folder: `tar -czf deployment.tar.gz vps_deployment_package/`
2. Upload przez panel VPS lub FileZilla
3. Na VPS: `tar -xzf deployment.tar.gz`

## 🚀 Krok 2: Uruchom deployment na VPS

```bash
ssh root@185.70.196.214
cd /tmp/trading-bot
chmod +x deploy_on_vps.sh
./deploy_on_vps.sh
```

## 🎯 Gotowe!
Po deployment'cie:
- Trading Bot: http://185.70.196.214
- API Docs: http://185.70.196.214/docs
- Health Check: http://185.70.196.214/health
EOF

# Create archive
echo "📦 Tworzenie archiwum..."
tar -czf vps_deployment_complete.tar.gz $DEPLOY_DIR/

echo ""
echo "✅ PAKIET DEPLOYMENT'U GOTOWY!"
echo "==============================="
echo "📁 Folder: $DEPLOY_DIR/"
echo "📦 Archiwum: vps_deployment_complete.tar.gz"
echo ""
echo "📋 NASTĘPNE KROKI:"
echo "1. Skopiuj pliki na VPS (zobacz UPLOAD_INSTRUCTIONS.md)"
echo "2. Na VPS uruchom: ./deploy_on_vps.sh"
echo "3. Profit! 🚀"

ls -la $DEPLOY_DIR/
echo ""
echo "📖 Szczegółowe instrukcje w: $DEPLOY_DIR/UPLOAD_INSTRUCTIONS.md"
