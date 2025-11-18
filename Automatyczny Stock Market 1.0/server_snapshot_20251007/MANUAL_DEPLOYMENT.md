# Manual VPS Deployment Commands

If SSH key setup doesn't work, you can deploy manually through VPS console.

## Step 1: Connect to VPS Console
- Access your VPS provider's web console
- Login as root with password: MIlik112!@4

## Step 2: Update System and Install Dependencies
```bash
# Update system
apt update && apt upgrade -y

# Install essential packages
apt install -y curl wget git unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release build-essential

# Install Python 3.11
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.11 python3.11-dev python3.11-venv python3-pip

# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
apt install -y nodejs

# Install Redis
apt install -y redis-server
systemctl enable redis-server
systemctl start redis-server

# Install Nginx
apt install -y nginx
systemctl enable nginx
systemctl start nginx
```

## Step 3: Create Project Structure
```bash
# Create service user
useradd -r -s /bin/bash -d /opt/trading-bot -m tradingbot

# Create project directories
mkdir -p /opt/trading-bot/{logs,data,backups}
chown -R tradingbot:tradingbot /opt/trading-bot
```

## Step 4: Upload Project Files (Option A - Git)
```bash
# If you have a git repository
cd /opt/trading-bot
git clone <your-repository-url> .
chown -R tradingbot:tradingbot /opt/trading-bot
```

## Step 4: Upload Project Files (Option B - Manual)
Create each file manually by copying content from your local files:

### Create main files:
```bash
cd /opt/trading-bot

# Create start_app.py
cat > start_app.py << 'EOF'
import asyncio
import uvicorn
from web.app import app

if __name__ == "__main__":
    uvicorn.run(
        "web.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        workers=1
    )
EOF

# Create requirements.txt
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

# Create .env file
cat > .env << 'EOF'
ENVIRONMENT=production
DEBUG=false
API_HOST=0.0.0.0
API_PORT=8000
LOG_LEVEL=INFO
DATABASE_URL=sqlite:///./trading.db
JWT_SECRET=CHANGE_THIS_TO_SECURE_SECRET
SECRET_KEY=CHANGE_THIS_TO_SECURE_SECRET
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
```

## Step 5: Install Python Dependencies
```bash
cd /opt/trading-bot
sudo -u tradingbot python3.11 -m venv venv
sudo -u tradingbot bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
```

## Step 6: Create Systemd Services
```bash
# Create API service
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

# Reload and start services
systemctl daemon-reload
systemctl enable trading-bot-api
systemctl start trading-bot-api
```

## Step 7: Configure Nginx (Optional)
```bash
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

ln -s /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

## Step 8: Configure Firewall
```bash
ufw --force enable
ufw allow ssh
ufw allow 80/tcp
ufw allow 443/tcp
```

## Step 9: Test Deployment
```bash
# Check service status
systemctl status trading-bot-api

# Test API
curl http://localhost:8000/
curl http://localhost:8000/health

# Check logs
journalctl -u trading-bot-api -f
```

## Step 10: Generate Secure Secrets
```bash
cd /opt/trading-bot
JWT_SECRET=$(openssl rand -hex 32)
SECRET_KEY=$(openssl rand -hex 32)
sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" .env
sed -i "s/SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
systemctl restart trading-bot-api
```

## Final Test
After completing all steps, test the API:
- http://185.70.196.55:8000
- http://185.70.196.55:8000/health

Your trading bot should now be running on the VPS!
