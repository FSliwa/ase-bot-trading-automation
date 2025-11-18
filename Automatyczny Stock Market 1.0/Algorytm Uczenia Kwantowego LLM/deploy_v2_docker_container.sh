#!/bin/bash

# Deploy V2 as Docker container in the same network as gateway

echo "=== Deploying V2 as Docker container ==="

SERVER_IP="185.70.198.201"
SERVER_USER="admin"

# Create deployment archive
echo "Creating deployment archive..."
tar -czf trading-bot-v2-docker.tar.gz \
    Dockerfile.v2 \
    src/ \
    requirements.txt \
    alembic.ini \
    migrations/ \
    .env.example \
    pyproject.toml \
    README.md 2>/dev/null || true

# Upload to server
echo "Uploading to server..."
scp trading-bot-v2-docker.tar.gz ${SERVER_USER}@${SERVER_IP}:/home/${SERVER_USER}/

# Deploy on server
echo "Deploying on server..."
ssh ${SERVER_USER}@${SERVER_IP} << 'EOF'
cd /home/admin

# Extract files
echo "Extracting files..."
tar -xzf trading-bot-v2-docker.tar.gz

# Stop old application
echo "Stopping old application..."
pkill -f uvicorn || true

# Build Docker image
echo "Building Docker image..."
docker build -f Dockerfile.v2 -t trading-bot-v2:latest . || { echo "Need sudo for Docker"; exit 1; }

# Stop old backend container if exists
echo "Stopping old backend container..."
docker stop backend 2>/dev/null || true
docker rm backend 2>/dev/null || true

# Create .env file for container
echo "Creating .env file..."
cat > .env << 'ENVEOF'
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/trading_bot
REDIS_URL=redis://redis:6379
SECRET_KEY=your-secret-key-here
VAPID_PUBLIC_KEY=BDrsEIkUKE9J1m4F2t4MfQ6XR0-UmSw6w2WzxCrRqPWbJdGiAs5uEzVDZH8KQCWMAOgGz9lIJGnceNM7PqHh2lU
VAPID_PRIVATE_KEY=MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgKPMiQ6TBxU7v7yD2no5RRnyUvVLR-m5F0HOa1KTxAeWhRANCAAQ67RCJFChPSdZuBdreDn0Ol0dPlJksOsNls8Qq0aj1myXRogLObhM1Q2R_CkAlhgDoBs_ZSCR53HjOz6h4dpZV
SMTP_HOST=smtp.brevo.com
SMTP_PORT=587
SMTP_USERNAME=7e2cec001@smtp-brevo.com
SMTP_PASSWORD=Hk5Vz1Ctq9xjKJaw
SMTP_FROM_EMAIL=contact@ase-bot.live
SMTP_FROM_NAME=ASE Trading Bot
SMTP_USE_TLS=true
ENVEOF

# Run container in the same network as gateway
echo "Starting V2 container..."
docker run -d \
    --name backend \
    --network trading-bot-network \
    -p 8009:8000 \
    --env-file .env \
    --restart unless-stopped \
    trading-bot-v2:latest || { echo "Need sudo for Docker"; exit 1; }

# Check if container is running
sleep 5
docker ps | grep backend && echo "Container started successfully!"

# Test health endpoint
sleep 10
curl -f http://localhost:8009/health && echo "Health check passed!"
EOF

echo "=== Deployment complete! ==="
echo "Test the application at: https://ase-bot.live/"
