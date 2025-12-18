#!/bin/bash

# Manual steps to deploy V2 as Docker container

cat << 'EOF'
=== Manual Deployment Steps for V2 Docker Container ===

Please run these commands on the server as root or with sudo:

1. SSH to server:
   ssh root@185.70.198.201

2. Go to trading bot directory:
   cd /home/admin/trading-bot-v2

3. Build Docker image:
   docker build -f Dockerfile.v2 -t trading-bot-v2:latest .

4. Stop and remove old backend container:
   docker stop backend 2>/dev/null || true
   docker rm backend 2>/dev/null || true

5. Create .env file for container:
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

6. Run V2 container:
   docker run -d \
       --name backend \
       --network trading-bot-network \
       -p 8009:8000 \
       --env-file .env \
       --restart unless-stopped \
       trading-bot-v2:latest

7. Check if container is running:
   docker ps | grep backend

8. Test health endpoint:
   curl -f http://localhost:8009/health

9. Test through gateway:
   curl -f http://localhost:8080/health

Alternative if gateway is looking for backend on different port:

10. Stop backend container:
    docker stop backend

11. Run on port 8000 instead:
    docker run -d \
        --name backend \
        --network trading-bot-network \
        -p 8000:8000 \
        --env-file .env \
        --restart unless-stopped \
        trading-bot-v2:latest

12. Test again:
    curl -f http://localhost:8080/health

EOF
