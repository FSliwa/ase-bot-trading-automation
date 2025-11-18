#!/bin/bash

# 🚀 Trading Bot - Complete Framework Installation
# Install all required Python packages and system dependencies

echo "🚀 Installing Trading Bot Frameworks on VPS"
echo "=============================================="

# Update system first
echo "📦 Updating system packages..."
apt update

# Install Python pip and development tools
echo "🐍 Installing Python development tools..."
apt install -y python3-pip python3-dev python3-venv build-essential

# Install system dependencies for Python packages
echo "🔧 Installing system dependencies..."
apt install -y \
    libffi-dev \
    libssl-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    pkg-config \
    curl \
    wget

# Upgrade pip
echo "⬆️ Upgrading pip..."
python3 -m pip install --upgrade pip setuptools wheel

# Create virtual environment in /opt/trading-bot
echo "🌐 Creating virtual environment..."
mkdir -p /opt/trading-bot
cd /opt/trading-bot
python3 -m venv venv
source venv/bin/activate

# Install core frameworks
echo "📦 Installing core frameworks..."
pip install fastapi==0.111.0
pip install uvicorn[standard]==0.30.0
pip install jinja2==3.1.4
pip install python-multipart==0.0.9
pip install pydantic==2.8.0

# Install database & ORM
echo "💾 Installing database frameworks..."
pip install sqlalchemy==2.0.0
pip install alembic==1.12.0

# Install utilities
echo "🔧 Installing utilities..."
pip install typer==0.12.3
pip install rich==13.7.1
pip install python-dotenv==1.0.1
pip install requests==2.32.3

# Install authentication & security
echo "🔐 Installing security frameworks..."
pip install pyjwt==2.8.0
pip install cryptography==41.0.0
pip install passlib==1.7.4

# Install real-time frameworks
echo "⚡ Installing real-time frameworks..."
pip install websockets==11.0.0
pip install redis==5.0.0

# Install data processing
echo "📊 Installing data processing frameworks..."
pip install pandas==2.0.0
pip install numpy==1.24.0
pip install python-dateutil==2.8.0

# Install trading APIs
echo "💹 Installing trading frameworks..."
pip install ccxt==4.0.0
pip install yfinance==0.2.22

# Install AI frameworks (optional but recommended)
echo "🤖 Installing AI frameworks..."
pip install openai==1.0.0
pip install anthropic==0.7.0
pip install scikit-learn==1.3.0

# Install HTTP frameworks
echo "🌐 Installing HTTP frameworks..."
pip install aiohttp==3.8.0
pip install httpx==0.25.0

# Install monitoring
echo "📈 Installing monitoring frameworks..."
pip install prometheus-client==0.19.0
pip install structlog==23.2.0

# Install additional utilities
echo "⚙️ Installing additional utilities..."
pip install orjson==3.9.0
pip install statsmodels==0.14.0

# Copy application files
echo "📁 Setting up application..."
if [ -d "/home/admin/deployment_package" ]; then
    cp -r /home/admin/deployment_package/* /opt/trading-bot/
    echo "✅ Application files copied"
else
    echo "⚠️ Deployment package not found in /home/admin/"
fi

# Create .env file
echo "⚙️ Creating configuration..."
if [ ! -f "/opt/trading-bot/.env" ]; then
    cp /opt/trading-bot/.env.example /opt/trading-bot/.env 2>/dev/null || echo "# Trading Bot Configuration" > /opt/trading-bot/.env
fi

# Initialize database
echo "💾 Initializing database..."
python init_database.py 2>/dev/null || echo "Database initialization skipped"

# Install Redis server
echo "🗄️ Installing Redis server..."
apt install -y redis-server
systemctl enable redis-server
systemctl start redis-server

# Install Nginx
echo "🌐 Installing Nginx..."
apt install -y nginx
systemctl enable nginx

# Test installation
echo "🧪 Testing installation..."
python -c "import fastapi, uvicorn, requests; print('✅ Core frameworks OK')"
python -c "import pandas, numpy; print('✅ Data processing OK')"
python -c "import ccxt; print('✅ Trading APIs OK')"

# Show installation summary
echo ""
echo "🎉 INSTALLATION COMPLETE!"
echo "========================="
echo "✅ FastAPI & Uvicorn - Web framework"
echo "✅ SQLAlchemy & Alembic - Database ORM"
echo "✅ Pandas & NumPy - Data processing"
echo "✅ CCXT - Trading APIs"
echo "✅ Redis - Caching & sessions"
echo "✅ Nginx - Web server"
echo "✅ WebSockets - Real-time communication"
echo "✅ AI frameworks - OpenAI, Anthropic"
echo "✅ Security - JWT, Cryptography"
echo ""
echo "📍 Virtual environment: /opt/trading-bot/venv"
echo "📍 Application path: /opt/trading-bot"
echo ""
echo "🚀 Next step: Start the trading bot"
echo "cd /opt/trading-bot && source venv/bin/activate && python start_app.py"
echo ""
