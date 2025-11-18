#!/bin/bash
# Emergency deployment script for ASE-Bot

echo "🚀 ASE-Bot Emergency Deployment"
echo "==============================="

# Check if we can connect to server
if ping -c 1 185.70.198.201 > /dev/null 2>&1; then
    echo "✅ Server is responding - proceeding with deployment"
    
    # Try to deploy via SSH
    if ssh -o ConnectTimeout=10 -o BatchMode=yes root@185.70.198.201 'exit' 2>/dev/null; then
        echo "✅ SSH connection successful"
        
        # Upload and deploy
        scp deployment_package.tar.gz root@185.70.198.201:/root/
        ssh root@185.70.198.201 '
            cd /root
            tar -xzf deployment_package.tar.gz
            chmod +x *.sh
            ./deploy_on_server.sh
        '
    else
        echo "❌ SSH connection failed - check SSH key or server access"
    fi
else
    echo "❌ Server not responding - manual intervention required"
    echo "👉 Use UpCloud console to access server directly"
fi
