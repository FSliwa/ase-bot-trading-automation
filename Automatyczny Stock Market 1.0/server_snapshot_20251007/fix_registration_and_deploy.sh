#!/bin/bash
# fix_registration_and_deploy.sh
# This script packages the necessary files to fix the registration flow and prepares for server deployment.

set -e

# --- Configuration ---
APP_DIR="Algorytm Uczenia Kwantowego LLM"
REMOTE_USER="root"
REMOTE_HOST="185.70.196.214"
REMOTE_APP_DIR="/root/Algorytm_Uczenia_Kwantowego_LLM"
PACKAGE_NAME="deployment_package_reg_fix.tar.gz"
RUN_ON_SERVER_SCRIPT="run_on_server_reg_fix.sh"

# --- Files to include in the package ---
FILES_TO_PACKAGE=(
    "$APP_DIR/fastapi_app.py"
    "requirements.txt"
    "$APP_DIR/.env.db"
)

echo "--- Starting Deployment Fix for Registration ---"

# --- 1. Create Deployment Package ---
echo "Creating deployment package: $PACKAGE_NAME"
tar -czvf "$PACKAGE_NAME" "${FILES_TO_PACKAGE[@]}"
echo "Package created successfully."

# --- 2. Generate the 'run_on_server_reg_fix.sh' script ---
echo "Generating the server-side execution script: $RUN_ON_SERVER_SCRIPT"

# Ensure the script is created with the correct permissions
umask 077
cat > "$RUN_ON_SERVER_SCRIPT" <<'EOF'
#!/bin/bash
set -e

# --- Server Configuration ---
REMOTE_APP_DIR="/root/Algorytm_Uczenia_Kwantowego_LLM"
VENV_PATH="$REMOTE_APP_DIR/venv"
PACKAGE_NAME="deployment_package_reg_fix.tar.gz"
SERVICE_NAME="trading-bot.service"

echo "--- Running Server-Side Fix Script ---"

# --- 1. Stop the Service ---
echo "Stopping the trading-bot service..."
sudo systemctl stop $SERVICE_NAME || echo "Service was not running, which is okay."

# --- 2. Extract the Package ---
echo "Extracting deployment package..."
# Ensure the target directory exists
mkdir -p "$REMOTE_APP_DIR"
# Extract files, overwriting existing ones
tar -xzvf "$PACKAGE_NAME" -C "$REMOTE_APP_DIR" --strip-components=1

# Move requirements.txt to the correct location
if [ -f "$REMOTE_APP_DIR/requirements.txt" ]; then
    mv "$REMOTE_APP_DIR/requirements.txt" "$REMOTE_APP_DIR/../requirements.txt"
fi


# --- 3. Update Dependencies ---
echo "Updating Python dependencies..."
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r "$REMOTE_APP_DIR/../requirements.txt"
deactivate
echo "Dependencies updated successfully."

# --- 4. Set up PostgreSQL User and Database ---
echo "Configuring PostgreSQL..."
# Check if user and database exist, create if not.
# This is idempotent and safe to run multiple times.
sudo -u postgres psql -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'trading_user') THEN CREATE USER trading_user WITH PASSWORD 'your_secure_password_here'; END IF; END \$\$;"
sudo -u postgres psql -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_database WHERE datname = 'trading_bot') THEN CREATE DATABASE trading_bot OWNER trading_user; END IF; END \$\$;"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE trading_bot TO trading_user;"
echo "PostgreSQL configuration checked/updated."


# --- 5. Restart the Service ---
echo "Restarting the trading-bot service..."
sudo systemctl daemon-reload
sudo systemctl restart $SERVICE_NAME
echo "Service restarted."

# --- 6. Verify Service Status ---
echo "Waiting for service to initialize..."
sleep 5
sudo systemctl status $SERVICE_NAME --no-pager
journalctl -u $SERVICE_NAME -n 50 --no-pager

echo "--- Server-Side Fix Script Finished ---"
echo "Please check the status output above for any errors."

EOF

# Make the script executable
chmod +x "$RUN_ON_SERVER_SCRIPT"

echo "Generated $RUN_ON_SERVER_SCRIPT successfully."

# --- 3. Upload Files to Server ---
echo "Uploading package and script to the server..."
scp "$PACKAGE_NAME" "$RUN_ON_SERVER_SCRIPT" "$REMOTE_USER@$REMOTE_HOST:~/"
echo "Upload complete."

# --- 4. Instructions for User ---
echo ""
echo "--- DEPLOYMENT READY ---"
echo "The fix has been uploaded to your server."
echo "To complete the deployment, please log in to your server and run the script."
echo ""
echo "1. SSH into your server:"
echo "   ssh $REMOTE_USER@$REMOTE_HOST"
echo ""
echo "2. Once logged in, run the following command:"
echo "   ./$RUN_ON_SERVER_SCRIPT"
echo ""
echo "This will update the application, install dependencies, and restart the service."
echo "--------------------------"

# --- Cleanup ---
# rm "$PACKAGE_NAME"
# rm "$RUN_ON_SERVER_SCRIPT"

echo "Local script finished."
