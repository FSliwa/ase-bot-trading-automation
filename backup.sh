#!/bin/bash
# Trading Bot automated backup script
# - Dumps PostgreSQL database (if configured)
# - Archives config and data files
# - Applies retention policy

set -euo pipefail

BACKUP_DIR="/opt/trading-bot/backups"
LOG_DIR="/opt/trading-bot/logs"
ENV_FILE="/opt/trading-bot/.env.db"
RETENTION_DAYS="14"

mkdir -p "$BACKUP_DIR" "$LOG_DIR"
chmod 750 "$BACKUP_DIR"

TS=$(date +%Y%m%d_%H%M%S)
LOG_FILE="$LOG_DIR/backup_$TS.log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "[INFO] Starting backup at $TS"

# Load environment if present (PostgreSQL credentials etc.)
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "[WARN] Env file not found: $ENV_FILE"
fi

# Database backup (PostgreSQL)
if [ -n "${POSTGRES_PASSWORD:-}" ] && [ -n "${POSTGRES_DB:-}" ]; then
  echo "[INFO] Dumping PostgreSQL database: $POSTGRES_DB"
  export PGPASSWORD="$POSTGRES_PASSWORD"
  DB_FILE="$BACKUP_DIR/pg_${POSTGRES_DB}_${TS}.sql.gz"
  if command -v pg_dump >/dev/null 2>&1; then
    pg_dump -h "${POSTGRES_HOST:-localhost}" -p "${POSTGRES_PORT:-5432}" -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB}" | gzip -9 > "$DB_FILE"
    echo "[OK] DB dump created: $DB_FILE"
  else
    echo "[WARN] pg_dump not found, skipping DB backup"
  fi
else
  echo "[INFO] PostgreSQL not configured, skipping DB backup"
fi

# Config and data backup
CFG_ARCHIVE="$BACKUP_DIR/config_${TS}.tar.gz"
INCLUDE=("/opt/trading-bot/.env.db" \
         "/opt/trading-bot/users.json" \
         "/opt/trading-bot/nginx_8009.conf" \
         "/opt/trading-bot/fastapi_app.py" \
         "/opt/trading-bot/requirements.txt")

# Only include existing files
EXISTING=()
for f in "${INCLUDE[@]}"; do
  [ -e "$f" ] && EXISTING+=("$f")
done

if [ ${#EXISTING[@]} -gt 0 ]; then
  tar -czf "$CFG_ARCHIVE" "${EXISTING[@]}"
  echo "[OK] Config archive created: $CFG_ARCHIVE"
else
  echo "[WARN] No config files to archive"
fi

# Retention policy
find "$BACKUP_DIR" -type f -mtime +"$RETENTION_DAYS" -print -delete || true

echo "[INFO] Backup completed"
