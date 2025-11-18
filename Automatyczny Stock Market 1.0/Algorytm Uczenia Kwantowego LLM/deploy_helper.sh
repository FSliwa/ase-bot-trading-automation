#!/bin/bash
# VPS Deployment Helper Script
# Assists with project deployment and configuration

set -e

# Source configuration
source ./vps_config.conf 2>/dev/null || true

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to deploy project files
deploy_project_files() {
    local project_dir=${1:-/opt/trading-bot}
    local service_user=${2:-tradingbot}
    
    print_status "Deploying project files to $project_dir"
    
    # Create temporary deployment directory
    local temp_dir="/tmp/trading-bot-deploy"
    mkdir -p $temp_dir
    
    # Copy project files
    rsync -av --progress \
        --exclude='venv/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='logs/' \
        --exclude='.git/' \
        --exclude='node_modules/' \
        ./ $temp_dir/
    
    # Move to project directory
    sudo mkdir -p $project_dir
    sudo rsync -av --progress $temp_dir/ $project_dir/
    sudo chown -R $service_user:$service_user $project_dir
    
    # Clean up
    rm -rf $temp_dir
    
    print_success "Project files deployed"
}

# Function to generate secure secrets
generate_secrets() {
    local env_file=${1:-/opt/trading-bot/.env}
    
    print_status "Generating secure secrets..."
    
    # Generate JWT secret
    local jwt_secret=$(openssl rand -hex 32)
    
    # Generate app secret key
    local secret_key=$(openssl rand -hex 32)
    
    # Update .env file
    sudo sed -i "s/JWT_SECRET=.*/JWT_SECRET=$jwt_secret/" $env_file
    sudo sed -i "s/SECRET_KEY=.*/SECRET_KEY=$secret_key/" $env_file
    
    print_success "Secrets generated and updated in $env_file"
}

# Function to validate environment
validate_environment() {
    local env_file=${1:-/opt/trading-bot/.env}
    
    print_status "Validating environment configuration..."
    
    if [[ ! -f $env_file ]]; then
        print_error "Environment file not found: $env_file"
        return 1
    fi
    
    # Check required variables
    local missing_vars=()
    
    while IFS= read -r line; do
        if [[ $line =~ ^([^=]+)=(.*)$ ]]; then
            local var_name="${BASH_REMATCH[1]}"
            local var_value="${BASH_REMATCH[2]}"
            
            # Check if it's a required variable and empty
            for required_var in "${REQUIRED_ENV_VARS[@]}"; do
                if [[ "$var_name" == "$required_var" ]] && [[ -z "$var_value" ]]; then
                    missing_vars+=("$var_name")
                fi
            done
        fi
    done < $env_file
    
    if [[ ${#missing_vars[@]} -gt 0 ]]; then
        print_error "Missing required environment variables:"
        printf ' - %s\n' "${missing_vars[@]}"
        return 1
    fi
    
    print_success "Environment validation passed"
}

# Function to run database migrations
run_migrations() {
    local project_dir=${1:-/opt/trading-bot}
    local service_user=${2:-tradingbot}
    
    print_status "Running database migrations..."
    
    sudo -u $service_user bash << EOF
cd $project_dir
source venv/bin/activate

# Initialize database
if [ -f init_database.py ]; then
    python init_database.py
    echo "Database initialized"
fi

# Run migrations if using Alembic
if [ -f alembic.ini ]; then
    alembic upgrade head
    echo "Database migrations completed"
fi

# Initialize demo data
if [ -f initialize_demo_data.py ]; then
    python initialize_demo_data.py
    echo "Demo data initialized"
fi
EOF

    print_success "Database setup completed"
}

# Function to test API endpoints
test_api_endpoints() {
    local base_url=${1:-http://localhost:8000}
    
    print_status "Testing API endpoints..."
    
    # Wait for API to be available
    local max_attempts=30
    local attempt=1
    
    while [[ $attempt -le $max_attempts ]]; do
        if curl -s -f "$base_url/health" > /dev/null; then
            break
        fi
        print_status "Waiting for API to be available... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    
    if [[ $attempt -gt $max_attempts ]]; then
        print_error "API not available after $max_attempts attempts"
        return 1
    fi
    
    # Test endpoints
    local endpoints=("/" "/health" "/api/health" "/api/status")
    local failed_tests=()
    
    for endpoint in "${endpoints[@]}"; do
        local url="$base_url$endpoint"
        if curl -s -f "$url" > /dev/null; then
            print_success "✓ $endpoint"
        else
            print_error "✗ $endpoint"
            failed_tests+=("$endpoint")
        fi
    done
    
    if [[ ${#failed_tests[@]} -gt 0 ]]; then
        print_error "Failed endpoint tests:"
        printf ' - %s\n' "${failed_tests[@]}"
        return 1
    fi
    
    print_success "All API endpoints are working"
}

# Function to setup monitoring
setup_monitoring() {
    local project_dir=${1:-/opt/trading-bot}
    
    print_status "Setting up monitoring..."
    
    # Create monitoring script
    cat > $project_dir/health_check.sh << 'EOF'
#!/bin/bash
# Health check script for trading bot

STATUS_FILE="/tmp/trading_bot_status"
LOG_FILE="/opt/trading-bot/logs/health_check.log"

check_service() {
    local service=$1
    if systemctl is-active --quiet $service; then
        echo "✓ $service is running" >> $LOG_FILE
        return 0
    else
        echo "✗ $service is not running" >> $LOG_FILE
        return 1
    fi
}

check_port() {
    local port=$1
    if netstat -tlnp | grep -q ":$port "; then
        echo "✓ Port $port is listening" >> $LOG_FILE
        return 0
    else
        echo "✗ Port $port is not listening" >> $LOG_FILE
        return 1
    fi
}

check_api() {
    local url=$1
    if curl -s -f "$url" > /dev/null; then
        echo "✓ API $url is responding" >> $LOG_FILE
        return 0
    else
        echo "✗ API $url is not responding" >> $LOG_FILE
        return 1
    fi
}

# Main health check
echo "$(date): Starting health check" >> $LOG_FILE

FAILED=0

# Check services
check_service "trading-bot-api" || FAILED=1
check_service "trading-bot" || FAILED=1
check_service "trading-bot-monitor" || FAILED=1
check_service "redis-server" || FAILED=1

# Check ports
check_port "8000" || FAILED=1
check_port "6379" || FAILED=1

# Check API
check_api "http://localhost:8000/health" || FAILED=1

# Update status
if [[ $FAILED -eq 0 ]]; then
    echo "HEALTHY" > $STATUS_FILE
    echo "$(date): All checks passed" >> $LOG_FILE
else
    echo "UNHEALTHY" > $STATUS_FILE
    echo "$(date): Some checks failed" >> $LOG_FILE
    
    # Send alert if configured
    if [[ -n "$TELEGRAM_BOT_TOKEN" ]] && [[ -n "$TELEGRAM_CHAT_ID" ]]; then
        curl -s -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage" \
            -d "chat_id=$TELEGRAM_CHAT_ID" \
            -d "text=🚨 Trading Bot Health Check Failed on $(hostname)"
    fi
fi

echo "$(date): Health check completed" >> $LOG_FILE
EOF

    chmod +x $project_dir/health_check.sh
    chown tradingbot:tradingbot $project_dir/health_check.sh
    
    print_success "Monitoring setup completed"
}

# Function to create SSL certificate
create_ssl_certificate() {
    local domain=$1
    local email=${2:-admin@$domain}
    
    if [[ -z "$domain" ]]; then
        print_error "Domain name required for SSL certificate"
        return 1
    fi
    
    print_status "Creating SSL certificate for $domain..."
    
    # Install certbot if not already installed
    if ! command -v certbot &> /dev/null; then
        apt-get update
        apt-get install -y certbot python3-certbot-nginx
    fi
    
    # Get certificate
    certbot --nginx -d $domain --non-interactive --agree-tos --email $email
    
    # Setup auto-renewal
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet") | crontab -
    
    print_success "SSL certificate created for $domain"
}

# Function to optimize performance
optimize_performance() {
    local project_dir=${1:-/opt/trading-bot}
    
    print_status "Optimizing system performance..."
    
    # Ensure systemd drop-in directory exists for trading-bot-api
    mkdir -p /etc/systemd/system/trading-bot-api.service.d
    
    # Update systemd service files with performance settings
    cat > /etc/systemd/system/trading-bot-api.service.d/performance.conf << EOF
[Service]
# Performance optimizations
LimitNOFILE=65536
LimitNPROC=4096

# Memory settings
MemoryHigh=1G
MemoryMax=2G

# CPU settings
CPUQuota=200%

# I/O settings
IOSchedulingClass=1
IOSchedulingPriority=4
EOF

    # Create performance tuning script
    cat > $project_dir/tune_performance.sh << 'EOF'
#!/bin/bash
# Performance tuning for trading bot

# Kernel parameters
echo 'net.core.somaxconn = 1024' >> /etc/sysctl.conf
echo 'net.core.netdev_max_backlog = 5000' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_max_syn_backlog = 8192' >> /etc/sysctl.conf
echo 'net.ipv4.tcp_fin_timeout = 30' >> /etc/sysctl.conf
echo 'vm.swappiness = 10' >> /etc/sysctl.conf

# Apply settings
sysctl -p

# Redis optimization
sed -i 's/^# maxclients 10000/maxclients 10000/' /etc/redis/redis.conf
sed -i 's/^save 900 1/# save 900 1/' /etc/redis/redis.conf
sed -i 's/^save 300 10/# save 300 10/' /etc/redis/redis.conf
sed -i 's/^save 60 10000/save 60 10000/' /etc/redis/redis.conf

systemctl restart redis-server

echo "Performance tuning completed"
EOF

    chmod +x $project_dir/tune_performance.sh
    
    # Reload systemd
    systemctl daemon-reload
    
    print_success "Performance optimization completed"
}

# Function to setup log aggregation
setup_log_aggregation() {
    local project_dir=${1:-/opt/trading-bot}
    
    print_status "Setting up log aggregation..."
    
    # Create log aggregation script
    cat > $project_dir/aggregate_logs.sh << 'EOF'
#!/bin/bash
# Log aggregation for trading bot

LOG_DIR="/opt/trading-bot/logs"
ARCHIVE_DIR="/opt/trading-bot/logs/archive"
DATE=$(date +%Y%m%d)

mkdir -p $ARCHIVE_DIR

# Aggregate application logs
journalctl -u trading-bot-api --since="1 day ago" --no-pager > $ARCHIVE_DIR/api_$DATE.log
journalctl -u trading-bot --since="1 day ago" --no-pager > $ARCHIVE_DIR/bot_$DATE.log
journalctl -u trading-bot-monitor --since="1 day ago" --no-pager > $ARCHIVE_DIR/monitor_$DATE.log

# Compress old logs
find $ARCHIVE_DIR -name "*.log" -mtime +1 -exec gzip {} \;

# Remove old compressed logs
find $ARCHIVE_DIR -name "*.gz" -mtime +30 -delete

echo "Log aggregation completed for $DATE"
EOF

    chmod +x $project_dir/aggregate_logs.sh
    
    # Add to crontab
    (crontab -u tradingbot -l 2>/dev/null; echo "0 1 * * * $project_dir/aggregate_logs.sh") | crontab -u tradingbot -
    
    print_success "Log aggregation setup completed"
}

# Function to create deployment summary
create_deployment_summary() {
    local project_dir=${1:-/opt/trading-bot}
    
    print_status "Creating deployment summary..."
    
    cat > $project_dir/DEPLOYMENT_SUMMARY.md << EOF
# Trading Bot VPS Deployment Summary

## Deployment Information
- **Deployment Date**: $(date)
- **Server**: $(hostname)
- **Operating System**: $(lsb_release -d | cut -f2)
- **Python Version**: $(python3 --version)
- **Project Directory**: $project_dir

## Services Status
$(systemctl status trading-bot-api --no-pager -l | head -3)
$(systemctl status trading-bot --no-pager -l | head -3)
$(systemctl status trading-bot-monitor --no-pager -l | head -3)

## Network Configuration
- **API Port**: 8000
- **Nginx Port**: 80, 443
- **Redis Port**: 6379
- **Prometheus Port**: 9090

## Security
- **Firewall**: Enabled (UFW)
- **SSL Certificate**: $([ -d /etc/letsencrypt/live ] && echo "Configured" || echo "Not configured")
- **Service User**: tradingbot

## Monitoring
- **Health Check**: /opt/trading-bot/health_check.sh
- **Log Directory**: /opt/trading-bot/logs
- **Backup Directory**: /opt/trading-bot/backups

## Important Files
- **Environment**: /opt/trading-bot/.env
- **Database**: /opt/trading-bot/trading.db
- **Nginx Config**: /etc/nginx/sites-available/trading-bot
- **Systemd Services**: /etc/systemd/system/trading-bot-*.service

## Next Steps
1. Update API keys in .env file
2. Configure domain name and SSL
3. Test all functionality
4. Set up monitoring alerts
5. Schedule regular backups

## Useful Commands
\`\`\`bash
# Check service status
systemctl status trading-bot-api

# View logs
journalctl -u trading-bot-api -f

# Restart services
systemctl restart trading-bot-api

# Run health check
/opt/trading-bot/health_check.sh

# Create backup
/opt/trading-bot/backup.sh
\`\`\`

## Support
For issues or questions, check the logs and refer to the documentation.
EOF

    print_success "Deployment summary created: $project_dir/DEPLOYMENT_SUMMARY.md"
}

# Main function
main() {
    case ${1:-help} in
        deploy)
            deploy_project_files "${2:-/opt/trading-bot}" "${3:-tradingbot}"
            ;;
        secrets)
            generate_secrets "${2:-/opt/trading-bot/.env}"
            ;;
        validate)
            validate_environment "${2:-/opt/trading-bot/.env}"
            ;;
        migrate)
            run_migrations "${2:-/opt/trading-bot}" "${3:-tradingbot}"
            ;;
        test)
            test_api_endpoints "${2:-http://localhost:8000}"
            ;;
        monitor)
            setup_monitoring "${2:-/opt/trading-bot}"
            ;;
        ssl)
            create_ssl_certificate "$2" "$3"
            ;;
        optimize)
            optimize_performance "${2:-/opt/trading-bot}"
            ;;
        logs)
            setup_log_aggregation "${2:-/opt/trading-bot}"
            ;;
        summary)
            create_deployment_summary "${2:-/opt/trading-bot}"
            ;;
        full)
            print_status "Running full deployment helper..."
            deploy_project_files
            generate_secrets
            validate_environment
            run_migrations
            setup_monitoring
            optimize_performance
            setup_log_aggregation
            sleep 10  # Wait for services to start
            test_api_endpoints
            create_deployment_summary
            print_success "Full deployment helper completed!"
            ;;
        help|*)
            echo "VPS Deployment Helper"
            echo "Usage: $0 <command> [options]"
            echo
            echo "Commands:"
            echo "  deploy [project_dir] [user]     Deploy project files"
            echo "  secrets [env_file]              Generate secure secrets"
            echo "  validate [env_file]             Validate environment"
            echo "  migrate [project_dir] [user]    Run database migrations"
            echo "  test [base_url]                 Test API endpoints"
            echo "  monitor [project_dir]           Setup monitoring"
            echo "  ssl <domain> [email]            Create SSL certificate"
            echo "  optimize [project_dir]          Optimize performance"
            echo "  logs [project_dir]              Setup log aggregation"
            echo "  summary [project_dir]           Create deployment summary"
            echo "  full                            Run all deployment steps"
            echo "  help                            Show this help"
            ;;
    esac
}

main "$@"
