#!/bin/bash
# filepath: /Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM/fix_auth_and_deploy.sh

set -e

echo "🔧 KOMPLETNA NAPRAWA SYSTEMU AUTORYZACJI I DEPLOYMENT"
echo "===================================================="

# Configuration
VPS_IP="185.70.196.214"
VPS_USER="admin"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PACKAGE_NAME="auth_fix_${TIMESTAMP}.tar.gz"

cd "$LOCAL_DIR"

# 1. Install bcrypt locally if needed
echo "📦 1. Sprawdzanie zależności..."
pip3 install bcrypt PyJWT --quiet

# 2. Update requirements.txt
echo "📝 2. Aktualizacja requirements.txt..."
cat > requirements_auth.txt << 'EOF'
# Core FastAPI
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
python-multipart>=0.0.9

# Authentication
bcrypt>=4.1.2
PyJWT>=2.8.0
python-jose[cryptography]>=3.3.0
passlib[bcrypt]>=1.7.4

# Database
psycopg2-binary>=2.9.9
sqlalchemy>=2.0.23

# AI Integration
google-generativeai>=0.5.4
openai>=1.12.0

# Market Data
ccxt>=4.2.25
pandas>=2.1.4
numpy>=1.24.3
yfinance>=0.2.33

# Web & API
httpx>=0.25.2
websockets>=12.0
redis>=5.0.1
prometheus-client>=0.19.0

# Utils
python-dotenv>=1.0.0
structlog>=23.2.0
tenacity>=8.2.3
cryptography>=41.0.7
EOF

# 3. Create package
echo "📦 3. Tworzenie pakietu deployment..."
tar -czf "$PACKAGE_NAME" \
    fastapi_app.py \
    login.html \
    register.html \
    requirements_auth.txt \
    user_database.py 2>/dev/null || true

# 4. Upload to server
echo "📤 4. Wysyłanie na serwer..."
scp -q "$PACKAGE_NAME" "${VPS_USER}@${VPS_IP}:/tmp/"

# 5. Create deployment script
cat > deploy_auth_fix.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 INSTALACJA POPRAWEK AUTORYZACJI"
echo "=================================="

cd /opt/trading-bot

# Backup
echo "📦 Backup..."
sudo cp -r /opt/trading-bot /opt/trading-bot-backup-auth-$(date +%Y%m%d-%H%M%S) 2>/dev/null || true

# Extract
echo "📂 Rozpakowywanie..."
sudo tar -xzf /tmp/auth_fix_*.tar.gz -C /opt/trading-bot

# Install Python dependencies
echo "🐍 Instalacja zależności Python..."
sudo /opt/trading-bot/.venv/bin/pip install -r /opt/trading-bot/requirements_auth.txt

# Set permissions
echo "🔐 Ustawienie uprawnień..."
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod 600 /opt/trading-bot/.env.db 2>/dev/null || true
sudo chmod 755 /opt/trading-bot/*.html

# Create empty users.json if doesn't exist
if [ ! -f /opt/trading-bot/users.json ]; then
    echo "{}" | sudo tee /opt/trading-bot/users.json > /dev/null
    sudo chown www-data:www-data /opt/trading-bot/users.json
    sudo chmod 600 /opt/trading-bot/users.json
fi

# Restart service
echo "🔄 Restart usługi..."
sudo systemctl restart trading-bot

# Wait for service to start
sleep 3

# Test endpoints
echo "🧪 Testowanie endpointów..."
echo ""
echo "Test rejestracji:"
curl -s http://localhost:8009/api/register -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser_'$(date +%s)'","email":"test'$(date +%s)'@example.com","password":"TestPass123"}' \
  -w "\nHTTP Status: %{http_code}\n" | head -5

echo ""
echo "Test logowania:"
curl -s http://localhost:8009/api/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' \
  -w "\nHTTP Status: %{http_code}\n" | head -5

echo ""
echo "✅ Deployment zakończony!"
echo ""
echo "📋 Status usługi:"
sudo systemctl status trading-bot --no-pager | head -15
EOF

# 6. Upload deployment script
scp -q deploy_auth_fix.sh "${VPS_USER}@${VPS_IP}:/tmp/"

# 7. Execute on server with password prompt
echo ""
echo "🔐 WYMAGANE: Wprowadź hasło sudo na serwerze"
echo "============================================"
echo ""
ssh -tt "${VPS_USER}@${VPS_IP}" "chmod +x /tmp/deploy_auth_fix.sh && /tmp/deploy_auth_fix.sh"

# 8. Cleanup
rm -f "$PACKAGE_NAME" deploy_auth_fix.sh

echo ""
echo "✅ ZAKOŃCZONO!"
echo ""
echo "🌐 Testuj aplikację:"
echo "   - Rejestracja: http://${VPS_IP}/register.html"
echo "   - Logowanie: http://${VPS_IP}/login.html"
echo "   - Dashboard: http://${VPS_IP}/"
