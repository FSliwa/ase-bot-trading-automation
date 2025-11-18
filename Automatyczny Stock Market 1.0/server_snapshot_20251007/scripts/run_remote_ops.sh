#!/bin/bash
set -euo pipefail

# Remote ops: mergerfs test, clean backups, set GEMINI key, run Gemini test, gather metrics, verify health, clean stale files.
# Required env: REMOTE_USER, REMOTE_HOST
# Optional: SSHPASS (and SUDO_PASSWORD), GEMINI_API_KEY

REMOTE_USER=${REMOTE_USER:-}
REMOTE_HOST=${REMOTE_HOST:-}
SUDO_PASSWORD=${SUDO_PASSWORD:-${SSHPASS:-}}
GEMINI_API_KEY=${GEMINI_API_KEY:-}

if [[ -z "$REMOTE_USER" || -z "$REMOTE_HOST" ]]; then
  echo "ERROR: REMOTE_USER and REMOTE_HOST are required." >&2
  exit 1
fi

SCP="scp"
SSH="ssh"
if [[ -n "${SSHPASS:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    sudo apt-get update -y && sudo apt-get install -y sshpass || true
  fi
  if command -v sshpass >/dev/null 2>&1; then
    SCP="sshpass -p \"$SSHPASS\" scp -o StrictHostKeyChecking=no"
    SSH="sshpass -p \"$SSHPASS\" ssh -t -o StrictHostKeyChecking=no"
  fi
fi

REMOTE_SCRIPT=$(cat <<'RSH'
set -euo pipefail

echo "=== MERGERFS WRITE TEST ==="
TESTDIR="/mnt/storage/pool_test_$(date +%s)_$RANDOM"
mkdir -p "$TESTDIR"
for i in $(seq 1 10); do
  fallocate -l 10M "$TESTDIR/file_$i.bin" || dd if=/dev/zero of="$TESTDIR/file_$i.bin" bs=1M count=10 status=none
done
sleep 1

# Determine distribution between branches
IN_DATA=0; IN_ROOT=0
for f in "$TESTDIR"/*.bin; do
  REL="${f#/mnt/storage}"
  if [[ -f "/data$REL" ]]; then IN_DATA=$((IN_DATA+1)); fi
  if [[ -f "$REL" ]]; then IN_ROOT=$((IN_ROOT+1)); fi
done
echo "Files created: 10 | in /data: $IN_DATA | in / (root_storage): $IN_ROOT"

echo "Cleaning test files..."
rm -rf "/data${TESTDIR#/mnt/storage}" "$TESTDIR" "/${TESTDIR#/mnt/storage}" 2>/dev/null || true

echo "=== CLEAN BACKUPS ==="
if [[ -d /opt/trading-bot/backups ]]; then
  find /opt/trading-bot/backups -mindepth 1 -maxdepth 1 -type f -print -delete || true
  find /opt/trading-bot/backups -mindepth 1 -maxdepth 1 -type d -print -exec rm -rf {} + || true
fi

echo "=== SET GEMINI API KEY ==="
if [[ -n "__GEMINI_API_KEY__" ]]; then
  grep -q '^GEMINI_API_KEY=' /opt/trading-bot/.env 2>/dev/null && sed -i 's/^GEMINI_API_KEY=.*/GEMINI_API_KEY=__GEMINI_API_KEY__/g' /opt/trading-bot/.env || echo "GEMINI_API_KEY=__GEMINI_API_KEY__" >> /opt/trading-bot/.env
fi

echo "=== GEMINI TEST ==="
set +e
GEM_KEY="__GEMINI_API_KEY__"
/usr/bin/env GEMINI_API_KEY="$GEM_KEY" /opt/trading-bot/.venv/bin/python - <<'PY'
import os, asyncio, json, time
os.chdir('/opt/trading-bot')
os.environ.setdefault('GEMINI_API_KEY', os.getenv('GEMINI_API_KEY',''))
start=time.time()
try:
  from bot.gemini_analysis import GeminiAnalyzer
  ga = GeminiAnalyzer()
  if not ga.is_configured():
    print(json.dumps({"ok": False, "error": "Gemini not configured"}))
  else:
    resp = asyncio.run(ga.analyze_market({"exchange":"PrimeXBT","notional":1000}))
    ok = isinstance(resp, dict) and 'error' not in resp
    print(json.dumps({"ok": ok, "resp_keys": list(resp.keys()) if isinstance(resp, dict) else None, "elapsed_ms": int((time.time()-start)*1000)}))
except Exception as e:
  print(json.dumps({"ok": False, "error": str(e)}))
PY
set -e

echo "=== SERVER METRICS ==="
echo "-- uptime --"; uptime
echo "-- cpu --"; lscpu | sed -n '1,12p' || true
echo "-- mem --"; free -h || true
echo "-- disk df --"; df -h / /data /mnt/storage 2>/dev/null || df -h
echo "-- lsblk --"; lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT
echo "-- trading-bot service --"; systemctl is-active trading-bot || true
echo "-- uvicorn mem/cpu --"; ps -C python3 -o pid,%cpu,%mem,cmd --no-headers | grep uvicorn || true

echo "=== EXTERNAL HEALTH ==="
curl -fsSL -m 10 http://127.0.0.1:8009/health || true
curl -fsSL -m 10 http://ase-bot.live/health || true

echo "=== CLEAN STALE FILES ==="
find /opt/trading-bot -maxdepth 1 -type f \( -name 'trading_bot_update_*.tar.gz' -o -name 'trading-bot-deployment*.tar.gz' -o -name 'deployment_package*.tar.gz' \) -print -delete || true
find /opt/trading-bot/temp_pkg_dir -mindepth 1 -mtime +3 -print -exec rm -rf {} + 2>/dev/null || true

echo "=== DB URL IN USE ==="
grep -E '^(DATABASE_URL=|GEMINI_API_KEY=)' /opt/trading-bot/.env 2>/dev/null || true
python3 - <<'PY'
import os
print({"DATABASE_URL_runtime": os.getenv('DATABASE_URL','sqlite:///trading.db')})
PY
RSH
)

if [[ -n "$SUDO_PASSWORD" ]]; then
  $SSH "$REMOTE_USER@$REMOTE_HOST" "echo '$SUDO_PASSWORD' | sudo -S bash -lc $(printf '%q' "${REMOTE_SCRIPT//__GEMINI_API_KEY__/$GEMINI_API_KEY}")"
else
  $SSH "$REMOTE_USER@$REMOTE_HOST" "sudo bash -lc $(printf '%q' "${REMOTE_SCRIPT//__GEMINI_API_KEY__/$GEMINI_API_KEY}")"
fi

echo "--- Remote ops completed ---"


