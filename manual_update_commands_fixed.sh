#!/bin/bash

# 📋 MANUAL UPDATE COMMANDS FOR VPS (run as admin) - FIXED VERSION

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

# Install PostgreSQL development headers and other dependencies
echo "📦 Installing PostgreSQL development headers..."
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip libpq-dev postgresql-server-dev-all build-essential

# Python venv (isolated)
echo "🐍 Preparing Python venv..."
sudo /usr/bin/python3 -m venv /opt/trading-bot/.venv || true
sudo /opt/trading-bot/.venv/bin/pip install --upgrade pip || true

# Install requirements in venv (with PostgreSQL support)
echo "📦 Installing Python packages in venv..."
sudo /opt/trading-bot/.venv/bin/pip install -r requirements.txt || true

# Also install requirements for system Python used by systemd
echo "📦 Installing Python packages system-wide..."
sudo python3 -m pip install --upgrade pip || true
sudo python3 -m pip install --break-system-packages -r requirements.txt || true

# Ensure psycopg2 is available for DB (force binary version if source fails)
echo "🐘 Installing PostgreSQL Python adapter..."
sudo python3 -m pip install --break-system-packages psycopg2-binary || true
sudo /opt/trading-bot/.venv/bin/pip install psycopg2-binary || true

# Resolve Python binary for compilation
PYTHON_BIN="/opt/trading-bot/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  if command -v python3 >/dev/null 2>&1; then PYTHON_BIN="$(command -v python3)"; else PYTHON_BIN="$(command -v python)"; fi
fi

# Quick syntax check (compile)
echo "🧩 Compiling Python code..."
sudo "$PYTHON_BIN" -m compileall -q /opt/trading-bot || true

# Create necessary directories
echo "📁 Creating directories..."
sudo mkdir -p /opt/trading-bot/logs /opt/trading-bot/backups

# Set permissions
echo "🔐 Setting permissions..."
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x enhanced_server_gpt5.py || true
sudo chmod +x test_deployment.sh || true
sudo chmod +x setup_postgresql.sh || true
sudo chmod +x backup.sh || true

# Setup PostgreSQL database (if setup script exists)
if [ -f "./setup_postgresql.sh" ]; then
  echo "🐘 Setting up PostgreSQL database..."
  ./setup_postgresql.sh || echo "PostgreSQL setup failed, continuing with JSON fallback..."
fi

# Update Nginx configuration
echo "🌐 Updating Nginx configuration..."
sudo cp nginx_8009.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Ensure env file exists with updated template
if [ ! -f /opt/trading-bot/.env.db ]; then
  echo "⚙️ Creating environment configuration..."
  cat << 'ENV_EOF' | sudo tee /opt/trading-bot/.env.db >/dev/null
GEMINI_API_KEY=PUT_YOUR_KEY_HERE

# PostgreSQL configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trading_bot
POSTGRES_USER=trading_bot_user
POSTGRES_PASSWORD=generated_password_here

# JWT/OAuth config
JWT_SECRET=CHANGE_ME_LONG_RANDOM
JWT_ISSUER=trading-bot
JWT_EXPIRE_MIN=120

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# GitHub OAuth
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
ENV_EOF
  echo '>> Edit /opt/trading-bot/.env.db and fill in real secrets, then restart: sudo systemctl restart trading-bot'
else
  echo "⚙️ Updating environment configuration..."
  # Ensure all required environment variables exist
  for key in GEMINI_API_KEY POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD JWT_SECRET JWT_ISSUER JWT_EXPIRE_MIN GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET; do
    if ! grep -q "^$key=" /opt/trading-bot/.env.db; then
      echo "$key=" | sudo tee -a /opt/trading-bot/.env.db >/dev/null
    fi
  done
fi

sudo chown root:root /opt/trading-bot/.env.db
sudo chmod 600 /opt/trading-bot/.env.db

# Initialize/Update user database
echo "🗄️ Initializing user database..."
sudo "$PYTHON_BIN" user_database.py || true

# Update systemd service - use venv python
echo "🚀 Updating systemd service..."
sudo /bin/bash -c 'cat > /etc/systemd/system/trading-bot.service << "EOF"'
[Unit]
Description=Trading Bot FastAPI Server
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trading-bot
ExecStart=/opt/trading-bot/.venv/bin/python -m uvicorn fastapi_app:app --host 0.0.0.0 --port 8009
Restart=always
RestartSec=3
EnvironmentFile=/opt/trading-bot/.env.db
Environment=PYTHONUNBUFFERED=1
StandardOutput=append:/opt/trading-bot/logs/app.out.log
StandardError=append:/opt/trading-bot/logs/app.err.log

[Install]
WantedBy=multi-user.target
EOF

# Setup backup service and timer
echo "📦 Setting up backup automation..."
sudo /bin/bash -c 'cat > /etc/systemd/system/trading-bot-backup.service << "EOF"'
[Unit]
Description=Trading Bot backup
After=network.target

[Service]
Type=oneshot
User=root
ExecStart=/bin/bash /opt/trading-bot/backup.sh

[Install]
WantedBy=multi-user.target
EOF

sudo /bin/bash -c 'cat > /etc/systemd/system/trading-bot-backup.timer << "EOF"'
[Unit]
Description=Run Trading Bot backup daily

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
EOF

# Enable backup timer
sudo systemctl daemon-reload
sudo systemctl enable --now trading-bot-backup.timer

# Reload and start main service
echo "🚀 Starting updated service..."
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot

# Wait and check status
echo "⏳ Waiting for service to start..."
sleep 5

echo "📊 Service status:"
sudo systemctl status trading-bot --no-pager || true

# Quick health checks
echo ""
echo "🧪 Testing endpoints..."
sleep 2

curl -s -o /dev/null -w "Login page: %{http_code}\n" http://localhost:8009/login || echo "Login test failed"
curl -s -o /dev/null -w "Register page: %{http_code}\n" http://localhost:8009/register || echo "Register test failed"
curl -s -o /dev/null -w "Healthz: %{http_code}\n" http://localhost:8009/healthz || echo "Health test failed"
curl -s -o /dev/null -w "Readyz: %{http_code}\n" http://localhost:8009/readyz || echo "Ready test failed"
curl -s -o /dev/null -w "Metrics: %{http_code}\n" http://localhost:8009/metrics || echo "Metrics test failed"

echo ""
echo "✅ Manual update completed!"
echo "🌐 Test at: http://185.70.196.214/login"
echo "📊 Monitor logs: sudo journalctl -u trading-bot -f"
echo "📦 Check backup timer: sudo systemctl status trading-bot-backup.timer"
echo ""
echo "⚠️  IMPORTANT: Edit /opt/trading-bot/.env.db to set real API keys and database credentials!"
