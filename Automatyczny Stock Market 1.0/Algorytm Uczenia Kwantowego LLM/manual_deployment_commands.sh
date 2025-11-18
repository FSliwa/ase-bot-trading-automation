#!/bin/bash

# VPS Manual Deployment Instructions
# Execute these commands in VPS console (root@185.70.196.55)

echo "=== AUTOMATIC VPS DEPLOYMENT COMMANDS ==="
echo "Copy and paste these commands in VPS console:"
echo ""

echo "# 1. UPDATE SYSTEM"
echo "apt update && apt upgrade -y"
echo ""

echo "# 2. INSTALL DEPENDENCIES"
echo "apt install -y curl wget git unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release build-essential"
echo ""

echo "# 3. INSTALL PYTHON 3.11"
echo "add-apt-repository ppa:deadsnakes/ppa -y"
echo "apt update"
echo "apt install -y python3.11 python3.11-dev python3.11-venv python3-pip"
echo ""

echo "# 4. INSTALL NODE.JS"
echo "curl -fsSL https://deb.nodesource.com/setup_18.x | bash -"
echo "apt install -y nodejs"
echo ""

echo "# 5. INSTALL REDIS"
echo "apt install -y redis-server"
echo "systemctl enable redis-server"
echo "systemctl start redis-server"
echo ""

echo "# 6. INSTALL NGINX"
echo "apt install -y nginx"
echo "systemctl enable nginx"
echo "systemctl start nginx"
echo ""

echo "# 7. CREATE PROJECT USER"
echo "useradd -r -s /bin/bash -d /opt/trading-bot -m tradingbot"
echo "mkdir -p /opt/trading-bot/{logs,data,backups}"
echo "chown -R tradingbot:tradingbot /opt/trading-bot"
echo ""

echo "# 8. CREATE PROJECT FILES"
echo "cd /opt/trading-bot"
echo ""

echo "# Create requirements.txt"
cat << 'REQUIREMENTS_EOF'
cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
pydantic==2.5.0
python-multipart==0.0.6
jinja2==3.1.2
aiofiles==23.2.1
python-dotenv==1.0.0
pandas==2.1.4
numpy==1.24.3
requests==2.31.0
ccxt==4.1.64
openai==1.3.7
anthropic==0.8.1
websockets==12.0
redis==5.0.1
aioredis==2.0.1
sqlalchemy==2.0.23
cryptography==41.0.8
passlib==1.7.4
PyJWT==2.8.0
psutil==5.9.6
prometheus-client==0.19.0
EOF
REQUIREMENTS_EOF

echo ""
echo "# Create .env file"
cat << 'ENV_EOF'
cat > .env << 'EOF'
ENVIRONMENT=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./trading.db
JWT_SECRET=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)
REDIS_URL=redis://localhost:6379/0
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
BINANCE_API_KEY=
BINANCE_SECRET_KEY=
BINANCE_TESTNET=true
BYBIT_API_KEY=
BYBIT_SECRET_KEY=
BYBIT_TESTNET=true
PRIMEXBT_API_KEY=
PRIMEXBT_SECRET_KEY=
ENABLE_PROMETHEUS=true
PROMETHEUS_PORT=9090
EOF
ENV_EOF

echo ""
echo "# Create minimal app structure"
echo "mkdir -p {bot,web,web/templates,web/static}"
echo ""

echo "# Create start_app.py"
cat << 'APP_EOF'
cat > start_app.py << 'EOF'
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
from datetime import datetime

app = FastAPI(title="Trading Bot API", version="1.0.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

@app.get("/")
async def root(request: Request):
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading Bot</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
            h1 { color: #333; text-align: center; }
            .status { padding: 20px; background: #e8f5e8; border: 1px solid #4caf50; border-radius: 5px; margin: 20px 0; }
            .info { background: #e3f2fd; border: 1px solid #2196f3; padding: 15px; border-radius: 5px; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🤖 Trading Bot API</h1>
            <div class="status">
                <h3>✅ Server is running!</h3>
                <p>Deployment successful on VPS</p>
            </div>
            <div class="info">
                <h4>📊 System Info:</h4>
                <p><strong>Server:</strong> Ubuntu 24.04 LTS</p>
                <p><strong>Status:</strong> Active</p>
                <p><strong>Time:</strong> """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
            </div>
            <div class="info">
                <h4>🔗 API Endpoints:</h4>
                <p><a href="/health">/health</a> - Health check</p>
                <p><a href="/docs">/docs</a> - API documentation</p>
            </div>
        </div>
    </body>
    </html>
    """)

@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "server": "VPS Ubuntu 24.04",
        "version": "1.0.0"
    })

if __name__ == "__main__":
    uvicorn.run(
        "start_app:app",
        host="0.0.0.0",
        port=8000,
        reload=False
    )
EOF
APP_EOF

echo ""
echo "# 9. INSTALL PYTHON DEPENDENCIES"
echo "sudo -u tradingbot python3.11 -m venv venv"
echo "sudo -u tradingbot bash -c 'source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'"
echo ""

echo "# 10. CREATE SYSTEMD SERVICE"
cat << 'SERVICE_EOF'
cat > /etc/systemd/system/trading-bot-api.service << 'EOF'
[Unit]
Description=Trading Bot API Server
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=tradingbot
Group=tradingbot
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/venv/bin
ExecStart=/opt/trading-bot/venv/bin/python start_app.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
SERVICE_EOF

echo ""
echo "# 11. CONFIGURE NGINX"
cat << 'NGINX_EOF'
cat > /etc/nginx/sites-available/trading-bot << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
NGINX_EOF

echo ""
echo "ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/"
echo "rm -f /etc/nginx/sites-enabled/default"
echo "nginx -t && systemctl reload nginx"
echo ""

echo "# 12. START SERVICES"
echo "chown -R tradingbot:tradingbot /opt/trading-bot"
echo "systemctl daemon-reload"
echo "systemctl enable trading-bot-api"
echo "systemctl start trading-bot-api"
echo ""

echo "# 13. CONFIGURE FIREWALL"
echo "ufw --force enable"
echo "ufw allow ssh"
echo "ufw allow 80/tcp"
echo "ufw allow 443/tcp"
echo ""

echo "# 14. VERIFY DEPLOYMENT"
echo "systemctl status trading-bot-api"
echo "curl http://localhost:8000/"
echo "curl http://localhost:8000/health"
echo ""

echo "=== DEPLOYMENT COMPLETE ==="
echo "Your trading bot should be accessible at: http://185.70.196.55"
echo ""
