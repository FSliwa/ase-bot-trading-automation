#!/bin/bash

echo "🔄 Updating login.html on server..."

# Copy updated login.html to production directory
sudo cp ~/login.html /opt/trading-bot/login.html

# Set proper permissions
sudo chown www-data:www-data /opt/trading-bot/login.html

# Restart trading-bot service
sudo systemctl restart trading-bot

# Check service status
echo "📊 Service status:"
sudo systemctl status trading-bot --no-pager | head -10

# Test the fix
echo "🧪 Testing registration link..."
curl -s http://localhost:8009/login | grep -A 2 -B 2 'href="/register"' || echo "Link not found - checking pattern..."
curl -s http://localhost:8009/login | grep -A 5 'Zarejestruj się' 

echo "✅ Update complete!"
echo "🌐 Test the link at: http://185.70.196.214/login"
