#!/bin/bash

# 🚀 KONTYNUACJA AUTOMATYCZNEGO DEPLOYMENT'U
# Updated for VPS: 185.70.196.214

set -e

echo "🎯 AUTOMATYCZNY DEPLOYMENT - VPS 185.70.196.214"
echo "================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

VPS_IP="185.70.196.214"

echo -e "${BLUE}1. Sprawdzanie połączenia SSH...${NC}"

# Test SSH connection
if ssh -o ConnectTimeout=5 -o BatchMode=yes root@$VPS_IP "echo 'SSH OK'" 2>/dev/null; then
    echo -e "${GREEN}✅ SSH Connection: SUCCESS${NC}"
    SSH_OK=true
else
    echo -e "${RED}❌ SSH Connection: FAILED${NC}"
    echo -e "${YELLOW}⚠️  Wymagana konfiguracja SSH klucza w panelu VPS${NC}"
    SSH_OK=false
fi

if [ "$SSH_OK" = true ]; then
    echo -e "${GREEN}🚀 Uruchamianie automatycznego deployment...${NC}"
    
    # Run automated deployment
    if [ -f "./auto_deploy_with_ssh.sh" ]; then
        echo -e "${BLUE}Executing: ./auto_deploy_with_ssh.sh${NC}"
        chmod +x ./auto_deploy_with_ssh.sh
        ./auto_deploy_with_ssh.sh
    else
        echo -e "${RED}❌ auto_deploy_with_ssh.sh not found${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Deployment completed!${NC}"
    echo -e "${BLUE}🔗 Your trading bot: http://$VPS_IP${NC}"
    
else
    echo -e "${YELLOW}📋 KROKI DO WYKONANIA:${NC}"
    echo "1. Dodaj klucz SSH do panelu VPS:"
    echo "   ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJse5FI4ZPuXQvtL7eqqKvCEGPr2FgQzQRW1CfxjWasr f.sliwa@nowybankpolski.pl"
    echo ""
    echo "2. Sprawdź SSH_SETUP_REQUIRED.md dla szczegółowych instrukcji"
    echo ""
    echo "3. Po dodaniu klucza, uruchom ponownie:"
    echo "   ./continue_deployment.sh"
    echo ""
    echo -e "${BLUE}📚 Alternatywnie - manual deployment:${NC}"
    echo "   ./manual_deployment_commands.sh"
fi

echo ""
echo -e "${GREEN}🔧 Debug scripts available:${NC}"
echo "   ./debug_comprehensive.py     - Full system check"
echo "   ./check_deployment_status.sh - VPS status check"
echo "   ./monitor_deployment.sh      - Real-time monitoring"
