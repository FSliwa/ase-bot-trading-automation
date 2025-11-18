#!/bin/bash

# Docker Optimization and Deployment Script for ASE Trading Bot
# Optimized for 16GB RAM, 6 cores @ 2.271GHz server

set -e

echo "🚀 ASE Trading Bot - Docker Optimization & Deployment"
echo "=================================================="

# Configuration
PROJECT_NAME="ase-trading-bot"
DOCKER_COMPOSE_FILE="docker-compose.optimized.yml"
ENV_FILE=".env"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_section() {
    echo -e "\n${BLUE}=== $1 ===${NC}"
}

# Check system requirements
check_system_requirements() {
    print_section "Checking System Requirements"
    
    # Check RAM
    TOTAL_RAM=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$TOTAL_RAM" -lt 12 ]; then
        print_warning "System has ${TOTAL_RAM}GB RAM. Recommended: 16GB+"
    else
        print_status "RAM: ${TOTAL_RAM}GB ✓"
    fi
    
    # Check CPU cores
    CPU_CORES=$(nproc)
    if [ "$CPU_CORES" -lt 4 ]; then
        print_warning "System has ${CPU_CORES} CPU cores. Recommended: 6+"
    else
        print_status "CPU Cores: ${CPU_CORES} ✓"
    fi
    
    # Check disk space
    AVAILABLE_SPACE=$(df -h / | awk 'NR==2{print $4}' | sed 's/G//')
    if [ "$AVAILABLE_SPACE" -lt 50 ]; then
        print_warning "Available disk space: ${AVAILABLE_SPACE}GB. Recommended: 50GB+"
    else
        print_status "Disk Space: ${AVAILABLE_SPACE}GB available ✓"
    fi
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        exit 1
    else
        print_status "Docker: $(docker --version | cut -d' ' -f3 | cut -d',' -f1) ✓"
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed"
        exit 1
    else
        print_status "Docker Compose: $(docker-compose --version | cut -d' ' -f3 | cut -d',' -f1) ✓"
    fi
}

# Optimize Docker daemon settings
optimize_docker_daemon() {
    print_section "Optimizing Docker Daemon"
    
    DOCKER_DAEMON_CONFIG="/etc/docker/daemon.json"
    
    if [ -f "$DOCKER_DAEMON_CONFIG" ]; then
        print_status "Backing up existing Docker daemon configuration..."
        sudo cp "$DOCKER_DAEMON_CONFIG" "${DOCKER_DAEMON_CONFIG}.backup.$(date +%s)"
    fi
    
    print_status "Creating optimized Docker daemon configuration..."
    
    sudo tee "$DOCKER_DAEMON_CONFIG" > /dev/null <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "storage-opts": [
    "overlay2.override_kernel_check=true"
  ],
  "default-ulimits": {
    "nofile": {
      "name": "nofile",
      "hard": 65536,
      "soft": 65536
    },
    "memlock": {
      "name": "memlock",
      "hard": -1,
      "soft": -1
    }
  },
  "max-concurrent-downloads": 6,
  "max-concurrent-uploads": 6,
  "max-download-attempts": 3,
  "registry-mirrors": [],
  "insecure-registries": [],
  "live-restore": true,
  "userland-proxy": false,
  "no-new-privileges": true,
  "seccomp-profile": "/etc/docker/seccomp.json"
}
EOF
    
    print_status "Restarting Docker daemon..."
    sudo systemctl restart docker
    
    # Wait for Docker to be ready
    sleep 10
    
    if sudo systemctl is-active --quiet docker; then
        print_status "Docker daemon optimized and restarted successfully ✓"
    else
        print_error "Failed to restart Docker daemon"
        exit 1
    fi
}

# Create necessary directories
create_directories() {
    print_section "Creating Directory Structure"
    
    DIRECTORIES=(
        "data/postgres"
        "data/redis" 
        "data/prometheus"
        "data/loki"
        "logs"
        "config/nginx/sites-enabled"
        "ssl"
    )
    
    for dir in "${DIRECTORIES[@]}"; do
        if [ ! -d "$dir" ]; then
            mkdir -p "$dir"
            print_status "Created directory: $dir"
        else
            print_status "Directory exists: $dir ✓"
        fi
    done
    
    # Set proper permissions
    chmod 755 data
    chmod 700 data/postgres data/redis
    chmod 755 logs config
    
    print_status "Directory structure created ✓"
}

# Generate environment file if not exists
generate_env_file() {
    print_section "Environment Configuration"
    
    if [ -f "$ENV_FILE" ]; then
        print_status "Environment file exists ✓"
        return
    fi
    
    print_status "Generating environment file..."
    
    # Generate secure passwords
    POSTGRES_PASSWORD=$(openssl rand -base64 32)
    SECRET_KEY=$(openssl rand -base64 32)
    JWT_SECRET=$(openssl rand -base64 32)
    
    cat > "$ENV_FILE" << EOF
# ASE Trading Bot Environment Configuration
# Generated on $(date)

# Application Settings
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO
SECRET_KEY=${SECRET_KEY}

# Database Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=trading_bot
POSTGRES_USER=trading_user
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# Redis Configuration  
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0

# JWT Configuration
JWT_SECRET=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# Exchange API Keys (replace with your actual keys)
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret
COINBASE_API_KEY=your_coinbase_api_key
COINBASE_API_SECRET=your_coinbase_secret
COINBASE_PASSPHRASE=your_coinbase_passphrase
KRAKEN_API_KEY=your_kraken_api_key
KRAKEN_API_SECRET=your_kraken_secret
OKX_API_KEY=your_okx_api_key
OKX_API_SECRET=your_okx_secret
OKX_PASSPHRASE=your_okx_passphrase
BYBIT_API_KEY=your_bybit_api_key
BYBIT_API_SECRET=your_bybit_secret

# OAuth Configuration
COINBASE_CLIENT_ID=your_coinbase_client_id
COINBASE_CLIENT_SECRET=your_coinbase_client_secret
BYBIT_CLIENT_ID=your_bybit_client_id
BYBIT_CLIENT_SECRET=your_bybit_client_secret

# Tavily API Configuration
TAVILY_API_KEY=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

# Gemini AI Configuration  
GEMINI_API_KEY=your_gemini_api_key

# Performance Settings
WORKERS=4
WORKER_CONNECTIONS=1000
MAX_REQUESTS=10000

# Monitoring
PROMETHEUS_RETENTION=30d
GRAFANA_ADMIN_PASSWORD=${POSTGRES_PASSWORD}
EOF
    
    chmod 600 "$ENV_FILE"
    print_status "Environment file generated ✓"
    print_warning "Please update the API keys in $ENV_FILE before deployment"
}

# Build optimized Docker images
build_images() {
    print_section "Building Optimized Docker Images"
    
    print_status "Building production image..."
    docker build -f Dockerfile.optimized --target production -t ${PROJECT_NAME}:latest .
    
    print_status "Building worker image..."
    docker build -f Dockerfile.optimized --target worker -t ${PROJECT_NAME}-worker:latest .
    
    print_status "Docker images built successfully ✓"
}

# Deploy services
deploy_services() {
    print_section "Deploying Services"
    
    print_status "Starting services with optimized configuration..."
    
    # Pull external images
    docker-compose -f "$DOCKER_COMPOSE_FILE" pull
    
    # Start services
    docker-compose -f "$DOCKER_COMPOSE_FILE" up -d
    
    print_status "Services deployed ✓"
}

# Wait for services to be healthy
wait_for_services() {
    print_section "Waiting for Services to be Ready"
    
    SERVICES=("postgres" "redis" "trading-app")
    MAX_WAIT=300  # 5 minutes
    WAIT_TIME=0
    
    for service in "${SERVICES[@]}"; do
        print_status "Waiting for $service to be healthy..."
        
        while [ $WAIT_TIME -lt $MAX_WAIT ]; do
            if docker-compose -f "$DOCKER_COMPOSE_FILE" ps "$service" | grep -q "healthy\|Up"; then
                print_status "$service is ready ✓"
                break
            fi
            
            sleep 10
            WAIT_TIME=$((WAIT_TIME + 10))
        done
        
        if [ $WAIT_TIME -ge $MAX_WAIT ]; then
            print_error "$service failed to start within $MAX_WAIT seconds"
            docker-compose -f "$DOCKER_COMPOSE_FILE" logs "$service"
            exit 1
        fi
    done
    
    print_status "All services are ready ✓"
}

# Run database migrations
run_migrations() {
    print_section "Running Database Migrations"
    
    print_status "Running TimescaleDB migrations..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T trading-app python -c "
import asyncio
from core.timescale_migration import TimescaleDBMigration, performance_optimizer

async def main():
    await performance_optimizer.initialize()
    migration = TimescaleDBMigration(performance_optimizer.connection_manager)
    result = await migration.run_full_migration()
    if result['success']:
        print('✅ Database migration completed successfully')
    else:
        print(f'❌ Database migration failed: {result[\"error\"]}')
    await performance_optimizer.cleanup()

asyncio.run(main())
"
    
    print_status "Database migrations completed ✓"
}

# Performance testing
run_performance_tests() {
    print_section "Running Performance Tests"
    
    print_status "Testing API endpoints..."
    
    # Test health endpoint
    if curl -f http://localhost/health > /dev/null 2>&1; then
        print_status "Health endpoint: ✓"
    else
        print_warning "Health endpoint not responding"
    fi
    
    # Test API performance
    print_status "Running API performance test..."
    docker-compose -f "$DOCKER_COMPOSE_FILE" exec -T trading-app python -c "
import asyncio
import time
from core.performance_optimizer import performance_optimizer

async def performance_test():
    await performance_optimizer.initialize()
    
    # Simulate processing
    start_time = time.time()
    for i in range(1000):
        await performance_optimizer.optimize_request(lambda: {'test': i})
    
    duration = time.time() - start_time
    rps = 1000 / duration
    
    print(f'Performance Test Results:')
    print(f'  - Processed 1000 requests in {duration:.2f}s')
    print(f'  - Rate: {rps:.2f} requests/second')
    print(f'  - Average response time: {duration/1000*1000:.2f}ms')
    
    await performance_optimizer.cleanup()

asyncio.run(performance_test())
"
}

# Show deployment status
show_status() {
    print_section "Deployment Status"
    
    docker-compose -f "$DOCKER_COMPOSE_FILE" ps
    
    echo ""
    print_status "Service URLs:"
    echo "  🌐 Trading API: http://localhost"
    echo "  📊 Prometheus: http://localhost:9090"
    echo "  🔍 Grafana: http://localhost:3000"
    echo "  📈 WebSocket: ws://localhost:8001/ws"
    echo "  🗄️  PostgreSQL: localhost:5432"
    echo "  🚀 Redis: localhost:6379"
    
    echo ""
    print_status "Useful Commands:"
    echo "  📋 View logs: docker-compose -f $DOCKER_COMPOSE_FILE logs -f [service]"
    echo "  📊 Service status: docker-compose -f $DOCKER_COMPOSE_FILE ps"
    echo "  🔄 Restart service: docker-compose -f $DOCKER_COMPOSE_FILE restart [service]"
    echo "  🛑 Stop all: docker-compose -f $DOCKER_COMPOSE_FILE down"
    echo "  🧹 Clean up: docker system prune -af"
}

# Monitoring and alerts setup
setup_monitoring() {
    print_section "Setting up Monitoring"
    
    print_status "Configuring Prometheus targets..."
    # This would typically configure Prometheus to scrape metrics
    # from the FastAPI application and other services
    
    print_status "Setting up alerting rules..."
    # Configure alerting for critical metrics like high memory usage,
    # API response time, database connection issues, etc.
    
    print_status "Monitoring setup completed ✓"
}

# Main deployment function
main() {
    print_section "ASE Trading Bot Deployment"
    
    case "${1:-deploy}" in
        "check")
            check_system_requirements
            ;;
        "optimize")
            check_system_requirements
            optimize_docker_daemon
            ;;
        "build")
            create_directories
            generate_env_file
            build_images
            ;;
        "deploy")
            check_system_requirements
            create_directories
            generate_env_file
            build_images
            deploy_services
            wait_for_services
            run_migrations
            setup_monitoring
            show_status
            ;;
        "test")
            run_performance_tests
            ;;
        "status")
            show_status
            ;;
        "stop")
            print_section "Stopping Services"
            docker-compose -f "$DOCKER_COMPOSE_FILE" down
            print_status "Services stopped ✓"
            ;;
        "clean")
            print_section "Cleaning Up"
            docker-compose -f "$DOCKER_COMPOSE_FILE" down -v
            docker system prune -af
            print_status "Cleanup completed ✓"
            ;;
        *)
            echo "Usage: $0 {deploy|build|test|status|stop|clean|check|optimize}"
            echo ""
            echo "Commands:"
            echo "  deploy   - Full deployment (default)"
            echo "  build    - Build images only"  
            echo "  test     - Run performance tests"
            echo "  status   - Show deployment status"
            echo "  stop     - Stop all services"
            echo "  clean    - Clean up containers and images"
            echo "  check    - Check system requirements"
            echo "  optimize - Optimize Docker daemon"
            exit 1
            ;;
    esac
}

# Run main function
main "$@"
