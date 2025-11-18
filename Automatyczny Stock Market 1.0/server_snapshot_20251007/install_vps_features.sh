#!/bin/bash

# VPS Features Installation Script
# Installs and configures new advanced features for trading bot

set -e

echo "🚀 Installing VPS Trading Bot Advanced Features..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_step() {
    echo -e "${BLUE}📋 $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check Python version
print_step "Checking Python version..."
python_version=$(python3 --version 2>&1 | cut -d" " -f2)
required_version="3.8"

if python3 -c "import sys; exit(0 if sys.version_info >= (3, 8) else 1)"; then
    print_success "Python $python_version detected"
else
    print_error "Python 3.8+ required. Current version: $python_version"
    exit 1
fi

# Install Python dependencies
print_step "Installing Python dependencies..."
if pip3 install -r requirements.txt; then
    print_success "Python dependencies installed"
else
    print_error "Failed to install Python dependencies"
    exit 1
fi

# Install Redis (for real-time streaming)
print_step "Checking Redis installation..."
if command -v redis-server &> /dev/null; then
    print_success "Redis already installed"
else
    print_warning "Redis not found. Installing..."
    
    # Detect OS and install Redis
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Ubuntu/Debian
        if command -v apt-get &> /dev/null; then
            sudo apt-get update
            sudo apt-get install -y redis-server
        # CentOS/RHEL
        elif command -v yum &> /dev/null; then
            sudo yum install -y redis
        else
            print_warning "Please install Redis manually for your Linux distribution"
        fi
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew install redis
        else
            print_warning "Please install Homebrew and Redis manually"
        fi
    else
        print_warning "Please install Redis manually for your operating system"
    fi
fi

# Start Redis service
print_step "Starting Redis service..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    sudo systemctl start redis-server
    sudo systemctl enable redis-server
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew services start redis
fi

# Create necessary directories
print_step "Creating directory structure..."
mkdir -p logs/streaming
mkdir -p data/users
mkdir -p data/ai_cache
mkdir -p backups
mkdir -p certificates

print_success "Directory structure created"

# Setup database schema
print_step "Setting up database schema..."
if python3 -c "
from bot.user_manager import Base
from bot.db import SessionLocal, engine
Base.metadata.create_all(bind=engine)
print('Database schema created successfully')
"; then
    print_success "Database schema initialized"
else
    print_error "Failed to initialize database schema"
fi

# Generate JWT secret if not exists
print_step "Configuring authentication..."
if [ ! -f .env ]; then
    cp env.example .env
    print_success "Environment file created from template"
fi

# Generate JWT secret
jwt_secret=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
if grep -q "JWT_SECRET=" .env; then
    sed -i "s/JWT_SECRET=.*/JWT_SECRET=$jwt_secret/" .env
else
    echo "JWT_SECRET=$jwt_secret" >> .env
fi

print_success "JWT secret configured"

# Setup logging configuration
print_step "Configuring logging..."
cat > logging_config.json << EOF
{
    "version": 1,
    "disable_existing_loggers": false,
    "formatters": {
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        },
        "simple": {
            "format": "%(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "level": "INFO",
            "formatter": "simple",
            "stream": "ext://sys.stdout"
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "detailed",
            "filename": "logs/trading_bot.log",
            "maxBytes": 10485760,
            "backupCount": 5
        },
        "streaming": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "INFO", 
            "formatter": "detailed",
            "filename": "logs/streaming/websocket.log",
            "maxBytes": 5242880,
            "backupCount": 3
        }
    },
    "loggers": {
        "bot.streaming": {
            "level": "INFO",
            "handlers": ["streaming", "console"],
            "propagate": false
        },
        "bot.user_manager": {
            "level": "INFO",
            "handlers": ["file", "console"],
            "propagate": false
        },
        "bot.advanced_ai": {
            "level": "INFO",
            "handlers": ["file", "console"],
            "propagate": false
        }
    },
    "root": {
        "level": "INFO",
        "handlers": ["console", "file"]
    }
}
EOF

print_success "Logging configuration created"

# Create systemd service file (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]] && command -v systemctl &> /dev/null; then
    print_step "Creating systemd service..."
    
    current_dir=$(pwd)
    user=$(whoami)
    
    sudo tee /etc/systemd/system/trading-bot.service > /dev/null << EOF
[Unit]
Description=Advanced Trading Bot VPS
After=network.target redis.service
Requires=redis.service

[Service]
Type=simple
User=$user
WorkingDirectory=$current_dir
Environment=PATH=$current_dir/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$current_dir/venv/bin/python -m uvicorn web.app:app --host 0.0.0.0 --port 8008
Restart=always
RestartSec=10

# Logging
StandardOutput=append:$current_dir/logs/service.log
StandardError=append:$current_dir/logs/service_error.log

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=$current_dir

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    print_success "Systemd service created"
fi

# Create backup script
print_step "Setting up backup system..."
cat > backup_system.sh << 'EOF'
#!/bin/bash

# Trading Bot Backup Script
BACKUP_DIR="backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="trading_bot_backup_$DATE.tar.gz"

echo "🔄 Creating backup..."

# Create backup archive
tar -czf "$BACKUP_DIR/$BACKUP_FILE" \
    --exclude="logs/*" \
    --exclude="backups/*" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude="venv" \
    --exclude="node_modules" \
    .

echo "✅ Backup created: $BACKUP_FILE"

# Keep only last 7 backups
cd "$BACKUP_DIR"
ls -t trading_bot_backup_*.tar.gz | tail -n +8 | xargs rm -f 2>/dev/null || true

echo "🧹 Old backups cleaned up"
EOF

chmod +x backup_system.sh
print_success "Backup system configured"

# Create monitoring script
print_step "Setting up monitoring..."
cat > monitor_system.sh << 'EOF'
#!/bin/bash

# System Health Monitor
check_service() {
    if pgrep -f "uvicorn web.app:app" > /dev/null; then
        echo "✅ Trading Bot: Running"
    else
        echo "❌ Trading Bot: Stopped"
    fi
}

check_redis() {
    if redis-cli ping > /dev/null 2>&1; then
        echo "✅ Redis: Running"
    else
        echo "❌ Redis: Stopped"
    fi
}

check_disk_space() {
    usage=$(df -h . | awk 'NR==2 {print $5}' | sed 's/%//')
    if [ "$usage" -gt 85 ]; then
        echo "⚠️  Disk Space: ${usage}% (Critical)"
    elif [ "$usage" -gt 70 ]; then
        echo "⚠️  Disk Space: ${usage}% (Warning)"
    else
        echo "✅ Disk Space: ${usage}% (OK)"
    fi
}

check_memory() {
    if command -v free &> /dev/null; then
        usage=$(free | awk 'NR==2{printf "%.0f", $3*100/$2}')
        if [ "$usage" -gt 85 ]; then
            echo "⚠️  Memory: ${usage}% (Critical)"
        elif [ "$usage" -gt 70 ]; then
            echo "⚠️  Memory: ${usage}% (Warning)"
        else
            echo "✅ Memory: ${usage}% (OK)"
        fi
    fi
}

echo "🔍 System Health Check - $(date)"
echo "================================"
check_service
check_redis
check_disk_space
check_memory
echo "================================"
EOF

chmod +x monitor_system.sh
print_success "Monitoring system configured"

# Test API endpoints
print_step "Testing new API endpoints..."
if python3 -c "
import asyncio
import sys
sys.path.append('.')

async def test_imports():
    try:
        from bot.user_manager import get_user_manager
        from bot.streaming import get_connection_manager
        from bot.advanced_ai import get_ai_engine
        print('✅ All imports successful')
        return True
    except Exception as e:
        print(f'❌ Import error: {e}')
        return False

result = asyncio.run(test_imports())
sys.exit(0 if result else 1)
"; then
    print_success "API modules imported successfully"
else
    print_error "API module import failed"
fi

# Create quick start guide
print_step "Creating documentation..."
cat > VPS_QUICK_START.md << 'EOF'
# VPS Trading Bot - Quick Start Guide

## 🚀 New Features Added

### 1. Multi-User Authentication
- JWT-based user authentication
- Role-based access control (Free, Basic, Pro, Enterprise)
- API key management for external access

### 2. Real-time WebSocket Streaming
- Live price feeds
- Portfolio updates
- Trading notifications
- AI signals streaming

### 3. Advanced AI Analysis
- Multi-model AI support (GPT-5 Pro, GPT-4, Claude)
- Consensus trading signals
- Technical, fundamental, and sentiment analysis

### 4. Enhanced Portfolio Management
- Cross-exchange portfolio tracking
- Performance analytics
- Risk metrics

## 🔧 Quick Commands

### Start the system:
```bash
# Start Redis (if not running)
redis-server &

# Start the trading bot
python -m uvicorn web.app:app --host 0.0.0.0 --port 8008
```

### System monitoring:
```bash
# Check system health
./monitor_system.sh

# Create backup
./backup_system.sh
```

### API Testing:
```bash
# Test user registration
curl -X POST "http://localhost:8008/api/auth/register" \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","username":"testuser","password":"secure123"}'

# Test AI analysis
curl -X POST "http://localhost:8008/api/ai/analyze/BTCUSDT" \
     -H "Content-Type: application/json" \
     -d '{"analysis_types":["technical"],"models":["gpt-5-pro"]}'
```

## 🌐 WebSocket Connection

Connect to real-time stream:
```javascript
const ws = new WebSocket('ws://localhost:8008/ws/1');
ws.onopen = () => {
    // Subscribe to price feed
    ws.send(JSON.stringify({
        action: 'subscribe',
        stream_type: 'price_feed'
    }));
};
```

## 📊 System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Client    │───▶│   FastAPI App    │───▶│   Trading Bot   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   Redis/WebSocket │
                       └──────────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │   SQLite DB      │
                       └──────────────────┘
```

## 🔒 Security Features

- JWT token authentication
- Password hashing with salt
- Rate limiting per user plan
- Encrypted API credentials storage
- Session management

## 📈 Monitoring

- Health check endpoint: `/health`
- System status: `/api/admin/system/status`
- User statistics: `/api/admin/users/stats`
- Real-time metrics via WebSocket

## 🛠️ Configuration

Key environment variables in `.env`:
- `JWT_SECRET`: Secret for JWT token signing
- `OPENAI_API_KEY`: OpenAI API key for AI analysis
- `APP_PORT`: Application port (default: 8008)
- `DATABASE_URL`: Database connection string

## 📞 Support

For issues and feature requests, check the logs:
- Main log: `logs/trading_bot.log`
- WebSocket log: `logs/streaming/websocket.log`
- Service log: `logs/service.log`
EOF

print_success "Documentation created"

# Final status check
print_step "Final system check..."

# Check if Redis is running
if redis-cli ping > /dev/null 2>&1; then
    print_success "Redis is running"
else
    print_warning "Redis is not running - some features may not work"
fi

# Check if required Python modules can be imported
if python3 -c "import jwt, redis, websockets" > /dev/null 2>&1; then
    print_success "All Python dependencies available"
else
    print_warning "Some Python dependencies may be missing"
fi

echo ""
echo "🎉 VPS Trading Bot Advanced Features Installation Complete!"
echo ""
print_success "✅ User Management System"
print_success "✅ Real-time WebSocket Streaming" 
print_success "✅ Advanced AI Analysis Engine"
print_success "✅ Enhanced API Endpoints"
print_success "✅ Monitoring & Backup Systems"
echo ""
echo "📚 Read VPS_QUICK_START.md for usage instructions"
echo ""
echo "🚀 To start the system:"
echo "   python -m uvicorn web.app:app --host 0.0.0.0 --port 8008"
echo ""
echo "🌐 Dashboard will be available at: http://localhost:8008"
echo "📡 WebSocket endpoint: ws://localhost:8008/ws/{user_id}"
echo "📋 API documentation: http://localhost:8008/docs"
