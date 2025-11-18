#!/bin/bash

# This script automates the process of updating the trading bot application on the remote server.

set -e

# --- Configuration ---
VPS_IP="185.70.196.214"
USER="root"
# Find the latest update package
UPDATE_PACKAGE=$(ls -t trading_bot_update_*.tar.gz | head -n 1)
REMOTE_DIR="/opt/trading-bot"
BACKUP_DIR="/opt/trading-bot-backups"
SERVICE_NAME="trading-bot-api.service"

# --- Validation ---
if [ -z "$UPDATE_PACKAGE" ]; then
    echo "❌ No update package found. Please run ./package_update.sh first."
    exit 1
fi

echo "🚀 Starting Server Update Process"
echo "================================="
echo "Server: $VPS_IP"
echo "Package: $UPDATE_PACKAGE"
echo "Remote Directory: $REMOTE_DIR"
echo "---------------------------------"

# --- Step 1: Upload the package ---
echo "STEP 1: Uploading $UPDATE_PACKAGE to server..."
scp "$UPDATE_PACKAGE" "$USER@$VPS_IP:/root/$UPDATE_PACKAGE"
echo "✅ Upload complete."
echo "---------------------------------"

# --- Step 2: Execute remote commands ---
echo "STEP 2: Executing update commands on the server via SSH..."

ssh "$USER@$VPS_IP" << EOF
set -e

echo "  -> Connected to server. Running as \$(whoami)..."

# Stop the service to prevent file conflicts
echo "  -> Stopping the trading bot service..."
systemctl stop $SERVICE_NAME || echo "Warning: Could not stop service. It might not be running."

# Create backup directory if it doesn't exist
echo "  -> Ensuring backup directory exists at $BACKUP_DIR..."
mkdir -p $BACKUP_DIR

# Create a timestamped backup of the current application
BACKUP_FILE="$BACKUP_DIR/backup_\$(date +'%Y%m%d_%H%M%S').tar.gz"
echo "  -> Backing up current application to \$BACKUP_FILE..."
if [ -d "$REMOTE_DIR" ] && [ "\$(ls -A $REMOTE_DIR)" ]; then
    tar -czf "\$BACKUP_FILE" -C "$REMOTE_DIR" .
else
    echo "Warning: Remote directory is empty or does not exist. Skipping backup."
fi


# Navigate to the application directory
cd "$REMOTE_DIR"

# Remove old files that will be replaced
echo "  -> Removing old application files..."
rm -f fastapi_app.py
rm -rf web/

# Extract the new update package
echo "  -> Extracting new version from /root/$UPDATE_PACKAGE..."
tar -xzf "/root/$UPDATE_PACKAGE" -C "$REMOTE_DIR" --exclude='._*' --warning=no-unknown-keyword

# Update dependencies
echo "  -> Updating Python dependencies..."
VENV_DIR="$REMOTE_DIR/venv"
if [ ! -f "\$VENV_DIR/bin/activate" ]; then
    echo "  -> Virtual environment not found at \$VENV_DIR. Creating it..."
    python3.11 -m venv "\$VENV_DIR"
fi
source "\$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install -r "$REMOTE_DIR/requirements.txt"

# Ensure correct ownership
echo "  -> Setting file permissions..."
chown -R tradingbot:tradingbot "$REMOTE_DIR"

echo "  -> Verifying directory and database file permissions..."
ls -ld "$REMOTE_DIR"
ls -l "$REMOTE_DIR/trading.db"

# Restart the service
echo "  -> Restarting the trading bot service..."
systemctl daemon-reload
systemctl restart $SERVICE_NAME

# Give it a moment to start up
sleep 5

# Check the status of the service
echo "  -> Verifying service status..."
systemctl status $SERVICE_NAME --no-pager

echo "✅ Remote update process finished."
EOF

echo "---------------------------------"
echo "🚀 Update script completed."
echo "Please check the output above to ensure the service restarted correctly."
