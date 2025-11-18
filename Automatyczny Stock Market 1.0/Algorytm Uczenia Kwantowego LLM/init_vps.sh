#!/bin/bash
# VPS Initialization Script for Automated Trading Bot
# This script sets up a complete production environment on Ubuntu/Debian VPS

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_NAME="trading-bot"
PROJECT_DIR="/opt/trading-bot"
SERVICE_USER="tradingbot"
PYTHON_VERSION="3.11"
NGINX_ENABLED=true
SSL_ENABLED=false
DOMAIN=""

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Function to detect OS
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$NAME
        VER=$VERSION_ID
    else
        print_error "Cannot detect OS. This script supports Ubuntu/Debian only."
        exit 1
    fi
    
    print_status "Detected OS: $OS $VER"
}

# Function to update system packages
update_system() {
    print_status "Updating system packages..."
    apt-get update -y
    apt-get upgrade -y
    apt-get install -y curl wget git unzip software-properties-common apt-transport-https ca-certificates gnupg lsb-release
    print_success "System updated successfully"
}

# Function to install Python (system python3)
install_python() {
    print_status "Installing system Python (python3) and venv..."
    apt-get install -y python3 python3-venv python3-dev python3-pip
    print_success "System Python installed"
}

# Function to install Node.js and npm
install_nodejs() {
    print_status "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs
    print_success "Node.js installed successfully"
}

# Function to install Redis
install_redis() {
    print_status "Installing Redis..."
    apt-get install -y redis-server
    
    # Configure Redis
    sed -i 's/^supervised no/supervised systemd/' /etc/redis/redis.conf
    sed -i 's/^# maxmemory <bytes>/maxmemory 256mb/' /etc/redis/redis.conf
    sed -i 's/^# maxmemory-policy noeviction/maxmemory-policy allkeys-lru/' /etc/redis/redis.conf
    
    systemctl enable redis-server
    systemctl start redis-server
    print_success "Redis installed and configured"
}

# Function to install PostgreSQL (optional, if user wants to migrate from SQLite)
install_postgresql() {
    print_status "Installing PostgreSQL..."
    apt-get install -y postgresql postgresql-contrib postgresql-client
    
    # Start and enable PostgreSQL
    systemctl enable postgresql
    systemctl start postgresql
    
    # Create database and user
    sudo -u postgres psql -c "CREATE DATABASE trading_bot;"
    sudo -u postgres psql -c "CREATE USER tradingbot WITH PASSWORD 'secure_password_123';"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE trading_bot TO tradingbot;"
    
    print_success "PostgreSQL installed and configured"
    print_warning "Database password: secure_password_123 (change this in production!)"
}

# Function to install Nginx
install_nginx() {
    if [[ "$NGINX_ENABLED" == true ]]; then
        print_status "Installing Nginx..."
        apt-get install -y nginx
        
        systemctl enable nginx
        systemctl start nginx
        
        # Configure firewall
        ufw allow 'Nginx Full'
        
        print_success "Nginx installed and configured"
    fi
}

# Function to create service user
create_service_user() {
    print_status "Creating service user: $SERVICE_USER"
    
    # Create user if it doesn't exist
    if ! id "$SERVICE_USER" &>/dev/null; then
        useradd -r -s /bin/bash -d $PROJECT_DIR -m $SERVICE_USER
        print_success "User $SERVICE_USER created"
    else
        print_warning "User $SERVICE_USER already exists"
    fi
}

# Function to set up project directory
setup_project_directory() {
    print_status "Setting up project directory: $PROJECT_DIR"
    
    # Create project directory
    mkdir -p $PROJECT_DIR
    # Ensure recursive ownership (handles leftover files from previous runs)
    chown -R $SERVICE_USER:$SERVICE_USER $PROJECT_DIR
    
    # Create necessary subdirectories
    sudo -u $SERVICE_USER mkdir -p $PROJECT_DIR/{logs,data,backups,uploads}
    
    print_success "Project directory created"
}

# Function to clone and setup the project
setup_project() {
    print_status "Setting up trading bot project..."
    
    # Clean any previous virtualenv owned by root
    if [ -d "$PROJECT_DIR/venv" ]; then
        rm -rf "$PROJECT_DIR/venv"
    fi
    chown -R $SERVICE_USER:$SERVICE_USER $PROJECT_DIR
    
    # Switch to service user
    sudo -u $SERVICE_USER bash << 'EOF'
set -e
cd /opt/trading-bot

# Copy project files (assuming they're being deployed)
# In production, you would clone from git or copy from deployment package
echo "Project files should be deployed to this directory"

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Ensure pip is present in venv (Ubuntu sometimes creates venv without pip)
python -m ensurepip --upgrade || true
python -m pip install --upgrade pip setuptools wheel

# Install Python dependencies (if requirements.txt exists)
if [ -f requirements.txt ]; then
    pip install -r requirements.txt
fi

# Install additional production packages
pip install gunicorn uvicorn[standard] supervisor

echo "Python environment set up successfully"
EOF

    print_success "Project setup completed"
}

# Function to create environment file
create_env_file() {
    print_status "Creating environment configuration..."
    
    sudo -u $SERVICE_USER cat > $PROJECT_DIR/.env << 'EOF'
# Production Environment Configuration
ENVIRONMENT=production
DEBUG=false

# Database Configuration
DATABASE_URL=sqlite:///./trading.db
# If using PostgreSQL, uncomment below:
# DATABASE_URL=postgresql://tradingbot:secure_password_123@localhost/trading_bot

# Security
JWT_SECRET=your_jwt_secret_key_here_change_this
SECRET_KEY=your_secret_key_here_change_this

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000

# Exchange API Keys (set these manually)
BINANCE_API_KEY=
BINANCE_SECRET_KEY=
BINANCE_TESTNET=true

BYBIT_API_KEY=
BYBIT_SECRET_KEY=
BYBIT_TESTNET=true

PRIMEXBT_API_KEY=
PRIMEXBT_SECRET_KEY=

# AI Configuration
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# Redis Configuration
REDIS_URL=redis://localhost:6379/0

# Monitoring
ENABLE_PROMETHEUS=true
PROMETHEUS_PORT=9090

# Logging
LOG_LEVEL=INFO
LOG_FILE=/opt/trading-bot/logs/app.log

# Email Configuration (for notifications)
SMTP_SERVER=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
FROM_EMAIL=

# Telegram Bot (for notifications)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
EOF

    chown $SERVICE_USER:$SERVICE_USER $PROJECT_DIR/.env
    chmod 600 $PROJECT_DIR/.env
    
    print_success "Environment file created"
    print_warning "Please update .env file with your API keys and secrets!"
}

# Function to create systemd service files
create_systemd_services() {
    print_status "Creating systemd service files..."
    
    # Main API service
    cat > /etc/systemd/system/trading-bot-api.service << EOF
[Unit]
Description=Trading Bot API Server
After=network.target redis-server.service
Wants=redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/uvicorn fastapi_app:app --host 0.0.0.0 --port 8000
ExecReload=/bin/kill -HUP \$MAINPID
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Trading bot service
    cat > /etc/systemd/system/trading-bot.service << EOF
[Unit]
Description=Trading Bot Worker
After=network.target redis-server.service trading-bot-api.service
Wants=redis-server.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/python start_bot.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Monitoring service
    cat > /etc/systemd/system/trading-bot-monitor.service << EOF
[Unit]
Description=Trading Bot Monitor
After=network.target trading-bot-api.service
Wants=trading-bot-api.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
ExecStart=$PROJECT_DIR/venv/bin/python -c "from bot.monitoring import start_monitor; start_monitor()"
Restart=always
RestartSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

    # Reload systemd
    systemctl daemon-reload
    
    print_success "Systemd services created"
}

# Function to configure Nginx
configure_nginx() {
    if [[ "$NGINX_ENABLED" == true ]]; then
        print_status "Configuring Nginx..."
        
        cat > /etc/nginx/sites-available/trading-bot << EOF
server {
    listen 80;
    server_name ${DOMAIN:-localhost};
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    location /static/ {
        alias $PROJECT_DIR/web/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
    
    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;
    add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
}
EOF

        # Enable the site
        ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
        rm -f /etc/nginx/sites-enabled/default
        
        # Test nginx configuration
        nginx -t
        systemctl reload nginx
        
        print_success "Nginx configured"
    fi
}

# Function to configure firewall
configure_firewall() {
    print_status "Configuring firewall..."
    
    # Enable UFW
    ufw --force enable
    
    # Allow SSH
    ufw allow ssh
    
    # Allow HTTP and HTTPS
    ufw allow 80/tcp
    ufw allow 443/tcp
    
    # Allow API port (if not behind nginx)
    if [[ "$NGINX_ENABLED" != true ]]; then
        ufw allow 8000/tcp
    fi
    
    # Allow monitoring ports (restrict to localhost)
    ufw allow from 127.0.0.1 to any port 9090
    
    print_success "Firewall configured"
}

# Function to set up log rotation
setup_log_rotation() {
    print_status "Setting up log rotation..."
    
    cat > /etc/logrotate.d/trading-bot << EOF
$PROJECT_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 $SERVICE_USER $SERVICE_USER
    postrotate
        systemctl reload trading-bot-api trading-bot trading-bot-monitor
    endscript
}
EOF

    print_success "Log rotation configured"
}

# Function to create backup script
create_backup_script() {
    print_status "Creating backup script..."
    
    cat > $PROJECT_DIR/backup.sh << 'EOF'
#!/bin/bash
# Trading Bot Backup Script

BACKUP_DIR="/opt/trading-bot/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="trading_bot_backup_${DATE}.tar.gz"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup database
cp /opt/trading-bot/trading.db $BACKUP_DIR/trading_${DATE}.db

# Backup configuration
cp /opt/trading-bot/.env $BACKUP_DIR/env_${DATE}.backup

# Create compressed archive
tar -czf $BACKUP_DIR/$BACKUP_FILE \
    --exclude='venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='logs/*.log' \
    /opt/trading-bot/

# Remove backups older than 7 days
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.backup" -mtime +7 -delete

echo "Backup completed: $BACKUP_FILE"
EOF

    chmod +x $PROJECT_DIR/backup.sh
    chown $SERVICE_USER:$SERVICE_USER $PROJECT_DIR/backup.sh
    
    # Add to crontab for daily backups
    (crontab -u $SERVICE_USER -l 2>/dev/null; echo "0 2 * * * $PROJECT_DIR/backup.sh") | crontab -u $SERVICE_USER -
    
    print_success "Backup script created and scheduled"
}

# Function to generate SSL certificate
setup_ssl() {
    if [[ "$SSL_ENABLED" == true ]] && [[ -n "$DOMAIN" ]]; then
        print_status "Setting up SSL certificate..."
        
        # Install certbot
        apt-get install -y certbot python3-certbot-nginx
        
        # Get certificate
        certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@$DOMAIN
        
        print_success "SSL certificate configured"
    fi
}

# Function to initialize database
initialize_database() {
    print_status "Initializing database..."
    
    sudo -u $SERVICE_USER bash << EOF
cd $PROJECT_DIR
source venv/bin/activate

# Run database initialization
if [ -f init_database.py ]; then
    python init_database.py
fi

# Create demo data if needed
if [ -f initialize_demo_data.py ]; then
    python initialize_demo_data.py
fi
EOF

    print_success "Database initialized"
}

# Function to start services
start_services() {
    print_status "Starting services..."
    
    # Enable and start services
    systemctl enable trading-bot-api
    systemctl enable trading-bot
    systemctl enable trading-bot-monitor
    
    systemctl start trading-bot-api
    sleep 5
    systemctl start trading-bot
    systemctl start trading-bot-monitor
    
    print_success "Services started"
}

# Function to display status
show_status() {
    print_status "Checking service status..."
    
    echo
    echo "=== Service Status ==="
    systemctl status trading-bot-api --no-pager -l
    echo
    systemctl status trading-bot --no-pager -l
    echo
    systemctl status trading-bot-monitor --no-pager -l
    echo
    
    print_status "Checking port availability..."
    netstat -tlnp | grep -E ':(80|443|8000|6379)'
    
    echo
    print_success "VPS setup completed!"
    echo
    echo "=== Next Steps ==="
    echo "1. Update API keys in $PROJECT_DIR/.env"
    echo "2. Configure domain name if using SSL"
    echo "3. Check logs: journalctl -u trading-bot-api -f"
    echo "4. Access dashboard: http://$(curl -s ifconfig.me):8000"
    echo "5. Monitor services: systemctl status trading-bot-api"
    echo
}

# Main installation function
main() {
    print_status "Starting VPS initialization for Trading Bot..."
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --domain)
                DOMAIN="$2"
                SSL_ENABLED=true
                shift 2
                ;;
            --no-nginx)
                NGINX_ENABLED=false
                shift
                ;;
            --postgresql)
                USE_POSTGRESQL=true
                shift
                ;;
            --help)
                echo "Usage: $0 [options]"
                echo "Options:"
                echo "  --domain DOMAIN    Set domain name and enable SSL"
                echo "  --no-nginx         Skip Nginx installation"
                echo "  --postgresql       Install PostgreSQL instead of SQLite"
                echo "  --help             Show this help message"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
    
    # Run installation steps
    check_root
    detect_os
    update_system
    install_python
    install_nodejs
    install_redis
    
    if [[ "$USE_POSTGRESQL" == true ]]; then
        install_postgresql
    fi
    
    install_nginx
    create_service_user
    setup_project_directory
    setup_project
    create_env_file
    create_systemd_services
    configure_nginx
    configure_firewall
    setup_log_rotation
    create_backup_script
    
    if [[ "$SSL_ENABLED" == true ]]; then
        setup_ssl
    fi
    
    initialize_database
    start_services
    show_status
}

# Run main function
main "$@"
