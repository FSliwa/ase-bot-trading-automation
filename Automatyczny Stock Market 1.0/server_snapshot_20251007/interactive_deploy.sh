#!/bin/bash
# Interactive VPS Deployment Script
# Handles password authentication for VPS deployment

set -e

# Configuration
VPS_IP="185.70.196.214"
VPS_USER="root"
PROJECT_NAME="trading-bot"
LOCAL_PROJECT_DIR="."

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

# Function to check if sshpass is available
check_sshpass() {
    if command -v sshpass &> /dev/null; then
        return 0
    else
        print_warning "sshpass not found. You'll need to enter password manually for each step."
        return 1
    fi
}

# Function to upload project files
upload_project_files() {
    print_status "Uploading project files to VPS..."
    
    # Create temporary directory for deployment
    print_status "Creating deployment directory on server..."
    ssh $VPS_USER@$VPS_IP "mkdir -p /tmp/trading-bot-deploy"
    
    print_status "Uploading files (this may take a few minutes)..."
    rsync -avz --progress \
        --exclude='venv/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.git/' \
        --exclude='node_modules/' \
        --exclude='logs/' \
        --exclude='*.log' \
        "$LOCAL_PROJECT_DIR/" \
        $VPS_USER@$VPS_IP:/tmp/trading-bot-deploy/
    
    print_success "Project files uploaded successfully"
}

# Function to run commands on remote server
run_remote_command() {
    local command="$1"
    local description="$2"
    
    print_status "$description"
    ssh $VPS_USER@$VPS_IP "$command"
    
    if [ $? -eq 0 ]; then
        print_success "$description completed"
    else
        print_error "$description failed"
        return 1
    fi
}

# Function to deploy in steps
deploy_step_by_step() {
    print_status "Starting step-by-step VPS deployment..."
    echo
    print_warning "You will be prompted for your VPS root password multiple times."
    print_warning "This is normal for password-based SSH authentication."
    echo
    
    # Step 1: Upload files
    upload_project_files
    
    # Step 2: Make scripts executable
    run_remote_command "cd /tmp/trading-bot-deploy && chmod +x init_vps.sh deploy_helper.sh" \
                      "Making deployment scripts executable"
    
    # Step 3: Run VPS initialization
    print_status "Running VPS initialization (this will take 5-10 minutes)..."
    run_remote_command "cd /tmp/trading-bot-deploy && ./init_vps.sh" \
                      "VPS initialization"
    
    # Step 4: Deploy application
    print_status "Deploying application..."
    run_remote_command "cd /tmp/trading-bot-deploy && ./deploy_helper.sh full" \
                      "Application deployment"
    
    # Step 5: Configure environment
    print_status "Configuring basic environment..."
    run_remote_command "cd /opt/trading-bot && \
        JWT_SECRET=\$(openssl rand -hex 32) && \
        SECRET_KEY=\$(openssl rand -hex 32) && \
        sed -i \"s/JWT_SECRET=.*/JWT_SECRET=\$JWT_SECRET/\" .env && \
        sed -i \"s/SECRET_KEY=.*/SECRET_KEY=\$SECRET_KEY/\" .env && \
        sed -i 's/ENVIRONMENT=.*/ENVIRONMENT=production/' .env && \
        sed -i 's/DEBUG=.*/DEBUG=false/' .env" \
                      "Environment configuration"
    
    # Step 6: Start services
    print_status "Starting services..."
    run_remote_command "systemctl enable trading-bot-api trading-bot trading-bot-monitor && \
                       systemctl start trading-bot-api && \
                       sleep 5 && \
                       systemctl start trading-bot && \
                       systemctl start trading-bot-monitor" \
                      "Service startup"
    
    # Step 7: Test deployment
    print_status "Testing deployment..."
    run_remote_command "sleep 10 && curl -s http://localhost:8000/health || echo 'Health check failed - check logs'" \
                      "Health check"
    
    # Step 8: Show status
    print_status "Checking service status..."
    run_remote_command "systemctl status trading-bot-api --no-pager -l | head -5" \
                      "Service status check"
}

# Function to show deployment summary
show_deployment_summary() {
    print_success "Deployment process completed!"
    echo
    echo "=== Deployment Summary ==="
    echo "Server: $VPS_IP"
    echo "Project Directory: /opt/trading-bot"
    echo "API URL: http://$VPS_IP:8000"
    echo "Health Check: http://$VPS_IP:8000/health"
    echo
    echo "=== Next Steps ==="
    echo "1. Configure API keys: ssh root@$VPS_IP 'nano /opt/trading-bot/.env'"
    echo "2. Check logs: ssh root@$VPS_IP 'journalctl -u trading-bot-api -f'"
    echo "3. Test API: curl http://$VPS_IP:8000/health"
    echo
    echo "=== Useful Commands ==="
    echo "Check services: ssh root@$VPS_IP 'systemctl status trading-bot-api'"
    echo "View logs: ssh root@$VPS_IP 'journalctl -u trading-bot-api -f'"
    echo "Restart API: ssh root@$VPS_IP 'systemctl restart trading-bot-api'"
    echo "Edit config: ssh root@$VPS_IP 'nano /opt/trading-bot/.env'"
    echo
}

# Function to test connection
test_connection() {
    print_status "Testing SSH connection to $VPS_IP..."
    
    if ssh -o ConnectTimeout=10 $VPS_USER@$VPS_IP "echo 'SSH connection successful'; uname -a"; then
        print_success "SSH connection working"
        return 0
    else
        print_error "SSH connection failed"
        echo
        echo "Please make sure:"
        echo "1. The server is running"
        echo "2. You have the correct root password"
        echo "3. SSH is enabled on the server"
        echo "4. The IP address is correct: $VPS_IP"
        return 1
    fi
}

# Function to setup SSH key (optional)
setup_ssh_key() {
    print_status "Setting up SSH key for passwordless access..."
    
    # Check if SSH key exists
    if [ ! -f ~/.ssh/id_rsa.pub ]; then
        print_warning "No SSH key found. Generating one..."
        ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -N ""
    fi
    
    # Copy SSH key to server
    print_status "Copying SSH key to server..."
    ssh-copy-id $VPS_USER@$VPS_IP
    
    if [ $? -eq 0 ]; then
        print_success "SSH key setup completed. Future connections will be passwordless."
    else
        print_warning "SSH key setup failed. You'll continue using password authentication."
    fi
}

# Main menu
show_menu() {
    echo
    echo "=== VPS Deployment Menu ==="
    echo "1. Test SSH Connection"
    echo "2. Upload Files Only"
    echo "3. Full Deployment"
    echo "4. Setup SSH Key (Optional)"
    echo "5. Check Server Status"
    echo "6. View Server Logs"
    echo "7. Exit"
    echo
    read -p "Choose an option (1-7): " choice
    
    case $choice in
        1)
            test_connection
            ;;
        2)
            upload_project_files
            ;;
        3)
            deploy_step_by_step
            show_deployment_summary
            ;;
        4)
            setup_ssh_key
            ;;
        5)
            ssh $VPS_USER@$VPS_IP 'systemctl status trading-bot-api trading-bot trading-bot-monitor'
            ;;
        6)
            ssh $VPS_USER@$VPS_IP 'journalctl -u trading-bot-api -n 50'
            ;;
        7)
            exit 0
            ;;
        *)
            print_error "Invalid option. Please choose 1-7."
            ;;
    esac
}

# Check prerequisites
check_prerequisites() {
    if ! command -v ssh &> /dev/null; then
        print_error "SSH client not found. Please install OpenSSH."
        exit 1
    fi
    
    if ! command -v rsync &> /dev/null; then
        print_error "rsync not found. Please install rsync."
        exit 1
    fi
    
    check_sshpass
}

# Main execution
main() {
    echo "=== Interactive VPS Deployment ==="
    echo "Server: $VPS_IP (Ubuntu 24.04 LTS)"
    echo "User: $VPS_USER"
    echo
    
    check_prerequisites
    
    # Parse command line arguments
    case "${1:-menu}" in
        "test")
            test_connection
            ;;
        "upload")
            upload_project_files
            ;;
        "deploy")
            deploy_step_by_step
            show_deployment_summary
            ;;
        "key")
            setup_ssh_key
            ;;
        "status")
            ssh $VPS_USER@$VPS_IP 'systemctl status trading-bot-api trading-bot trading-bot-monitor'
            ;;
        "logs")
            ssh $VPS_USER@$VPS_IP 'journalctl -u trading-bot-api -f'
            ;;
        "menu"|*)
            while true; do
                show_menu
                echo
                read -p "Press Enter to continue or Ctrl+C to exit..."
            done
            ;;
    esac
}

# Run main function
main "$@"
