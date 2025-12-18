#!/bin/bash
# ASE-Bot Emergency Recovery Script
# Skrypt do przywracania funkcjonalności po problemach z serwerem

echo "🚨 ASE-Bot Emergency Recovery Script"
echo "====================================="

# Funkcja logowania
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# Sprawdzenie połączenia z serwerem
check_server_connection() {
    log "Sprawdzanie połączenia z serwerem..."
    
    if ping -c 3 185.70.198.201 >/dev/null 2>&1; then
        log "✅ Ping do serwera - OK"
        return 0
    else
        log "❌ Serwer nie odpowiada na ping"
        return 1
    fi
}

# Sprawdzenie SSH
check_ssh_connection() {
    log "Sprawdzanie połączenia SSH..."
    
    if timeout 10 ssh -o ConnectTimeout=5 admin@185.70.198.201 'echo "SSH OK"' >/dev/null 2>&1; then
        log "✅ SSH działa"
        return 0
    else
        log "❌ SSH nie działa"
        return 1
    fi
}

# Sprawdzenie portów HTTP
check_http_ports() {
    log "Sprawdzanie portów HTTP..."
    
    local ports=(80 8008 8081 3000 4000)
    local working_ports=()
    
    for port in "${ports[@]}"; do
        if curl -s -I "http://185.70.198.201:$port/" | head -1 | grep -q "200\|301\|302"; then
            log "✅ Port $port - działa"
            working_ports+=($port)
        else
            log "❌ Port $port - nie działa"
        fi
    done
    
    if [ ${#working_ports[@]} -gt 0 ]; then
        log "🌐 Dostępne porty: ${working_ports[*]}"
        return 0
    else
        log "❌ Żaden port HTTP nie działa"
        return 1
    fi
}

# Sprawdzenie domeny
check_domain() {
    log "Sprawdzanie domeny..."
    
    # DNS resolution
    if nslookup ase-bot.live >/dev/null 2>&1; then
        log "✅ DNS ase-bot.live - rozwiązywanie OK"
    else
        log "❌ Problem z DNS"
    fi
    
    # HTTP access
    if curl -s -I "http://ase-bot.live/" | head -1 | grep -q "200\|301\|302"; then
        log "✅ HTTP ase-bot.live - działa"
    else
        log "❌ HTTP ase-bot.live - nie działa"
    fi
    
    # HTTPS access (prawdopodobnie nie działa)
    if curl -s -I "https://ase-bot.live/" | head -1 | grep -q "200\|301\|302"; then
        log "✅ HTTPS ase-bot.live - działa"
    else
        log "⚠️  HTTPS ase-bot.live - nie działa (znany problem)"
    fi
}

# Deployment gdy serwer jest dostępny
deploy_when_available() {
    log "🚀 Rozpoczynanie wdrożenia..."
    
    # Upload plików
    log "Przesyłanie plików konfiguracyjnych..."
    scp final_web_server.py admin@185.70.198.201:~/trading-platform/
    scp emergency_nginx.conf admin@185.70.198.201:~/trading-platform/
    scp server_startup.sh admin@185.70.198.201:~/trading-platform/
    
    # Uruchomienie na serwerze
    ssh admin@185.70.198.201 "
        cd ~/trading-platform
        
        echo '=== EMERGENCY DEPLOYMENT ==='
        
        # Zatrzymanie konfliktowych procesów
        pkill -f 'python.*4000' || true
        pkill -f 'node.*4000' || true
        
        # Uruchomienie głównego serwera
        nohup python3 final_web_server.py > final_server.log 2>&1 &
        sleep 2
        
        # Sprawdzenie czy działa
        if curl -s http://localhost:4000/health > /dev/null; then
            echo '✅ Final server uruchomiony na porcie 4000'
        else
            echo '❌ Problem z uruchomieniem final server'
        fi
        
        # Status wszystkich usług
        echo '=== STATUS USŁUG ==='
        ps aux | grep -E 'python.*[0-9]{4}|node.*[0-9]{4}' | grep -v grep
        
        echo '=== DOSTĘP ==='
        echo 'HTTP: http://185.70.198.201:4000'
        echo 'Domena: http://ase-bot.live:4000'
        echo 'Admin: http://185.70.198.201:4000/admin/'
    "
}

# Główna funkcja
main() {
    log "Rozpoczynanie diagnostyki..."
    
    # Sprawdzenia połączenia
    if ! check_server_connection; then
        log "🔴 KRYTYCZNE: Brak połączenia z serwerem"
        log "Możliwe przyczyny:"
        log "- Problem z dostawcą hostingu"
        log "- Restart serwera"
        log "- Blokada IP"
        log "Spróbuj ponownie za 5-10 minut"
        exit 1
    fi
    
    if ! check_ssh_connection; then
        log "🟡 SSH niedostępne - nie można wdrożyć bezpośrednio"
        log "Sprawdzanie dostępności HTTP..."
        check_http_ports
        check_domain
        log "Poczekaj aż SSH będzie dostępne i uruchom ponownie"
        exit 1
    fi
    
    log "🟢 Serwer dostępny - przeprowadzanie wdrożenia"
    check_http_ports
    check_domain
    deploy_when_available
    
    log "✅ Recovery script zakończony"
    log "Sprawdź dostępność na: http://185.70.198.201:4000"
}

# Uruchomienie
main "$@"
