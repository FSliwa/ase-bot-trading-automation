#!/bin/bash

# Create secure .env file with updated API keys
sudo tee /opt/trading-bot/.env > /dev/null << 'EOF'
# === SECURE CONFIGURATION ===
# Updated: 2025-01-25T12:00:00Z
# WARNING: NEVER commit this file to version control

# AI Configuration - UPDATED SECURE KEYS
GEMINI_API_KEY=YOUR_NEW_SECURE_GEMINI_API_KEY_HERE
TAVILY_API_KEY=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

# PostgreSQL Configuration - SECURE PASSWORDS
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=trading_bot
POSTGRES_USER=trading_user
POSTGRES_PASSWORD=$(openssl rand -base64 32)

# JWT Configuration - NEW SECURE KEYS
JWT_SECRET=$(openssl rand -hex 64)
JWT_ISSUER=trading-bot
JWT_EXPIRE_MIN=120

# Encryption Key for sensitive data
ENCRYPTION_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "GENERATE_NEW_FERNET_KEY")

# Redis Configuration
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=$(openssl rand -base64 24)

# Logging
LOG_DIR=/opt/trading-bot/logs
LOG_LEVEL=INFO

# Web Search Configuration
NEWS_SOURCES=coindesk,cointelegraph,cryptonews,bitcoinmagazine
NEWS_UPDATE_INTERVAL_MINUTES=15
SENTIMENT_ANALYSIS_ENABLED=true

# Security Settings
CORS_ORIGINS=["http://localhost:8010", "https://ase-bot.live"]
TRUSTED_HOSTS=["localhost", "127.0.0.1", "ase-bot.live"]
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60

# OAuth Configuration (placeholder - update with real values)
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
GITHUB_CLIENT_ID=YOUR_GITHUB_CLIENT_ID
GITHUB_CLIENT_SECRET=YOUR_GITHUB_CLIENT_SECRET

# Trading Configuration (safe defaults for production)
USE_TESTNET=true
EXCHANGE_NAME=binance
RISK_PER_TRADE_PCT=1.0
MAX_POSITIONS=3
DAILY_LOSS_LIMIT_PCT=5.0
REQUIRE_STOP_LOSS_LIVE=true
CONFIRM_LIVE_TRADING=NO

EOF

# Set strict permissions
sudo chown www-data:www-data /opt/trading-bot/.env
sudo chmod 600 /opt/trading-bot/.env

echo "✅ Updated .env file with secure configuration and new API keys"
echo "⚠️  Remember to:"
echo "   1. Replace YOUR_NEW_SECURE_GEMINI_API_KEY_HERE with your actual new Gemini API key"
echo "   2. Update OAuth credentials with real values"
echo "   3. Test the configuration before deploying to production"
