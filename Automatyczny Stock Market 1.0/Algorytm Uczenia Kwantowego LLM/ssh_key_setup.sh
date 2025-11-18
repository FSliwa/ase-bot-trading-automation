#!/bin/bash
# SSH Key Setup for VPS

VPS_IP="185.70.196.214"
VPS_USER="root"
PUBLIC_KEY=$(cat ~/.ssh/id_ed25519.pub)

echo "=== SSH Key Setup Guide ==="
echo "Your public key:"
echo "$PUBLIC_KEY"
echo
echo "To add this key to your VPS, you have several options:"
echo
echo "1. Through VPS Provider Panel:"
echo "   - Log into your VPS provider's panel"
echo "   - Go to SSH Keys section"
echo "   - Add the above public key"
echo "   - Restart the server if needed"
echo
echo "2. Through VPS Console (in browser):"
echo "   - Access your VPS console through provider's website"
echo "   - Login as root with password: MIlik112!@4"
echo "   - Run these commands:"
echo "   mkdir -p ~/.ssh"
echo "   echo '$PUBLIC_KEY' >> ~/.ssh/authorized_keys"
echo "   chmod 600 ~/.ssh/authorized_keys"
echo "   chmod 700 ~/.ssh"
echo
echo "3. Manual deployment (if console access available):"
echo "   Copy and paste the deployment commands manually"
echo
echo "After adding the SSH key, test with:"
echo "ssh root@$VPS_IP"
echo
echo "Then run the deployment:"
echo "./deploy.sh deploy"
