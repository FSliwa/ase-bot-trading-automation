#!/bin/bash

# Quick VPS Deployment Script - Single Command
# Execute this command in VPS console for instant deployment

# One-line deployment command for copy-paste:
cat << 'DEPLOYMENT_COMMAND'
curl -sSL https://raw.githubusercontent.com/tradingbot/vps-deploy/main/quick-deploy.sh | bash

# OR run this comprehensive one-liner:
apt update && apt upgrade -y && apt install -y curl wget git python3.11 python3.11-venv python3-pip nodejs redis-server nginx && systemctl enable redis-server nginx && systemctl start redis-server nginx && useradd -r -s /bin/bash -d /opt/trading-bot -m tradingbot && mkdir -p /opt/trading-bot/{logs,data,backups} && cd /opt/trading-bot && cat > requirements.txt << 'EOF'
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
&& cat > .env << 'EOF'
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
&& mkdir -p {bot,web,web/templates,web/static} && cat > start_app.py << 'EOF'
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn
from datetime import datetime

app = FastAPI(title="Trading Bot API", version="1.0.0")

@app.get("/")
async def root():
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html>
    <head><title>Trading Bot</title>
    <style>body{{font-family:Arial;margin:40px;background:#f5f5f5}}
    .container{{max-width:800px;margin:0 auto;background:white;padding:30px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
    h1{{color:#333;text-align:center}}.status{{padding:20px;background:#e8f5e8;border:1px solid #4caf50;border-radius:5px;margin:20px 0}}
    .info{{background:#e3f2fd;border:1px solid #2196f3;padding:15px;border-radius:5px;margin:10px 0}}</style>
    </head><body><div class="container"><h1>🤖 Trading Bot API</h1>
    <div class="status"><h3>✅ Server is running!</h3><p>Deployment successful on VPS</p></div>
    <div class="info"><h4>📊 System Info:</h4><p><strong>Server:</strong> Ubuntu 24.04 LTS</p>
    <p><strong>Status:</strong> Active</p><p><strong>Time:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p></div>
    <div class="info"><h4>🔗 API Endpoints:</h4><p><a href="/health">/health</a> - Health check</p>
    <p><a href="/docs">/docs</a> - API documentation</p></div></div></body></html>
    """)

@app.get("/health")
async def health():
    return {{"status":"healthy","timestamp":datetime.now().isoformat(),"server":"VPS Ubuntu 24.04"}}

if __name__ == "__main__":
    uvicorn.run("start_app:app", host="0.0.0.0", port=8000, reload=False)
EOF
&& sudo -u tradingbot python3.11 -m venv venv && sudo -u tradingbot bash -c 'source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt' && cat > /etc/systemd/system/trading-bot-api.service << 'EOF'
[Unit]
Description=Trading Bot API Server
After=network.target

[Service]
Type=simple
User=tradingbot
Group=tradingbot
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/venv/bin
ExecStart=/opt/trading-bot/venv/bin/python start_app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
&& cat > /etc/nginx/sites-available/trading-bot << 'EOF'
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
&& ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/ && rm -f /etc/nginx/sites-enabled/default && nginx -t && systemctl reload nginx && chown -R tradingbot:tradingbot /opt/trading-bot && systemctl daemon-reload && systemctl enable trading-bot-api && systemctl start trading-bot-api && ufw --force enable && ufw allow ssh && ufw allow 80/tcp && echo "=== DEPLOYMENT COMPLETE ===" && echo "Trading bot accessible at: http://185.70.196.55" && systemctl status trading-bot-api && curl -s http://localhost:8000/health
DEPLOYMENT_COMMAND

echo ""
echo "=== QUICK DEPLOYMENT INSTRUCTIONS ==="
echo ""
echo "1. Access VPS console at your hosting provider"
echo "2. Login as root with password: MIlik112!@4"
echo "3. Copy and paste the ONE-LINER command above"
echo "4. Wait for completion (5-10 minutes)"
echo "5. Test: http://185.70.196.55"
echo ""
echo "=== ALTERNATIVE: Step by Step ==="
echo "Use: ./manual_deployment_commands.sh for detailed steps"
echo ""
