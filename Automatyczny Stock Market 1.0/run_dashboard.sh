#!/bin/bash
# Dashboard UI - Panel kontrolny

echo "📊 Trading Bot Dashboard"
echo "========================"

# Przejdź do katalogu projektu
cd "$(dirname "$0")"

# Sprawdź czy istnieje środowisko wirtualne
if [ ! -d ".venv" ]; then
    echo "📦 Tworzenie środowiska wirtualnego..."
    python3 -m venv .venv
fi

# Aktywuj środowisko
echo "🔧 Aktywacja środowiska..."
source .venv/bin/activate

# Zainstaluj zależności
echo "📚 Instalacja/aktualizacja zależności..."
pip install -r "Algorytm Uczenia Kwantowego LLM/requirements.txt" --quiet

# Sprawdź czy istnieje plik .env
if [ ! -f "Algorytm Uczenia Kwantowego LLM/.env" ]; then
    echo ""
    echo "⚠️  UWAGA: Nie znaleziono pliku .env!"
    echo "📝 Kopiuję przykładową konfigurację..."
    cp "Algorytm Uczenia Kwantowego LLM/env.example" "Algorytm Uczenia Kwantowego LLM/.env"
fi

# Uruchom dashboard
echo ""
echo "🚀 Uruchamianie dashboardu..."

# Load environment variables and get port
source "Algorytm Uczenia Kwantowego LLM/.env" 2>/dev/null || true
APP_PORT=${APP_PORT:-8008}

echo "   Otwórz w przeglądarce: http://localhost:$APP_PORT"
echo "   (Naciśnij Ctrl+C aby zatrzymać)"
echo ""

cd "Algorytm Uczenia Kwantowego LLM"
python -m uvicorn web.app:app --host 0.0.0.0 --port $APP_PORT --reload
