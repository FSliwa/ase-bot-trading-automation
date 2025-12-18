#!/bin/bash

# Continuous deployment checker - runs until SSH works and deployment completes

SERVER="185.70.196.214"
USER="root"

echo "=== AUTOMATIC DEPLOYMENT MONITOR ==="
echo "Waiting for SSH to be configured..."
echo "Checking every 30 seconds..."
echo ""

# Function to test SSH
test_ssh() {
    ssh -o ConnectTimeout=5 -o BatchMode=yes root@$SERVER "echo 'SSH working'" 2>/dev/null
    return $?
}

# Function to test deployment
test_deployment() {
    curl -s -o /dev/null -w "%{http_code}" http://$SERVER --connect-timeout 10 --max-time 30
}

# Monitor loop
counter=0
while true; do
    counter=$((counter + 1))
    echo "[$counter] Testing SSH connection..."
    
    if test_ssh; then
        echo "✅ SSH is working!"
        echo ""
        echo "🚀 Starting automatic deployment..."
        
        if ./deploy.sh deploy; then
            echo ""
            echo "🎉 Deployment completed!"
            
            # Wait for service to start
            echo "⏳ Waiting for service to start..."
            sleep 30
            
            HTTP_STATUS=$(test_deployment)
            if [ "$HTTP_STATUS" = "200" ]; then
                echo "✅ HTTP 200 - Trading bot is running!"
                echo ""
                echo "🎯 SUCCESS! Your trading bot is accessible at:"
                echo "   📱 Web interface: http://$SERVER"
                echo "   🔍 Health check: http://$SERVER/health"
                echo "   📚 API docs: http://$SERVER/docs"
                echo ""
                exit 0
            else
                echo "⚠️ HTTP $HTTP_STATUS - Service may still be starting..."
                echo "Check manually: http://$SERVER"
            fi
        else
            echo "❌ Deployment failed!"
            exit 1
        fi
        
        break
    else
        echo "⏳ SSH not ready yet. Make sure to configure SSH key in VPS console:"
        echo "   Run: ./setup_ssh_only.sh for instructions"
        echo ""
        sleep 30
    fi
done
