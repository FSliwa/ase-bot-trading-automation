#!/bin/bash
# Server Startup Script - kompletny restart wszystkich usług

echo "🚀 ASE-Bot Server Startup Script"
echo "================================="

cd ~/trading-platform

# Funkcja logowania
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Zatrzymanie wszystkich konfliktowych procesów
stop_all_services() {
    log "Zatrzymywanie wszystkich usług..."
    
    # Python servers
    pkill -f "python.*4000" || true
    pkill -f "python.*3000" || true
    pkill -f "python.*8081" || true
    pkill -f "python.*8008" || true
    
    # Node servers
    pkill -f "node.*4000" || true
    pkill -f "node.*3000" || true
    pkill -f "node.*8081" || true
    pkill -f "node.*8008" || true
    
    sleep 2
    log "Usługi zatrzymane"
}

# Sprawdzenie portów
check_ports() {
    log "Sprawdzanie dostępności portów..."
    
    local ports=(4000 8012 8081)
    for port in "${ports[@]}"; do
        if netstat -tulpn 2>/dev/null | grep ":$port " >/dev/null; then
            log "⚠️  Port $port jest zajęty"
            lsof -ti:$port | xargs kill -9 2>/dev/null || true
        else
            log "✅ Port $port jest dostępny"
        fi
    done
}

# Uruchomienie głównego serwera
start_main_server() {
    log "Uruchamianie głównego serwera (port 4000)..."
    
    if [ -f "final_web_server.py" ]; then
        nohup python3 final_web_server.py > final_server.log 2>&1 &
        sleep 3
        
        if curl -s http://localhost:4000/health >/dev/null; then
            log "✅ Główny serwer uruchomiony"
        else
            log "❌ Problem z głównym serwerem"
            return 1
        fi
    else
        log "❌ Brak pliku final_web_server.py"
        return 1
    fi
}

# Uruchomienie SPA serwera (backup)
start_spa_server() {
    log "Uruchamianie SPA serwera (port 8081)..."
    
    if [ -f "robust_spa.cjs" ]; then
        nohup node robust_spa.cjs > spa_server.log 2>&1 &
        sleep 2
        
        if curl -s http://localhost:8081/ >/dev/null; then
            log "✅ SPA serwer uruchomiony"
        else
            log "⚠️  Problem z SPA serwerem"
        fi
    else
        log "⚠️  Brak pliku robust_spa.cjs"
    fi
}

# Sprawdzenie API backend
check_api_backend() {
    log "Sprawdzanie API backend (port 8012)..."
    
    if curl -s http://localhost:8012/health >/dev/null 2>&1; then
        log "✅ API backend działa"
    elif curl -s http://localhost:8012/ >/dev/null 2>&1; then
        log "✅ API backend odpowiada"
    else
        log "⚠️  API backend nie odpowiada - może wymagać uruchomienia"
        log "Sprawdzanie procesów FastAPI..."
        if ps aux | grep -v grep | grep -q "fastapi\|uvicorn"; then
            log "✅ FastAPI proces znaleziony"
        else
            log "❌ FastAPI proces nie znaleziony"
        fi
    fi
}

# Status wszystkich usług
show_status() {
    log "=== STATUS USŁUG ==="
    
    # Procesy
    echo "Aktywne procesy serwerów:"
    ps aux | grep -E "python.*[0-9]{4}|node.*[0-9]{4}|fastapi|uvicorn" | grep -v grep | while read line; do
        echo "  $line"
    done
    
    # Porty
    echo ""
    echo "Zajęte porty:"
    netstat -tulpn 2>/dev/null | grep -E ":4000|:8012|:8081|:3000|:80 " | while read line; do
        echo "  $line"
    done
    
    # Testy HTTP
    echo ""
    echo "Testy HTTP:"
    local endpoints=(
        "http://localhost:4000/health|Główny serwer"
        "http://localhost:8081/|SPA serwer" 
        "http://localhost:8012/health|API backend"
    )
    
    for endpoint in "${endpoints[@]}"; do
        url=$(echo "$endpoint" | cut -d'|' -f1)
        name=$(echo "$endpoint" | cut -d'|' -f2)
        
        if curl -s "$url" >/dev/null 2>&1; then
            echo "  ✅ $name: $url"
        else
            echo "  ❌ $name: $url"
        fi
    done
}

# Generowanie info o dostępie
generate_access_info() {
    log "Generowanie informacji o dostępie..."
    
    cat > ACCESS_INFO.txt << EOF
ASE-Bot Trading Platform - Informacje o dostępie
===============================================

Data: $(date)

DOSTĘP GŁÓWNY:
- Główna aplikacja: http://185.70.198.201:4000
- Przez domenę: http://ase-bot.live:4000  (gdy nginx skonfigurowany)
- Admin panel: http://185.70.198.201:4000/admin/

ALTERNATYWNE DOSTĘPY:
- SPA serwer: http://185.70.198.201:8081
- Przez domenę: http://ase-bot.live:8081

API ENDPOINTS:
- Health check: http://185.70.198.201:4000/health
- API backend: http://185.70.198.201:4000/api/*

STATUS USŁUG:
$(show_status)

LOGI:
- Główny serwer: ~/trading-platform/final_server.log
- SPA serwer: ~/trading-platform/spa_server.log

UWAGI:
- HTTPS (port 443) jest zablokowany - używaj HTTP
- Nginx wymaga sudo do konfiguracji
- Wszystkie usługi działają na HTTP

EOF

    log "✅ Informacje zapisane w ACCESS_INFO.txt"
}

# Główna funkcja
main() {
    log "Rozpoczynanie pełnego restartu systemu..."
    
    stop_all_services
    check_ports
    
    # Uruchomienie serwisów
    if start_main_server; then
        log "✅ Główny system uruchomiony"
    else
        log "❌ Problem z głównym systemem"
        exit 1
    fi
    
    start_spa_server
    check_api_backend
    
    # Status i info
    show_status
    generate_access_info
    
    log "🎉 Server startup completed!"
    log "Główny dostęp: http://185.70.198.201:4000"
    log "Sprawdź ACCESS_INFO.txt dla szczegółów"
}

# Uruchomienie
main "$@"
