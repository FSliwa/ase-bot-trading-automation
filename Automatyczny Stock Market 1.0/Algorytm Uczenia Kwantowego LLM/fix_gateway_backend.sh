#!/bin/bash

# Fix gateway to connect to V2 backend

SERVER_IP="185.70.198.201"
SERVER_USER="admin"

echo "=== Fixing Gateway Configuration ==="

# Option 1: Restart gateway container with correct environment variable
ssh ${SERVER_USER}@${SERVER_IP} << 'EOF'
# Check current gateway container
echo "Current gateway container:"
docker ps | grep gateway || echo "No gateway container found"

# If gateway is running, restart it with correct backend URL
docker ps -q --filter name=gateway | xargs -r docker stop
docker ps -aq --filter name=gateway | xargs -r docker rm

# Run gateway with correct backend URL
docker run -d \
    --name gateway \
    --network trading-bot-network \
    -p 8080:8080 \
    -e BACKEND_BASE=http://backend:8000 \
    --restart unless-stopped \
    gateway:latest || echo "Failed to start gateway container"

# Alternative: If the above fails, check if gateway is running as a process
if ! docker ps | grep -q gateway; then
    echo "Gateway might be running as a process, not container"
    ps aux | grep -E "gateway|8080" | grep -v grep
fi
EOF

echo "=== Gateway configuration updated ==="
