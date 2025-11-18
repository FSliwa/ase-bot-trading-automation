#!/bin/bash
set -e

# Szybka naprawa serwera przez SSH
VPS_IP="185.70.196.214"
VPS_USER="admin"

echo "🚨 SZYBKA NAPRAWA SERWERA - zatrzymanie pętli awarii"
echo "=================================================="

# Wykonaj komendy na serwerze przez SSH
ssh ${VPS_USER}@${VPS_IP} << 'REMOTE_COMMANDS'
set -e

echo "🛑 Zatrzymywanie usługi trading-bot..."
sudo systemctl stop trading-bot
sudo systemctl disable trading-bot

echo "🧹 Czyszczenie procesów..."
sudo pkill -f "uvicorn" || true
sudo pkill -f "fastapi_app" || true

echo "📁 Sprawdzanie plików aplikacji..."
ls -la /opt/trading-bot/

echo "🔧 Ręczny test uruchomienia aplikacji..."
cd /opt/trading-bot

# Sprawdź czy plik aplikacji istnieje
if [ ! -f "fastapi_app.py" ]; then
    echo "❌ Brak pliku fastapi_app.py w /opt/trading-bot/"
    exit 1
fi

# Sprawdź czy venv istnieje
if [ ! -f ".venv/bin/python" ]; then
    echo "❌ Brak wirtualnego środowiska w /opt/trading-bot/.venv/"
    exit 1
fi

# Sprawdź czy .env.db istnieje
if [ ! -f ".env.db" ]; then
    echo "❌ Brak pliku .env.db w /opt/trading-bot/"
    exit 1
fi

echo "✅ Podstawowe pliki istnieją"

# Test ręcznego uruchomienia
echo "🧪 Test ręcznego uruchomienia aplikacji..."
timeout 10s sudo -u www-data .venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/trading-bot')
try:
    import fastapi_app
    print('✅ Import fastapi_app zakończony sukcesem')
except Exception as e:
    print(f'❌ Błąd podczas importu fastapi_app: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
" || echo "⚠️ Test zakończony (timeout lub błąd)"

echo "🔍 Sprawdzenie zmiennych środowiskowych w .env.db:"
grep -v "^#" .env.db | grep -v "^$" || true

REMOTE_COMMANDS

echo "✅ Szybka analiza zakończona"
