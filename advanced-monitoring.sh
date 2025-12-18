#!/bin/bash

################################################################################
# ASE-Bot Advanced Monitoring and Alerting System
# System monitoringu z alertami email/slack oraz dashboard healthcheck
# Wersja: 1.0
################################################################################

set -euo pipefail

# === KONFIGURACJA ===
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_VERSION="1.0"

# Ścieżki
DEPLOY_DIR="/home/admin/trading-platform"
LOG_DIR="/var/log/asebot"
MONITOR_DIR="/home/admin/monitoring"
WEB_DIR="/var/www/asebot-dashboard"

# Konfiguracja alertów
ADMIN_EMAIL="admin@ase-bot.live"
SLACK_WEBHOOK_URL=""  # Opcjonalnie - ustaw webhook URL Slack
TELEGRAM_BOT_TOKEN=""  # Opcjonalnie - token bota Telegram
TELEGRAM_CHAT_ID=""    # Opcjonalnie - ID czatu Telegram

# Progi alertów
CPU_THRESHOLD=80         # %
MEMORY_THRESHOLD=85      # %
DISK_THRESHOLD=90        # %
RESPONSE_TIME_THRESHOLD=5000  # ms
ERROR_RATE_THRESHOLD=5   # %

# Konfiguracja dashboardu
DASHBOARD_PORT=9999
DASHBOARD_REFRESH_INTERVAL=30  # sekund

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
    echo "[$level] [$timestamp] $message" >> "$LOG_DIR/monitoring-$(date +%Y%m%d).log"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# === FUNKCJE ALERTÓW ===

send_email_alert() {
    local subject=$1
    local message=$2
    local priority=${3:-"normal"}  # low, normal, high
    
    if ! command_exists mail && ! command_exists sendmail; then
        log "WARN" "Brak narzędzi email - instalowanie..."
        sudo apt-get update && sudo apt-get install -y mailutils ssmtp
    fi
    
    if command_exists mail; then
        # Przygotuj wiadomość email
        local email_body="
ASE-Bot Monitoring Alert

Time: $(date)
Priority: $priority
Subject: $subject

Message:
$message

---
System Information:
Hostname: $(hostname)
Uptime: $(uptime)
Load Average: $(uptime | awk -F'load average:' '{print $2}')

Recent logs:
$(tail -10 "$LOG_DIR/monitoring-$(date +%Y%m%d).log" 2>/dev/null || echo "No recent logs")

---
ASE-Bot Monitoring System
"
        
        echo -e "$email_body" | mail -s "[$priority] ASE-Bot Alert: $subject" "$ADMIN_EMAIL" 2>/dev/null || log "WARN" "Nie udało się wysłać alertu email"
    fi
}

send_slack_alert() {
    local subject=$1
    local message=$2
    local priority=${3:-"normal"}
    
    if [[ -z "$SLACK_WEBHOOK_URL" ]]; then
        return 0
    fi
    
    local emoji
    case $priority in
        "high")   emoji=":red_circle:" ;;
        "normal") emoji=":yellow_circle:" ;;
        "low")    emoji=":white_circle:" ;;
        *)        emoji=":information_source:" ;;
    esac
    
    local slack_payload='{
        "text": "'"$emoji"' ASE-Bot Alert",
        "attachments": [
            {
                "color": "'"$([ "$priority" = "high" ] && echo "danger" || echo "warning")"'",
                "fields": [
                    {
                        "title": "'"$subject"'",
                        "value": "'"$message"'",
                        "short": false
                    },
                    {
                        "title": "Server",
                        "value": "'"$(hostname)"'",
                        "short": true
                    },
                    {
                        "title": "Time",
                        "value": "'"$(date)"'",
                        "short": true
                    }
                ]
            }
        ]
    }'
    
    if curl -X POST -H 'Content-type: application/json' --data "$slack_payload" "$SLACK_WEBHOOK_URL" >/dev/null 2>&1; then
        log "INFO" "Alert Slack wysłany"
    else
        log "WARN" "Nie udało się wysłać alertu Slack"
    fi
}

send_telegram_alert() {
    local subject=$1
    local message=$2
    local priority=${3:-"normal"}
    
    if [[ -z "$TELEGRAM_BOT_TOKEN" || -z "$TELEGRAM_CHAT_ID" ]]; then
        return 0
    fi
    
    local emoji
    case $priority in
        "high")   emoji="🔴" ;;
        "normal") emoji="🟡" ;;
        "low")    emoji="⚪" ;;
        *)        emoji="ℹ️" ;;
    esac
    
    local telegram_message="$emoji *ASE-Bot Alert*

*$subject*

$message

🖥️ Server: $(hostname)
🕐 Time: $(date)
"
    
    local telegram_url="https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage"
    
    if curl -s -X POST "$telegram_url" \
        -d chat_id="$TELEGRAM_CHAT_ID" \
        -d text="$telegram_message" \
        -d parse_mode="Markdown" >/dev/null; then
        log "INFO" "Alert Telegram wysłany"
    else
        log "WARN" "Nie udało się wysłać alertu Telegram"
    fi
}

send_alert() {
    local subject=$1
    local message=$2
    local priority=${3:-"normal"}
    
    log "INFO" "Wysyłanie alertu: $subject (priority: $priority)"
    
    # Zapisz alert do pliku
    local alert_file="$LOG_DIR/alerts.log"
    echo "$(date '+%Y-%m-%d %H:%M:%S') [$priority] $subject: $message" >> "$alert_file"
    
    # Wyślij przez różne kanały
    send_email_alert "$subject" "$message" "$priority" &
    send_slack_alert "$subject" "$message" "$priority" &
    send_telegram_alert "$subject" "$message" "$priority" &
    
    wait  # Poczekaj na zakończenie wszystkich alertów
}

# === FUNKCJE MONITORINGU ===

get_system_metrics() {
    local output_file=${1:-"/tmp/metrics.json"}
    
    # Zbierz metryki systemowe
    local timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local uptime_seconds=$(cat /proc/uptime | cut -d' ' -f1)
    
    # CPU
    local cpu_usage
    cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//' || echo "0")
    
    # Memory
    local memory_total memory_used memory_free memory_usage
    memory_total=$(free | grep '^Mem:' | awk '{print $2}')
    memory_used=$(free | grep '^Mem:' | awk '{print $3}')
    memory_free=$(free | grep '^Mem:' | awk '{print $4}')
    memory_usage=$(echo "scale=2; $memory_used * 100 / $memory_total" | bc)
    
    # Disk
    local disk_total disk_used disk_free disk_usage
    disk_usage=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
    disk_total=$(df /home | tail -1 | awk '{print $2}')
    disk_used=$(df /home | tail -1 | awk '{print $3}')
    disk_free=$(df /home | tail -1 | awk '{print $4}')
    
    # Load Average
    local load_1min load_5min load_15min
    read load_1min load_5min load_15min < <(uptime | awk -F'load average:' '{print $2}' | tr ',' ' ')
    
    # Network
    local network_rx_bytes network_tx_bytes
    network_rx_bytes=$(cat /sys/class/net/*/statistics/rx_bytes | awk '{sum+=$1} END {print sum}' || echo "0")
    network_tx_bytes=$(cat /sys/class/net/*/statistics/tx_bytes | awk '{sum+=$1} END {print sum}' || echo "0")
    
    # ASE-Bot specific metrics
    local api_status=false
    local proxy_status=false
    local api_response_time=0
    local proxy_response_time=0
    
    # Test API Backend
    if pgrep -f "simple_test_api" >/dev/null; then
        api_status=true
        local start_time=$(date +%s%3N)
        if curl -s --connect-timeout 5 http://localhost:8012/health >/dev/null; then
            local end_time=$(date +%s%3N)
            api_response_time=$((end_time - start_time))
        fi
    fi
    
    # Test Proxy Server
    if pgrep -f "unified_working" >/dev/null; then
        proxy_status=true
        local start_time=$(date +%s%3N)
        if curl -s --connect-timeout 5 http://localhost:8008/health >/dev/null; then
            local end_time=$(date +%s%3N)
            proxy_response_time=$((end_time - start_time))
        fi
    fi
    
    # Process metrics
    local api_pid proxy_pid api_memory=0 api_cpu=0 proxy_memory=0 proxy_cpu=0
    
    api_pid=$(pgrep -f "simple_test_api" | head -1 || echo "")
    if [[ -n "$api_pid" ]]; then
        api_memory=$(ps -p "$api_pid" -o %mem --no-headers 2>/dev/null | tr -d ' ' || echo "0")
        api_cpu=$(ps -p "$api_pid" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0")
    fi
    
    proxy_pid=$(pgrep -f "unified_working" | head -1 || echo "")
    if [[ -n "$proxy_pid" ]]; then
        proxy_memory=$(ps -p "$proxy_pid" -o %mem --no-headers 2>/dev/null | tr -d ' ' || echo "0")
        proxy_cpu=$(ps -p "$proxy_pid" -o %cpu --no-headers 2>/dev/null | tr -d ' ' || echo "0")
    fi
    
    # Utwórz JSON z metrykami
    cat > "$output_file" << EOF
{
    "timestamp": "$timestamp",
    "uptime_seconds": $uptime_seconds,
    "system": {
        "cpu_usage": $cpu_usage,
        "memory": {
            "total": $memory_total,
            "used": $memory_used,
            "free": $memory_free,
            "usage_percent": $memory_usage
        },
        "disk": {
            "total": $disk_total,
            "used": $disk_used,
            "free": $disk_free,
            "usage_percent": $disk_usage
        },
        "load_average": {
            "1min": $load_1min,
            "5min": $load_5min,
            "15min": $load_15min
        },
        "network": {
            "rx_bytes": $network_rx_bytes,
            "tx_bytes": $network_tx_bytes
        }
    },
    "services": {
        "api_backend": {
            "status": $api_status,
            "response_time_ms": $api_response_time,
            "pid": "$api_pid",
            "cpu_usage": $api_cpu,
            "memory_usage": $api_memory
        },
        "proxy_server": {
            "status": $proxy_status,
            "response_time_ms": $proxy_response_time,
            "pid": "$proxy_pid",
            "cpu_usage": $proxy_cpu,
            "memory_usage": $proxy_memory
        }
    }
}
EOF
    
    echo "$output_file"
}

check_thresholds() {
    local metrics_file=$1
    
    if [[ ! -f "$metrics_file" ]]; then
        return 1
    fi
    
    # Sprawdź progi i wyślij alerty jeśli przekroczone
    local cpu_usage memory_usage disk_usage
    
    cpu_usage=$(jq -r '.system.cpu_usage' "$metrics_file" 2>/dev/null | cut -d'.' -f1 || echo "0")
    memory_usage=$(jq -r '.system.memory.usage_percent' "$metrics_file" 2>/dev/null | cut -d'.' -f1 || echo "0")
    disk_usage=$(jq -r '.system.disk.usage_percent' "$metrics_file" 2>/dev/null || echo "0")
    
    # Alert CPU
    if [[ $cpu_usage -gt $CPU_THRESHOLD ]]; then
        send_alert "High CPU Usage" "CPU usage is ${cpu_usage}% (threshold: ${CPU_THRESHOLD}%)" "high"
    fi
    
    # Alert Memory
    if [[ $memory_usage -gt $MEMORY_THRESHOLD ]]; then
        send_alert "High Memory Usage" "Memory usage is ${memory_usage}% (threshold: ${MEMORY_THRESHOLD}%)" "high"
    fi
    
    # Alert Disk
    if [[ $disk_usage -gt $DISK_THRESHOLD ]]; then
        send_alert "High Disk Usage" "Disk usage is ${disk_usage}% (threshold: ${DISK_THRESHOLD}%)" "high"
    fi
    
    # Alert Services
    local api_status proxy_status
    api_status=$(jq -r '.services.api_backend.status' "$metrics_file" 2>/dev/null || echo "false")
    proxy_status=$(jq -r '.services.proxy_server.status' "$metrics_file" 2>/dev/null || echo "false")
    
    if [[ "$api_status" = "false" ]]; then
        send_alert "API Backend Down" "API Backend service is not running" "high"
    fi
    
    if [[ "$proxy_status" = "false" ]]; then
        send_alert "Proxy Server Down" "Proxy Server service is not running" "high"
    fi
    
    # Alert Response Time
    local api_response_time proxy_response_time
    api_response_time=$(jq -r '.services.api_backend.response_time_ms' "$metrics_file" 2>/dev/null || echo "0")
    proxy_response_time=$(jq -r '.services.proxy_server.response_time_ms' "$metrics_file" 2>/dev/null || echo "0")
    
    if [[ $api_response_time -gt $RESPONSE_TIME_THRESHOLD ]]; then
        send_alert "Slow API Response" "API Backend response time is ${api_response_time}ms (threshold: ${RESPONSE_TIME_THRESHOLD}ms)" "normal"
    fi
    
    if [[ $proxy_response_time -gt $RESPONSE_TIME_THRESHOLD ]]; then
        send_alert "Slow Proxy Response" "Proxy Server response time is ${proxy_response_time}ms (threshold: ${RESPONSE_TIME_THRESHOLD}ms)" "normal"
    fi
}

# === DASHBOARD WEB ===

create_web_dashboard() {
    log "INFO" "🌐 Tworzenie dashboardu web..."
    
    # Utwórz katalog dashboardu
    sudo mkdir -p "$WEB_DIR"
    sudo chown "$USER:$USER" "$WEB_DIR"
    
    # Utwórz główny plik HTML
    cat > "$WEB_DIR/index.html" << 'EOF'
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASE-Bot Monitoring Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; }
        .header { background: #2d3748; color: white; padding: 1rem; text-align: center; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; margin: 20px 0; }
        .card { background: white; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .card h3 { margin-bottom: 15px; color: #2d3748; }
        .metric { display: flex; justify-content: space-between; margin: 10px 0; padding: 10px; border-radius: 4px; }
        .metric.ok { background: #c6f6d5; color: #22543d; }
        .metric.warn { background: #fbd38d; color: #744210; }
        .metric.error { background: #fed7d7; color: #742a2a; }
        .status-indicator { width: 12px; height: 12px; border-radius: 50%; margin-right: 8px; }
        .status-indicator.online { background: #48bb78; }
        .status-indicator.offline { background: #f56565; }
        .chart-container { height: 300px; margin: 20px 0; }
        .refresh-info { text-align: center; color: #718096; margin: 20px 0; }
        table { width: 100%; border-collapse: collapse; margin: 15px 0; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { background: #f7fafc; font-weight: 600; }
        .btn { background: #4299e1; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; margin: 5px; }
        .btn:hover { background: #3182ce; }
        .alert-log { max-height: 200px; overflow-y: auto; background: #f7fafc; padding: 10px; border-radius: 4px; margin: 10px 0; font-family: monospace; font-size: 12px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 ASE-Bot Monitoring Dashboard</h1>
        <p>Real-time system monitoring and health check</p>
    </div>

    <div class="container">
        <div class="refresh-info">
            <span>Last updated: <span id="lastUpdate">Loading...</span></span>
            <button class="btn" onclick="refreshData()">🔄 Refresh Now</button>
            <button class="btn" onclick="toggleAutoRefresh()" id="autoRefreshBtn">⏸️ Pause Auto-refresh</button>
        </div>

        <div class="grid">
            <!-- System Overview -->
            <div class="card">
                <h3>🖥️ System Overview</h3>
                <div id="systemMetrics">Loading...</div>
            </div>

            <!-- Services Status -->
            <div class="card">
                <h3>⚙️ Services Status</h3>
                <div id="servicesStatus">Loading...</div>
            </div>

            <!-- Performance Metrics -->
            <div class="card">
                <h3>📊 Performance</h3>
                <div id="performanceMetrics">Loading...</div>
            </div>
        </div>

        <!-- Charts -->
        <div class="grid">
            <div class="card">
                <h3>📈 CPU & Memory Usage</h3>
                <div class="chart-container">
                    <canvas id="resourceChart"></canvas>
                </div>
            </div>

            <div class="card">
                <h3>🌐 Response Times</h3>
                <div class="chart-container">
                    <canvas id="responseChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Recent Alerts -->
        <div class="card">
            <h3>🚨 Recent Alerts</h3>
            <div class="alert-log" id="alertLog">Loading alerts...</div>
        </div>

        <!-- Detailed Metrics -->
        <div class="card">
            <h3>📋 Detailed Metrics</h3>
            <table id="detailedTable">
                <thead>
                    <tr><th>Metric</th><th>Current</th><th>Threshold</th><th>Status</th></tr>
                </thead>
                <tbody id="detailedMetrics">
                    <tr><td colspan="4">Loading...</td></tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let autoRefresh = true;
        let refreshInterval;
        let resourceChart, responseChart;
        
        // Initialize charts
        function initCharts() {
            const resourceCtx = document.getElementById('resourceChart').getContext('2d');
            resourceChart = new Chart(resourceCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'CPU %',
                        data: [],
                        borderColor: '#f56565',
                        backgroundColor: 'rgba(245, 101, 101, 0.1)',
                        tension: 0.4
                    }, {
                        label: 'Memory %',
                        data: [],
                        borderColor: '#4299e1',
                        backgroundColor: 'rgba(66, 153, 225, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true, max: 100 } }
                }
            });

            const responseCtx = document.getElementById('responseChart').getContext('2d');
            responseChart = new Chart(responseCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'API Response (ms)',
                        data: [],
                        borderColor: '#48bb78',
                        backgroundColor: 'rgba(72, 187, 120, 0.1)',
                        tension: 0.4
                    }, {
                        label: 'Proxy Response (ms)',
                        data: [],
                        borderColor: '#ed8936',
                        backgroundColor: 'rgba(237, 137, 54, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: { y: { beginAtZero: true } }
                }
            });
        }

        // Fetch metrics from server
        async function fetchMetrics() {
            try {
                const response = await fetch('/api/metrics');
                return await response.json();
            } catch (error) {
                console.error('Error fetching metrics:', error);
                return null;
            }
        }

        // Update dashboard
        async function updateDashboard() {
            const metrics = await fetchMetrics();
            if (!metrics) return;

            const now = new Date().toLocaleString();
            document.getElementById('lastUpdate').textContent = now;

            // Update system metrics
            updateSystemMetrics(metrics.system);
            updateServicesStatus(metrics.services);
            updatePerformanceMetrics(metrics);
            updateCharts(metrics);
            updateDetailedTable(metrics);
        }

        function updateSystemMetrics(system) {
            const html = `
                <div class="metric ${system.cpu_usage > 80 ? 'error' : system.cpu_usage > 60 ? 'warn' : 'ok'}">
                    <span>CPU Usage</span><span>${system.cpu_usage}%</span>
                </div>
                <div class="metric ${system.memory.usage_percent > 85 ? 'error' : system.memory.usage_percent > 70 ? 'warn' : 'ok'}">
                    <span>Memory Usage</span><span>${system.memory.usage_percent}%</span>
                </div>
                <div class="metric ${system.disk.usage_percent > 90 ? 'error' : system.disk.usage_percent > 80 ? 'warn' : 'ok'}">
                    <span>Disk Usage</span><span>${system.disk.usage_percent}%</span>
                </div>
                <div class="metric ok">
                    <span>Load Average</span><span>${system.load_average['1min']}</span>
                </div>
            `;
            document.getElementById('systemMetrics').innerHTML = html;
        }

        function updateServicesStatus(services) {
            const html = `
                <div class="metric ${services.api_backend.status ? 'ok' : 'error'}">
                    <span><span class="status-indicator ${services.api_backend.status ? 'online' : 'offline'}"></span>API Backend</span>
                    <span>${services.api_backend.status ? 'Online' : 'Offline'}</span>
                </div>
                <div class="metric ${services.proxy_server.status ? 'ok' : 'error'}">
                    <span><span class="status-indicator ${services.proxy_server.status ? 'online' : 'offline'}"></span>Proxy Server</span>
                    <span>${services.proxy_server.status ? 'Online' : 'Offline'}</span>
                </div>
            `;
            document.getElementById('servicesStatus').innerHTML = html;
        }

        function updatePerformanceMetrics(metrics) {
            const html = `
                <div class="metric ${metrics.services.api_backend.response_time_ms > 5000 ? 'warn' : 'ok'}">
                    <span>API Response Time</span><span>${metrics.services.api_backend.response_time_ms}ms</span>
                </div>
                <div class="metric ${metrics.services.proxy_server.response_time_ms > 5000 ? 'warn' : 'ok'}">
                    <span>Proxy Response Time</span><span>${metrics.services.proxy_server.response_time_ms}ms</span>
                </div>
                <div class="metric ok">
                    <span>Uptime</span><span>${Math.floor(metrics.uptime_seconds / 3600)}h</span>
                </div>
            `;
            document.getElementById('performanceMetrics').innerHTML = html;
        }

        function updateCharts(metrics) {
            const time = new Date().toLocaleTimeString();
            
            // Resource chart
            resourceChart.data.labels.push(time);
            resourceChart.data.datasets[0].data.push(metrics.system.cpu_usage);
            resourceChart.data.datasets[1].data.push(metrics.system.memory.usage_percent);
            
            if (resourceChart.data.labels.length > 20) {
                resourceChart.data.labels.shift();
                resourceChart.data.datasets[0].data.shift();
                resourceChart.data.datasets[1].data.shift();
            }
            resourceChart.update('none');

            // Response chart
            responseChart.data.labels.push(time);
            responseChart.data.datasets[0].data.push(metrics.services.api_backend.response_time_ms);
            responseChart.data.datasets[1].data.push(metrics.services.proxy_server.response_time_ms);
            
            if (responseChart.data.labels.length > 20) {
                responseChart.data.labels.shift();
                responseChart.data.datasets[0].data.shift();
                responseChart.data.datasets[1].data.shift();
            }
            responseChart.update('none');
        }

        function updateDetailedTable(metrics) {
            const rows = [
                ['CPU Usage', `${metrics.system.cpu_usage}%`, '80%', metrics.system.cpu_usage > 80 ? '⚠️' : '✅'],
                ['Memory Usage', `${metrics.system.memory.usage_percent}%`, '85%', metrics.system.memory.usage_percent > 85 ? '⚠️' : '✅'],
                ['Disk Usage', `${metrics.system.disk.usage_percent}%`, '90%', metrics.system.disk.usage_percent > 90 ? '⚠️' : '✅'],
                ['API Backend', metrics.services.api_backend.status ? 'Online' : 'Offline', 'Online', metrics.services.api_backend.status ? '✅' : '❌'],
                ['Proxy Server', metrics.services.proxy_server.status ? 'Online' : 'Offline', 'Online', metrics.services.proxy_server.status ? '✅' : '❌']
            ];

            const html = rows.map(row => 
                `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td><td>${row[3]}</td></tr>`
            ).join('');
            
            document.getElementById('detailedMetrics').innerHTML = html;
        }

        function refreshData() {
            updateDashboard();
        }

        function toggleAutoRefresh() {
            autoRefresh = !autoRefresh;
            const btn = document.getElementById('autoRefreshBtn');
            
            if (autoRefresh) {
                btn.textContent = '⏸️ Pause Auto-refresh';
                startAutoRefresh();
            } else {
                btn.textContent = '▶️ Start Auto-refresh';
                clearInterval(refreshInterval);
            }
        }

        function startAutoRefresh() {
            refreshInterval = setInterval(updateDashboard, 30000); // 30 seconds
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            initCharts();
            updateDashboard();
            startAutoRefresh();
        });
    </script>
</body>
</html>
EOF
    
    # Utwórz API endpoint dla metryk
    cat > "$WEB_DIR/api.py" << 'EOF'
#!/usr/bin/env python3
from flask import Flask, jsonify, send_from_directory
import json
import os
import subprocess
from datetime import datetime

app = Flask(__name__)

@app.route('/')
def dashboard():
    return send_from_directory('.', 'index.html')

@app.route('/api/metrics')
def get_metrics():
    try:
        # Wykonaj skrypt zbierający metryki
        result = subprocess.run(['/home/admin/trading-platform/get_metrics.sh'], 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            metrics = json.loads(result.stdout)
            return jsonify(metrics)
        else:
            return jsonify({'error': 'Failed to collect metrics'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/alerts')
def get_alerts():
    try:
        alerts = []
        alert_file = '/var/log/asebot/alerts.log'
        
        if os.path.exists(alert_file):
            with open(alert_file, 'r') as f:
                lines = f.readlines()[-50:]  # Last 50 alerts
                for line in lines:
                    alerts.append(line.strip())
        
        return jsonify({'alerts': alerts})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9999, debug=False)
EOF
    
    chmod +x "$WEB_DIR/api.py"
    
    log "INFO" "✅ Dashboard web utworzony"
    return 0
}

# Utwórz skrypt zbierający metryki dla dashboard
create_metrics_collector() {
    cat > "$DEPLOY_DIR/get_metrics.sh" << 'EOF'
#!/bin/bash

METRICS_FILE="/tmp/current_metrics.json"

# Użyj funkcji get_system_metrics z głównego skryptu
source "$(dirname "$0")/advanced-monitoring.sh"

get_system_metrics "$METRICS_FILE" >/dev/null 2>&1
cat "$METRICS_FILE"
EOF
    
    chmod +x "$DEPLOY_DIR/get_metrics.sh"
    
    return 0
}

# === KONFIGURACJA GŁÓWNA ===

setup_advanced_monitoring() {
    log "INFO" "🚀 Konfiguracja zaawansowanego monitoringu..."
    
    # Utwórz katalogi
    mkdir -p "$MONITOR_DIR" "$LOG_DIR"
    sudo mkdir -p "$WEB_DIR"
    sudo chown "$USER:$USER" "$WEB_DIR"
    
    # Zainstaluj wymagane narzędzia
    install_monitoring_tools
    
    # Utwórz skrypty monitoringu
    create_monitoring_scripts
    
    # Konfiguruj dashboard
    create_web_dashboard
    create_metrics_collector
    
    # Konfiguruj zadania cron
    setup_monitoring_cron
    
    # Start dashboard server
    start_dashboard_server
    
    log "INFO" "✅ Zaawansowany monitoring skonfigurowany"
    show_monitoring_info
    
    return 0
}

install_monitoring_tools() {
    log "INFO" "📦 Instalacja narzędzi monitoringu..."
    
    # Lista wymaganych pakietów
    local packages=(
        "jq"           # JSON parsing
        "bc"           # Calculator
        "curl"         # HTTP requests  
        "mailutils"    # Email sending
        "ssmtp"        # SMTP client
        "htop"         # Process monitoring
        "iotop"        # I/O monitoring
        "nethogs"      # Network monitoring
        "python3-flask" # Dashboard backend
    )
    
    local missing_packages=()
    
    for package in "${packages[@]}"; do
        if ! dpkg -l | grep -q "^ii.*$package"; then
            missing_packages+=("$package")
        fi
    done
    
    if [[ ${#missing_packages[@]} -gt 0 ]]; then
        log "INFO" "Instalowanie pakietów: ${missing_packages[*]}"
        if sudo apt-get update && sudo apt-get install -y "${missing_packages[@]}"; then
            log "INFO" "✅ Narzędzia monitoringu zainstalowane"
        else
            log "WARN" "⚠️ Nie udało się zainstalować niektórych narzędzi"
        fi
    else
        log "INFO" "✅ Wszystkie narzędzia już zainstalowane"
    fi
    
    return 0
}

create_monitoring_scripts() {
    log "INFO" "📝 Tworzenie skryptów monitoringu..."
    
    # Skrypt głównego monitoringu
    cat > "$MONITOR_DIR/main_monitor.sh" << 'EOF'
#!/bin/bash

source "$(dirname "$0")/../advanced-monitoring.sh"

# Zbierz metryki
METRICS_FILE="/tmp/monitoring_metrics.json"
get_system_metrics "$METRICS_FILE"

# Sprawdź progi i wyślij alerty
check_thresholds "$METRICS_FILE"

# Zapisz metryki do historii
HISTORY_DIR="/var/log/asebot/history"
mkdir -p "$HISTORY_DIR"
DATE=$(date +%Y%m%d)
cp "$METRICS_FILE" "$HISTORY_DIR/metrics_$(date +%Y%m%d_%H%M%S).json"

# Czyść starą historię (starsze niż 7 dni)
find "$HISTORY_DIR" -name "metrics_*.json" -mtime +7 -delete
EOF
    
    chmod +x "$MONITOR_DIR/main_monitor.sh"
    
    # Skrypt emergency response
    cat > "$MONITOR_DIR/emergency_response.sh" << 'EOF'
#!/bin/bash

LOG_DIR="/var/log/asebot"

log_emergency() {
    local message="$1"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] EMERGENCY: $message" | tee -a "$LOG_DIR/emergency.log"
}

# Sprawdź krytyczne problemy
check_critical_issues() {
    local critical_alerts=()
    
    # Sprawdź czy API Backend działa
    if ! pgrep -f "simple_test_api" >/dev/null; then
        critical_alerts+=("API Backend is down")
        
        # Próbuj restart
        log_emergency "Attempting to restart API Backend"
        cd /home/admin/trading-platform
        nohup python3 simple_test_api.py > /dev/null 2>&1 &
        sleep 5
        
        if pgrep -f "simple_test_api" >/dev/null; then
            log_emergency "API Backend restarted successfully"
        else
            log_emergency "Failed to restart API Backend"
        fi
    fi
    
    # Sprawdź czy Proxy Server działa
    if ! pgrep -f "unified_working" >/dev/null; then
        critical_alerts+=("Proxy Server is down")
        
        # Próbuj restart
        log_emergency "Attempting to restart Proxy Server"
        cd /home/admin/trading-platform
        nohup python3 unified_working.py > /dev/null 2>&1 &
        sleep 5
        
        if pgrep -f "unified_working" >/dev/null; then
            log_emergency "Proxy Server restarted successfully"
        else
            log_emergency "Failed to restart Proxy Server"
        fi
    fi
    
    # Sprawdź krytyczne zasoby
    local disk_usage
    disk_usage=$(df /home | tail -1 | awk '{print $5}' | sed 's/%//')
    
    if [[ $disk_usage -gt 95 ]]; then
        critical_alerts+=("Critical disk usage: ${disk_usage}%")
        
        # Wyczyść logi
        log_emergency "Cleaning old logs due to critical disk usage"
        find /var/log -name "*.log" -mtime +1 -delete 2>/dev/null || true
        find /tmp -mtime +1 -delete 2>/dev/null || true
    fi
    
    if [[ ${#critical_alerts[@]} -gt 0 ]]; then
        local alert_message="Critical issues detected:\n$(printf '%s\n' "${critical_alerts[@]}")"
        log_emergency "$alert_message"
        
        # Wyślij krytyczny alert
        echo -e "$alert_message" | mail -s "CRITICAL: ASE-Bot Emergency" admin@ase-bot.live 2>/dev/null || true
    fi
}

check_critical_issues
EOF
    
    chmod +x "$MONITOR_DIR/emergency_response.sh"
    
    log "INFO" "✅ Skrypty monitoringu utworzone"
    return 0
}

setup_monitoring_cron() {
    log "INFO" "⏰ Konfiguracja zadań cron dla monitoringu..."
    
    # Usuń stare zadania
    crontab -l 2>/dev/null | grep -v "asebot-monitoring" | crontab - 2>/dev/null || true
    
    # Dodaj nowe zadania cron
    (crontab -l 2>/dev/null; cat << EOF
# ASE-Bot Advanced Monitoring
*/5 * * * * $MONITOR_DIR/main_monitor.sh # asebot-monitoring-main
*/2 * * * * $MONITOR_DIR/emergency_response.sh # asebot-monitoring-emergency
*/1 * * * * $DEPLOY_DIR/get_metrics.sh > /tmp/current_metrics.json # asebot-monitoring-metrics
0 0 * * * find $LOG_DIR -name "*.log" -mtime +7 -delete # asebot-monitoring-cleanup
0 */6 * * * $DEPLOY_DIR/health_check.sh >> $LOG_DIR/health-summary.log # asebot-monitoring-health
EOF
    ) | crontab -
    
    log "INFO" "✅ Zadania cron skonfigurowane"
    return 0
}

start_dashboard_server() {
    log "INFO" "🌐 Uruchamianie serwera dashboard..."
    
    # Zatrzymaj istniejący dashboard
    pkill -f "dashboard.*api.py" 2>/dev/null || true
    sleep 2
    
    # Uruchom nowy dashboard
    cd "$WEB_DIR"
    nohup python3 api.py > "$LOG_DIR/dashboard.log" 2>&1 &
    
    sleep 3
    
    if pgrep -f "dashboard.*api.py" >/dev/null || pgrep -f "api.py" >/dev/null; then
        log "INFO" "✅ Dashboard server uruchomiony na porcie $DASHBOARD_PORT"
    else
        log "WARN" "⚠️ Nie udało się uruchomić dashboard servera"
    fi
    
    return 0
}

show_monitoring_info() {
    log "INFO" ""
    log "INFO" "📊 INFORMACJE O MONITORINGU"
    log "INFO" "=========================="
    log "INFO" "Dashboard URL: http://$(hostname):$DASHBOARD_PORT"
    log "INFO" "Katalog logów: $LOG_DIR"
    log "INFO" "Monitoring scripts: $MONITOR_DIR"
    log "INFO" "Alerty email: $ADMIN_EMAIL"
    log "INFO" ""
    log "INFO" "🔧 DOSTĘPNE KOMENDY"
    log "INFO" "=================="
    log "INFO" "$SCRIPT_DIR/advanced-monitoring.sh status    - Status monitoringu"
    log "INFO" "$SCRIPT_DIR/advanced-monitoring.sh test      - Test alertów"
    log "INFO" "$SCRIPT_DIR/advanced-monitoring.sh dashboard - Restart dashboard"
    log "INFO" ""
}

# === MAIN ===

show_help() {
    echo "ASE-Bot Advanced Monitoring and Alerting System v$MONITOR_VERSION"
    echo ""
    echo "Użycie:"
    echo "  $0 COMMAND [OPTIONS]"
    echo ""
    echo "Komendy:"
    echo "  setup                Pełna konfiguracja monitoringu"
    echo "  status               Status systemu monitoringu"
    echo "  test                 Test wysyłania alertów"
    echo "  dashboard            Restart dashboard web"
    echo "  metrics              Pokaż aktualne metryki"
    echo "  alerts               Pokaż ostatnie alerty"
    echo "  thresholds           Sprawdź progi alertów"
    echo ""
    echo "Przykłady:"
    echo "  $0 setup             # Konfiguruj monitoring"
    echo "  $0 status            # Sprawdź status"
    echo "  $0 test              # Test alertów"
    echo "  $0 metrics           # Aktualne metryki"
    echo ""
}

main() {
    local command=${1:-"help"}
    
    case $command in
        "setup"|"s")
            setup_advanced_monitoring
            ;;
        "status"|"st")
            log "INFO" "📊 Status monitoringu:"
            
            # Sprawdź czy skrypty działają
            if [[ -f "$MONITOR_DIR/main_monitor.sh" ]]; then
                log "INFO" "✅ Skrypty monitoringu zainstalowane"
            else
                log "WARN" "⚠️ Skrypty monitoringu nie są zainstalowane"
            fi
            
            # Sprawdź dashboard
            if pgrep -f "api.py" >/dev/null; then
                log "INFO" "✅ Dashboard web działa"
            else
                log "WARN" "⚠️ Dashboard web nie działa"
            fi
            
            # Sprawdź zadania cron
            if crontab -l | grep -q "asebot-monitoring"; then
                log "INFO" "✅ Zadania cron skonfigurowane"
            else
                log "WARN" "⚠️ Zadania cron nie są skonfigurowane"
            fi
            
            # Pokaż ostatnie metryki
            if [[ -f "/tmp/current_metrics.json" ]]; then
                log "INFO" "📊 Ostatnie metryki:"
                jq -r '.timestamp, .system.cpu_usage, .system.memory.usage_percent, .system.disk.usage_percent' /tmp/current_metrics.json 2>/dev/null || echo "Błąd odczytu metryk"
            fi
            ;;
        "test"|"t")
            log "INFO" "🧪 Test alertów..."
            send_alert "Test Alert" "To jest testowy alert z systemu monitoringu ASE-Bot" "normal"
            ;;
        "dashboard"|"d")
            start_dashboard_server
            ;;
        "metrics"|"m")
            local metrics_file="/tmp/current_metrics.json"
            get_system_metrics "$metrics_file" >/dev/null
            
            log "INFO" "📊 Aktualne metryki:"
            if command_exists jq; then
                jq . "$metrics_file"
            else
                cat "$metrics_file"
            fi
            ;;
        "alerts"|"a")
            log "INFO" "🚨 Ostatnie alerty:"
            if [[ -f "$LOG_DIR/alerts.log" ]]; then
                tail -20 "$LOG_DIR/alerts.log"
            else
                log "INFO" "Brak alertów"
            fi
            ;;
        "thresholds"|"th")
            log "INFO" "⚖️ Sprawdzanie progów alertów..."
            local metrics_file="/tmp/threshold_check.json"
            get_system_metrics "$metrics_file" >/dev/null
            check_thresholds "$metrics_file"
            ;;
        "help"|"h"|"-h"|"--help")
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
