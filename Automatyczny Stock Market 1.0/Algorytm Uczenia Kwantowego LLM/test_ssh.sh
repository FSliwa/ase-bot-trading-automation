#!/bin/bash
# SSH Connection Setup for VPS Deployment

VPS_IP="185.70.196.214"
VPS_USER="root"

echo "=== VPS Connection Setup ==="
echo "Server: $VPS_IP"
echo "OS: Ubuntu 24.04 LTS"
echo "User: $VPS_USER"
echo

# Test SSH connection with password authentication
echo "Testing SSH connection..."
echo "If this is your first connection, you'll need to:"
echo "1. Accept the server's SSH fingerprint"
echo "2. Enter the root password provided by your hosting provider"
echo

# Try to connect and run a simple command
ssh -o ConnectTimeout=10 $VPS_USER@$VPS_IP "echo 'SSH connection successful!'; uname -a"

if [ $? -eq 0 ]; then
    echo
    echo "✅ SSH connection successful!"
    echo
    echo "Next steps:"
    echo "1. Run: ./deploy.sh deploy"
    echo "2. Or manually upload files and run initialization"
else
    echo
    echo "❌ SSH connection failed."
    echo
    echo "Troubleshooting steps:"
    echo "1. Make sure you have the root password from your hosting provider"
    echo "2. Try connecting manually: ssh root@$VPS_IP"
    echo "3. Check if the server is running and accessible"
    echo "4. Verify the IP address: $VPS_IP"
fi
