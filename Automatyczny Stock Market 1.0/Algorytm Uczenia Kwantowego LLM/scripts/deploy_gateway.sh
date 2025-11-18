#!/bin/bash
set -euo pipefail

# Build Rust gateway and deploy to server
# Env: REMOTE_USER, REMOTE_HOST, SSHPASS/SUDO_PASSWORD optional

REMOTE_USER=${REMOTE_USER:-}
REMOTE_HOST=${REMOTE_HOST:-}
SUDO_PASSWORD=${SUDO_PASSWORD:-${SSHPASS:-}}

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "ERROR: REMOTE_USER and REMOTE_HOST are required." >&2
  exit 1
fi

pushd "$(dirname "$0")/../gateway" >/dev/null
if ! command -v cargo >/dev/null 2>&1; then
  echo "ERROR: Rust toolchain (cargo) not found locally." >&2
  exit 1
fi
cargo build --release
popd >/dev/null

BIN_PATH="$(dirname "$0")/../gateway/target/release/gateway"
SCP="scp"; SSH="ssh"
if [[ -n "${SSHPASS:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y sshpass || true
  fi
  if command -v sshpass >/dev/null 2>&1; then
    SCP="sshpass -p \"$SSHPASS\" scp -o StrictHostKeyChecking=no"
    SSH="sshpass -p \"$SSHPASS\" ssh -t -o StrictHostKeyChecking=no"
  fi
fi

TMPDIR_NAME="gw_$(date +%s)_$RANDOM"
$SSH "$REMOTE_USER@$REMOTE_HOST" "mkdir -p /tmp/$TMPDIR_NAME && echo $TMPDIR_NAME > /tmp/$TMPDIR_NAME/.name"
$SCP "$BIN_PATH" "$REMOTE_USER@$REMOTE_HOST:/tmp/$TMPDIR_NAME/gateway"
$SCP "$(dirname "$0")/../deploy/systemd/trading-gateway.service" "$REMOTE_USER@$REMOTE_HOST:/tmp/$TMPDIR_NAME/trading-gateway.service"
$SCP "$(dirname "$0")/../deploy/nginx/ase-bot.live-gateway.conf" "$REMOTE_USER@$REMOTE_HOST:/tmp/$TMPDIR_NAME/ase-bot.live-gateway.conf"

remote_cmd=$(cat <<'RSH'
set -euo pipefail
TMPDIR_NAME=$(ls -1dt /tmp/gw_* 2>/dev/null | head -n1 | xargs -I{} basename {} || true)
cd /
mkdir -p /opt/trading-bot/gateway
install -m 0755 /tmp/${TMPDIR_NAME}/gateway /opt/trading-bot/gateway/gateway
chmod +x /opt/trading-bot/gateway/gateway
mv /tmp/${TMPDIR_NAME}/trading-gateway.service /etc/systemd/system/trading-gateway.service
chown root:root /etc/systemd/system/trading-gateway.service
chmod 644 /etc/systemd/system/trading-gateway.service
systemctl daemon-reload
systemctl enable trading-gateway || true
mv /tmp/${TMPDIR_NAME}/ase-bot.live-gateway.conf /etc/nginx/sites-available/ase-bot.live-gateway.conf
ln -sf /etc/nginx/sites-available/ase-bot.live-gateway.conf /etc/nginx/sites-enabled/ase-bot.live-gateway.conf
# Remove old site to avoid conflicts
rm -f /etc/nginx/sites-enabled/ase-bot.live.conf || true
nginx -t
systemctl restart trading-gateway
systemctl restart nginx
sleep 2
systemctl status trading-gateway --no-pager | head -n 50 || true
curl -fsS http://127.0.0.1:8080/health || true
RSH
)

if [[ -n "$SUDO_PASSWORD" ]]; then
  $SSH "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash -lc $(printf '%q' "$remote_cmd")"
else
  $SSH "$REMOTE_USER@$REMOTE_HOST" "sudo bash -lc $(printf '%q' "$remote_cmd")"
fi

echo "Gateway deployed."


