#!/bin/bash

# Port Conflict Resolution Script
# Usage: ./resolve_port_conflicts.sh

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -i :$port >/dev/null 2>&1; then
        return 0  # Port is in use
    else
        return 1  # Port is free
    fi
}

# Function to kill process on port
kill_port() {
    local port=$1
    local pids=$(lsof -ti :$port)
    if [ -n "$pids" ]; then
        warn "Killing processes on port $port: $pids"
        echo $pids | xargs kill -9
        sleep 2
        if check_port $port; then
            error "Failed to free port $port"
            return 1
        else
            log "Port $port freed successfully"
        fi
    fi
}

# Main conflict resolution
resolve_conflicts() {
    log "Starting port conflict resolution..."
    
    # Check critical ports that need to be free for Docker deployment
    local conflict_ports=(3000 8080)
    local conflicts_found=false
    
    for port in "${conflict_ports[@]}"; do
        if check_port $port; then
            warn "Port $port is in use"
            conflicts_found=true
            
            # Show what's using the port
            echo "Process using port $port:"
            lsof -i :$port
            echo
            
            # Ask user if they want to kill the process
            read -p "Do you want to kill the process on port $port? (y/N): " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                kill_port $port
            else
                warn "Port $port left occupied - may cause conflicts during deployment"
            fi
        else
            log "Port $port is free"
        fi
    done
    
    if [ "$conflicts_found" = false ]; then
        log "No port conflicts detected"
    fi
}

# Check current port usage
show_current_ports() {
    log "Current port usage:"
    echo
    echo "Critical ports status:"
    
    local ports=(8008 3000 3001 5432 5433 6379 8080 8081 9090 9100 9121 9187)
    
    for port in "${ports[@]}"; do
        if check_port $port; then
            echo -e "${RED}✗${NC} Port $port: IN USE"
            lsof -i :$port | head -1 | awk '{print "   Process: " $1 " (PID: " $2 ")"}'
        else
            echo -e "${GREEN}✓${NC} Port $port: FREE"
        fi
    done
    echo
}

# Verify Docker requirements
check_docker_requirements() {
    log "Checking Docker requirements..."
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        error "Docker is not running. Please start Docker first."
        return 1
    fi
    
    # Check if docker-compose is available
    if ! command -v docker-compose &> /dev/null; then
        error "docker-compose is not installed"
        return 1
    fi
    
    log "Docker requirements satisfied"
}

# Test new port configuration
test_configuration() {
    log "Testing new port configuration..."
    
    # Check if .env file has the new port configurations
    if grep -q "GRAFANA_PORT=3001" .env; then
        log "✓ Grafana port updated to 3001"
    else
        warn "Grafana port not configured in .env"
    fi
    
    if grep -q "POSTGRES_PORT=5433" .env; then
        log "✓ PostgreSQL port updated to 5433"
    else
        warn "PostgreSQL port not configured in .env"
    fi
    
    if grep -q "NGINX_MONITORING_PORT=8081" .env; then
        log "✓ Nginx monitoring port updated to 8081"
    else
        warn "Nginx monitoring port not configured in .env"
    fi
}

# Main script
main() {
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════╗"
    echo "║        Port Conflict Resolution          ║"
    echo "║           Trading Bot System             ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    
    show_current_ports
    check_docker_requirements
    resolve_conflicts
    test_configuration
    
    log "Port conflict resolution completed"
    echo
    info "You can now run: ./deploy.sh deploy"
    info "New service URLs after deployment:"
    echo "  - Main App:     http://localhost:8008"
    echo "  - Grafana:      http://localhost:3001"
    echo "  - Prometheus:   http://localhost:9090"
    echo "  - Monitoring:   http://localhost:8081"
    echo "  - Database:     localhost:5433"
}

# Script options
case "${1:-main}" in
    "check")
        show_current_ports
        ;;
    "resolve")
        resolve_conflicts
        ;;
    "test")
        test_configuration
        ;;
    "main"|"")
        main
        ;;
    *)
        echo "Usage: $0 {check|resolve|test|main}"
        echo ""
        echo "Options:"
        echo "  check     - Show current port usage"
        echo "  resolve   - Resolve port conflicts"
        echo "  test      - Test configuration"
        echo "  main      - Run full resolution (default)"
        exit 1
        ;;
esac
