#!/bin/bash

# 🚀 Trading Bot - Virtual Environment Installation
# Creates virtual environment and installs all frameworks

echo "🚀 Installing Trading Bot with Virtual Environment"
echo "================================================="

# Create virtual environment
echo "🌐 Creating virtual environment..."
cd /home/admin/deployment_package
python3 -m venv trading_env

# Activate virtual environment
echo "⚡ Activating virtual environment..."
source trading_env/bin/activate

# Upgrade pip in virtual environment
echo "⬆️ Upgrading pip..."
pip install --upgrade pip

# Install all frameworks step by step
echo "📦 Installing core frameworks..."
pip install fastapi==0.111.0
pip install "uvicorn[standard]==0.30.0"
pip install jinja2==3.1.4
pip install python-multipart==0.0.9
pip install pydantic==2.8.0

echo "💾 Installing database frameworks..."
pip install sqlalchemy==2.0.0

echo "🔧 Installing utilities..."
pip install typer==0.12.3
pip install rich==13.7.1
pip install python-dotenv==1.0.1
pip install requests==2.32.3

echo "🔐 Installing security frameworks..."
pip install pyjwt==2.8.0
pip install passlib==1.7.4

echo "⚡ Installing real-time frameworks..."
pip install websockets==11.0.0

echo "📊 Installing data processing frameworks..."
pip install pandas==2.0.0
pip install numpy==1.24.0
pip install python-dateutil==2.8.0

echo "💹 Installing trading frameworks..."
pip install ccxt==4.0.0
pip install yfinance==0.2.22

echo "🤖 Installing AI frameworks..."
pip install openai==1.0.0

echo "🌐 Installing HTTP frameworks..."
pip install aiohttp==3.8.0
pip install httpx==0.25.0

echo "📈 Installing monitoring..."
pip install prometheus-client==0.19.0

# Test installation
echo "🧪 Testing installation..."
python -c "import fastapi; print('✅ FastAPI OK')"
python -c "import uvicorn; print('✅ Uvicorn OK')"
python -c "import pandas; print('✅ Pandas OK')"
python -c "import ccxt; print('✅ CCXT OK')"
python -c "from dotenv import load_dotenv; print('✅ Python-dotenv OK')"

# Initialize database
echo "💾 Initializing database..."
python init_database.py

# Create startup script
echo "📝 Creating startup script..."
cat > start_trading_bot.sh << 'EOF'
#!/bin/bash
cd /home/admin/deployment_package
source trading_env/bin/activate
echo "🚀 Starting Trading Bot with all frameworks..."
echo "🌐 Dashboard: http://185.70.196.214:8008"
echo "📚 API Docs: http://185.70.196.214:8008/docs"
echo "❤️ Health: http://185.70.196.214:8008/health"
echo ""
echo "Press Ctrl+C to stop"
python start_app.py
EOF

chmod +x start_trading_bot.sh

echo ""
echo "🎉 INSTALLATION COMPLETE!"
echo "========================"
echo "✅ Virtual environment: /home/admin/deployment_package/trading_env"
echo "✅ All frameworks installed successfully!"
echo ""
echo "🚀 To start Trading Bot:"
echo "./start_trading_bot.sh"
echo ""
echo "🌐 Trading Bot will be available at:"
echo "   http://185.70.196.214:8008"
echo ""
echo "Starting Trading Bot now..."
./start_trading_bot.sh
