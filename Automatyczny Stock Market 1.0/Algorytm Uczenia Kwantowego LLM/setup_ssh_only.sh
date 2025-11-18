#!/bin/bash

# SSH Key Setup Script - Just copy these commands to VPS console

echo "=== SSH KEY SETUP FOR VPS ==="
echo "Server: 185.70.196.55"
echo "User: root"
echo ""

echo "📋 COPY THESE COMMANDS TO VPS CONSOLE:"
echo ""
echo "1. Access VPS console via web browser"
echo "2. Login as root with password: MIlik112!@4"
echo "3. Copy and paste this EXACT command:"
echo ""

cat << 'SSH_SETUP'
mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIG74EI1jKvKNRqHv/PLEGxaWc+9EuUgr7gARbejvV8Mq f.sliwa@nowybankpolski.pl" >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && chown -R root:root ~/.ssh && echo "SSH key configured successfully!"
SSH_SETUP

echo ""
echo "4. After running the command, test SSH from here:"
echo "   ssh root@185.70.196.55"
echo ""
echo "5. Once SSH works, run full deployment:"
echo "   ./deploy.sh deploy"
echo ""
