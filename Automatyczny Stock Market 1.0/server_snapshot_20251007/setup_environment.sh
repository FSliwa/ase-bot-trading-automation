# Email Configuration for Trading Panel
# Set these environment variables to enable email notifications

# SMTP Server Configuration
export SMTP_SERVER="smtp.gmail.com"
export SMTP_PORT="587"
export SMTP_USERNAME="your_gmail@gmail.com"
export SMTP_PASSWORD="your_app_password"
export SMTP_FROM_NAME="Trading Panel"
export SMTP_FROM_EMAIL="noreply@tradingpanel.com"

# Database Configuration
export DB_HOST="localhost"
export DB_PORT="5432"
export DB_NAME="trading_bot"
export DB_USER="trading_user"
export DB_PASSWORD="trading_password_2024!"

# OAuth Configuration (optional)
export GOOGLE_CLIENT_ID="your-google-client-id"
export GOOGLE_CLIENT_SECRET="your-google-client-secret"
export GITHUB_CLIENT_ID="your-github-client-id"
export GITHUB_CLIENT_SECRET="your-github-client-secret"

echo "Environment variables loaded for Trading Panel"
echo "📧 SMTP: ${SMTP_SERVER}:${SMTP_PORT}"
echo "🐘 Database: ${DB_HOST}:${DB_PORT}/${DB_NAME}"
