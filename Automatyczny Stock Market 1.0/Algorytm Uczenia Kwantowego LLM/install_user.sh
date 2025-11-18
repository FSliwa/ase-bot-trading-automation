#!/bin/bash

# 🚀 Trading Bot - User Installation (bez sudo)
# Install Python packages for admin user without root privileges

echo "🚀 Installing Trading Bot Frameworks for User"
echo "=============================================="

# Check Python version
echo "🐍 Python version:"
python3 --version

# Try to install pip for user
echo "📦 Installing pip for user..."
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py --user
export PATH=$PATH:~/.local/bin

# Upgrade pip
echo "⬆️ Upgrading pip..."
python3 -m pip install --user --upgrade pip setuptools wheel

# Install core frameworks
echo "📦 Installing core frameworks..."
python3 -m pip install --user fastapi==0.111.0
python3 -m pip install --user uvicorn[standard]==0.30.0
python3 -m pip install --user jinja2==3.1.4
python3 -m pip install --user python-multipart==0.0.9
python3 -m pip install --user pydantic==2.8.0

# Install database & ORM
echo "💾 Installing database frameworks..."
python3 -m pip install --user sqlalchemy==2.0.0

# Install utilities
echo "🔧 Installing utilities..."
python3 -m pip install --user typer==0.12.3
python3 -m pip install --user rich==13.7.1
python3 -m pip install --user python-dotenv==1.0.1
python3 -m pip install --user requests==2.32.3

# Install security frameworks
echo "🔐 Installing security frameworks..."
python3 -m pip install --user pyjwt==2.8.0
python3 -m pip install --user passlib==1.7.4

# Install real-time frameworks
echo "⚡ Installing real-time frameworks..."
python3 -m pip install --user websockets==11.0.0

# Install data processing
echo "📊 Installing data processing frameworks..."
python3 -m pip install --user pandas==2.0.0
python3 -m pip install --user numpy==1.24.0
python3 -m pip install --user python-dateutil==2.8.0

# Install trading APIs
echo "💹 Installing trading frameworks..."
python3 -m pip install --user ccxt==4.0.0
python3 -m pip install --user yfinance==0.2.22

# Install AI frameworks
echo "🤖 Installing AI frameworks..."
python3 -m pip install --user openai==1.0.0

# Install HTTP frameworks
echo "🌐 Installing HTTP frameworks..."
python3 -m pip install --user aiohttp==3.8.0
python3 -m pip install --user httpx==0.25.0

# Test installation
echo "🧪 Testing installation..."
python3 -c "import fastapi; print('✅ FastAPI installed')" 2>/dev/null || echo "❌ FastAPI failed"
python3 -c "import uvicorn; print('✅ Uvicorn installed')" 2>/dev/null || echo "❌ Uvicorn failed"
python3 -c "import pandas; print('✅ Pandas installed')" 2>/dev/null || echo "❌ Pandas failed"
python3 -c "import ccxt; print('✅ CCXT installed')" 2>/dev/null || echo "❌ CCXT failed"

# Show installation summary
echo ""
echo "🎉 USER INSTALLATION COMPLETE!"
echo "=============================="
echo "✅ Packages installed to: ~/.local/lib/python3.12/site-packages"
echo "✅ Scripts installed to: ~/.local/bin"
echo ""
echo "📁 Setup application..."
cd /home/admin/deployment_package

# Initialize database
echo "💾 Initializing database..."
python3 init_database.py

# Start the application
echo "🚀 Starting Trading Bot..."
echo "🌐 Will be available at: http://185.70.196.214:8008"
echo "Press Ctrl+C to stop"
python3 start_app.py
