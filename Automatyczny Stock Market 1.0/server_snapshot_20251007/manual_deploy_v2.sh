#!/bin/bash
# Manual deployment script for Trading Bot V2
# This script creates a package and provides instructions for manual deployment

set -e

echo "🚀 Preparing Trading Bot V2 for manual deployment"

# Create deployment package
TIMESTAMP=$(date +'%Y%m%d_%H%M%S')
PACKAGE="trading_bot_v2_${TIMESTAMP}.tar.gz"

echo "📦 Creating deployment package: ${PACKAGE}"
tar -czf "${PACKAGE}" \
    src/ \
    templates/ \
    static/ \
    migrations/ \
    alembic.ini \
    requirements.txt \
    package.json \
    tailwind.config.js \
    Dockerfile.v2 \
    docker-compose.yml \
    .env.example

echo "✅ Package created successfully: ${PACKAGE}"
echo

echo "📋 MANUAL DEPLOYMENT INSTRUCTIONS:"
echo "=================================="
echo
echo "1. Upload the package to your server:"
echo "   scp ${PACKAGE} admin@185.70.198.201:/tmp/"
echo
echo "2. Connect to your server:"
echo "   ssh admin@185.70.198.201"
echo
echo "3. On the server, run these commands:"
echo "   cd /opt"
echo "   mkdir -p trading-bot-v2"
echo "   cd trading-bot-v2"
echo "   tar -xzf /tmp/${PACKAGE}"
echo
echo "4. Copy environment configuration:"
echo "   cp .env.example .env"
echo "   nano .env  # Edit with your actual configuration"
echo
echo "5. Build and start the V2 application:"
echo "   docker build -f Dockerfile.v2 -t trading-bot-v2:latest ."
echo "   docker-compose up -d"
echo
echo "6. Run database migration:"
echo "   docker-compose exec backend-v2 alembic upgrade head"
echo
echo "7. Test the new application:"
echo "   curl http://localhost:8000/health"
echo
echo "8. If everything works, update Nginx to point to the new service"
echo
echo "📧 Don't forget to configure SMTP settings in .env:"
echo "   SMTP_HOST=smtp-relay.gmail.com"
echo "   SMTP_PORT=587"
echo "   EMAIL_FROM=\"ASE Bot <biuro@nowybankpolski.pl>\""
echo "   # Leave SMTP_USERNAME and SMTP_PASSWORD empty for IP-based auth"
echo
echo "🎉 V2 deployment package ready!"
