#!/bin/bash

# PostgreSQL Installation and Configuration for Trading Panel
# Run this script on the VPS server to set up PostgreSQL

set -e

echo "🐘 Installing PostgreSQL for Trading Panel..."

# Update system
sudo apt update

# Install PostgreSQL and required packages
sudo apt install -y postgresql postgresql-contrib python3-psycopg2

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Create database and user
sudo -u postgres psql << EOF
-- Create database
CREATE DATABASE trading_bot;

-- Create user with password
CREATE USER trading_user WITH PASSWORD 'trading_password_2024!';

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

echo "✅ PostgreSQL installation completed!"

# Configure PostgreSQL for remote connections (if needed)
PG_VERSION=$(sudo -u postgres psql -t -c "SELECT version();" | head -n1 | awk '{print $2}' | cut -d. -f1,2)
PG_MAIN="/etc/postgresql/$PG_VERSION/main"

# Backup original files
sudo cp "$PG_MAIN/postgresql.conf" "$PG_MAIN/postgresql.conf.backup"
sudo cp "$PG_MAIN/pg_hba.conf" "$PG_MAIN/pg_hba.conf.backup"

# Configure PostgreSQL to listen on localhost
sudo sed -i "s/#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" "$PG_MAIN/postgresql.conf"

# Allow local connections
echo "# Trading Panel local connection" | sudo tee -a "$PG_MAIN/pg_hba.conf"
echo "local   trading_bot   trading_user                     md5" | sudo tee -a "$PG_MAIN/pg_hba.conf"

# Restart PostgreSQL
sudo systemctl restart postgresql

# Test connection
echo "🧪 Testing database connection..."
export PGPASSWORD='trading_password_2024!'
psql -h localhost -U trading_user -d trading_bot -c "SELECT version();"

if [ $? -eq 0 ]; then
    echo "✅ Database connection test successful!"
else
    echo "❌ Database connection test failed!"
    exit 1
fi

# Create environment file for database
cat > /opt/trading-bot/.env.db << EOF
# PostgreSQL Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=trading_bot
DB_USER=trading_user
DB_PASSWORD=trading_password_2024!

# SMTP Email Configuration (optional)
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_NAME=Trading Panel
SMTP_FROM_EMAIL=noreply@tradingpanel.com
EOF

echo "📝 Database environment file created at /opt/trading-bot/.env.db"

# Install required Python packages
pip3 install psycopg2-binary

echo ""
echo "🎉 PostgreSQL setup completed successfully!"
echo ""
echo "📋 Database Details:"
echo "  Database: trading_bot"
echo "  User: trading_user"
echo "  Password: trading_password_2024!"
echo "  Host: localhost"
echo "  Port: 5432"
echo ""
echo "📁 Environment file: /opt/trading-bot/.env.db"
echo ""
echo "🔧 Next steps:"
echo "1. Update enhanced_server_gpt5.py to use PostgreSQL"
echo "2. Configure SMTP settings in .env.db"
echo "3. Test the new database system"
echo ""
