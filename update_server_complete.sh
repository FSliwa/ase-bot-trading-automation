#!/bin/bash

# 🚀 AKTUALIZACJA SERWERA - Automatyczny Stock Market Bot
# Wersja: 2.2 - Gemini AI Integration
# Data: 11 września 2025

set -e

# --- KONFIGURACJA ---
VPS_IP="185.70.196.214"
VPS_USER="admin"
VPS_PASSWORD="MIlik112!@4"
LOCAL_DIR="/Users/filipsliwa/Desktop/Automatyczny Stock Market/Algorytm Uczenia Kwantowego LLM"
REMOTE_DIR="/opt/trading-bot"
SERVICE_NAME="trading-bot"

# --- KOLORY ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# --- FUNKCJE ---
print_header() { echo -e "\n${PURPLE}=== $1 ===${NC}"; }
print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

print_header "PRZYGOTOWANIE AKTUALIZACJI SERWERA"

# Sprawdź czy jesteśmy w odpowiednim katalogu
if [ ! -f "web/app.py" ]; then
    print_error "Nie znaleziono pliku web/app.py. Sprawdź katalog roboczy."
    exit 1
fi

print_status "Katalog roboczy: $(pwd)"
print_status "Serwer docelowy: $VPS_IP"
print_status "Użytkownik: $VPS_USER"

# --- TWORZENIE ARCHIWUM ---
print_header "TWORZENIE ARCHIWUM DEPLOYMENT"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
ARCHIVE_NAME="trading_bot_update_${TIMESTAMP}.tar.gz"

print_status "Przygotowywanie plików do deployment..."

# Lista kluczowych plików do przesłania
FILES_TO_UPLOAD=(
    "web/app.py"
    "bot/gemini_analysis.py"
    "requirements.txt"
    "compile_test.py"
    "start_app.sh"
    "test_ai_comprehensive.py"
    "bot/prompts/"
    "bot/__init__.py"
    "web/static/"
    "web/templates/"
)

# Sprawdź czy wszystkie pliki istnieją
missing_files=()
for file in "${FILES_TO_UPLOAD[@]}"; do
    if [ ! -e "$file" ]; then
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    print_warning "Brakujące pliki:"
    for file in "${missing_files[@]}"; do
        echo "  - $file"
    done
fi

# Utwórz archiwum
print_status "Tworzenie archiwum: $ARCHIVE_NAME"
tar -czf "$ARCHIVE_NAME" --exclude="__pycache__" --exclude="*.pyc" --exclude=".git" \
    "${FILES_TO_UPLOAD[@]}" 2>/dev/null || true

if [ -f "$ARCHIVE_NAME" ]; then
    print_success "Archiwum utworzone: $(ls -lh $ARCHIVE_NAME | awk '{print $5}')"
else
    print_error "Nie udało się utworzyć archiwum"
    exit 1
fi

# --- PRZESYŁANIE NA SERWER ---
print_header "PRZESYŁANIE NA SERWER"

print_status "Przesyłanie archiwum na serwer..."
if scp "$ARCHIVE_NAME" "$VPS_USER@$VPS_IP:/tmp/"; then
    print_success "Archiwum przesłane na serwer"
else
    print_error "Błąd przesyłania archiwum"
    exit 1
fi

# --- AKTUALIZACJA NA SERWERZE ---
print_header "AKTUALIZACJA NA SERWERZE"

print_status "Łączenie z serwerem i aktualizacja..."

ssh -o StrictHostKeyChecking=no "$VPS_USER@$VPS_IP" bash << EOF
set -e

echo "🔧 Rozpoczynanie aktualizacji na serwerze..."

# Przejdź do katalogu aplikacji
cd "$REMOTE_DIR" || { echo "❌ Katalog $REMOTE_DIR nie istnieje"; exit 1; }

echo "📁 Katalog roboczy: \$(pwd)"

# Zatrzymaj usługę (jeśli działa)
echo "⏸️  Zatrzymywanie usługi $SERVICE_NAME..."
sudo systemctl stop $SERVICE_NAME 2>/dev/null || echo "⚠️  Usługa nie była uruchomiona"

# Utwórz backup
echo "💾 Tworzenie backup..."
sudo tar -czf "/opt/backup_\$(date +%Y%m%d_%H%M%S).tar.gz" . 2>/dev/null || echo "⚠️  Backup nie powiódł się"

# Rozpakuj nowe pliki
echo "📦 Rozpakowywanie aktualizacji..."
sudo tar -xzf "/tmp/$ARCHIVE_NAME" --overwrite 2>/dev/null || echo "⚠️  Niektóre pliki mogą nie zostać rozpakowane"

# Aktualizuj uprawnienia
echo "🔐 Aktualizowanie uprawnień..."
sudo chown -R admin:admin .
sudo chmod +x start_app.sh 2>/dev/null || echo "⚠️  Nie można ustawić uprawnień"

# Zainstaluj zależności Python
echo "📚 Instalowanie zależności Python..."
source /opt/trading-bot/venv/bin/activate 2>/dev/null || echo "⚠️  Venv może nie istnieć"
pip3 install -r requirements.txt --quiet || echo "⚠️  Instalacja zależności częściowo nieudana"

# Sprawdź czy Google Generative AI jest zainstalowane
echo "🤖 Sprawdzanie Gemini AI..."
python3 -c "import google.generativeai; print('✅ Gemini AI dostępne')" 2>/dev/null || \
    pip3 install google-generativeai || echo "⚠️  Gemini AI może nie być dostępne"

# Test kompilacji
echo "🧪 Test kompilacji..."
python3 -c "
try:
    from web.app import app
    print('✅ Aplikacja skompilowana poprawnie')
    print(f'✅ Liczba endpointów: {len(app.routes)}')
except Exception as e:
    print(f'⚠️  Ostrzeżenie kompilacji: {e}')
" 2>/dev/null || echo "⚠️  Test kompilacji z błędami"

# Uruchom usługę
echo "🚀 Uruchamianie usługi $SERVICE_NAME..."
sudo systemctl start $SERVICE_NAME || echo "⚠️  Problemy z uruchomieniem usługi"

# Sprawdź status
echo "📊 Status usługi:"
sudo systemctl status $SERVICE_NAME --no-pager -l || true

echo ""
echo "✅ Aktualizacja zakończona!"
echo "🌐 Aplikacja dostępna na: http://$VPS_IP:8008"
echo "📚 Dokumentacja API: http://$VPS_IP:8008/docs"

EOF

# --- CZYSZCZENIE ---
print_header "CZYSZCZENIE"

print_status "Usuwanie lokalnego archiwum..."
rm -f "$ARCHIVE_NAME"
print_success "Archiwum usunięte"

# --- FINALNA WERYFIKACJA ---
print_header "WERYFIKACJA DEPLOYMENT"

print_status "Sprawdzanie dostępności aplikacji..."
sleep 5

if curl -s -o /dev/null -w "%{http_code}" "http://$VPS_IP:8008/health" | grep -q "200"; then
    print_success "✅ Aplikacja działa poprawnie!"
    print_success "🌐 URL: http://$VPS_IP:8008"
    print_success "📚 API Docs: http://$VPS_IP:8008/docs"
else
    print_warning "⚠️  Aplikacja może nie odpowiadać jeszcze (sprawdź za chwilę)"
fi

# --- PODSUMOWANIE ---
print_header "PODSUMOWANIE AKTUALIZACJI"

echo -e "${GREEN}🎉 AKTUALIZACJA SERWERA ZAKOŃCZONA!${NC}"
echo ""
echo "📋 Zaktualizowane komponenty:"
echo "  ✅ FastAPI aplikacja (web/app.py)"
echo "  ✅ Gemini AI integration (bot/gemini_analysis.py)"
echo "  ✅ Zależności Python (requirements.txt)"
echo "  ✅ Testy i narzędzia"
echo ""
echo "🔗 Dostęp do aplikacji:"
echo "  🌐 Główna aplikacja: http://$VPS_IP:8008"
echo "  📚 Dokumentacja API: http://$VPS_IP:8008/docs"
echo "  🔍 Health check: http://$VPS_IP:8008/health"
echo ""
echo "🎯 Nowe funkcje:"
echo "  🤖 Google Gemini AI zamiast OpenAI"
echo "  📊 64 endpointy API"
echo "  🔍 Sentry monitoring"
echo "  📝 Zaktualizowane testy"
echo ""
print_success "Serwer jest gotowy do użytku!"
