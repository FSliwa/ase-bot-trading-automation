#!/bin/bash

# System Health Monitor for Trading Bot
# Usage: ./monitor.sh [check_type]

set -e

# Configuration
LOG_FILE="./logs/health_monitor.log"
ALERT_EMAIL="admin@tradingbot.com"
SLACK_WEBHOOK_URL=""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    send_alert "ERROR" "$1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
    send_alert "WARNING" "$1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

# Send alerts (email/slack)
send_alert() {
    local level=$1
    local message=$2
    
    # Log to file
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $level: $message" >> "$LOG_FILE"
    
    # Send to Slack if webhook configured
    if [[ -n "$SLACK_WEBHOOK_URL" ]]; then
        curl -X POST -H 'Content-type: application/json' \
            --data "{\"text\":\"🚨 Trading Bot Alert [$level]: $message\"}" \
            "$SLACK_WEBHOOK_URL" > /dev/null 2>&1
    fi
}

# Check Docker containers
check_containers() {
    log "Checking Docker containers..."
    
    local failed_containers=()
    local containers=("tradingbot" "postgres" "redis" "nginx" "prometheus" "grafana")
    
    for container in "${containers[@]}"; do
        if ! docker-compose ps "$container" | grep -q "Up"; then
            failed_containers+=("$container")
        fi
    done
    
    if [[ ${#failed_containers[@]} -gt 0 ]]; then
        error "Containers not running: ${failed_containers[*]}"
        return 1
    else
        info "All containers are running"
        return 0
    fi
}

# Check application health
check_application() {
    log "Checking application health..."
    
    # Check health endpoint
    if curl -s --max-time 10 http://localhost:8008/health > /dev/null; then
        info "Application health check passed"
    else
        error "Application health check failed"
        return 1
    fi
    
    # Check API endpoint
    if curl -s --max-time 10 http://localhost:8008/api/test-ai > /dev/null; then
        info "API health check passed"
    else
        warn "API health check failed"
        return 1
    fi
    
    return 0
}

# Check database connectivity
check_database() {
    log "Checking database connectivity..."
    
    if docker-compose exec -T postgres pg_isready -U tradingbot > /dev/null 2>&1; then
        info "Database is accessible"
    else
        error "Database connection failed"
        return 1
    fi
    
    # Check database size
    local db_size=$(docker-compose exec -T postgres psql -U tradingbot -d tradingbot -t -c "SELECT pg_size_pretty(pg_database_size('tradingbot'));" | xargs)
    info "Database size: $db_size"
    
    return 0
}

# Check Redis connectivity
check_redis() {
    log "Checking Redis connectivity..."
    
    if docker-compose exec -T redis redis-cli ping | grep -q "PONG"; then
        info "Redis is accessible"
    else
        error "Redis connection failed"
        return 1
    fi
    
    # Check Redis memory usage
    local redis_memory=$(docker-compose exec -T redis redis-cli info memory | grep used_memory_human | cut -d: -f2 | tr -d '\r')
    info "Redis memory usage: $redis_memory"
    
    return 0
}

# Check system resources
check_resources() {
    log "Checking system resources..."
    
    # CPU usage
    local cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | cut -d'%' -f1)
    info "CPU usage: ${cpu_usage}%"
    
    if (( $(echo "$cpu_usage > 80" | bc -l) )); then
        warn "High CPU usage: ${cpu_usage}%"
    fi
    
    # Memory usage
    local memory_info=$(free -h | grep '^Mem:')
    local memory_used=$(echo $memory_info | awk '{print $3}')
    local memory_total=$(echo $memory_info | awk '{print $2}')
    local memory_percent=$(free | grep '^Mem:' | awk '{printf "%.1f", $3/$2 * 100.0}')
    
    info "Memory usage: $memory_used / $memory_total (${memory_percent}%)"
    
    if (( $(echo "$memory_percent > 85" | bc -l) )); then
        warn "High memory usage: ${memory_percent}%"
    fi
    
    # Disk usage
    local disk_usage=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
    local disk_available=$(df -h . | tail -1 | awk '{print $4}')
    
    info "Disk usage: ${disk_usage}% (Available: $disk_available)"
    
    if [[ $disk_usage -gt 85 ]]; then
        warn "High disk usage: ${disk_usage}%"
    fi
    
    return 0
}

# Check SSL certificate
check_ssl() {
    log "Checking SSL certificate..."
    
    if [[ -f "ssl/cert.pem" ]]; then
        local expiry_date=$(openssl x509 -in ssl/cert.pem -noout -enddate | cut -d= -f2)
        local expiry_timestamp=$(date -d "$expiry_date" +%s)
        local current_timestamp=$(date +%s)
        local days_until_expiry=$(( (expiry_timestamp - current_timestamp) / 86400 ))
        
        info "SSL certificate expires in $days_until_expiry days"
        
        if [[ $days_until_expiry -lt 30 ]]; then
            warn "SSL certificate expires soon: $days_until_expiry days"
        fi
    else
        warn "SSL certificate not found"
    fi
    
    return 0
}

# Check log files for errors
check_logs() {
    log "Checking for critical errors in logs..."
    
    # Check for recent errors (last 1 hour)
    local error_count=$(find logs/ -name "*.log" -mmin -60 -exec grep -c "ERROR\|CRITICAL\|FATAL" {} + 2>/dev/null | awk -F: '{sum+=$2} END {print sum+0}')
    
    if [[ $error_count -gt 10 ]]; then
        warn "High error count in last hour: $error_count errors"
    else
        info "Error count in last hour: $error_count"
    fi
    
    return 0
}

# Check trading performance
check_trading() {
    log "Checking trading performance..."
    
    # This would connect to your trading database and check key metrics
    # Placeholder for actual implementation
    local recent_trades=$(docker-compose exec -T postgres psql -U tradingbot -d tradingbot -t -c "SELECT COUNT(*) FROM trades WHERE created_at > NOW() - INTERVAL '1 hour';" 2>/dev/null | xargs || echo "0")
    
    info "Recent trades (last hour): $recent_trades"
    
    if [[ $recent_trades -eq 0 ]]; then
        warn "No trades in the last hour"
    fi
    
    return 0
}

# Comprehensive health check
full_health_check() {
    log "Starting comprehensive health check..."
    
    local checks=(
        "check_containers"
        "check_application" 
        "check_database"
        "check_redis"
        "check_resources"
        "check_ssl"
        "check_logs"
        "check_trading"
    )
    
    local failed_checks=()
    
    for check in "${checks[@]}"; do
        if ! $check; then
            failed_checks+=("$check")
        fi
    done
    
    if [[ ${#failed_checks[@]} -eq 0 ]]; then
        log "✅ All health checks passed"
        return 0
    else
        error "❌ Failed checks: ${failed_checks[*]}"
        return 1
    fi
}

# Generate health report
generate_report() {
    log "Generating health report..."
    
    local report_file="./logs/health_report_$(date +%Y%m%d_%H%M%S).txt"
    
    {
        echo "=== Trading Bot Health Report ==="
        echo "Generated: $(date)"
        echo ""
        echo "=== Container Status ==="
        docker-compose ps
        echo ""
        echo "=== System Resources ==="
        echo "CPU Usage:"
        top -bn1 | head -3
        echo ""
        echo "Memory Usage:"
        free -h
        echo ""
        echo "Disk Usage:"
        df -h
        echo ""
        echo "=== Application Logs (Last 20 lines) ==="
        docker-compose logs --tail=20 tradingbot
        echo ""
        echo "=== Database Status ==="
        docker-compose exec -T postgres psql -U tradingbot -d tradingbot -c "SELECT version();"
        echo ""
        echo "=== Recent Errors ==="
        find logs/ -name "*.log" -mmin -60 -exec grep "ERROR\|CRITICAL\|FATAL" {} + 2>/dev/null | tail -10
    } > "$report_file"
    
    info "Health report generated: $report_file"
}

# Main script logic
case "${1:-full}" in
    "containers")
        check_containers
        ;;
    "app")
        check_application
        ;;
    "database")
        check_database
        ;;
    "redis")
        check_redis
        ;;
    "resources")
        check_resources
        ;;
    "ssl")
        check_ssl
        ;;
    "logs")
        check_logs
        ;;
    "trading")
        check_trading
        ;;
    "report")
        generate_report
        ;;
    "full")
        full_health_check
        ;;
    *)
        echo "Usage: $0 {containers|app|database|redis|resources|ssl|logs|trading|report|full}"
        echo ""
        echo "Health check options:"
        echo "  containers - Check Docker container status"
        echo "  app        - Check application health endpoints"
        echo "  database   - Check PostgreSQL connectivity"
        echo "  redis      - Check Redis connectivity"
        echo "  resources  - Check system resources (CPU, RAM, Disk)"
        echo "  ssl        - Check SSL certificate status"
        echo "  logs       - Check for recent errors in logs"
        echo "  trading    - Check trading performance metrics"
        echo "  report     - Generate comprehensive health report"
        echo "  full       - Run all health checks (default)"
        exit 1
        ;;
esac
