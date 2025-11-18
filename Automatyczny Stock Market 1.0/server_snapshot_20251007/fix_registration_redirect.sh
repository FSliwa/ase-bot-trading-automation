#!/bin/bash

# 🔧 FIX REGISTRATION REDIRECT - Update Server Files
echo "🔧 Naprawianie przekierowania do rejestracji..."
echo "================================================"

VPS_IP="185.70.196.214"
USER="admin"

echo "1. 📤 Kopiowanie naprawionego pliku login.html..."
# Już skopiowane

echo "2. 🔐 Łączenie z serwerem i aktualizacja..."

# Utwórz skrypt do wykonania na serwerze
cat > update_login_fix.sh << 'EOF'
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
EOF

# Skopiuj skrypt na serwer i wykonaj
scp update_login_fix.sh admin@$VPS_IP:~/
ssh admin@$VPS_IP 'chmod +x update_login_fix.sh && ./update_login_fix.sh'

echo ""
echo "🎯 PODSUMOWANIE NAPRAWY:"
echo "======================="
echo "✅ Naprawiono link z 'register.html' na '/register'"
echo "✅ Zaktualizowano plik na serwerze"
echo "✅ Zrestartowano serwis trading-bot"
echo ""
echo "📍 LOKALIZACJA BAZY DANYCH UŻYTKOWNIKÓW:"
echo "Plik: /opt/trading-bot/users.json"
echo "Format: JSON z hashowanymi hasłami"
echo "Właściciel: www-data:www-data"
echo ""
echo "🌐 Testuj teraz: http://185.70.196.214/login"
echo "   Kliknij 'Zarejestruj się tutaj' → powinno przekierować na /register"
