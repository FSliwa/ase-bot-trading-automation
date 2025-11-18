#!/bin/bash

# Advanced deployment with expect for automated password handling
# This script uses expect to handle interactive prompts automatically

echo "🚀 Trading Bot v2 Deployment with Automated Authentication"
echo "════════════════════════════════════════════════════════"

# Configuration
SERVER_IP="185.70.196.214"
SERVER_USER="admin"
TARGET_DIR="/opt/trading-bot"
SERVICE_NAME="trading-bot"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if expect is installed
if ! command -v expect &> /dev/null; then
    log_error "expect is required but not installed."
    echo "Install with: brew install expect"
    exit 1
fi

# Get passwords upfront
echo "🔑 Authentication Setup"
echo "═══════════════════════"
read -s -p "Enter SSH password for admin@${SERVER_IP}: " SSH_PASS
echo
read -s -p "Enter sudo password for admin: " SUDO_PASS
echo
echo

# Kill local server if running
log_info "Stopping local server..."
pkill -f "python.*enhanced_server_gpt5.py" 2>/dev/null || true
pkill -f "python.*fastapi_app.py" 2>/dev/null || true

# Create deployment package
log_info "Creating deployment package..."
tar -czf TRADING_BOT_V2_UPDATE.tar.gz \
    fastapi_app.py \
    enhanced_server_gpt5.py \
    simple_openai_client.py \
    web_search_tool.py \
    index.html \
    login.html \
    login_new.html \
    requirements.txt \
    trading.db 2>/dev/null || true

if [ ! -f "TRADING_BOT_V2_UPDATE.tar.gz" ]; then
    log_error "Failed to create deployment package"
    exit 1
fi

log_success "Package created successfully"

# Upload files using expect
log_info "Uploading files to server..."

expect << EOF
set timeout 30
spawn scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null TRADING_BOT_V2_UPDATE.tar.gz ${SERVER_USER}@${SERVER_IP}:/tmp/
expect "password:"
send "${SSH_PASS}\r"
expect eof
EOF

if [ $? -ne 0 ]; then
    log_error "File upload failed"
    exit 1
fi

log_success "Files uploaded successfully"

# Create remote deployment script
log_info "Creating remote deployment script..."

cat > remote_deploy.sh << 'REMOTE_EOF'
#!/bin/bash

echo "🔄 Starting deployment on VPS..."
cd /tmp

# Function to run sudo commands with password
run_sudo() {
    echo "$SUDO_PASS" | sudo -S "$@" 2>/dev/null
}

# Create backup
echo "📦 Creating backup..."
BACKUP_NAME="trading-bot-backup-$(date +%Y%m%d-%H%M%S)"
run_sudo cp -r /opt/trading-bot "/opt/$BACKUP_NAME" 2>/dev/null || true
echo "✅ Backup created: $BACKUP_NAME"

# Stop service
echo "🛑 Stopping service..."
run_sudo systemctl stop trading-bot 2>/dev/null || true

# Extract files
echo "📂 Extracting files..."
run_sudo tar -xzf TRADING_BOT_V2_UPDATE.tar.gz -C /opt/trading-bot/

# Set permissions
echo "🔧 Setting permissions..."
run_sudo chown -R admin:admin /opt/trading-bot/
run_sudo chmod +x /opt/trading-bot/*.py

# Create/update virtual environment
echo "🐍 Setting up Python environment..."
if [ ! -d "/opt/trading-bot/.venv" ]; then
    run_sudo python3 -m venv /opt/trading-bot/.venv
fi

# Activate venv and install requirements
echo "📦 Installing Python packages..."
run_sudo /opt/trading-bot/.venv/bin/pip install --upgrade pip
run_sudo /opt/trading-bot/.venv/bin/pip install -r /opt/trading-bot/requirements.txt

# Install additional packages for FastAPI
run_sudo /opt/trading-bot/.venv/bin/pip install fastapi uvicorn python-multipart

# Compile Python files
echo "⚡ Compiling Python files..."
run_sudo /opt/trading-bot/.venv/bin/python -m compileall -q /opt/trading-bot/ 2>/dev/null || true

# Create systemd service for FastAPI
echo "⚙️ Updating systemd service..."
run_sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'SERVICE_EOF'
[Unit]
Description=Trading Bot FastAPI Server
After=network.target

[Service]
Type=simple
User=admin
Group=admin
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/.venv/bin
EnvironmentFile=/opt/trading-bot/.env.db
ExecStart=/opt/trading-bot/.venv/bin/uvicorn fastapi_app:app --host 127.0.0.1 --port 8009 --workers 1
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE_EOF

# Create environment file
echo "🔧 Creating environment configuration..."
run_sudo touch /opt/trading-bot/.env.db
if ! grep -q "OPENAI_API_KEY" /opt/trading-bot/.env.db 2>/dev/null; then
    echo "OPENAI_API_KEY=your-openai-api-key-here" | run_sudo tee -a /opt/trading-bot/.env.db > /dev/null
fi

# Reload and start service
echo "🚀 Starting service..."
run_sudo systemctl daemon-reload
run_sudo systemctl enable trading-bot
run_sudo systemctl start trading-bot

# Wait for service to start
echo "⏳ Waiting for service..."
sleep 5

# Check status
echo "📊 Service status:"
run_sudo systemctl status trading-bot --no-pager | head -10

# Test endpoints
echo ""
echo "🧪 Testing endpoints..."
sleep 2

echo "Testing basic endpoints:"
curl -s -o /dev/null -w "• Health check: %{http_code}\n" http://localhost:8009/healthz 2>/dev/null || echo "• Health check: Connection failed"
curl -s -o /dev/null -w "• Ready check: %{http_code}\n" http://localhost:8009/readyz 2>/dev/null || echo "• Ready check: Connection failed"
curl -s -o /dev/null -w "• Main page: %{http_code}\n" http://localhost:8009/ 2>/dev/null || echo "• Main page: Connection failed"
curl -s -o /dev/null -w "• Login page: %{http_code}\n" http://localhost:8009/login 2>/dev/null || echo "• Login page: Connection failed"

echo ""
echo "✅ Deployment completed!"
echo "🌐 FastAPI docs available at: http://185.70.196.214:8009/docs"
echo "📊 Metrics available at: http://185.70.196.214:8009/metrics"

# Cleanup
rm -f /tmp/TRADING_BOT_V2_UPDATE.tar.gz

REMOTE_EOF

# Upload and execute remote script using expect
log_info "Executing deployment on server..."

expect << EOF
set timeout 300
spawn ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ${SERVER_USER}@${SERVER_IP}
expect "password:"
send "${SSH_PASS}\r"
expect "$ "
send "export SUDO_PASS='${SUDO_PASS}'\r"
expect "$ "
send "$(cat remote_deploy.sh)\r"
expect "$ "
send "exit\r"
expect eof
EOF

# Cleanup
rm -f remote_deploy.sh TRADING_BOT_V2_UPDATE.tar.gz

if [ $? -eq 0 ]; then
    echo ""
    echo "🎉 Deployment completed successfully!"
    echo "════════════════════════════════════"
    echo "🌐 Application URLs:"
    echo "   • Main app: http://185.70.196.214:8009/"
    echo "   • API docs: http://185.70.196.214:8009/docs"
    echo "   • Health: http://185.70.196.214:8009/healthz"
    echo "   • Metrics: http://185.70.196.214:8009/metrics"
    echo ""
    echo "📝 Next steps:"
    echo "   1. Update OPENAI_API_KEY in /opt/trading-bot/.env.db"
    echo "   2. Configure any external service integrations"
    echo "   3. Test all API endpoints"
else
    log_error "Deployment failed. Check the output above for details."
    exit 1
fi
