#!/bin/bash

# 🚀 DEPLOYMENT NA VPS Z HASŁEM
# Dla przypadku gdy SSH klucz nie jest jeszcze skonfigurowany

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

VPS_IP="185.70.196.214"

echo -e "${BLUE}🚀 DEPLOYMENT NA VPS ${VPS_IP}${NC}"
echo "=========================================="

echo -e "${YELLOW}⚠️  SSH klucz nie jest skonfigurowany${NC}"
echo -e "${BLUE}Użyjemy hasła do deployment'u${NC}"
echo ""

echo -e "${GREEN}📋 OPCJE DEPLOYMENT'U:${NC}"
echo "1. 🔑 Automatyczny deployment z hasłem"
echo "2. 📝 Manual deployment (kopiuj-wklej komendy)"
echo "3. 🔧 Setup SSH klucza i potem auto deployment"
echo ""

read -p "Wybierz opcję (1/2/3): " choice

case $choice in
    1)
        echo -e "${BLUE}🔑 Automatyczny deployment z hasłem...${NC}"
        echo "Będziesz musiał wpisać hasło root kilka razy."
        echo ""
        
        # Test connection with password
        echo -e "${YELLOW}Testowanie połączenia...${NC}"
        if ssh -o ConnectTimeout=10 root@$VPS_IP "echo 'Connection OK'"; then
            echo -e "${GREEN}✅ Połączenie działa!${NC}"
            
            echo -e "${BLUE}Uruchamianie deployment...${NC}"
            ./deploy_with_password.sh
            
        else
            echo -e "${RED}❌ Nie można się połączyć z VPS${NC}"
            echo "Sprawdź IP, hasło i dostępność serwera."
        fi
        ;;
        
    2)
        echo -e "${BLUE}📝 Manual Deployment${NC}"
        echo "Skopiuj i wykonaj te komendy na VPS:"
        echo ""
        
        # Show first part of manual commands
        echo -e "${GREEN}=== KROK 1: Przygotowanie systemu ===${NC}"
        echo "ssh root@$VPS_IP"
        echo ""
        echo "# Na VPS wykonaj:"
        echo "apt update && apt upgrade -y"
        echo "apt install -y curl wget git unzip python3.11 python3.11-venv python3-pip nodejs npm redis-server nginx"
        echo ""
        
        echo -e "${GREEN}=== KROK 2: Download projektu ===${NC}"
        echo "cd /opt"
        echo "git clone https://github.com/your-repo/trading-bot.git || mkdir -p trading-bot"
        echo "cd trading-bot"
        echo ""
        
        echo -e "${YELLOW}💡 Pełne instrukcje w: ./manual_deployment_commands.sh${NC}"
        cat ./manual_deployment_commands.sh
        ;;
        
    3)
        echo -e "${BLUE}🔧 Setup SSH klucza${NC}"
        echo ""
        echo "1. Dodaj ten klucz w panelu VPS:"
        echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJse5FI4ZPuXQvtL7eqqKvCEGPr2FgQzQRW1CfxjWasr f.sliwa@nowybankpolski.pl"
        echo ""
        echo "2. Po dodaniu klucza uruchom:"
        echo "./continue_deployment.sh"
        echo ""
        ;;
        
    *)
        echo -e "${RED}❌ Nieprawidłowa opcja${NC}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🔗 Po deployment'cie aplikacja będzie dostępna na:${NC}"
echo "http://$VPS_IP"
echo "http://$VPS_IP/docs (API docs)"
echo "http://$VPS_IP/health (health check)"
