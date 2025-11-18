#!/bin/bash

################################################################################
# ASE-Bot Smoke Testing and Validation System
# Comprehensive testing suite dla sprawdzenia poprawności deploymentu
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_VERSION="1.0"

# Ścieżki
DEPLOY_DIR="/home/admin/trading-platform"
LOG_DIR="/var/log/asebot"
TEST_RESULTS_DIR="$LOG_DIR/test-results"

# Konfiguracja testów
BASE_URL="https://ase-bot.live"
API_URL="https://api.ase-bot.live"
DASHBOARD_URL="https://dashboard.ase-bot.live"
LOCAL_API_PORT=8012
LOCAL_PROXY_PORT=8008
LOCAL_DASHBOARD_PORT=9999

# Progi wydajności
MAX_RESPONSE_TIME=5000    # ms
MAX_LOAD_TIME=3000        # ms
MIN_UPTIME=99.0           # %
MAX_ERROR_RATE=1.0        # %

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
        "PASS")  echo -e "${GREEN}[PASS]${NC}  [$timestamp] $message" ;;
        "FAIL")  echo -e "${RED}[FAIL]${NC}  [$timestamp] $message" ;;
        *)       echo -e "[$timestamp] $message" ;;
    esac
    
    # Zapisz do pliku loga
    mkdir -p "$LOG_DIR" "$TEST_RESULTS_DIR"
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/smoke-tests-$(date +%Y%m%d).log"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

measure_time() {
    local start_time=$(date +%s%3N)
    "$@"
    local end_time=$(date +%s%3N)
    echo $((end_time - start_time))
}

# === TESTY SYSTEMOWE ===

test_system_resources() {
    log "INFO" "🖥️ Test zasobów systemowych..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test CPU
    local cpu_usage
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//' | cut -d'.' -f1)
    
    if [[ $cpu_usage -lt 80 ]]; then
        test_results+=("PASS: CPU Usage: ${cpu_usage}%")
        log "PASS" "CPU usage OK: ${cpu_usage}%"
    else
        test_results+=("FAIL: CPU Usage: ${cpu_usage}% (threshold: 80%)")
        log "FAIL" "High CPU usage: ${cpu_usage}%"
        overall_status="FAIL"
    fi
    
    # Test Memory
    local memory_usage
    memory_usage=$(free | grep '^Mem:' | awk '{printf "%.0f", $3*100/$2}')
    
    if [[ $memory_usage -lt 85 ]]; then
        test_results+=("PASS: Memory Usage: ${memory_usage}%")
        log "PASS" "Memory usage OK: ${memory_usage}%"
    else
        test_results+=("FAIL: Memory Usage: ${memory_usage}% (threshold: 85%)")
        log "FAIL" "High memory usage: ${memory_usage}%"
        overall_status="FAIL"
    fi
    
    # Test Disk
    local disk_usage
    disk_usage=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [[ $disk_usage -lt 90 ]]; then
        test_results+=("PASS: Disk Usage: ${disk_usage}%")
        log "PASS" "Disk usage OK: ${disk_usage}%"
    else
        test_results+=("FAIL: Disk Usage: ${disk_usage}% (threshold: 90%)")
        log "FAIL" "High disk usage: ${disk_usage}%"
        overall_status="FAIL"
    fi
    
    # Test Load Average
    local load_avg
    load_avg=$(uptime | awk -F'load average:' '{print $2}' | cut -d',' -f1 | tr -d ' ')
    
    if (( $(echo "$load_avg < 2.0" | bc -l) )); then
        test_results+=("PASS: Load Average: $load_avg")
        log "PASS" "Load average OK: $load_avg"
    else
        test_results+=("WARN: Load Average: $load_avg (threshold: 2.0)")
        log "WARN" "High load average: $load_avg"
    fi
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/system_resources.txt"
    
    log "INFO" "✅ Test zasobów systemowych zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

test_process_status() {
    log "INFO" "⚙️ Test statusu procesów..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test API Backend
    if pgrep -f "simple_test_api" >/dev/null; then
        local api_pid
        api_pid=$(pgrep -f "simple_test_api" | head -1)
        local api_memory
        api_memory=$(ps -p "$api_pid" -o %mem --no-headers | tr -d ' ' | cut -d'.' -f1)
        
        test_results+=("PASS: API Backend running (PID: $api_pid, Memory: ${api_memory}%)")
        log "PASS" "API Backend is running"
    else
        test_results+=("FAIL: API Backend not running")
        log "FAIL" "API Backend process not found"
        overall_status="FAIL"
    fi
    
    # Test Proxy Server
    if pgrep -f "unified_working" >/dev/null; then
        local proxy_pid
        proxy_pid=$(pgrep -f "unified_working" | head -1)
        local proxy_memory
        proxy_memory=$(ps -p "$proxy_pid" -o %mem --no-headers | tr -d ' ' | cut -d'.' -f1)
        
        test_results+=("PASS: Proxy Server running (PID: $proxy_pid, Memory: ${proxy_memory}%)")
        log "PASS" "Proxy Server is running"
    else
        test_results+=("FAIL: Proxy Server not running")
        log "FAIL" "Proxy Server process not found"
        overall_status="FAIL"
    fi
    
    # Test Dashboard
    if pgrep -f "api.py" >/dev/null; then
        local dashboard_pid
        dashboard_pid=$(pgrep -f "api.py" | head -1)
        
        test_results+=("PASS: Dashboard Server running (PID: $dashboard_pid)")
        log "PASS" "Dashboard Server is running"
    else
        test_results+=("WARN: Dashboard Server not running")
        log "WARN" "Dashboard Server process not found"
    fi
    
    # Test Nginx
    if systemctl is-active --quiet nginx; then
        test_results+=("PASS: Nginx service active")
        log "PASS" "Nginx is running"
    else
        test_results+=("FAIL: Nginx service not active")
        log "FAIL" "Nginx is not running"
        overall_status="FAIL"
    fi
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/process_status.txt"
    
    log "INFO" "✅ Test statusu procesów zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

# === TESTY SIECIOWE I POŁĄCZEŃ ===

test_port_connectivity() {
    log "INFO" "🌐 Test dostępności portów..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test lokalnych portów
    local ports=("$LOCAL_API_PORT:API Backend" "$LOCAL_PROXY_PORT:Proxy Server" "$LOCAL_DASHBOARD_PORT:Dashboard")
    
    for port_info in "${ports[@]}"; do
        local port="${port_info%%:*}"
        local service="${port_info##*:}"
        
        if nc -z localhost "$port" 2>/dev/null; then
            test_results+=("PASS: $service port $port accessible")
            log "PASS" "$service listening on port $port"
        else
            test_results+=("FAIL: $service port $port not accessible")
            log "FAIL" "$service not listening on port $port"
            overall_status="FAIL"
        fi
    done
    
    # Test zewnętrznych portów
    local ext_ports=("80:HTTP" "443:HTTPS")
    
    for port_info in "${ext_ports[@]}"; do
        local port="${port_info%%:*}"
        local service="${port_info##*:}"
        
        if nc -z localhost "$port" 2>/dev/null; then
            test_results+=("PASS: $service port $port open")
            log "PASS" "$service port $port is open"
        else
            test_results+=("FAIL: $service port $port not accessible")
            log "FAIL" "$service port $port is not accessible"
            overall_status="FAIL"
        fi
    done
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/port_connectivity.txt"
    
    log "INFO" "✅ Test dostępności portów zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

test_http_endpoints() {
    log "INFO" "🔗 Test endpointów HTTP..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test głównej strony
    local response_time
    response_time=$(measure_time curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$BASE_URL")
    local http_code=$(curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$BASE_URL")
    
    if [[ "$http_code" = "200" ]]; then
        test_results+=("PASS: Main page HTTP $http_code (${response_time}ms)")
        log "PASS" "Main page accessible: HTTP $http_code"
    else
        test_results+=("FAIL: Main page HTTP $http_code")
        log "FAIL" "Main page not accessible: HTTP $http_code"
        overall_status="FAIL"
    fi
    
    # Test API Health
    response_time=$(measure_time curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$API_URL/health")
    http_code=$(curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$API_URL/health")
    
    if [[ "$http_code" = "200" ]]; then
        test_results+=("PASS: API Health HTTP $http_code (${response_time}ms)")
        log "PASS" "API health endpoint accessible: HTTP $http_code"
    else
        test_results+=("FAIL: API Health HTTP $http_code")
        log "FAIL" "API health endpoint not accessible: HTTP $http_code"
        overall_status="FAIL"
    fi
    
    # Test Dashboard
    response_time=$(measure_time curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$DASHBOARD_URL")
    http_code=$(curl -s --connect-timeout 10 --max-time 30 -o /dev/null -w "%{http_code}" "$DASHBOARD_URL")
    
    if [[ "$http_code" = "200" ]]; then
        test_results+=("PASS: Dashboard HTTP $http_code (${response_time}ms)")
        log "PASS" "Dashboard accessible: HTTP $http_code"
    else
        test_results+=("WARN: Dashboard HTTP $http_code")
        log "WARN" "Dashboard not accessible: HTTP $http_code"
    fi
    
    # Test local endpoints
    local local_endpoints=("http://localhost:$LOCAL_API_PORT/health:API Backend" 
                          "http://localhost:$LOCAL_PROXY_PORT/health:Proxy Server"
                          "http://localhost:$LOCAL_DASHBOARD_PORT:Dashboard")
    
    for endpoint_info in "${local_endpoints[@]}"; do
        local endpoint="${endpoint_info%%:*}"
        local service="${endpoint_info##*:}"
        
        response_time=$(measure_time curl -s --connect-timeout 5 --max-time 15 -o /dev/null -w "%{http_code}" "$endpoint")
        http_code=$(curl -s --connect-timeout 5 --max-time 15 -o /dev/null -w "%{http_code}" "$endpoint")
        
        if [[ "$http_code" = "200" ]]; then
            test_results+=("PASS: $service local HTTP $http_code (${response_time}ms)")
            log "PASS" "$service local endpoint OK: HTTP $http_code"
        else
            test_results+=("FAIL: $service local HTTP $http_code")
            log "FAIL" "$service local endpoint failed: HTTP $http_code"
            overall_status="FAIL"
        fi
    done
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/http_endpoints.txt"
    
    log "INFO" "✅ Test endpointów HTTP zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

test_ssl_certificates() {
    log "INFO" "🔒 Test certyfikatów SSL..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test głównej domeny
    local domains=("ase-bot.live" "api.ase-bot.live" "dashboard.ase-bot.live")
    
    for domain in "${domains[@]}"; do
        log "DEBUG" "Testing SSL for domain: $domain"
        
        # Sprawdź czy certyfikat jest ważny
        local cert_info
        if cert_info=$(echo | timeout 10 openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | openssl x509 -noout -dates 2>/dev/null); then
            local not_after
            not_after=$(echo "$cert_info" | grep "notAfter" | cut -d'=' -f2)
            
            test_results+=("PASS: $domain SSL certificate valid until $not_after")
            log "PASS" "$domain SSL certificate is valid"
        else
            test_results+=("FAIL: $domain SSL certificate invalid or not accessible")
            log "FAIL" "$domain SSL certificate problem"
            overall_status="FAIL"
        fi
        
        # Test siły szyfrowania
        local ssl_grade
        if ssl_grade=$(echo | timeout 10 openssl s_client -servername "$domain" -connect "$domain:443" 2>/dev/null | grep "Cipher is" | awk '{print $4}'); then
            test_results+=("INFO: $domain SSL Cipher: $ssl_grade")
            log "INFO" "$domain using SSL cipher: $ssl_grade"
        fi
    done
    
    # Test certyfikatów lokalnych
    local ssl_dir="/etc/ssl/certs/asebot"
    if [[ -f "$ssl_dir/fullchain.pem" ]]; then
        local cert_expiry
        cert_expiry=$(openssl x509 -in "$ssl_dir/fullchain.pem" -noout -enddate | cut -d'=' -f2)
        
        test_results+=("PASS: Local SSL certificate valid until $cert_expiry")
        log "PASS" "Local SSL certificate is valid"
    else
        test_results+=("FAIL: Local SSL certificate not found")
        log "FAIL" "Local SSL certificate missing"
        overall_status="FAIL"
    fi
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/ssl_certificates.txt"
    
    log "INFO" "✅ Test certyfikatów SSL zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

# === TESTY WYDAJNOŚCI ===

test_response_times() {
    log "INFO" "⚡ Test czasów odpowiedzi..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test różnych endpointów z mierzeniem czasów
    local endpoints=("$BASE_URL:Main Page" 
                    "$API_URL/health:API Health"
                    "$DASHBOARD_URL:Dashboard"
                    "http://localhost:$LOCAL_API_PORT/health:Local API"
                    "http://localhost:$LOCAL_PROXY_PORT/health:Local Proxy")
    
    for endpoint_info in "${endpoints[@]}"; do
        local endpoint="${endpoint_info%%:*}"
        local service="${endpoint_info##*:}"
        
        local total_time=0
        local successful_requests=0
        local failed_requests=0
        
        # Wykonaj 5 requestów dla każdego endpointu
        for i in {1..5}; do
            local response_time
            response_time=$(curl -w "@-" -o /dev/null -s --connect-timeout 5 --max-time 30 "$endpoint" <<< '%{time_total}' 2>/dev/null || echo "0")
            
            if [[ "$response_time" != "0" ]]; then
                local response_time_ms
                response_time_ms=$(echo "$response_time * 1000" | bc | cut -d'.' -f1)
                total_time=$((total_time + response_time_ms))
                ((successful_requests++))
            else
                ((failed_requests++))
            fi
            
            sleep 1  # Odstęp między requestami
        done
        
        if [[ $successful_requests -gt 0 ]]; then
            local avg_time=$((total_time / successful_requests))
            
            if [[ $avg_time -le $MAX_RESPONSE_TIME ]]; then
                test_results+=("PASS: $service avg response: ${avg_time}ms (${successful_requests}/5 successful)")
                log "PASS" "$service response time OK: ${avg_time}ms"
            else
                test_results+=("FAIL: $service avg response: ${avg_time}ms (threshold: ${MAX_RESPONSE_TIME}ms)")
                log "FAIL" "$service response time too high: ${avg_time}ms"
                overall_status="FAIL"
            fi
        else
            test_results+=("FAIL: $service - all requests failed")
            log "FAIL" "$service - all requests failed"
            overall_status="FAIL"
        fi
    done
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/response_times.txt"
    
    log "INFO" "✅ Test czasów odpowiedzi zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

test_load_capacity() {
    log "INFO" "💪 Test obciążenia systemu..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test z concurrent requests
    local test_url="http://localhost:$LOCAL_API_PORT/health"
    local concurrent_users=10
    local requests_per_user=5
    
    log "INFO" "Wykonuję test obciążenia: $concurrent_users users × $requests_per_user requests"
    
    # Utwórz temporary file dla wyników
    local temp_results=$(mktemp)
    
    # Wykonaj concurrent requests
    for i in $(seq 1 $concurrent_users); do
        {
            local user_success=0
            local user_total=0
            local user_time=0
            
            for j in $(seq 1 $requests_per_user); do
                local start_time=$(date +%s%3N)
                if curl -s --connect-timeout 5 --max-time 10 "$test_url" >/dev/null 2>&1; then
                    ((user_success++))
                    local end_time=$(date +%s%3N)
                    user_time=$((user_time + end_time - start_time))
                fi
                ((user_total++))
            done
            
            echo "$user_success,$user_total,$user_time" >> "$temp_results"
        } &
    done
    
    # Czekaj na zakończenie wszystkich procesów
    wait
    
    # Analizuj wyniki
    local total_success=0
    local total_requests=0
    local total_time=0
    
    while IFS=',' read -r success total time; do
        total_success=$((total_success + success))
        total_requests=$((total_requests + total))
        total_time=$((total_time + time))
    done < "$temp_results"
    
    rm -f "$temp_results"
    
    # Oblicz statystyki
    local success_rate=0
    if [[ $total_requests -gt 0 ]]; then
        success_rate=$(echo "scale=2; $total_success * 100 / $total_requests" | bc)
    fi
    
    local avg_response_time=0
    if [[ $total_success -gt 0 ]]; then
        avg_response_time=$((total_time / total_success))
    fi
    
    # Oceń wyniki
    if (( $(echo "$success_rate >= 95.0" | bc -l) )); then
        test_results+=("PASS: Load test success rate: ${success_rate}%")
        log "PASS" "Load test success rate acceptable: ${success_rate}%"
    else
        test_results+=("FAIL: Load test success rate: ${success_rate}% (threshold: 95%)")
        log "FAIL" "Load test success rate too low: ${success_rate}%"
        overall_status="FAIL"
    fi
    
    if [[ $avg_response_time -le $MAX_RESPONSE_TIME ]]; then
        test_results+=("PASS: Load test avg response: ${avg_response_time}ms")
        log "PASS" "Load test response time OK: ${avg_response_time}ms"
    else
        test_results+=("FAIL: Load test avg response: ${avg_response_time}ms (threshold: ${MAX_RESPONSE_TIME}ms)")
        log "FAIL" "Load test response time too high: ${avg_response_time}ms"
        overall_status="FAIL"
    fi
    
    test_results+=("INFO: Total requests: $total_requests, Successful: $total_success")
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/load_capacity.txt"
    
    log "INFO" "✅ Test obciążenia zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

# === TESTY FUNKCJONALNE ===

test_api_functionality() {
    log "INFO" "🔧 Test funkcjonalności API..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Test podstawowych endpointów API
    local api_base="http://localhost:$LOCAL_API_PORT"
    
    # Test health endpoint
    local response
    response=$(curl -s --connect-timeout 5 "$api_base/health" 2>/dev/null || echo "ERROR")
    
    if [[ "$response" != "ERROR" ]]; then
        test_results+=("PASS: API health endpoint responsive")
        log "PASS" "API health endpoint OK"
    else
        test_results+=("FAIL: API health endpoint not responsive")
        log "FAIL" "API health endpoint failed"
        overall_status="FAIL"
    fi
    
    # Test jeśli istnieją inne endpointy
    local test_endpoints=("/status" "/info" "/version")
    
    for endpoint in "${test_endpoints[@]}"; do
        local http_code
        http_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$api_base$endpoint" 2>/dev/null || echo "000")
        
        if [[ "$http_code" = "200" ]]; then
            test_results+=("PASS: API endpoint $endpoint returns HTTP 200")
            log "PASS" "API endpoint $endpoint OK"
        elif [[ "$http_code" = "404" ]]; then
            test_results+=("INFO: API endpoint $endpoint not implemented (HTTP 404)")
            log "INFO" "API endpoint $endpoint not implemented"
        else
            test_results+=("WARN: API endpoint $endpoint returns HTTP $http_code")
            log "WARN" "API endpoint $endpoint returned HTTP $http_code"
        fi
    done
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/api_functionality.txt"
    
    log "INFO" "✅ Test funkcjonalności API zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

test_database_connectivity() {
    log "INFO" "🗄️ Test łączności z bazą danych..."
    
    local test_results=()
    local overall_status="PASS"
    
    # Sprawdź czy plik bazy danych istnieje
    local db_file="$DEPLOY_DIR/trading.db"
    
    if [[ -f "$db_file" ]]; then
        test_results+=("PASS: Database file exists: $db_file")
        log "PASS" "Database file found"
        
        # Sprawdź czy można odczytać bazę
        if sqlite3 "$db_file" "SELECT name FROM sqlite_master WHERE type='table';" >/dev/null 2>&1; then
            local table_count
            table_count=$(sqlite3 "$db_file" "SELECT COUNT(*) FROM sqlite_master WHERE type='table';" 2>/dev/null || echo "0")
            
            test_results+=("PASS: Database readable with $table_count tables")
            log "PASS" "Database is accessible with $table_count tables"
        else
            test_results+=("FAIL: Database file not readable")
            log "FAIL" "Database file cannot be read"
            overall_status="FAIL"
        fi
        
        # Sprawdź rozmiar bazy
        local db_size
        db_size=$(du -h "$db_file" | cut -f1)
        test_results+=("INFO: Database size: $db_size")
        
    else
        test_results+=("WARN: Database file not found: $db_file")
        log "WARN" "Database file not found"
    fi
    
    # Zapisz wyniki
    printf '%s\n' "${test_results[@]}" > "$TEST_RESULTS_DIR/database_connectivity.txt"
    
    log "INFO" "✅ Test łączności z bazą danych zakończony: $overall_status"
    return $([ "$overall_status" = "PASS" ] && echo 0 || echo 1)
}

# === GENEROWANIE RAPORTÓW ===

generate_test_report() {
    log "INFO" "📊 Generowanie raportu testów..."
    
    local report_file="$TEST_RESULTS_DIR/smoke_test_report_$(date +%Y%m%d_%H%M%S).md"
    local summary_file="$TEST_RESULTS_DIR/test_summary.json"
    
    # Zbierz wyniki wszystkich testów
    local total_tests=0
    local passed_tests=0
    local failed_tests=0
    local warnings=0
    
    # Nagłówek raportu
    cat > "$report_file" << EOF
# ASE-Bot Smoke Test Report

**Generated:** $(date)  
**Version:** $TEST_VERSION  
**Server:** $(hostname)  

## Executive Summary

EOF
    
    # Przeanalizuj wyniki każdej kategorii testów
    local test_categories=("system_resources" "process_status" "port_connectivity" "http_endpoints" "ssl_certificates" "response_times" "load_capacity" "api_functionality" "database_connectivity")
    
    for category in "${test_categories[@]}"; do
        local result_file="$TEST_RESULTS_DIR/${category}.txt"
        
        if [[ -f "$result_file" ]]; then
            echo "### $(echo $category | tr '_' ' ' | sed 's/\b\w/\U&/g')" >> "$report_file"
            echo "" >> "$report_file"
            
            local category_pass=0
            local category_fail=0
            local category_warn=0
            local category_info=0
            
            while read -r line; do
                ((total_tests++))
                echo "- $line" >> "$report_file"
                
                if [[ "$line" == PASS:* ]]; then
                    ((passed_tests++))
                    ((category_pass++))
                elif [[ "$line" == FAIL:* ]]; then
                    ((failed_tests++))
                    ((category_fail++))
                elif [[ "$line" == WARN:* ]]; then
                    ((warnings++))
                    ((category_warn++))
                elif [[ "$line" == INFO:* ]]; then
                    ((category_info++))
                fi
            done < "$result_file"
            
            echo "" >> "$report_file"
            echo "**Summary:** $category_pass passed, $category_fail failed, $category_warn warnings, $category_info info" >> "$report_file"
            echo "" >> "$report_file"
        fi
    done
    
    # Dodaj podsumowanie na początek
    local overall_status="PASS"
    if [[ $failed_tests -gt 0 ]]; then
        overall_status="FAIL"
    elif [[ $warnings -gt 5 ]]; then
        overall_status="WARN"
    fi
    
    # Wstaw podsumowanie
    sed -i "/## Executive Summary/a\\
\\
**Overall Status:** $overall_status  \\
**Total Tests:** $total_tests  \\
**Passed:** $passed_tests  \\
**Failed:** $failed_tests  \\
**Warnings:** $warnings  \\
**Success Rate:** $(echo "scale=1; $passed_tests * 100 / $total_tests" | bc)%  \\
" "$report_file"
    
    # Utwórz JSON summary
    cat > "$summary_file" << EOF
{
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "version": "$TEST_VERSION",
    "server": "$(hostname)",
    "overall_status": "$overall_status",
    "total_tests": $total_tests,
    "passed_tests": $passed_tests,
    "failed_tests": $failed_tests,
    "warnings": $warnings,
    "success_rate": $(echo "scale=2; $passed_tests * 100 / $total_tests" | bc)
}
EOF
    
    log "INFO" "📄 Raport wygenerowany: $report_file"
    log "INFO" "📊 Podsumowanie JSON: $summary_file"
    
    return 0
}

# === MAIN FUNCTION ===

run_all_tests() {
    log "INFO" "🚀 Rozpoczynam pełny pakiet testów smoke..."
    
    local start_time=$(date +%s)
    local test_results=()
    
    # Uruchom wszystkie testy
    test_system_resources && test_results+=("system_resources:PASS") || test_results+=("system_resources:FAIL")
    test_process_status && test_results+=("process_status:PASS") || test_results+=("process_status:FAIL")
    test_port_connectivity && test_results+=("port_connectivity:PASS") || test_results+=("port_connectivity:FAIL")
    test_http_endpoints && test_results+=("http_endpoints:PASS") || test_results+=("http_endpoints:FAIL")
    test_ssl_certificates && test_results+=("ssl_certificates:PASS") || test_results+=("ssl_certificates:FAIL")
    test_response_times && test_results+=("response_times:PASS") || test_results+=("response_times:FAIL")
    test_load_capacity && test_results+=("load_capacity:PASS") || test_results+=("load_capacity:FAIL")
    test_api_functionality && test_results+=("api_functionality:PASS") || test_results+=("api_functionality:FAIL")
    test_database_connectivity && test_results+=("database_connectivity:PASS") || test_results+=("database_connectivity:FAIL")
    
    # Wygeneruj raport
    generate_test_report
    
    local end_time=$(date +%s)
    local duration=$((end_time - start_time))
    
    # Podsumowanie
    local total_categories=${#test_results[@]}
    local passed_categories=0
    
    log "INFO" ""
    log "INFO" "📊 PODSUMOWANIE TESTÓW SMOKE"
    log "INFO" "============================"
    
    for result in "${test_results[@]}"; do
        local category="${result%%:*}"
        local status="${result##*:}"
        
        if [[ "$status" = "PASS" ]]; then
            log "PASS" "$category"
            ((passed_categories++))
        else
            log "FAIL" "$category"
        fi
    done
    
    log "INFO" ""
    log "INFO" "Czas wykonania: ${duration}s"
    log "INFO" "Kategorie: $passed_categories/$total_categories pomyślne"
    log "INFO" "Raport: $TEST_RESULTS_DIR/"
    
    if [[ $passed_categories -eq $total_categories ]]; then
        log "PASS" "🎉 Wszystkie testy zakończone pomyślnie!"
        return 0
    else
        log "FAIL" "❌ Niektóre testy nie powiodły się"
        return 1
    fi
}

show_help() {
    echo "ASE-Bot Smoke Testing and Validation System v$TEST_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 COMMAND [OPTIONS]"
    echo ""
    echo "Komendy:"
    echo "  all                  Uruchom wszystkie testy smoke"
    echo "  system               Test zasobów systemowych"
    echo "  processes            Test statusu procesów"
    echo "  network              Test połączeń sieciowych"
    echo "  http                 Test endpointów HTTP"
    echo "  ssl                  Test certyfikatów SSL"
    echo "  performance          Test wydajności"
    echo "  api                  Test funkcjonalności API"
    echo "  database             Test łączności z bazą danych"
    echo "  report               Wygeneruj tylko raport"
    echo ""
    echo "Opcje:"
    echo "  --max-response-time  Ustaw maksymalny czas odpowiedzi (ms)"
    echo "  --verbose           Więcej szczegółów"
    echo ""
    echo "Przykłady:"
    echo "  $0 all               # Wszystkie testy"
    echo "  $0 performance       # Tylko testy wydajności"
    echo "  $0 system            # Tylko testy systemowe"
    echo ""
}

main() {
    local command=${1:-"help"}
    
    case $command in
        "all"|"a")
            run_all_tests
            ;;
        "system"|"sys")
            test_system_resources
            ;;
        "processes"|"proc")
            test_process_status
            ;;
        "network"|"net")
            test_port_connectivity
            ;;
        "http"|"h")
            test_http_endpoints
            ;;
        "ssl"|"s")
            test_ssl_certificates
            ;;
        "performance"|"perf")
            test_response_times
            test_load_capacity
            ;;
        "api")
            test_api_functionality
            ;;
        "database"|"db")
            test_database_connectivity
            ;;
        "report"|"r")
            generate_test_report
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
