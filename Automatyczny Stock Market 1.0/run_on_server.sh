#!/bin/bash
set -euo pipefail

REMOTE_APP_DIR="/opt/trading-bot"
PACKAGE_NAME="deployment_package.tar.gz" # Define PACKAGE_NAME for remote script

if [ -z "$REMOTE_APP_DIR" ] || [ "$REMOTE_APP_DIR" == "/" ]; then
    echo "CRITICAL ERROR: REMOTE_APP_DIR is not set or is set to root. Aborting."
    exit 1
fi

echo "--- Starting deployment on server ---"

# Stop the service to prevent file conflicts
echo "--> Stopping trading-bot service..."
systemctl stop trading-bot || echo "Service was not running, which is OK."

# Clean the target directory before deployment (preserve .env)
echo "--> Cleaning old application files from $REMOTE_APP_DIR (preserving .env)..."
mkdir -p "$REMOTE_APP_DIR"
find "$REMOTE_APP_DIR" -mindepth 1 ! -name ".env" -delete

# Untar the new package
echo "--> Unpacking /tmp/$PACKAGE_NAME..."
tar -xzf "/tmp/$PACKAGE_NAME" -C "$REMOTE_APP_DIR"

# Ensure venv package is installed
echo "--> Ensuring python3-venv is installed..."
apt-get update -y > /dev/null
apt-get install -y python3.12-venv > /dev/null

# Set up Python environment
VENV_DIR="$REMOTE_APP_DIR/.venv"
echo "--> Ensuring Python virtual environment exists at $VENV_DIR..."
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "--> Virtual environment not found, creating it..."
    python3 -m venv "$VENV_DIR"
fi

echo "--> Activating virtual environment and installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip > /dev/null
pip install -r "$REMOTE_APP_DIR/requirements.txt"

# Set ownership and permissions (service runs as 'tradingbot')
echo "--> Setting file permissions..."
chown -R tradingbot:tradingbot "$REMOTE_APP_DIR" || true
chmod -R 775 "$REMOTE_APP_DIR"

# Start the service again
echo "--> Starting trading-bot service..."
systemctl start trading-bot

# Give it a moment to start up
sleep 5

# Check status to confirm it's running
echo "--> Verifying service status..."
systemctl status trading-bot --no-pager | head -n 20

echo "--- Deployment on server finished successfully! ---"
