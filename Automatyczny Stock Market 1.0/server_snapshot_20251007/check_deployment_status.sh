#!/bin/bash

echo "🔍 VPS DEPLOYMENT STATUS CHECK"
echo "=============================="
echo ""

VPS_IP="185.70.196.214"

echo "📡 Testing VPS connectivity..."
if ping -c 2 $VPS_IP > /dev/null 2>&1; then
    echo "✅ VPS is reachable"
else
    echo "❌ VPS is not reachable"
    exit 1
fi

echo ""
echo "🌐 Testing HTTP endpoints..."

# Test health endpoint
echo "Testing /health endpoint..."
if curl -s http://$VPS_IP/health | grep -q "healthy\|status"; then
    echo "✅ Health endpoint working"
else
    echo "❌ Health endpoint not responding"
fi

# Test root endpoint  
echo "Testing root endpoint..."
if curl -s http://$VPS_IP/ | grep -q "Trading Bot\|Server"; then
    echo "✅ Root endpoint working"
else
    echo "❌ Root endpoint not responding"
fi

echo ""
echo "📊 Deployment Summary:"
echo "======================"
echo "VPS IP: $VPS_IP"
echo "Main URL: http://$VPS_IP/"
echo "Health Check: http://$VPS_IP/health"
echo "API Docs: http://$VPS_IP/docs"
echo ""

echo "🚀 If all tests pass, your trading bot is successfully deployed!"
echo ""
echo "Next steps:"
echo "1. Visit http://$VPS_IP/ in your browser"
echo "2. Check health status at http://$VPS_IP/health"
echo "3. Access API documentation at http://$VPS_IP/docs"
echo "4. Monitor logs: ssh root@$VPS_IP 'journalctl -u trading-bot-api -f'"
