#!/bin/bash
# Automatyczny Bot Tradingowy - Skrypt Uruchomieniowy

echo "🤖 Automatyczny Bot Tradingowy"
echo "================================"

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
    echo ""
    echo "❗ WAŻNE: Edytuj plik 'Algorytm Uczenia Kwantowego LLM/.env' i wprowadź swoje klucze API!"
    echo "   Następnie uruchom skrypt ponownie."
    exit 1
fi

# Uruchom bota
echo ""
echo "🚀 Uruchamianie bota..."
echo "   (Naciśnij Ctrl+C aby zatrzymać)"
echo ""

cd "Algorytm Uczenia Kwantowego LLM"
python start_bot.py
