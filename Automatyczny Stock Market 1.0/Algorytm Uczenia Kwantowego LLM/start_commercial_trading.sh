#!/bin/bash
# Start Commercial Trading Bot for specific user
# Usage: ./start_commercial_trading.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}🚀 ASE Commercial Trading Bot Launcher${NC}"
echo -e "${BLUE}========================================${NC}\n"

# Configuration for user filipsliwa
export USER_ID="fd21db06-2278-4109-a6d0-0468e72272cf"
export USER_EMAIL="filipsliwa"

echo -e "${GREEN}👤 User: ${USER_EMAIL}${NC}"
echo -e "${GREEN}🆔 User ID: ${USER_ID}${NC}\n"

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}✅ Loading environment from .env${NC}"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${RED}❌ .env file not found!${NC}"
    exit 1
fi

# Check required environment variables
REQUIRED_VARS=(
    "ANTHROPIC_API_KEY"
    "GEMINI_API_KEY"
    "TAVILY_API_KEY"
    "SUPABASE_PROJECT_ID"
    "SUPABASE_SERVICE_ROLE_KEY"
    "ENCRYPTION_KEY"
)

echo -e "\n${BLUE}🔍 Checking environment variables...${NC}"
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}❌ Missing: $var${NC}"
        exit 1
    else
        echo -e "${GREEN}✅ $var${NC}"
    fi
done

# Check Python version
echo -e "\n${BLUE}🐍 Python version:${NC}"
python3 --version

# Check if commercial_trading_bot.py exists
if [ ! -f "commercial_trading_bot.py" ]; then
    echo -e "${RED}❌ commercial_trading_bot.py not found!${NC}"
    exit 1
fi

# Create logs directory
mkdir -p logs

# Set log file
LOG_FILE="logs/commercial_bot_$(date +%Y%m%d_%H%M%S).log"

echo -e "\n${BLUE}📝 Log file: ${LOG_FILE}${NC}\n"

# Find Python with required packages
PYTHON_BIN="python3"
if [ -f "/home/admin/asebot-backend/app/.venv/bin/python3" ]; then
    echo -e "${GREEN}✅ Using virtual environment Python${NC}"
    PYTHON_BIN="/home/admin/asebot-backend/app/.venv/bin/python3"
else
    echo -e "${YELLOW}⚠️  Using system Python${NC}"
fi

# Start the bot
echo -e "${GREEN}🚀 Starting Commercial Trading Bot...${NC}\n"
echo -e "${YELLOW}Press Ctrl+C to stop${NC}\n"

# Run bot with output to both console and log file
$PYTHON_BIN -u commercial_trading_bot.py 2>&1 | tee "$LOG_FILE"

echo -e "\n${BLUE}========================================${NC}"
echo -e "${BLUE}👋 Trading Bot Stopped${NC}"
echo -e "${BLUE}========================================${NC}"
