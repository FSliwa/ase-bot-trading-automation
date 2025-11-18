# 🚀 MANUAL DEPLOYMENT INSTRUCTIONS
# VPS: 185.70.196.214
# Login: admin
# Password: MIlik112!@3

## 📋 KROKI DEPLOYMENT'U:

### 1. 🔐 Połącz się z VPS:
```bash
ssh admin@185.70.196.214
# Wpisz hasło: MIlik112!@3
```

### 2. 📦 Skopiuj i wklej te komendy na VPS:

```bash
# === DEPLOYMENT TRADING BOT - COPY ALL ===

# 1. Update system
apt update && apt upgrade -y

# 2. Install dependencies
sudo apt install -y curl wget git unzip python3.11 python3.11-venv python3-pip nodejs npm redis-server nginx ufw

# 3. Setup services
sudo systemctl enable redis-server nginx
sudo systemctl start redis-server nginx

# 4. Create project
sudo mkdir -p /opt/trading-bot && cd /opt/trading-bot

# 5. Python environment
python3.11 -m venv venv
source venv/bin/activate

# 6. Create requirements
cat > requirements.txt << 'EOF'
fastapi==0.104.1
uvicorn[standard]==0.24.0
websockets==12.0
python-multipart==0.0.6
jinja2==3.1.2
aiofiles==23.2.1
python-dotenv==1.0.0
requests==2.31.0
EOF

pip install -r requirements.txt

# 7. Create application
cat > app.py << 'EOF'
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import time
import random

app = FastAPI(title="Trading Bot API", version="1.0.0")

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <html>
    <head><title>🚀 Trading Bot</title></head>
    <body style="font-family: Arial; margin: 40px; background: #f5f5f5;">
        <div style="background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h1 style="color: #2c3e50;">🚀 Trading Bot API - LIVE!</h1>
            <p><strong>Status:</strong> <span style="color: green;">✅ Running</span></p>
            <p><strong>Demo Balance:</strong> <span style="color: #27ae60; font-size: 1.2em;">$28,570.42</span></p>
            <p><strong>VPS:</strong> 185.70.196.214</p>
            <div style="margin-top: 20px;">
                <a href="/docs" style="background: #3498db; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; margin-right: 10px;">📊 API Documentation</a>
                <a href="/health" style="background: #27ae60; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; margin-right: 10px;">❤️ Health Check</a>
                <a href="/balance" style="background: #f39c12; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px;">💰 View Balance</a>
            </div>
        </div>
    </body>
    </html>
    """

@app.get("/health")
async def health():
    return {
        "status": "healthy", 
        "timestamp": time.time(),
        "demo_balance": round(random.uniform(28000, 29000), 2),
        "connected_exchanges": ["binance_demo", "bybit_demo"],
        "vps_ip": "185.70.196.214"
    }

@app.get("/balance")
async def get_balance():
    return {
        "total_usd": round(random.uniform(28000, 29000), 2),
        "assets": [
            {"symbol": "USDT", "amount": 10000, "value_usd": 10000},
            {"symbol": "BTC", "amount": 0.3, "value_usd": 13500},
            {"symbol": "ETH", "amount": 2.1, "value_usd": 5070}
        ],
        "last_updated": time.time(),
        "account_type": "demo"
    }
EOF

# 8. Create startup script
cat > start_app.py << 'EOF'
import uvicorn
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
EOF

# 9. Create systemd service
sudo cat > /etc/systemd/system/trading-bot.service << 'EOF'
[Unit]
Description=Trading Bot API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/venv/bin
ExecStart=/opt/trading-bot/venv/bin/python start_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 10. Configure Nginx
sudo cat > /etc/nginx/sites-available/trading-bot << 'EOF'
server {
    listen 80;
    server_name _;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t

# 11. Setup firewall
sudo ufw --force enable
sudo ufw allow ssh
sudo ufw allow 80/tcp

# 12. Start everything
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl reload nginx

# 13. Test
echo ""
echo "🎉 TESTING DEPLOYMENT..."
sleep 5

SERVER_IP=$(hostname -I | awk '{print $1}')
echo "Server IP: $SERVER_IP"

curl -s http://localhost:8000/health
echo ""
echo "🎉🎉🎉 DEPLOYMENT COMPLETE! 🎉🎉🎉"
echo "🌐 Trading Bot: http://$SERVER_IP"
echo "📊 API Docs: http://$SERVER_IP/docs"  
echo "❤️ Health Check: http://$SERVER_IP/health"
echo "💰 Balance: http://$SERVER_IP/balance"

# === END DEPLOYMENT ===
```

### 3. 🎯 Po deployment'cie:
- **Trading Bot:** http://185.70.196.214
- **API Docs:** http://185.70.196.214/docs
- **Health Check:** http://185.70.196.214/health
- **Balance:** http://185.70.196.214/balance

### 4. 🔧 Zarządzanie:
```bash
sudo systemctl status trading-bot    # Check status
sudo systemctl restart trading-bot   # Restart service  
sudo journalctl -u trading-bot -f   # View logs
```

## ✅ GOTOWE DO DEPLOYMENT!

**Credentials:**
- IP: 185.70.196.214
- Login: admin  
- Password: MIlik112!@3
