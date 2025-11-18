#!/bin/bash

# VPS Deployment Monitor - Check if deployment is complete

echo "=== VPS DEPLOYMENT MONITOR ==="
echo "Server: 185.70.196.214"
echo "Checking deployment status..."
echo ""

# Check if server is reachable
echo "🔍 Testing server connectivity..."
if ping -c 3 185.70.196.214 > /dev/null 2>&1; then
    echo "✅ Server is reachable"
else
    echo "❌ Server is not reachable"
    exit 1
fi

# Check HTTP response
echo ""
echo "🌐 Testing HTTP response..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://185.70.196.214 --connect-timeout 10 --max-time 30)

if [ "$HTTP_STATUS" = "200" ]; then
    echo "✅ HTTP 200 - Server is responding correctly"
    echo ""
    echo "🎉 DEPLOYMENT SUCCESSFUL!"
    echo ""
    echo "📊 Server Details:"
    echo "   URL: http://185.70.196.214"
    echo "   Health Check: http://185.70.196.214/health"
    echo "   API Docs: http://185.70.196.214/docs"
    echo ""
    
    # Get health check data
    echo "🔍 Health Check Response:"
    curl -s http://185.70.196.214/health | python3 -m json.tool 2>/dev/null || curl -s http://185.70.196.214/health
    echo ""
    
elif [ "$HTTP_STATUS" = "502" ] || [ "$HTTP_STATUS" = "503" ]; then
    echo "⚠️  HTTP $HTTP_STATUS - Server is starting up..."
    echo "   This is normal during deployment. Try again in 1-2 minutes."
    
elif [ "$HTTP_STATUS" = "000" ]; then
    echo "❌ Connection failed - Server may still be setting up"
    echo "   Check if deployment is still running"
    
else
    echo "❌ HTTP $HTTP_STATUS - Unexpected response"
    echo "   Manual check needed"
fi

echo ""
echo "=== NEXT STEPS ==="
if [ "$HTTP_STATUS" = "200" ]; then
    echo "1. ✅ Open browser: http://185.70.196.214"
    echo "2. ✅ Configure API keys in the web interface"
    echo "3. ✅ Start trading bot functionality"
else
    echo "1. ⏳ Wait for deployment to complete (5-10 minutes)"
    echo "2. 🔄 Run this monitor again: ./monitor_deployment.sh"
    echo "3. 🆘 If issues persist, check VPS console logs"
fi

echo ""
echo "=== TROUBLESHOOTING ==="
echo "If deployment fails:"
echo "- Check VPS console for error messages"
echo "- Verify all commands completed successfully"
echo "- Run: systemctl status trading-bot-api"
echo "- Check logs: journalctl -u trading-bot-api -f"
echo ""
