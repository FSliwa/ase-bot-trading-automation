#!/bin/bash

# 🐘 PostgreSQL Setup for Trading Bot
# This script sets up PostgreSQL database and user

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Configuration
DB_NAME="trading_bot"
DB_USER="trading_user"
DB_PASSWORD="$(openssl rand -base64 32 | tr -d '=+/' | head -c 32)"

print_status "Setting up PostgreSQL for Trading Bot..."

# Install PostgreSQL if not present
if ! command -v psql &> /dev/null; then
    print_status "Installing PostgreSQL..."
    sudo apt-get update
    sudo apt-get install -y postgresql postgresql-contrib
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
    print_success "PostgreSQL installed"
else
    print_success "PostgreSQL already installed"
fi

# Create database and user
print_status "Creating database and user..."

sudo -u postgres psql << EOF
-- Drop existing database and user if they exist
DROP DATABASE IF EXISTS $DB_NAME;
DROP USER IF EXISTS $DB_USER;

-- Create user
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';

-- Create database
CREATE DATABASE $DB_NAME OWNER $DB_USER;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;

-- Connect to the database and grant schema privileges
\c $DB_NAME

-- Grant schema privileges
GRANT ALL ON SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO $DB_USER;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO $DB_USER;

-- Set default privileges
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO $DB_USER;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO $DB_USER;

\q
EOF

print_success "Database '$DB_NAME' and user '$DB_USER' created"

# Update .env.db file
ENV_FILE="/opt/trading-bot/.env.db"
print_status "Updating environment configuration..."

# Create backup of existing .env.db
if [ -f "$ENV_FILE" ]; then
    sudo cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)"
fi

# Add PostgreSQL configuration
sudo bash -c "cat >> $ENV_FILE << 'EOF'

# PostgreSQL Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=$DB_NAME
POSTGRES_USER=$DB_USER
POSTGRES_PASSWORD=$DB_PASSWORD
EOF"

print_success "Environment configuration updated"

# Set permissions
sudo chown root:root "$ENV_FILE"
sudo chmod 600 "$ENV_FILE"

# Test connection
print_status "Testing database connection..."
sudo -u postgres psql -d "$DB_NAME" -c "SELECT version();" > /dev/null
print_success "Database connection test passed"

# Initialize tables (will be done by the app)
print_status "Database setup complete!"

echo ""
echo "🎉 PostgreSQL Setup Summary:"
echo "============================="
echo "📊 Database: $DB_NAME"
echo "👤 User: $DB_USER"
echo "🔑 Password: $DB_PASSWORD"
echo "🌐 Host: localhost"
echo "📡 Port: 5432"
echo ""
echo "✅ Configuration saved to: $ENV_FILE"
echo "🔄 Restart trading-bot service to apply changes:"
echo "   sudo systemctl restart trading-bot"
echo ""
print_success "Setup completed successfully!"
