#!/bin/bash
set -euo pipefail

# Fix backend service and nginx on remote host.
# Env:
#   REMOTE_USER, REMOTE_HOST (required)
#   SSHPASS (optional) for password auth; also used for sudo if SUDO_PASSWORD not set
#   SUDO_PASSWORD (optional)

REMOTE_USER=${REMOTE_USER:-}
REMOTE_HOST=${REMOTE_HOST:-}
SUDO_PASSWORD=${SUDO_PASSWORD:-${SSHPASS:-}}

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "ERROR: REMOTE_USER and REMOTE_HOST are required." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

SCP="scp"
SSH="ssh"
if [[ -n "${SSHPASS:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "Installing sshpass locally (requires sudo)..."
    sudo apt-get update -y && sudo apt-get install -y sshpass || true
  fi
  if command -v sshpass >/dev/null 2>&1; then
    SCP="sshpass -p \"$SSHPASS\" scp -o StrictHostKeyChecking=no"
    SSH="sshpass -p \"$SSHPASS\" ssh -o StrictHostKeyChecking=no"
  else
    echo "WARNING: sshpass not available; interactive auth may be required."
  fi
fi

echo "--- Preparing remote temp directory ---"
TMPDIR_NAME="webfix_$(date +%s)_$RANDOM"
$SSH -t "$REMOTE_USER@$REMOTE_HOST" "mkdir -p /tmp/$TMPDIR_NAME && chmod 777 /tmp/$TMPDIR_NAME && echo $TMPDIR_NAME > /tmp/$TMPDIR_NAME/.name"

echo "--- Uploading service and nginx configs ---"
if ! $SCP "$SCRIPT_DIR/../deploy/systemd/trading-bot.service" "$REMOTE_USER@$REMOTE_HOST:/tmp/$TMPDIR_NAME/trading-bot.service"; then
  echo "WARNING: SCP to /tmp may be restricted; retrying to home and moving with sudo."
  $SCP "$SCRIPT_DIR/../deploy/systemd/trading-bot.service" "$REMOTE_USER@$REMOTE_HOST:trading-bot.service"
  $SCP "$SCRIPT_DIR/../deploy/nginx/ase-bot.live.conf" "$REMOTE_USER@$REMOTE_HOST:ase-bot.live.conf"
  # Move into /tmp/$TMPDIR_NAME
  if [[ -n "$SUDO_PASSWORD" ]]; then
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "mkdir -p /tmp/$TMPDIR_NAME && echo '$SUDO_PASSWORD' | sudo -S mv ~/trading-bot.service /tmp/$TMPDIR_NAME/ && echo '$SUDO_PASSWORD' | sudo -S mv ~/ase-bot.live.conf /tmp/$TMPDIR_NAME/ && echo $TMPDIR_NAME > /tmp/$TMPDIR_NAME/.name"
  else
    $SSH -t "$REMOTE_USER@$REMOTE_HOST" "mkdir -p /tmp/$TMPDIR_NAME && sudo mv ~/trading-bot.service /tmp/$TMPDIR_NAME/ && sudo mv ~/ase-bot.live.conf /tmp/$TMPDIR_NAME/ && echo $TMPDIR_NAME > /tmp/$TMPDIR_NAME/.name"
  fi
else
  $SCP "$SCRIPT_DIR/../deploy/nginx/ase-bot.live.conf" "$REMOTE_USER@$REMOTE_HOST:/tmp/$TMPDIR_NAME/ase-bot.live.conf"
fi

remote_fix=$(cat <<RSH
set -euo pipefail

# Read shared tmpdir name if available
if [[ -f /tmp/*/.name ]]; then
  TMPDIR_NAME=$(cat /tmp/*/.name || true)
fi
TMPDIR_NAME="${TMPDIR_NAME:-}"
if [[ -z "$TMPDIR_NAME" ]]; then
  # Fallback: try to detect our directory by pattern
  TMPDIR_NAME=$(ls -1dt /tmp/webfix_* 2>/dev/null | head -n1 | xargs -I{} basename {} || true)
fi

if command -v systemctl >/dev/null; then
  has_systemd=1
else
  echo "systemctl not found" >&2; exit 1
fi

# Ensure target dirs
mkdir -p /etc/systemd/system
mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled

# Install service
mv "/tmp/${TMPDIR_NAME}/trading-bot.service" /etc/systemd/system/trading-bot.service
chown root:root /etc/systemd/system/trading-bot.service
chmod 644 /etc/systemd/system/trading-bot.service

# Ensure 'tradingbot' user exists
if ! id -u tradingbot >/dev/null 2>&1; then
  useradd --system --create-home --home-dir /home/tradingbot --shell /usr/sbin/nologin tradingbot || true
fi

# Enable service
systemctl daemon-reload
systemctl enable trading-bot.service || true

# Install nginx site and disable duplicates
mv "/tmp/${TMPDIR_NAME}/ase-bot.live.conf" /etc/nginx/sites-available/ase-bot.live.conf
chown root:root /etc/nginx/sites-available/ase-bot.live.conf
chmod 644 /etc/nginx/sites-available/ase-bot.live.conf
ln -sf /etc/nginx/sites-available/ase-bot.live.conf /etc/nginx/sites-enabled/ase-bot.live.conf

# Remove other default or duplicate server_name entries that conflict
if [[ -f /etc/nginx/sites-enabled/default ]]; then rm -f /etc/nginx/sites-enabled/default; fi
# Remove any old 'trading-bot' symlink to avoid duplicate default_server errors
if [[ -f /etc/nginx/sites-enabled/trading-bot ]]; then rm -f /etc/nginx/sites-enabled/trading-bot; fi
find /etc/nginx/sites-enabled -type l ! -name 'ase-bot.live.conf' -exec rm -f {} +

# Check app files
if [[ ! -f /opt/trading-bot/fastapi_app.py ]]; then
  echo "ERROR: fastapi_app.py not found under /opt/trading-bot" >&2
fi

# Force external Postgres in .env
if [[ -f /opt/trading-bot/.env ]]; then
  if grep -q '^DATABASE_URL=' /opt/trading-bot/.env; then
    sed -i 's#^DATABASE_URL=.*#DATABASE_URL=postgresql+psycopg2://upadmin:AVNS_ynqNx-mSYLQXZiCgbhi@public-automatic-stock-exchange-bot-hhiyptsoiomb.db.upclouddatabases.com:11569/defaultdb?sslmode=require#g' /opt/trading-bot/.env
  else
    echo 'DATABASE_URL=postgresql+psycopg2://upadmin:AVNS_ynqNx-mSYLQXZiCgbhi@public-automatic-stock-exchange-bot-hhiyptsoiomb.db.upclouddatabases.com:11569/defaultdb?sslmode=require' >> /opt/trading-bot/.env
  fi
fi

# Restart services
nginx -t
systemctl restart nginx
systemctl restart trading-bot || true
sleep 4
systemctl status trading-bot --no-pager | head -n 50 || true

curl -fsS http://127.0.0.1:8009/health || true
RSH
)

echo "--- Applying remote fixes ---"
if [[ -n "$SUDO_PASSWORD" ]]; then
  $SSH -t "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash -lc $(printf '%q' "$remote_fix")"
else
  $SSH -t "$REMOTE_USER@$REMOTE_HOST" "sudo bash -lc $(printf '%q' "$remote_fix")"
fi

echo "--- Done. Verify via: curl -I http://ase-bot.live/health ---"


