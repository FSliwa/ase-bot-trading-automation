#!/bin/bash

################################################################################
# ASE-Bot Process Management System
# PM2/systemd konfiguracja z automatycznym restartem i monitoringiem
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PM_VERSION="1.0"

# Ścieżki
DEPLOY_DIR="/home/admin/trading-platform"
SERVICE_USER="admin"
LOG_DIR="/var/log/asebot"

# Konfiguracja procesów
PROCESSES=(
    "api-backend:simple_test_api.py:8012:API Backend Server"
    "proxy-server:unified_working.py:8008:Proxy Server"
)

# Preferowany system zarządzania procesami
PREFERRED_MANAGER="pm2"  # pm2 lub systemd

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

# === FUNKCJE POMOCNICZE ===

log() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "INFO")  echo -e "${GREEN}[INFO]${NC}  [$timestamp] $message" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC}  [$timestamp] $message" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} [$timestamp] $message" ;;
        "DEBUG") echo -e "${BLUE}[DEBUG]${NC} [$timestamp] $message" ;;
        *)       echo -e "[$timestamp] $message" ;;
    esac
    
    # Zapisz do pliku loga
    mkdir -p "$LOG_DIR"
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/process-management-$(date +%Y%m%d).log"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Sprawdź czy proces działa na porcie
check_port_in_use() {
    local port=$1
    netstat -tlnp | grep ":$port " | grep LISTEN >/dev/null 2>&1
}

# Znajdź PID procesu na porcie
get_pid_by_port() {
    local port=$1
    netstat -tlnp | grep ":$port " | grep LISTEN | awk '{print $7}' | cut -d'/' -f1
}

# === FUNKCJE PM2 ===

install_pm2() {
    log "INFO" "📦 Instalacja PM2..."
    
    # Sprawdź czy Node.js jest zainstalowany
    if ! command_exists node; then
        log "INFO" "Instalacja Node.js (wymagane dla PM2)..."
        if command_exists curl; then
            curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
            sudo apt-get install -y nodejs
        else
            log "ERROR" "Brak curl - nie można zainstalować Node.js"
            return 1
        fi
    fi
    
    # Zainstaluj PM2 globalnie
    if ! command_exists pm2; then
        log "INFO" "Instalowanie PM2..."
        if sudo npm install -g pm2; then
            log "INFO" "✅ PM2 zainstalowany"
        else
            log "ERROR" "❌ Błąd instalacji PM2"
            return 1
        fi
    else
        log "INFO" "✅ PM2 już zainstalowany"
    fi
    
    # Sprawdź wersję PM2
    local pm2_version
    pm2_version=$(pm2 --version)
    log "INFO" "PM2 wersja: $pm2_version"
    
    return 0
}

create_pm2_ecosystem() {
    log "INFO" "📝 Tworzenie pliku konfiguracyjnego PM2 ecosystem..."
    
    cat > "$DEPLOY_DIR/ecosystem.config.js" << 'EOF'
module.exports = {
  apps: [
    {
      name: 'ase-bot-api',
      script: 'simple_test_api.py',
      interpreter: 'python3',
      cwd: '/home/admin/trading-platform',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
        PORT: 8012
      },
      error_file: '/var/log/asebot/api-error.log',
      out_file: '/var/log/asebot/api-out.log',
      log_file: '/var/log/asebot/api-combined.log',
      time: true,
      restart_delay: 4000,
      max_restarts: 10,
      min_uptime: '10s'
    },
    {
      name: 'ase-bot-proxy',
      script: 'unified_working.py',
      interpreter: 'python3',
      cwd: '/home/admin/trading-platform',
      instances: 1,
      exec_mode: 'fork',
      watch: false,
      max_memory_restart: '300M',
      env: {
        NODE_ENV: 'production',
        PORT: 8008
      },
      error_file: '/var/log/asebot/proxy-error.log',
      out_file: '/var/log/asebot/proxy-out.log',
      log_file: '/var/log/asebot/proxy-combined.log',
      time: true,
      restart_delay: 4000,
      max_restarts: 10,
      min_uptime: '10s'
    }
  ]
};
EOF
    
    log "INFO" "✅ Plik ecosystem.config.js utworzony"
    return 0
}

setup_pm2_services() {
    log "INFO" "🚀 Konfiguracja serwisów PM2..."
    
    # Sprawdź czy PM2 jest zainstalowany
    if ! command_exists pm2; then
        if ! install_pm2; then
            return 1
        fi
    fi
    
    # Utwórz katalog logów
    sudo mkdir -p "$LOG_DIR"
    sudo chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
    
    # Utwórz plik ecosystem
    create_pm2_ecosystem
    
    # Zatrzymaj istniejące procesy
    log "INFO" "Zatrzymywanie istniejących procesów..."
    pm2 delete all 2>/dev/null || true
    
    # Uruchom aplikacje z ecosystem
    log "INFO" "Uruchamianie aplikacji przez PM2..."
    if pm2 start "$DEPLOY_DIR/ecosystem.config.js"; then
        log "INFO" "✅ Aplikacje uruchomione przez PM2"
    else
        log "ERROR" "❌ Błąd uruchamiania aplikacji przez PM2"
        return 1
    fi
    
    # Zapisz konfigurację PM2
    pm2 save
    
    # Włącz autostart PM2 przy restarcie systemu
    log "INFO" "Konfiguracja autostartu PM2..."
    if pm2 startup systemd -u "$SERVICE_USER" --hp "/home/$SERVICE_USER"; then
        log "INFO" "✅ Autostart PM2 skonfigurowany"
    else
        log "WARN" "⚠️ Nie udało się skonfigurować autostartu PM2"
    fi
    
    return 0
}

manage_pm2_services() {
    local action=$1
    
    case $action in
        "start")
            log "INFO" "🚀 Uruchamianie serwisów PM2..."
            pm2 start "$DEPLOY_DIR/ecosystem.config.js" || pm2 restart all
            pm2 save
            ;;
        "stop")
            log "INFO" "🛑 Zatrzymywanie serwisów PM2..."
            pm2 stop all
            ;;
        "restart")
            log "INFO" "🔄 Restart serwisów PM2..."
            pm2 restart all
            ;;
        "reload")
            log "INFO" "♻️ Reload serwisów PM2..."
            pm2 reload all
            ;;
        "status")
            log "INFO" "📊 Status serwisów PM2..."
            pm2 status
            pm2 monit --no-interaction &
            ;;
        "logs")
            log "INFO" "📋 Logi serwisów PM2..."
            pm2 logs --lines 50
            ;;
        *)
            log "ERROR" "Nieznana akcja PM2: $action"
            return 1
            ;;
    esac
    
    return 0
}

# === FUNKCJE SYSTEMD ===

create_systemd_services() {
    log "INFO" "📝 Tworzenie serwisów systemd..."
    
    # Twórz serwis dla każdego procesu
    for process_def in "${PROCESSES[@]}"; do
        local name="${process_def%%:*}"
        local script=$(echo "$process_def" | cut -d':' -f2)
        local port=$(echo "$process_def" | cut -d':' -f3)
        local description=$(echo "$process_def" | cut -d':' -f4)
        
        local service_file="/etc/systemd/system/asebot-${name}.service"
        
        log "INFO" "Tworzenie serwisu: asebot-${name}.service"
        
        sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=$description
After=network.target
StartLimitIntervalSec=0

[Service]
Type=simple
Restart=always
RestartSec=5
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$DEPLOY_DIR
Environment=PATH=/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$DEPLOY_DIR
ExecStart=/usr/bin/python3 $DEPLOY_DIR/$script
ExecReload=/bin/kill -HUP \$MAINPID
StandardOutput=journal
StandardError=journal
SyslogIdentifier=asebot-$name
KillMode=mixed
TimeoutStopSec=30

# Security settings
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=$DEPLOY_DIR $LOG_DIR /tmp
PrivateTmp=yes

# Resource limits
LimitNOFILE=65536
MemoryMax=512M

[Install]
WantedBy=multi-user.target
EOF
        
        log "INFO" "✅ Serwis asebot-${name}.service utworzony"
    done
    
    # Utwórz serwis główny (target)
    local target_file="/etc/systemd/system/asebot.target"
    
    sudo tee "$target_file" > /dev/null << 'EOF'
[Unit]
Description=ASE-Bot Trading Platform
Wants=asebot-api-backend.service asebot-proxy-server.service
After=asebot-api-backend.service asebot-proxy-server.service

[Install]
WantedBy=multi-user.target
EOF
    
    # Przeładuj systemd
    sudo systemctl daemon-reload
    
    log "INFO" "✅ Serwisy systemd utworzone"
    return 0
}

setup_systemd_services() {
    log "INFO" "🚀 Konfiguracja serwisów systemd..."
    
    # Utwórz katalog logów
    sudo mkdir -p "$LOG_DIR"
    sudo chown "$SERVICE_USER:$SERVICE_USER" "$LOG_DIR"
    
    # Utwórz serwisy
    create_systemd_services
    
    # Włącz serwisy
    for process_def in "${PROCESSES[@]}"; do
        local name="${process_def%%:*}"
        local service_name="asebot-${name}.service"
        
        log "INFO" "Włączanie serwisu: $service_name"
        
        if sudo systemctl enable "$service_name"; then
            log "INFO" "✅ Serwis $service_name włączony"
        else
            log "WARN" "⚠️ Nie udało się włączyć serwisu $service_name"
        fi
    done
    
    # Włącz główny target
    sudo systemctl enable asebot.target
    
    log "INFO" "✅ Serwisy systemd skonfigurowane"
    return 0
}

manage_systemd_services() {
    local action=$1
    
    case $action in
        "start")
            log "INFO" "🚀 Uruchamianie serwisów systemd..."
            sudo systemctl start asebot.target
            ;;
        "stop")
            log "INFO" "🛑 Zatrzymywanie serwisów systemd..."
            sudo systemctl stop asebot.target
            ;;
        "restart")
            log "INFO" "🔄 Restart serwisów systemd..."
            sudo systemctl restart asebot.target
            ;;
        "reload")
            log "INFO" "♻️ Reload serwisów systemd..."
            sudo systemctl daemon-reload
            sudo systemctl reload-or-restart asebot.target
            ;;
        "status")
            log "INFO" "📊 Status serwisów systemd..."
            sudo systemctl status asebot.target
            
            for process_def in "${PROCESSES[@]}"; do
                local name="${process_def%%:*}"
                echo ""
                sudo systemctl status "asebot-${name}.service" --no-pager
            done
            ;;
        "logs")
            log "INFO" "📋 Logi serwisów systemd..."
            sudo journalctl -u asebot.target -f --lines=50
            ;;
        *)
            log "ERROR" "Nieznana akcja systemd: $action"
            return 1
            ;;
    esac
    
    return 0
}

# === FUNKCJE MONITORINGU ===

create_monitoring_scripts() {
    log "INFO" "📊 Tworzenie skryptów monitoringu..."
    
    # Skrypt sprawdzania zdrowia procesów
    cat > "$DEPLOY_DIR/health_check.sh" << 'EOF'
#!/bin/bash

DEPLOY_DIR="/home/admin/trading-platform"
LOG_DIR="/var/log/asebot"

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_health() {
    local level=$1
    shift
    local message="$*"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    
    case $level in
        "OK")    echo -e "${GREEN}[OK]${NC}   [$timestamp] $message" ;;
        "WARN")  echo -e "${YELLOW}[WARN]${NC} [$timestamp] $message" ;;
        "ERROR") echo -e "${RED}[ERROR]${NC} [$timestamp] $message" ;;
        *)       echo -e "[$timestamp] $message" ;;
    esac
    
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/health-check.log"
}

check_service_health() {
    local service_name=$1
    local port=$2
    local process_pattern=$3
    
    log_health "INFO" "Sprawdzanie serwisu: $service_name"
    
    # Sprawdź czy proces działa
    if pgrep -f "$process_pattern" > /dev/null; then
        log_health "OK" "$service_name: Proces aktywny"
        
        # Sprawdź czy port nasłuchuje
        if netstat -tlnp | grep ":$port " | grep LISTEN > /dev/null; then
            log_health "OK" "$service_name: Port $port nasłuchuje"
            
            # Sprawdź odpowiedź HTTP (jeśli możliwe)
            if curl -s --connect-timeout 5 "http://localhost:$port/health" | grep -q "healthy"; then
                log_health "OK" "$service_name: Endpoint /health odpowiada"
                return 0
            else
                log_health "WARN" "$service_name: Endpoint /health nie odpowiada poprawnie"
                return 1
            fi
        else
            log_health "ERROR" "$service_name: Port $port nie nasłuchuje"
            return 2
        fi
    else
        log_health "ERROR" "$service_name: Proces nie działa"
        return 3
    fi
}

# Główny health check
echo "=== ASE-Bot Health Check - $(date) ==="

# Sprawdź API Backend
check_service_health "API Backend" 8012 "simple_test_api"
api_status=$?

# Sprawdź Proxy Server
check_service_health "Proxy Server" 8008 "unified_working"
proxy_status=$?

# Sprawdź zasoby systemowe
echo ""
log_health "INFO" "=== Zasoby systemowe ==="

# RAM
memory_usage=$(free | grep '^Mem:' | awk '{printf "%.1f", $3/$2 * 100}')
if (( $(echo "$memory_usage > 80" | bc -l) )); then
    log_health "WARN" "Użycie pamięci RAM: ${memory_usage}% (wysokie)"
else
    log_health "OK" "Użycie pamięci RAM: ${memory_usage}%"
fi

# Dysk
disk_usage=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
if [[ $disk_usage -gt 85 ]]; then
    log_health "WARN" "Użycie dysku: ${disk_usage}% (wysokie)"
else
    log_health "OK" "Użycie dysku: ${disk_usage}%"
fi

# Load average
load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
log_health "OK" "Obciążenie systemu: $load_avg"

# Podsumowanie
echo ""
if [[ $api_status -eq 0 && $proxy_status -eq 0 ]]; then
    log_health "OK" "=== WSZYSTKIE SERWISY ZDROWE ==="
    exit 0
else
    log_health "ERROR" "=== WYKRYTO PROBLEMY Z SERWISAMI ==="
    exit 1
fi
EOF
    
    # Skrypt automatycznego restartu
    cat > "$DEPLOY_DIR/auto_restart.sh" << 'EOF'
#!/bin/bash

DEPLOY_DIR="/home/admin/trading-platform"
LOG_DIR="/var/log/asebot"

log_restart() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $message"
    echo "[$timestamp] $message" >> "$LOG_DIR/auto-restart.log"
}

restart_service() {
    local service_name=$1
    local process_pattern=$2
    local start_command=$3
    
    log_restart "Restarting $service_name..."
    
    # Zabij proces
    pkill -f "$process_pattern" && log_restart "Stopped $service_name"
    sleep 3
    
    # Uruchom ponownie
    cd "$DEPLOY_DIR"
    nohup $start_command > /dev/null 2>&1 &
    sleep 5
    
    # Sprawdź czy się uruchomił
    if pgrep -f "$process_pattern" > /dev/null; then
        log_restart "Successfully restarted $service_name"
    else
        log_restart "Failed to restart $service_name"
    fi
}

# Sprawdź i restartuj serwisy jeśli potrzeba
if ! pgrep -f "simple_test_api" > /dev/null; then
    restart_service "API Backend" "simple_test_api" "python3 simple_test_api.py"
fi

if ! pgrep -f "unified_working" > /dev/null; then
    restart_service "Proxy Server" "unified_working" "python3 unified_working.py"
fi
EOF
    
    # Skrypt monitoringu zasobów
    cat > "$DEPLOY_DIR/resource_monitor.sh" << 'EOF'
#!/bin/bash

LOG_DIR="/var/log/asebot"

# Zbierz metryki
timestamp=$(date '+%Y-%m-%d %H:%M:%S')
memory_usage=$(free | grep '^Mem:' | awk '{printf "%.1f", $3/$2 * 100}')
disk_usage=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')

# API Backend PID i zasoby
api_pid=$(pgrep -f "simple_test_api" | head -1)
if [[ -n "$api_pid" ]]; then
    api_memory=$(ps -p $api_pid -o %mem --no-headers | tr -d ' ')
    api_cpu=$(ps -p $api_pid -o %cpu --no-headers | tr -d ' ')
else
    api_memory="0"
    api_cpu="0"
fi

# Proxy Server PID i zasoby
proxy_pid=$(pgrep -f "unified_working" | head -1)
if [[ -n "$proxy_pid" ]]; then
    proxy_memory=$(ps -p $proxy_pid -o %mem --no-headers | tr -d ' ')
    proxy_cpu=$(ps -p $proxy_pid -o %cpu --no-headers | tr -d ' ')
else
    proxy_memory="0"
    proxy_cpu="0"
fi

# Zapisz metryki
echo "$timestamp,$memory_usage,$disk_usage,$load_avg,$cpu_usage,$api_memory,$api_cpu,$proxy_memory,$proxy_cpu" >> "$LOG_DIR/metrics.csv"

# Nagłówek pliku CSV (jeśli plik jest nowy)
if [[ ! -s "$LOG_DIR/metrics.csv" ]] || [[ $(wc -l < "$LOG_DIR/metrics.csv") -eq 1 ]]; then
    sed -i '1i timestamp,system_memory,disk_usage,load_avg,cpu_usage,api_memory,api_cpu,proxy_memory,proxy_cpu' "$LOG_DIR/metrics.csv"
fi
EOF
    
    # Ustaw uprawnienia wykonywania
    chmod +x "$DEPLOY_DIR"/{health_check.sh,auto_restart.sh,resource_monitor.sh}
    
    log "INFO" "✅ Skrypty monitoringu utworzone"
    return 0
}

setup_monitoring_cron() {
    log "INFO" "⏰ Konfiguracja zadań cron dla monitoringu..."
    
    # Usuń stare zadania cron dla asebot
    crontab -l 2>/dev/null | grep -v "asebot" | crontab - 2>/dev/null || true
    
    # Dodaj nowe zadania cron
    (crontab -l 2>/dev/null; cat << EOF
# ASE-Bot Monitoring Tasks
*/5 * * * * $DEPLOY_DIR/health_check.sh >> $LOG_DIR/health-check.log 2>&1
*/2 * * * * $DEPLOY_DIR/auto_restart.sh >> $LOG_DIR/auto-restart.log 2>&1
* * * * * $DEPLOY_DIR/resource_monitor.sh
0 0 * * 0 find $LOG_DIR -name "*.log" -mtime +7 -delete
EOF
    ) | crontab -
    
    log "INFO" "✅ Zadania cron skonfigurowane"
    return 0
}

# === FUNKCJE GŁÓWNE ===

check_process_manager_preference() {
    log "INFO" "🔍 Sprawdzanie dostępnych managerów procesów..."
    
    local available_managers=()
    
    # Sprawdź PM2
    if command_exists pm2 || command_exists node; then
        available_managers+=("pm2")
        log "INFO" "✅ PM2 dostępny"
    fi
    
    # Sprawdź systemd
    if command_exists systemctl && [[ -d /etc/systemd/system ]]; then
        available_managers+=("systemd")
        log "INFO" "✅ systemd dostępny"
    fi
    
    if [[ ${#available_managers[@]} -eq 0 ]]; then
        log "ERROR" "❌ Brak dostępnych managerów procesów"
        return 1
    fi
    
    # Wybierz preferowany manager
    if [[ " ${available_managers[*]} " =~ " $PREFERRED_MANAGER " ]]; then
        log "INFO" "🎯 Używam preferowanego managera: $PREFERRED_MANAGER"
        echo "$PREFERRED_MANAGER"
    else
        log "INFO" "🔄 Preferowany manager niedostępny, używam: ${available_managers[0]}"
        echo "${available_managers[0]}"
    fi
    
    return 0
}

setup_process_management() {
    log "INFO" "🚀 Konfiguracja zarządzania procesami..."
    
    local manager
    if ! manager=$(check_process_manager_preference); then
        return 1
    fi
    
    # Zatrzymaj istniejące procesy
    log "INFO" "Zatrzymywanie istniejących procesów..."
    pkill -f "simple_test_api" 2>/dev/null || true
    pkill -f "unified_working" 2>/dev/null || true
    sleep 3
    
    # Konfiguruj wybrany manager
    case $manager in
        "pm2")
            setup_pm2_services
            ;;
        "systemd")
            setup_systemd_services
            ;;
        *)
            log "ERROR" "Nieznany manager: $manager"
            return 1
            ;;
    esac
    
    local setup_result=$?
    
    if [[ $setup_result -eq 0 ]]; then
        # Konfiguruj monitoring
        create_monitoring_scripts
        setup_monitoring_cron
        
        log "INFO" "✅ Zarządzanie procesami skonfigurowane ($manager)"
        
        # Pokaż status
        sleep 5
        show_process_status
        
    else
        log "ERROR" "❌ Błąd konfiguracji zarządzania procesami"
        return 1
    fi
    
    return 0
}

show_process_status() {
    log "INFO" "📊 Status procesów:"
    
    # Sprawdź procesy
    for process_def in "${PROCESSES[@]}"; do
        local name="${process_def%%:*}"
        local script=$(echo "$process_def" | cut -d':' -f2)
        local port=$(echo "$process_def" | cut -d':' -f3)
        local description=$(echo "$process_def" | cut -d':' -f4)
        
        echo ""
        echo "=== $description ==="
        
        if pgrep -f "$script" > /dev/null; then
            local pid
            pid=$(pgrep -f "$script")
            echo "✅ Status: Running (PID: $pid)"
            
            if check_port_in_use "$port"; then
                echo "✅ Port: $port (Listening)"
            else
                echo "❌ Port: $port (Not listening)"
            fi
            
            # Pokaż zużycie zasobów
            local memory_usage cpu_usage
            memory_usage=$(ps -p "$pid" -o %mem --no-headers 2>/dev/null | tr -d ' ' || echo "N/A")
            cpu_usage=$(ps -p "$pid" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "N/A")
            echo "📊 Resources: CPU: ${cpu_usage}%, Memory: ${memory_usage}%"
            
        else
            echo "❌ Status: Not running"
        fi
    done
    
    # Sprawdź manager procesów
    echo ""
    echo "=== Process Manager ==="
    
    if command_exists pm2 && pm2 list 2>/dev/null | grep -q "ase-bot"; then
        echo "✅ PM2: Active"
        pm2 list | grep "ase-bot"
    elif systemctl is-active asebot.target >/dev/null 2>&1; then
        echo "✅ systemd: Active"
        systemctl status asebot.target --no-pager -l
    else
        echo "⚠️ Process Manager: Manual/None"
    fi
}

# === MAIN ===

show_help() {
    echo "ASE-Bot Process Management System v$PM_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 COMMAND [OPTIONS]"
    echo ""
    echo "Komendy:"
    echo "  setup                Konfiguracja zarządzania procesami"
    echo "  start                Uruchom wszystkie serwisy"
    echo "  stop                 Zatrzymaj wszystkie serwisy"
    echo "  restart              Restart wszystkich serwisów"
    echo "  status               Pokaż status procesów"
    echo "  logs                 Pokaż logi"
    echo "  health               Uruchom health check"
    echo "  monitoring           Konfiguruj monitoring"
    echo ""
    echo "Przykłady:"
    echo "  $0 setup             # Konfiguruj zarządzanie procesami"
    echo "  $0 start             # Uruchom serwisy"
    echo "  $0 status            # Sprawdź status"
    echo "  $0 health            # Health check"
    echo ""
}

main() {
    local command=${1:-"help"}
    
    # Ustal aktualny manager procesów
    local current_manager=""
    if command_exists pm2 && pm2 list 2>/dev/null | grep -q "ase-bot"; then
        current_manager="pm2"
    elif systemctl is-active asebot.target >/dev/null 2>&1; then
        current_manager="systemd"
    fi
    
    case $command in
        "setup"|"s")
            setup_process_management
            ;;
        "start")
            if [[ -n "$current_manager" ]]; then
                manage_${current_manager}_services "start"
            else
                log "ERROR" "Brak skonfigurowanego managera procesów. Uruchom: $0 setup"
                exit 1
            fi
            ;;
        "stop")
            if [[ -n "$current_manager" ]]; then
                manage_${current_manager}_services "stop"
            else
                # Manual stop
                pkill -f "simple_test_api" || true
                pkill -f "unified_working" || true
            fi
            ;;
        "restart"|"r")
            if [[ -n "$current_manager" ]]; then
                manage_${current_manager}_services "restart"
            else
                log "ERROR" "Brak skonfigurowanego managera procesów"
                exit 1
            fi
            ;;
        "status"|"st")
            show_process_status
            ;;
        "logs"|"l")
            if [[ -n "$current_manager" ]]; then
                manage_${current_manager}_services "logs"
            else
                log "INFO" "Wyświetlanie logów z $LOG_DIR..."
                tail -f "$LOG_DIR"/*.log 2>/dev/null || echo "Brak logów"
            fi
            ;;
        "health"|"h")
            if [[ -f "$DEPLOY_DIR/health_check.sh" ]]; then
                "$DEPLOY_DIR/health_check.sh"
            else
                log "ERROR" "Skrypt health check nie istnieje. Uruchom: $0 setup"
                exit 1
            fi
            ;;
        "monitoring"|"m")
            create_monitoring_scripts
            setup_monitoring_cron
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            log "ERROR" "Nieznana komenda: $command"
            show_help
            exit 1
            ;;
    esac
}

# Uruchom główną funkcję
main "$@"
