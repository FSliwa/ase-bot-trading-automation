#!/bin/bash

SERVER_IP="185.70.198.201"

echo "Quick fix for authentication UI"

# Create complete deployment package
tar -czf quick-fix.tar.gz \
    src/application/exceptions/__init__.py \
    src/application/__init__.py \
    web/templates/login_dark.html \
    web/templates/register_dark.html \
    web/static/css/auth-enhancements.css \
    web/static/js/auth-ux.js

# Upload and fix
sshpass -p 'MIlik112' scp quick-fix.tar.gz root@${SERVER_IP}:/home/admin/trading-bot-v2/

sshpass -p 'MIlik112' ssh root@${SERVER_IP} << 'EOF'
cd /home/admin/trading-bot-v2

# Extract files
tar -xzf quick-fix.tar.gz

# Ensure __init__.py files exist
touch src/__init__.py
touch src/application/__init__.py
touch src/application/exceptions/__init__.py

# Add content to exceptions file
cat > src/application/exceptions/__init__.py << 'EOEXC'
"""Application-specific exceptions."""


class UserAlreadyExistsError(Exception):
    """Raised when trying to create a user that already exists."""
    pass


class UserNotFoundError(Exception):
    """Raised when a user is not found."""
    pass


class InvalidCredentialsError(Exception):
    """Raised when login credentials are invalid."""
    pass


class PermissionError(Exception):
    """Raised when a user doesn't have permission for an action."""
    pass


__all__ = [
    "UserAlreadyExistsError",
    "UserNotFoundError", 
    "InvalidCredentialsError",
    "PermissionError"
]
EOEXC

# Stop old container
docker stop backend
docker rm backend

# Rebuild
docker build -f Dockerfile.v2 -t trading-bot-v2:latest .

# Start new container
docker run -d \
    --name backend \
    --network trading-bot-docker_trading-net \
    -p 8009:8000 \
    --env-file .env \
    --restart unless-stopped \
    trading-bot-v2:latest

# Check status
sleep 10
docker ps | grep backend
docker logs backend --tail 10

echo "Fix completed"
EOF

rm quick-fix.tar.gz
