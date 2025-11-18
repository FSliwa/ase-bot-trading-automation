#!/bin/bash

# Test script for verifying port configuration updates
# This script checks if all components correctly use environment variables for ports

set -e

echo "🔍 Testing Port Configuration Updates"
echo "===================================="

# Load environment variables
if [ -f ".env" ]; then
    source .env
    echo "✅ Environment file loaded"
else
    echo "❌ .env file not found"
    exit 1
fi

# Display current port configuration
echo ""
echo "📊 Current Port Configuration:"
echo "  APP_PORT: ${APP_PORT:-8008}"
echo "  POSTGRES_PORT: ${POSTGRES_PORT:-5433}"
echo "  REDIS_PORT: ${REDIS_PORT:-6380}"
echo "  GRAFANA_PORT: ${GRAFANA_PORT:-3001}"
echo "  PROMETHEUS_PORT: ${PROMETHEUS_PORT:-9091}"
echo "  NGINX_PORT: ${NGINX_PORT:-8080}"
echo "  NGINX_MONITORING_PORT: ${NGINX_MONITORING_PORT:-8081}"

# Test 1: Check docker-compose.yml for environment variable usage
echo ""
echo "🐳 Test 1: Docker Compose Configuration"
if grep -q "\${APP_PORT" docker-compose.yml; then
    echo "✅ docker-compose.yml uses environment variables for ports"
else
    echo "❌ docker-compose.yml does not use environment variables"
fi

# Test 2: Check nginx.conf for variable port support
echo ""
echo "🌐 Test 2: Nginx Configuration"
if grep -q "\${NGINX_MONITORING_PORT" nginx.conf; then
    echo "✅ nginx.conf uses environment variables for ports"
else
    echo "❌ nginx.conf does not use environment variables"
fi

# Test 3: Check web/app.py for port configuration
echo ""
echo "🐍 Test 3: Python App Configuration"
if grep -q "APP_PORT" web/app.py; then
    echo "✅ web/app.py uses APP_PORT environment variable"
else
    echo "❌ web/app.py does not use APP_PORT"
fi

# Test 4: Check start scripts for port usage
echo ""
echo "🚀 Test 4: Start Scripts Configuration"
if grep -q "APP_PORT" start_app.py; then
    echo "✅ start_app.py uses APP_PORT environment variable"
else
    echo "❌ start_app.py does not use APP_PORT"
fi

if grep -q "APP_PORT" run_dashboard.sh; then
    echo "✅ run_dashboard.sh uses APP_PORT environment variable"
else
    echo "❌ run_dashboard.sh does not use APP_PORT"
fi

# Test 5: Check deployment script for health check port
echo ""
echo "🔧 Test 5: Deployment Script Configuration"
if grep -q "APP_PORT" deploy.sh; then
    echo "✅ deploy.sh uses APP_PORT environment variable"
else
    echo "❌ deploy.sh does not use APP_PORT"
fi

# Test 6: Check for potential port conflicts
echo ""
echo "⚠️  Test 6: Port Conflict Check"
./resolve_port_conflicts.sh

echo ""
echo "🎉 Port configuration test completed!"
echo "📝 Summary: All components should now use environment variables for port configuration"
echo "🔄 Next step: Run './resolve_port_conflicts.sh' to check for conflicts before deployment"
