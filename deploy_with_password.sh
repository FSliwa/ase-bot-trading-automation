#!/bin/bash
# VPS Deployment with SSH Password
# Uses sshpass for automated deployment

set -ex

# Configuration
VPS_IP="185.70.198.201"
VPS_USER="root"
SSH_PASS="MIlik112!@4"
PROJECT_NAME="trading-bot"
LOCAL_PROJECT_DIR="."
# Remote directories
REMOTE_BASE_DIR="/tmp/trading-bot-deploy"
REMOTE_PROJECT_SUBDIR="Algorytm Uczenia Kwantowego LLM"
REMOTE_PROJECT_DIR="$REMOTE_BASE_DIR/$REMOTE_PROJECT_SUBDIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to install sshpass if needed
install_sshpass() {
    if ! command -v sshpass &> /dev/null; then
        print_status "Installing sshpass..."
        if [[ "$OSTYPE" == "darwin"* ]]; then
            # macOS
            if command -v brew &> /dev/null; then
                brew install hudochenkov/sshpass/sshpass
            else
                print_error "Please install Homebrew first, then run: brew install hudochenkov/sshpass/sshpass"
                exit 1
            fi
        else
            # Linux
            sudo apt-get update && sudo apt-get install -y sshpass
        fi
    fi
}

# Function to run SSH command with password
ssh_cmd() {
    local command="$1"
    sshpass -p "$SSH_PASS" ssh -o StrictHostKeyChecking=no $VPS_USER@$VPS_IP "$command"
}

# Function to upload files with password
upload_files() {
    print_status "Uploading project files to VPS..."
    
    # Create deployment directory
    ssh_cmd "mkdir -p $REMOTE_BASE_DIR"
    
    # Upload files using rsync with sshpass
    sshpass -p "$SSH_PASS" rsync -avz --progress \
        --exclude='.venv/' \
        --exclude='venv/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.git/' \
        --exclude='node_modules/' \
        --exclude='logs/' \
        --exclude='*.log' \
        --exclude='.DS_Store' \
        --exclude='*.DS_Store' \
        -e "ssh -o StrictHostKeyChecking=no" \
        "$LOCAL_PROJECT_DIR/" \
        $VPS_USER@$VPS_IP:$REMOTE_BASE_DIR/
    
    print_success "Files uploaded successfully"
}

# Function to run deployment steps
run_deployment() {
    print_status "Starting VPS deployment process..."
    
    # Step 1: Upload files
    upload_files
    
    # Step 2: Verify remote project dir
    print_status "Verifying remote project directory..."
    if ! ssh_cmd "test -d '$REMOTE_PROJECT_DIR'"; then
        print_error "Remote directory $REMOTE_PROJECT_DIR not found. Listing contents of $REMOTE_BASE_DIR for debugging:";
        ssh_cmd "ls -la $REMOTE_BASE_DIR" || true
        exit 1
    fi

    # Step 2.5: Repair system python for apt (if previous runs changed alternatives)
    print_status "Repairing system python3 for APT on server..."
    ssh_cmd "if [ -x /usr/bin/python3.12 ]; then update-alternatives --set python3 /usr/bin/python3.12 || true; fi; rm -f /etc/apt/apt.conf.d/50command-not-found || true; if [ -f /usr/lib/cnf-update-db ]; then sed -i '1s|/usr/bin/python3|/usr/bin/python3.12|' /usr/lib/cnf-update-db || true; fi"

    # Step 3: Make scripts executable
    print_status "Making scripts executable..."
    ssh_cmd "cd '$REMOTE_PROJECT_DIR' && chmod +x init_vps.sh deploy_helper.sh || true"
    
    # Step 4: Run VPS initialization
    print_status "Running VPS initialization (this may take 5-10 minutes)..."
    ssh_cmd "cd '$REMOTE_PROJECT_DIR' && ./init_vps.sh"
    
    # Step 5: Deploy application
    print_status "Deploying application..."
    ssh_cmd "cd '$REMOTE_PROJECT_DIR' && ./deploy_helper.sh full"
    
    # Step 6: Configure environment
    print_status "Configuring environment..."
    ssh_cmd "cd /opt/trading-bot && \
        JWT_SECRET=\$(openssl rand -hex 32) && \
        SECRET_KEY=\$(openssl rand -hex 32) && \
        sed -i \"s/JWT_SECRET=.*/JWT_SECRET=\$JWT_SECRET/\" .env && \
        sed -i \"s/SECRET_KEY=.*/SECRET_KEY=\$SECRET_KEY/\" .env && \
        sed -i 's/ENVIRONMENT=.*/ENVIRONMENT=production/' .env && \
        sed -i 's/DEBUG=.*/DEBUG=false/' .env"
    
    # Step 7: Start services
    print_status "Starting services..."
    ssh_cmd "systemctl enable trading-bot-api trading-bot trading-bot-monitor || true && \
             systemctl restart trading-bot-api || systemctl start trading-bot-api && \
             sleep 10 && \
             systemctl restart trading-bot || systemctl start trading-bot && \
             systemctl restart trading-bot-monitor || systemctl start trading-bot-monitor"
    
    # Step 8: Test deployment
    print_status "Testing deployment..."
    sleep 15
    ssh_cmd "curl -s http://localhost:8000/health || curl -s http://localhost:8009/health || echo 'API not ready yet'"
    
    # Step 9: Show status
    print_status "Checking service status..."
    ssh_cmd "systemctl status trading-bot-api --no-pager -l | head -50"
}

# Function to show final summary
show_summary() {
    print_success "Deployment completed!"
    echo
    echo "=== VPS Deployment Summary ==="
    echo "Server: $VPS_IP"
    echo "Project Directory: /opt/trading-bot"
    echo "API URL: http://$VPS_IP:8000 (or http://$VPS_IP:8009)"
    echo "Health Check: http://$VPS_IP:8000/health (fallback: /8009/health)"
    echo
    echo "=== Service Status ==="
    ssh_cmd "systemctl is-active trading-bot-api trading-bot trading-bot-monitor"
    echo
    echo "=== Next Steps ==="
    echo "1. Configure API keys: ssh root@$VPS_IP 'nano /opt/trading-bot/.env'"
    echo "2. Test API: curl http://$VPS_IP:8000/health || curl http://$VPS_IP:8009/health"
    echo "3. View logs: ssh root@$VPS_IP 'journalctl -u trading-bot-api -f'"
    echo
    echo "=== Useful Commands ==="
    echo "Connect to server: ssh root@$VPS_IP"
    echo "Check logs: journalctl -u trading-bot-api -f"
    echo "Restart API: systemctl restart trading-bot-api"
    echo "Edit config: nano /opt/trading-bot/.env"
}

# Test connection first
test_connection() {
    print_status "Testing SSH connection with password..."
    if ssh_cmd "echo 'SSH connection successful'; uname -a"; then
        print_success "SSH connection working!"
        return 0
    else
        print_error "SSH connection failed!"
        return 1
    fi
}

# Main execution
main() {
    echo "=== VPS Deployment with SSH Password ==="
    echo "Server: $VPS_IP"
    echo "User: $VPS_USER"
    echo
    
    # Install sshpass if needed
    install_sshpass
    
    # Test connection
    test_connection || exit 1
    
    # Run deployment
    run_deployment
    
    # Show summary
    show_summary
}

# Run main function
main "$@"
