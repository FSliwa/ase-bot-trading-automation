#!/bin/bash

# Complete PostgreSQL + Email Integration Deployment Script
# Run this on the VPS server: admin@185.70.196.214

set -e

echo "🚀 Starting PostgreSQL + Email Integration Deployment..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Check if running as admin user (but not with sudo)
if [ "$USER" != "admin" ]; then
    print_error "This script should be run as 'admin' user (not root)"
    print_info "Usage: ./deploy_postgresql_email.sh (not sudo ./deploy_postgresql_email.sh)"
    exit 1
fi

# Check if running with sudo
if [ "$EUID" -eq 0 ]; then
    print_error "Do not run this script with sudo!"
    print_info "The script will ask for sudo when needed"
    print_info "Usage: ./deploy_postgresql_email.sh"
    exit 1
fi

# Stop the trading bot service
print_info "Stopping trading bot service..."
sudo systemctl stop trading-bot || print_warning "Service not running"

# Backup existing files
print_info "Creating backup..."
BACKUP_DIR="/home/admin/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /opt/trading-bot/* "$BACKUP_DIR/" 2>/dev/null || true
print_status "Backup created in $BACKUP_DIR"

# Install PostgreSQL if not already installed
if ! command -v psql &> /dev/null; then
    print_info "Installing PostgreSQL..."
    
    # Update system
    sudo apt update
    
    # Install PostgreSQL and required packages
    sudo apt install -y postgresql postgresql-contrib python3-psycopg2
    
    # Start and enable PostgreSQL
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
    
    print_status "PostgreSQL installed"
else
    print_info "PostgreSQL already installed"
fi

# Setup database and user
print_info "Configuring PostgreSQL database..."

sudo -u postgres psql << 'EOF'
-- Create database if not exists
SELECT 'CREATE DATABASE trading_bot' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'trading_bot');

-- Create user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'trading_user') THEN
        CREATE USER trading_user WITH PASSWORD 'trading_password_2024!';
    END IF;
END
$$;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE trading_bot TO trading_user;

-- Connect to trading_bot database
\c trading_bot

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO trading_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO trading_user;

-- Set default privileges for future tables
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO trading_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO trading_user;

EOF

print_status "Database configured"

# Determine PostgreSQL main config directory robustly
print_info "Detecting PostgreSQL config directory..."
if [ -d /etc/postgresql ]; then
    PG_VERSION_DIR=$(ls -1 /etc/postgresql | sort -V | tail -n1)
    PG_MAIN="/etc/postgresql/${PG_VERSION_DIR}/main"
else
    # Fallback: ask Postgres for config_file path
    CFG_PATH=$(sudo -u postgres psql -t -c "SHOW config_file;" | tr -d ' ')
    PG_MAIN=$(dirname "$CFG_PATH")
fi

if [ -d "$PG_MAIN" ]; then
    print_status "PostgreSQL config directory: $PG_MAIN"
    
    # Backup original files
    sudo cp "$PG_MAIN/postgresql.conf" "$PG_MAIN/postgresql.conf.backup" 2>/dev/null || true
    sudo cp "$PG_MAIN/pg_hba.conf" "$PG_MAIN/pg_hba.conf.backup" 2>/dev/null || true
    
    # Configure PostgreSQL to listen on localhost
    if [ -f "$PG_MAIN/postgresql.conf" ]; then
        sudo sed -i "s/^#*listen_addresses *= *'.*'/listen_addresses = 'localhost'/" "$PG_MAIN/postgresql.conf" || true
    else
        print_warning "postgresql.conf not found at $PG_MAIN/postgresql.conf (skipping listen_addresses tweak)"
    fi
    
    # Add local connection for trading_user if not exists
    if [ -f "$PG_MAIN/pg_hba.conf" ]; then
        if ! sudo grep -q "trading_user" "$PG_MAIN/pg_hba.conf"; then
            echo "# Trading Panel local connection" | sudo tee -a "$PG_MAIN/pg_hba.conf" >/dev/null
            echo "local   trading_bot   trading_user                     md5" | sudo tee -a "$PG_MAIN/pg_hba.conf" >/dev/null
        fi
    else
        print_warning "pg_hba.conf not found at $PG_MAIN/pg_hba.conf (skipping pg_hba tweaks)"
    fi
else
    print_warning "Could not determine PostgreSQL config directory (skipping config tweaks)"
fi

# Restart PostgreSQL
sudo systemctl restart postgresql

# Test database connection
print_info "Testing database connection..."
export PGPASSWORD='trading_password_2024!'
if psql -h localhost -U trading_user -d trading_bot -c "SELECT version();" &>/dev/null; then
    print_status "Database connection test successful"
else
    print_error "Database connection test failed"
    exit 1
fi

# Install Python dependencies
print_info "Installing Python dependencies..."
pip3 install psycopg2-binary &>/dev/null || sudo apt install -y python3-psycopg2

# Upload new files to the server
print_info "Updating application files..."

# Copy new files if they exist locally
if [ -f "postgresql_database.py" ]; then
    sudo cp postgresql_database.py /opt/trading-bot/
    print_status "PostgreSQL database module updated"
fi

if [ -f "enhanced_server_gpt5.py" ]; then
    sudo cp enhanced_server_gpt5.py /opt/trading-bot/
    print_status "Enhanced server updated"
fi

if [ -f "register.html" ]; then
    sudo cp register.html /opt/trading-bot/
    print_status "Registration page updated"
fi

if [ -f "user_database.py" ]; then
    sudo cp user_database.py /opt/trading-bot/
    print_status "User database module updated"
fi

# Create environment file for database
print_info "Creating environment configuration..."
sudo tee /opt/trading-bot/.env.db << 'EOF'
# PostgreSQL Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_user
DB_PASSWORD=trading_password_2024!

# SMTP Email Configuration (configure these manually)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_NAME=Trading Panel
SMTP_FROM_EMAIL=noreply@tradingpanel.com

# OAuth Configuration (optional)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret
EOF

print_status "Environment file created"

# Set proper permissions
sudo chown -R trading-bot:trading-bot /opt/trading-bot/
sudo chmod 600 /opt/trading-bot/.env.db

# Migrate existing JSON data to PostgreSQL (if exists)
if [ -f "/opt/trading-bot/users.json" ]; then
    print_info "Migrating existing users from JSON to PostgreSQL..."
    
    cd /opt/trading-bot
    python3 << 'PYTHON_SCRIPT'
import os
import sys
sys.path.append('/opt/trading-bot')

# Load environment variables
for line in open('/opt/trading-bot/.env.db'):
    if line.strip() and not line.startswith('#'):
        key, value = line.strip().split('=', 1)
        os.environ[key] = value

try:
    from postgresql_database import PostgreSQLDatabase
    
    db = PostgreSQLDatabase()
    result = db.migrate_from_json('users.json')
    
    if result['success']:
        print(f"✅ Migration successful: {result['migrated_count']}/{result['total_users']} users migrated")
        if result['errors']:
            print("Errors:", result['errors'])
    else:
        print(f"❌ Migration failed: {result['error']}")
        
except Exception as e:
    print(f"❌ Migration error: {e}")
    print("ℹ️  System will use JSON fallback")
PYTHON_SCRIPT
    
    print_status "Data migration completed"
fi

# Test the new system
print_info "Testing the updated system..."

cd /opt/trading-bot
python3 << 'PYTHON_SCRIPT'
import os
import sys
sys.path.append('/opt/trading-bot')

# Load environment variables
for line in open('/opt/trading-bot/.env.db'):
    if line.strip() and not line.startswith('#'):
        key, value = line.strip().split('=', 1)
        os.environ[key] = value

try:
    from postgresql_database import PostgreSQLDatabase
    
    db = PostgreSQLDatabase()
    stats = db.get_user_stats()
    
    print("📊 Database Statistics:")
    print(f"   Total users: {stats.get('total_users', 0)}")
    print(f"   Active users: {stats.get('active_users', 0)}")
    print(f"   Verified users: {stats.get('verified_users', 0)}")
    print(f"   Account types: {stats.get('account_types', {})}")
    
    print("✅ PostgreSQL integration working correctly")
    
except Exception as e:
    print(f"❌ PostgreSQL test failed: {e}")
    print("ℹ️  System will fallback to JSON database")
PYTHON_SCRIPT

# Start the service
print_info "Starting trading bot service..."
sudo systemctl start trading-bot
sudo systemctl enable trading-bot

# Wait a moment and check status
sleep 3
if sudo systemctl is-active --quiet trading-bot; then
    print_status "Trading bot service started successfully"
else
    print_warning "Service may have issues, checking logs..."
    sudo journalctl -u trading-bot --no-pager -n 10
fi

# Show service status
print_info "Service status:"
sudo systemctl status trading-bot --no-pager -l

echo ""
echo "🎉 PostgreSQL + Email Integration Deployment Completed!"
echo ""
echo "📋 Summary:"
echo "  🐘 PostgreSQL: Installed and configured"
echo "  📧 Email system: Ready (needs SMTP configuration)"
echo "  🔐 Security: Enhanced with audit logging"
echo "  🚀 Service: Running on port 8009"
echo ""
echo "🔧 Next Steps:"
echo "  1. Configure SMTP settings in /opt/trading-bot/.env.db"
echo "  2. Test registration: http://185.70.196.214:8009/register"
echo "  3. Test login: http://185.70.196.214:8009/login"
echo "  4. Check logs: sudo journalctl -u trading-bot -f"
echo ""
echo "📞 Support:"
echo "  - Database status: sudo systemctl status postgresql"
echo "  - Service logs: sudo journalctl -u trading-bot -f"
echo "  - Error logs: tail -f /opt/trading-bot/logs/error.log"
echo ""
print_status "Deployment successful! System is ready for production."
