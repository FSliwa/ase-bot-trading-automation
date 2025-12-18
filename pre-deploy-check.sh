#!/bin/bash

################################################################################
# ASE-Bot Pre-Deployment System Check
# Sprawdzenie wymagań systemowych, zasobów i zależności przed deploymentem
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK_VERSION="1.0"

# Minimalne wymagania
MIN_DISK_GB=5
MIN_RAM_MB=1024
MIN_CPU_CORES=1

# Wymagane porty
REQUIRED_PORTS=(8008 8010 8012)

# Wymagane pakiety systemowe
REQUIRED_PACKAGES=(
    "python3"
    "python3-pip" 
    "curl"
    "git"
    "nginx"
)

# Kolory
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
}

# Konwertuj do human-readable rozmiarów
human_readable_size() {
    local bytes=$1
    if [[ $bytes -gt 1073741824 ]]; then
        echo "$((bytes / 1073741824))GB"
    elif [[ $bytes -gt 1048576 ]]; then
        echo "$((bytes / 1048576))MB"
    else
        echo "$((bytes / 1024))KB"
    fi
}

# Sprawdź czy komenda istnieje
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# === SPRAWDZENIA SYSTEMOWE ===

check_os_compatibility() {
    log "INFO" "🐧 Sprawdzanie zgodności systemu operacyjnego..."
    
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        log "INFO" "System: $PRETTY_NAME"
        log "INFO" "Kernel: $(uname -r)"
        
        # Sprawdź czy to Ubuntu/Debian
        if [[ "$ID" =~ ^(ubuntu|debian)$ ]]; then
            log "INFO" "✅ System operacyjny kompatybilny"
            
            # Sprawdź wersję Ubuntu
            if [[ "$ID" == "ubuntu" ]]; then
                local version_num=${VERSION_ID%.*}
                if [[ $version_num -ge 20 ]]; then
                    log "INFO" "✅ Wersja Ubuntu $VERSION_ID jest wspierana"
                else
                    log "WARN" "⚠️ Ubuntu $VERSION_ID może wymagać dodatkowych pakietów"
                fi
            fi
        else
            log "WARN" "⚠️ System $PRETTY_NAME może wymagać dodatkowej konfiguracji"
        fi
    else
        log "WARN" "⚠️ Nie można zidentyfikować systemu operacyjnego"
    fi
    
    return 0
}

check_hardware_resources() {
    log "INFO" "💻 Sprawdzanie zasobów sprzętowych..."
    
    # Sprawdź RAM
    local ram_mb
    ram_mb=$(free -m | grep '^Mem:' | awk '{print $2}')
    log "INFO" "RAM: ${ram_mb}MB"
    
    if [[ $ram_mb -ge $MIN_RAM_MB ]]; then
        log "INFO" "✅ RAM: wystarczające ($ram_mb MB >= $MIN_RAM_MB MB)"
    else
        log "WARN" "⚠️ RAM: może być niewystarczające ($ram_mb MB < $MIN_RAM_MB MB)"
    fi
    
    # Sprawdź CPU
    local cpu_cores
    cpu_cores=$(nproc)
    log "INFO" "CPU rdzenie: $cpu_cores"
    
    if [[ $cpu_cores -ge $MIN_CPU_CORES ]]; then
        log "INFO" "✅ CPU: wystarczające ($cpu_cores rdzeni >= $MIN_CPU_CORES)"
    else
        log "WARN" "⚠️ CPU: może być niewystarczające ($cpu_cores rdzeni < $MIN_CPU_CORES)"
    fi
    
    # Sprawdź obciążenie systemu
    local load_avg
    load_avg=$(uptime | awk -F'load average:' '{print $2}' | awk '{print $1}' | tr -d ',')
    log "INFO" "Obciążenie systemu (1min): $load_avg"
    
    # Sprawdź miejsce na dysku
    local disk_usage
    disk_usage=$(df /home --output=pcent | tail -1 | tr -d '% ')
    local disk_avail_kb
    disk_avail_kb=$(df /home --output=avail | tail -1 | tr -d ' ')
    local disk_avail_gb=$((disk_avail_kb / 1024 / 1024))
    
    log "INFO" "Dysk /home: ${disk_usage}% wykorzystane, ${disk_avail_gb}GB dostępne"
    
    if [[ $disk_avail_gb -ge $MIN_DISK_GB ]]; then
        log "INFO" "✅ Miejsce na dysku: wystarczające (${disk_avail_gb}GB >= ${MIN_DISK_GB}GB)"
    else
        log "WARN" "⚠️ Miejsce na dysku: może być niewystarczające (${disk_avail_gb}GB < ${MIN_DISK_GB}GB)"
    fi
    
    return 0
}

check_network_connectivity() {
    log "INFO" "🌐 Sprawdzanie łączności sieciowej..."
    
    # Test podstawowej łączności
    if ping -c 3 8.8.8.8 >/dev/null 2>&1; then
        log "INFO" "✅ Połączenie internetowe aktywne"
    else
        log "ERROR" "❌ Brak połączenia internetowego"
        return 1
    fi
    
    # Test rozwiązywania nazw
    if nslookup google.com >/dev/null 2>&1; then
        log "INFO" "✅ DNS działa poprawnie"
    else
        log "WARN" "⚠️ Problemy z rozwiązywaniem nazw DNS"
    fi
    
    # Test HTTPS
    if curl -s --connect-timeout 10 https://httpbin.org/status/200 >/dev/null; then
        log "INFO" "✅ HTTPS połączenia działają"
    else
        log "WARN" "⚠️ Problemy z połączeniami HTTPS"
    fi
    
    return 0
}

check_required_ports() {
    log "INFO" "🔌 Sprawdzanie dostępności portów..."
    
    local blocked_ports=()
    
    for port in "${REQUIRED_PORTS[@]}"; do
        if netstat -tlnp | grep ":$port " | grep LISTEN >/dev/null 2>&1; then
            local process
            process=$(netstat -tlnp | grep ":$port " | awk '{print $7}' | cut -d'/' -f2)
            log "WARN" "⚠️ Port $port zajęty przez: $process"
            blocked_ports+=("$port")
        else
            log "INFO" "✅ Port $port dostępny"
        fi
    done
    
    if [[ ${#blocked_ports[@]} -eq 0 ]]; then
        log "INFO" "✅ Wszystkie wymagane porty są dostępne"
        return 0
    else
        log "WARN" "⚠️ Niektóre porty są zajęte: ${blocked_ports[*]}"
        log "INFO" "Deployment może wymagać zatrzymania istniejących procesów"
        return 1
    fi
}

check_system_packages() {
    log "INFO" "📦 Sprawdzanie pakietów systemowych..."
    
    local missing_packages=()
    
    for package in "${REQUIRED_PACKAGES[@]}"; do
        if command_exists "$package" || dpkg -l | grep -q "^ii.*$package"; then
            local version=""
            case $package in
                "python3")
                    version=$(python3 --version 2>&1 | awk '{print $2}')
                    ;;
                "python3-pip")
                    if command_exists pip3; then
                        version=$(pip3 --version | awk '{print $2}')
                    fi
                    ;;
                "git")
                    version=$(git --version | awk '{print $3}')
                    ;;
                "nginx")
                    version=$(nginx -v 2>&1 | awk -F'/' '{print $2}')
                    ;;
                "curl")
                    version=$(curl --version | head -1 | awk '{print $2}')
                    ;;
            esac
            
            log "INFO" "✅ $package zainstalowany${version:+ ($version)}"
        else
            log "WARN" "⚠️ $package nie jest zainstalowany"
            missing_packages+=("$package")
        fi
    done
    
    if [[ ${#missing_packages[@]} -eq 0 ]]; then
        log "INFO" "✅ Wszystkie wymagane pakiety są zainstalowane"
        return 0
    else
        log "WARN" "⚠️ Brakujące pakiety: ${missing_packages[*]}"
        log "INFO" "Uruchom: sudo apt-get update && sudo apt-get install ${missing_packages[*]}"
        return 1
    fi
}

check_python_environment() {
    log "INFO" "🐍 Sprawdzanie środowiska Python..."
    
    # Sprawdź wersję Python
    if command_exists python3; then
        local python_version
        python_version=$(python3 --version | awk '{print $2}')
        log "INFO" "Python wersja: $python_version"
        
        # Sprawdź czy to Python 3.8+
        local major minor
        major=$(echo "$python_version" | cut -d'.' -f1)
        minor=$(echo "$python_version" | cut -d'.' -f2)
        
        if [[ $major -eq 3 && $minor -ge 8 ]]; then
            log "INFO" "✅ Wersja Python kompatybilna"
        else
            log "WARN" "⚠️ Wersja Python $python_version może nie być w pełni kompatybilna (zalecane 3.8+)"
        fi
    else
        log "ERROR" "❌ Python3 nie jest zainstalowany"
        return 1
    fi
    
    # Sprawdź pip
    if command_exists pip3; then
        local pip_version
        pip_version=$(pip3 --version | awk '{print $2}')
        log "INFO" "✅ pip3 zainstalowany ($pip_version)"
        
        # Test instalacji pakietu
        if pip3 list | grep -q "requests"; then
            log "INFO" "✅ Podstawowe pakiety Python dostępne"
        else
            log "INFO" "ℹ️ Deployment zainstaluje wymagane pakiety Python"
        fi
    else
        log "ERROR" "❌ pip3 nie jest zainstalowany"
        return 1
    fi
    
    # Sprawdź venv
    if python3 -m venv --help >/dev/null 2>&1; then
        log "INFO" "✅ Python venv dostępny"
    else
        log "WARN" "⚠️ Python venv może być niedostępny"
    fi
    
    return 0
}

check_web_server() {
    log "INFO" "🌐 Sprawdzanie serwera WWW..."
    
    # Sprawdź nginx
    if command_exists nginx; then
        local nginx_version
        nginx_version=$(nginx -v 2>&1 | awk -F'/' '{print $2}')
        log "INFO" "✅ Nginx zainstalowany ($nginx_version)"
        
        # Sprawdź status nginx
        if systemctl is-active nginx >/dev/null 2>&1; then
            log "INFO" "✅ Nginx uruchomiony"
        else
            log "INFO" "ℹ️ Nginx nie jest uruchomiony (zostanie uruchomiony podczas deploymentu)"
        fi
        
        # Sprawdź konfigurację
        if nginx -t >/dev/null 2>&1; then
            log "INFO" "✅ Konfiguracja Nginx poprawna"
        else
            log "WARN" "⚠️ Problemy z konfiguracją Nginx"
        fi
    else
        log "WARN" "⚠️ Nginx nie jest zainstalowany (zostanie zainstalowany podczas deploymentu)"
    fi
    
    return 0
}

check_permissions() {
    log "INFO" "🔐 Sprawdzanie uprawnień i dostępu..."
    
    # Sprawdź dostęp do katalogu home
    if [[ -w "$HOME" ]]; then
        log "INFO" "✅ Katalog domowy: dostęp do zapisu"
    else
        log "ERROR" "❌ Brak dostępu do zapisu w katalogu domowym"
        return 1
    fi
    
    # Sprawdź dostęp sudo
    if timeout 5 sudo -n true 2>/dev/null; then
        log "INFO" "✅ Dostęp sudo: bez hasła"
    elif sudo -l >/dev/null 2>&1; then
        log "INFO" "ℹ️ Dostęp sudo: z hasłem"
    else
        log "WARN" "⚠️ Brak dostępu sudo (niektóre operacje mogą się nie powieść)"
    fi
    
    # Sprawdź uprawnienia do portów privileged
    local can_bind_privileged=false
    if [[ $EUID -eq 0 ]] || sudo -n true 2>/dev/null; then
        can_bind_privileged=true
        log "INFO" "✅ Możliwość bindowania portów privileged (< 1024)"
    else
        log "INFO" "ℹ️ Używane będą tylko porty > 1024"
    fi
    
    return 0
}

check_security() {
    log "INFO" "🔒 Sprawdzanie konfiguracji bezpieczeństwa..."
    
    # Sprawdź firewall
    if command_exists ufw; then
        local ufw_status
        ufw_status=$(sudo ufw status 2>/dev/null | head -1 | awk '{print $2}' || echo "unknown")
        log "INFO" "UFW Firewall: $ufw_status"
        
        if [[ "$ufw_status" == "active" ]]; then
            log "INFO" "ℹ️ Firewall jest aktywny - sprawdź czy porty 80/443/8008/8012 są otwarte"
        fi
    else
        log "INFO" "ℹ️ UFW nie jest zainstalowany"
    fi
    
    # Sprawdź SELinux (jeśli dostępny)
    if command_exists getenforce; then
        local selinux_status
        selinux_status=$(getenforce)
        log "INFO" "SELinux: $selinux_status"
    fi
    
    # Sprawdź podstawowe pliki systemowe
    if [[ -f /etc/passwd && -r /etc/passwd ]]; then
        log "INFO" "✅ Pliki systemowe dostępne"
    else
        log "WARN" "⚠️ Problemy z dostępem do plików systemowych"
    fi
    
    return 0
}

# === GŁÓWNA FUNKCJA SPRAWDZANIA ===

run_all_checks() {
    log "INFO" "🚀 Rozpoczynanie sprawdzenia pre-deployment..."
    log "INFO" "Wersja sprawdzenia: $CHECK_VERSION"
    log "INFO" "Czas: $(date)"
    
    local checks=(
        "check_os_compatibility:Zgodność systemu operacyjnego"
        "check_hardware_resources:Zasoby sprzętowe"
        "check_network_connectivity:Łączność sieciowa"
        "check_required_ports:Dostępność portów"
        "check_system_packages:Pakiety systemowe"
        "check_python_environment:Środowisko Python"
        "check_web_server:Serwer WWW"
        "check_permissions:Uprawnienia"
        "check_security:Konfiguracja bezpieczeństwa"
    )
    
    local passed=0
    local warnings=0
    local errors=0
    
    for check_def in "${checks[@]}"; do
        local check_function="${check_def%%:*}"
        local check_description="${check_def##*:}"
        
        log "INFO" ""
        log "INFO" "🔍 $check_description..."
        
        if $check_function; then
            ((passed++))
            log "INFO" "✅ $check_description - PASS"
        else
            local exit_code=$?
            if [[ $exit_code -eq 1 ]]; then
                ((errors++))
                log "ERROR" "❌ $check_description - FAIL"
            else
                ((warnings++))
                log "WARN" "⚠️ $check_description - WARNING"
            fi
        fi
    done
    
    # Podsumowanie
    log "INFO" ""
    log "INFO" "📊 PODSUMOWANIE SPRAWDZENIA"
    log "INFO" "=========================="
    log "INFO" "✅ Testy przeszły: $passed"
    log "INFO" "⚠️ Ostrzeżenia: $warnings"
    log "INFO" "❌ Błędy: $errors"
    log "INFO" "📅 Data: $(date)"
    
    # Rekomendacje
    log "INFO" ""
    if [[ $errors -eq 0 ]]; then
        log "INFO" "🎉 SYSTEM GOTOWY DO DEPLOYMENTU!"
        if [[ $warnings -gt 0 ]]; then
            log "INFO" "ℹ️ Są ostrzeżenia, ale deployment może przebiec pomyślnie"
        fi
        return 0
    else
        log "ERROR" "🛑 SYSTEM WYMAGA POPRAWEK PRZED DEPLOYMENTEM"
        log "INFO" "Usuń błędy i uruchom ponownie sprawdzenie"
        return 1
    fi
}

# Funkcja pomocy
show_help() {
    echo "ASE-Bot Pre-Deployment System Check v$CHECK_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 [OPTIONS]"
    echo ""
    echo "Opcje:"
    echo "  -h, --help     Pokaż tę pomoc"
    echo "  -v, --verbose  Tryb szczegółowy"
    echo "  --quick       Szybkie sprawdzenie (podstawowe testy)"
    echo "  --report      Wygeneruj szczegółowy raport"
    echo ""
    echo "Przykłady:"
    echo "  $0                 # Standardowe sprawdzenie"
    echo "  $0 --verbose       # Szczegółowe sprawdzenie"
    echo "  $0 --quick         # Szybkie sprawdzenie"
    echo ""
}

# === MAIN ===

main() {
    local quick_mode=false
    local verbose_mode=false
    local generate_report=false
    
    # Parsuj argumenty
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                show_help
                exit 0
                ;;
            -v|--verbose)
                verbose_mode=true
                shift
                ;;
            --quick)
                quick_mode=true
                shift
                ;;
            --report)
                generate_report=true
                shift
                ;;
            *)
                echo "Nieznana opcja: $1"
                echo "Użyj '$0 --help' dla pomocy"
                exit 1
                ;;
        esac
    done
    
    # Ustaw tryb verbose jeśli wymagany
    if [[ "$verbose_mode" == true ]]; then
        set -x
    fi
    
    # Uruchom sprawdzenia
    if [[ "$quick_mode" == true ]]; then
        log "INFO" "🏃 Tryb szybki - podstawowe sprawdzenia"
        check_hardware_resources && check_network_connectivity && check_system_packages
    else
        run_all_checks
    fi
    
    local exit_code=$?
    
    # Wygeneruj raport jeśli wymagany
    if [[ "$generate_report" == true ]]; then
        log "INFO" "📄 Generowanie raportu..."
        # TODO: Implementuj generowanie raportu HTML/JSON
    fi
    
    exit $exit_code
}

# Uruchom główną funkcję
main "$@"
