#!/bin/bash

# 🚀 Automatyczny Trading Bot - Kompletny Deployment Package
# Ten skrypt tworzy gotowy pakiet do przesłania na serwer

echo "🔄 Tworzenie pakietu deployment..."

# Tworzymy folder deployment
mkdir -p deployment_package

# Kopiujemy wszystkie potrzebne pliki
echo "📦 Kopiowanie plików aplikacji..."

# Kopiujemy główne pliki
cp start_app.py deployment_package/
cp requirements.txt deployment_package/
cp trading.db deployment_package/ 2>/dev/null || echo "⚠️  Baza danych nie znaleziona - zostanie utworzona"

# Kopiujemy folder bot
cp -r bot deployment_package/

# Kopiujemy folder web  
cp -r web deployment_package/

# Tworzymy plik env.example
cat > deployment_package/.env.example << 'EOF'
# API Keys dla exchanges (opcjonalne - aplikacja działa w trybie demo)
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_SECRET_KEY=your_binance_secret_here
BINANCE_TESTNET=true

BYBIT_API_KEY=your_bybit_api_key_here  
BYBIT_SECRET_KEY=your_bybit_secret_here
BYBIT_TESTNET=true

PRIMEXBT_API_KEY=your_primexbt_api_key_here
PRIMEXBT_SECRET_KEY=your_primexbt_secret_here

# AI API Keys (opcjonalne)
OPENAI_API_KEY=your_openai_api_key_here
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Database
DATABASE_URL=sqlite:///./trading.db
EOF

# Tworzymy skrypt deployment dla serwera
cat > deployment_package/deploy_server.sh << 'EOF'
#!/bin/bash

# 🚀 Automatyczny Trading Bot - Server Deployment
# Uruchom ten skrypt na serwerze Ubuntu/Debian

set -e

echo "🚀 Rozpoczynam deployment Trading Bot na serwerze..."

# Update system
echo "📦 Aktualizacja systemu..."
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
echo "🐍 Instalacja Python 3.11..."
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Install other dependencies
echo "🔧 Instalacja zależności systemu..."
sudo apt install -y nginx redis-server supervisor git curl

# Create application directory
APP_DIR="/opt/trading-bot"
echo "📁 Tworzenie katalogu aplikacji: $APP_DIR"
sudo mkdir -p $APP_DIR
sudo cp -r * $APP_DIR/
sudo chown -R $USER:$USER $APP_DIR
cd $APP_DIR

# Create virtual environment
echo "🌐 Tworzenie środowiska wirtualnego..."
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
echo "📦 Instalacja pakietów Python..."
pip install --upgrade pip
pip install -r requirements.txt

# Create .env file if not exists
if [ ! -f .env ]; then
    echo "⚙️  Tworzenie pliku .env..."
    cp .env.example .env
fi

# Initialize database
echo "💾 Inicjalizacja bazy danych..."
python init_database.py

# Create systemd service
echo "🔧 Konfiguracja usługi systemd..."
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'EOL'
[Unit]
Description=Trading Bot FastAPI Application
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=/opt/trading-bot
Environment=PATH=/opt/trading-bot/venv/bin
ExecStart=/opt/trading-bot/venv/bin/python start_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOL

# Configure Nginx
echo "🌐 Konfiguracja Nginx..."
sudo tee /etc/nginx/sites-available/trading-bot > /dev/null << 'EOL'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8008;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOL

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

# Configure firewall
echo "🔥 Konfiguracja firewall..."
sudo ufw allow 22
sudo ufw allow 80
sudo ufw allow 443
sudo ufw --force enable

# Start services
echo "🚀 Uruchamianie usług..."
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl start trading-bot
sudo systemctl enable nginx
sudo systemctl enable redis-server

# Check status
echo "✅ Sprawdzanie statusu usług..."
sudo systemctl status trading-bot --no-pager
sudo systemctl status nginx --no-pager

# Get server IP
SERVER_IP=$(curl -s ifconfig.me || hostname -I | awk '{print $1}')

echo ""
echo "🎉 DEPLOYMENT ZAKOŃCZONY POMYŚLNIE!"
echo ""
echo "📊 Trading Bot Dashboard: http://$SERVER_IP"
echo "📚 API Documentation: http://$SERVER_IP/docs"
echo "❤️  Health Check: http://$SERVER_IP/health"
echo ""
echo "🔧 Zarządzanie:"
echo "   sudo systemctl status trading-bot    # Check status"
echo "   sudo systemctl restart trading-bot   # Restart"
echo "   sudo journalctl -u trading-bot -f   # View logs"
echo ""
EOF

chmod +x deployment_package/deploy_server.sh

# Tworzymy skrypt inicjalizacji bazy danych
cat > deployment_package/init_database.py << 'EOF'
#!/usr/bin/env python3
"""
Initialize trading bot database with demo data.
"""

import sqlite3
import json
from datetime import datetime
import os

def init_database():
    """Initialize the trading database."""
    db_path = "trading.db"
    
    print(f"🗄️  Inicjalizacja bazy danych: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    print("📋 Tworzenie tabel...")
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            settings TEXT DEFAULT '{}'
        )
    ''')
    
    # Exchange credentials table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS exchange_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exchange TEXT NOT NULL,
            api_key TEXT,
            api_secret TEXT,
            testnet BOOLEAN DEFAULT 1,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Trading history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trading_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exchange TEXT,
            symbol TEXT,
            side TEXT,
            amount REAL,
            price REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Balance history table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            exchange TEXT,
            total_balance_usd REAL,
            data TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # AI analysis table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            analysis TEXT,
            confidence REAL,
            recommendation TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Insert demo user if not exists
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'demo'")
    if cursor.fetchone()[0] == 0:
        print("👤 Tworzenie demo user...")
        cursor.execute('''
            INSERT INTO users (username, email, settings) 
            VALUES ('demo', 'demo@tradingbot.com', '{"theme": "dark", "notifications": true}')
        ''')
        
        user_id = cursor.lastrowid
        
        # Add demo exchange credentials
        demo_exchanges = [
            ("binance", "demo_binance_key", "demo_binance_secret"),
            ("bybit", "demo_bybit_key", "demo_bybit_secret"),
            ("primexbt", "demo_primexbt_key", "demo_primexbt_secret")
        ]
        
        for exchange, api_key, api_secret in demo_exchanges:
            cursor.execute('''
                INSERT INTO exchange_credentials (user_id, exchange, api_key, api_secret, testnet, active)
                VALUES (?, ?, ?, ?, 1, 1)
            ''', (user_id, exchange, api_key, api_secret))
    
    conn.commit()
    conn.close()
    
    print("✅ Baza danych zainicjalizowana pomyślnie!")

if __name__ == "__main__":
    init_database()
EOF

chmod +x deployment_package/init_database.py

# Tworzymy instrukcje deployment'u
cat > deployment_package/DEPLOYMENT_INSTRUCTIONS.md << 'EOF'
# 🚀 Trading Bot - Instrukcje Deployment

## Opcja 1: Automatyczny Deployment

1. **Prześlij cały folder `deployment_package` na serwer:**
   ```bash
   scp -r deployment_package admin@185.70.196.214:/home/admin/
   ```

2. **Połącz się z serwerem i uruchom deployment:**
   ```bash
   ssh admin@185.70.196.214
   cd deployment_package
   chmod +x deploy_server.sh
   sudo ./deploy_server.sh
   ```

## Opcja 2: Manualny Deployment

1. **Połącz się z serwerem:**
   ```bash
   ssh admin@185.70.196.214
   ```

2. **Skopiuj i wykonaj komendy z `MANUAL_VPS_DEPLOYMENT.md`**

## Po Deployment

Trading Bot będzie dostępny pod adresami:
- 🌐 **Dashboard:** http://185.70.196.214
- 📚 **API Docs:** http://185.70.196.214/docs  
- ❤️ **Health Check:** http://185.70.196.214/health

## Zarządzanie

```bash
# Status usługi
sudo systemctl status trading-bot

# Restart
sudo systemctl restart trading-bot

# Logi
sudo journalctl -u trading-bot -f

# Status Nginx
sudo systemctl status nginx
```

## Demo Features

Aplikacja zawiera demo dane:
- Demo balance: ~$28,570
-支持 Binance, Bybit, PrimeXBT (testnet)
- Real-time price feeds
- AI analysis (mock data)
EOF

# Tworzymy archiwum
echo "📦 Tworzenie archiwum deployment..."
tar -czf trading-bot-deployment.tar.gz deployment_package/

echo ""
echo "🎉 PAKIET DEPLOYMENT GOTOWY!"
echo ""
echo "📁 Utworzono:"
echo "   - deployment_package/ (folder z plikami)"
echo "   - trading-bot-deployment.tar.gz (archiwum)"
echo ""
echo "🚀 Następne kroki:"
echo "   1. Prześlij pakiet na serwer: scp -r deployment_package admin@185.70.196.214:/home/admin/"
echo "   2. Uruchom deployment: ssh admin@185.70.196.214 'cd deployment_package && sudo ./deploy_server.sh'"
echo ""
echo "🌐 Po deployment aplikacja będzie dostępna: http://185.70.196.214"
echo ""
