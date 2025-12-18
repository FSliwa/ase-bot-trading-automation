#!/bin/bash
#
# Unified launcher for the FastAPI backend.
#
# This script mirrors the behaviour expected by deployment tooling,
# compile tests and earlier documentation.  It creates (or reuses)
# a local Python virtual environment, installs dependencies from
# ``requirements.txt`` and then starts Uvicorn with the application
# exposed under ``web.app:app``.

set -euo pipefail

EMOJI_START="🚀"
EMOJI_INFO="ℹ️ "
EMOJI_WARN="⚠️ "
EMOJI_OK="✅"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="${VENV_DIR:-$SCRIPT_DIR/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIREMENTS_FILE="${REQUIREMENTS_FILE:-requirements.txt}"

APP_HOST="${APP_HOST:-0.0.0.0}"
APP_PORT="${APP_PORT:-8008}"
UVICORN_RELOAD="${UVICORN_RELOAD:-false}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"
EXTRA_UVICORN_ARGS=("${EXTRA_UVICORN_ARGS[@]:-}")

printf "%s FastAPI Trading Platform Launcher\n" "$EMOJI_START"
printf "===============================================\n"
printf "%s Working directory: %s\n" "$EMOJI_INFO" "$SCRIPT_DIR"

# 1. Ensure virtual environment exists
if [[ ! -d "$VENV_DIR" ]]; then
    printf "%s Tworzenie środowiska wirtualnego w %s...\n" "$EMOJI_INFO" "$VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# 2. Activate environment
source "$VENV_DIR/bin/activate"

# 3. Upgrade pip/setuptools wheel quietly to avoid noisy output
printf "%s Aktualizacja narzędzi pakietujących...\n" "$EMOJI_INFO"
pip install --upgrade pip setuptools wheel >/dev/null

# 4. Install dependencies from requirements file
if [[ -f "$REQUIREMENTS_FILE" ]]; then
    printf "%s Instalacja zależności z %s...\n" "$EMOJI_INFO" "$REQUIREMENTS_FILE"
    pip install -r "$REQUIREMENTS_FILE"
else
    printf "%s Brak pliku %s - kontynuuję bez instalacji zależności.\n" "$EMOJI_WARN" "$REQUIREMENTS_FILE"
fi

# 5. Optional Alembic migrations (disabled by default, enable via env)
if [[ "${RUN_DB_MIGRATIONS:-false}" == "true" ]]; then
    if command -v alembic >/dev/null 2>&1; then
        printf "%s Wykonywanie migracji bazy danych...\n" "$EMOJI_INFO"
        alembic upgrade head || printf "%s Migracje nie powiodły się, kontynuuję.\n" "$EMOJI_WARN"
    else
        printf "%s Narzędzie Alembic nie jest zainstalowane - pomijam migracje.\n" "$EMOJI_WARN"
    fi
fi

# 6. Prepare Uvicorn arguments
UVICORN_CMD=("uvicorn" "web.app:app" "--host" "$APP_HOST" "--port" "$APP_PORT")

if [[ "$UVICORN_RELOAD" =~ ^(1|true|TRUE|yes|on)$ ]]; then
    UVICORN_CMD+=("--reload")
fi

if [[ "$UVICORN_WORKERS" =~ ^[0-9]+$ && "$UVICORN_WORKERS" -gt 1 ]]; then
    UVICORN_CMD+=("--workers" "$UVICORN_WORKERS")
fi

if [[ ${#EXTRA_UVICORN_ARGS[@]} -gt 0 ]]; then
    UVICORN_CMD+=("${EXTRA_UVICORN_ARGS[@]}")
fi

printf "%s Uruchamianie serwera Uvicorn (host=%s port=%s reload=%s workers=%s)\n" \
       "$EMOJI_START" "$APP_HOST" "$APP_PORT" "$UVICORN_RELOAD" "$UVICORN_WORKERS"

exec "${UVICORN_CMD[@]}"
