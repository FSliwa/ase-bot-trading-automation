#!/bin/bash
# INSTRUKCJE DO WYKONANIA NA SERWERZE
# Skopiuj i wklej te komendy jedna po drugiej na serwerze

echo "🚨 SZYBKA DIAGNOZA I NAPRAWA"
echo "=============================="

echo "1. Zatrzymywanie usługi i pętli awarii..."
sudo systemctl stop trading-bot
sudo systemctl disable trading-bot
sudo pkill -f "uvicorn" || true
sudo pkill -f "fastapi_app" || true

echo "2. Sprawdzanie plików aplikacji..."
cd /opt/trading-bot
ls -la

echo "3. Test importu aplikacji..."
sudo -u www-data .venv/bin/python -c "
import sys
sys.path.insert(0, '/opt/trading-bot')
print('Próba importu fastapi_app...')
try:
    import fastapi_app
    print('✅ Import fastapi_app zakończony sukcesem')
except Exception as e:
    print(f'❌ Błąd podczas importu: {e}')
    import traceback
    traceback.print_exc()
"

echo "4. Sprawdzanie zmiennych środowiskowych..."
if [ -f ".env.db" ]; then
    echo "Zawartość .env.db:"
    grep -v "^#" .env.db | grep -v "^$"
else
    echo "❌ Brak pliku .env.db"
fi

echo "5. Test startowania uvicorn..."
echo "Próba uruchomienia na 10 sekund..."
timeout 10s sudo -u www-data .venv/bin/python -m uvicorn fastapi_app:app --host 127.0.0.1 --port 8009 || echo "Test zakończony"

echo "✅ Diagnoza zakończona"
