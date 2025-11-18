#!/bin/bash
set -euo pipefail

REMOTE_USER="admin"
REMOTE_HOST="185.70.198.201"
REMOTE_DIR="/opt/trading-bot"
PACKAGE="asebot-backend-20251012-updated.tar.gz"
REMOTE_PACKAGE="/tmp/asebot-backend-20251012-updated.tar.gz"
REMOTE_SCRIPT="/tmp/run_updated_backend.sh"

if [[ ! -f "$PACKAGE" ]]; then
  echo "Package $PACKAGE not found in $(pwd)" >&2
  exit 1
fi

echo "--- Uploading $PACKAGE to $REMOTE_USER@$REMOTE_HOST ---"
scp "$PACKAGE" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PACKAGE}"

echo "--- Uploading remote deployment script ---"
cat <<'EOF' | ssh "${REMOTE_USER}@${REMOTE_HOST}" "cat > ${REMOTE_SCRIPT} && chmod +x ${REMOTE_SCRIPT}"
#!/bin/bash
set -euo pipefail

REMOTE_DIR="/opt/trading-bot"
PACKAGE="/tmp/asebot-backend-20251012-updated.tar.gz"
SERVICE_NAME="trading-bot"
VENV_DIR="$REMOTE_DIR/.venv"

if [[ ! -f "$PACKAGE" ]]; then
  echo "Package $PACKAGE missing" >&2
  exit 1
fi

if [[ -z "$REMOTE_DIR" || "$REMOTE_DIR" == "/" ]]; then
  echo "REMOTE_DIR is invalid" >&2
  exit 1
fi

echo "--- Starting deployment on $(hostname) ---"

if systemctl list-units --full -all | grep -q "${SERVICE_NAME}.service"; then
  echo "Stopping ${SERVICE_NAME} service"
  systemctl stop "${SERVICE_NAME}" || true
fi

echo "Ensuring target directory exists"
mkdir -p "$REMOTE_DIR"

if [[ -d "$REMOTE_DIR" ]]; then
  echo "Creating timestamped backup"
  BACKUP_DIR="${REMOTE_DIR}-backup-$(date +%Y%m%d-%H%M%S)"
  cp -a "$REMOTE_DIR" "$BACKUP_DIR" || echo "Backup failed (continuing)"
fi

echo "Cleaning old deployment (preserving .env)"
find "$REMOTE_DIR" -mindepth 1 -maxdepth 1 ! -name ".env" -exec rm -rf {} +

echo "Unpacking new package"
tar -xzf "$PACKAGE" -C "$REMOTE_DIR"

echo "Ensuring python3-venv is installed"
apt-get update -y >/dev/null
apt-get install -y python3.12-venv >/dev/null

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "Creating venv in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
pip install --upgrade pip >/dev/null
pip install -r "$REMOTE_DIR/requirements.txt"

deactivate || true

echo "Setting ownership to tradingbot:tradingbot"
chown -R tradingbot:tradingbot "$REMOTE_DIR" || true
chmod -R 775 "$REMOTE_DIR"

if systemctl list-units --full -all | grep -q "${SERVICE_NAME}.service"; then
  echo "Starting ${SERVICE_NAME} service"
  systemctl start "${SERVICE_NAME}"
  sleep 5
  systemctl status "${SERVICE_NAME}" --no-pager
else
  echo "Warning: service ${SERVICE_NAME} not found"
fi

echo "Deployment completed"
EOF

echo "--- Executing remote deployment script (sudo) ---"
ssh -t "${REMOTE_USER}@${REMOTE_HOST}" "sudo bash ${REMOTE_SCRIPT}"

echo "--- Remote deployment done. Cleaning temporary script ---"
ssh "${REMOTE_USER}@${REMOTE_HOST}" "rm -f ${REMOTE_SCRIPT}"

echo "Deployment workflow finished"
