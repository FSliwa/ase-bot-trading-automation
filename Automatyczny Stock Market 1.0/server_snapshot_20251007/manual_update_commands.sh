#!/bin/bash

# 📋 MANUAL UPDATE COMMANDS FOR VPS (run as admin)

set -e

echo "🔄 Starting manual update on VPS..."

# Backup current version
cd /opt
sudo cp -r trading-bot trading-bot-backup-$(date +%Y%m%d-%H%M%S)

# Stop current service
sudo systemctl stop trading-bot || true

# Extract new files
cd /opt/trading-bot
sudo tar -xzf /tmp/TRADING_BOT_V2_UPDATE.tar.gz

# Prerequisites for venv
sudo apt-get update -y && sudo apt-get install -y python3-venv python3-pip

# Python venv (isolated)
sudo /usr/bin/python3 -m venv /opt/trading-bot/.venv
sudo /opt/trading-bot/.venv/bin/pip install --upgrade pip
sudo /opt/trading-bot/.venv/bin/pip install -r requirements.txt

# Resolve Python binary for compilation
PYTHON_BIN="/opt/trading-bot/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)"; else PYTHON_BIN="$(command -v python)"; fi
fi

# Quick syntax check (compile)
sudo "$PYTHON_BIN" -m compileall -q /opt/trading-bot || true

# Update permissions
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x enhanced_server_gpt5.py
sudo chmod +x test_deployment.sh

# Update Nginx configuration
sudo cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Ensure env file exists and permissions
if [ ! -f /opt/trading-bot/.env.db ]; then
  echo 'OPENAI_API_KEY=PUT_YOUR_KEY_HERE' | sudo tee /opt/trading-bot/.env.db >/dev/null
  echo '# ALLOW_PUBLIC_GPT_ENDPOINTS=true' | sudo tee -a /opt/trading-bot/.env.db >/dev/null
  echo '>> Edit /opt/trading-bot/.env.db and set your real OPENAI_API_KEY, then restart: sudo systemctl restart trading-bot'
fi
sudo chown root:root /opt/trading-bot/.env.db
sudo chmod 600 /opt/trading-bot/.env.db

# Initialize/Update user database
sudo "$PYTHON_BIN" user_database.py || true

# Update systemd service
sudo bash -c 'cat > /etc/systemd/system/trading-bot.service << "SYSTEMD_EOF"'
[Unit]
Description=Trading Bot FastAPI Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trading-bot
ExecStart=/usr/bin/python3 -m uvicorn fastapi_app:app --host 0.0.0.0 --port 8009
Restart=always
RestartSec=3
EnvironmentFile=/opt/trading-bot/.env.db
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

# Reload and start service
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

# Check status
sleep 3
sudo systemctl status trading-bot --no-pager

# Quick health checks
curl -s -o /dev/null -w "Healthz: %{http_code}\n" http://localhost:8009/healthz
curl -s -o /dev/null -w "Readyz: %{http_code}\n" http://localhost:8009/readyz

echo "✅ Manual update completed!"
echo "🌐 Test at: http://185.70.196.214/login"
