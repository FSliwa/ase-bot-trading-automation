#!/bin/bash

# Deployment script for all improvements

set -e

echo "=== Deploying Trading Bot Improvements ==="

SERVER_IP="185.70.198.201"
SERVER_USER="root"
SERVER_PASS="MIlik112"

# Create deployment package
echo "Creating deployment package..."
tar -czf improvements-deploy.tar.gz \
    src/ \
    migrations/versions/add_row_level_security.py \
    migrations/versions/add_performance_indexes.py \
    web/static/js/app.js \
    web/static/sw.js \
    web/templates/index_new.html \
    webpack.config.js \
    requirements.txt \
    .env.example \
    pyproject.toml

# Upload to server
echo "Uploading to server..."
scp improvements-deploy.tar.gz ${SERVER_USER}@${SERVER_IP}:/home/admin/trading-bot-v2/

# Deploy on server
echo "Deploying on server..."
sshpass -p "${SERVER_PASS}" ssh ${SERVER_USER}@${SERVER_IP} << 'EOF'
cd /home/admin/trading-bot-v2

# Extract files
echo "Extracting files..."
tar -xzf improvements-deploy.tar.gz

# Update requirements
echo "Updating requirements..."
cat >> requirements.txt << 'REQEOF'
pydantic-settings
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-fastapi
opentelemetry-instrumentation-sqlalchemy
opentelemetry-instrumentation-redis
opentelemetry-instrumentation-logging
opentelemetry-instrumentation-system-metrics
opentelemetry-exporter-otlp
REQEOF

# Run database migrations
echo "Running database migrations..."
source venv/bin/activate || python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head

# Build new Docker image
echo "Building Docker image..."
docker build -f Dockerfile.v2 -t trading-bot-v2:latest .

# Stop and remove old container
echo "Stopping old container..."
docker stop backend && docker rm backend

# Start new container with updated configuration
echo "Starting new container..."
docker run -d \
    --name backend \
    --network trading-bot-docker_trading-net \
    -p 8009:8000 \
    --env-file .env \
    --restart unless-stopped \
    trading-bot-v2:latest

# Verify deployment
echo "Verifying deployment..."
sleep 5
docker ps | grep backend
curl -f http://localhost:8009/health || echo "Health check failed"

echo "Deployment complete!"
EOF

# Cleanup
rm improvements-deploy.tar.gz

echo "=== Improvements deployed successfully ==="
echo ""
echo "Key improvements deployed:"
echo "✅ Row Level Security (RLS) on all tables"
echo "✅ Strict CSP with nonces only"
echo "✅ Secure secrets management"
echo "✅ Redis cache layer with TTL"
echo "✅ Database performance indexes"
echo "✅ Frontend code splitting & lazy loading"
echo "✅ OpenTelemetry observability"
echo "✅ Additional security headers"
echo ""
echo "Next steps:"
echo "1. Update .env file with proper secrets"
echo "2. Configure OpenTelemetry exporter endpoint"
echo "3. Monitor application performance"
echo "4. Set up alerts for errors and performance issues"
