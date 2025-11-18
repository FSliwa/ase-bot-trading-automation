#!/bin/bash

# 🚀 QUICK SERVER UPDATE - Direct Commands
# Bezpośrednie komendy do aktualizacji serwera

VPS_IP="185.70.196.214"
USER="admin"

echo "🚀 Kontynuacja aktualizacji serwera..."
echo "═══════════════════════════════════════"

# Execute deployment commands directly on server
echo "📋 Wykonywanie komend deployment na serwerze..."

# Command 1: Check if files are uploaded
echo "1. Sprawdzanie przesłanych plików..."
ssh $USER@$VPS_IP "ls -la /tmp/TRADING_BOT_V2_FINAL.tar.gz && ls -la ~/deploy_on_server.sh"

if [ $? -eq 0 ]; then
    echo "✅ Pliki zostały przesłane"
else
    echo "❌ Pliki nie zostały przesłane"
    exit 1
fi

# Command 2: Execute deployment step by step
echo ""
echo "2. Uruchamianie deployment krok po kroku..."

# Make script executable
echo "🔧 Ustawianie uprawnień..."
ssh $USER@$VPS_IP "chmod +x ~/deploy_on_server.sh"

# Try to run with different sudo methods
echo "🚀 Próba uruchomienia deployment..."

# Method 1: Try with sudo -S (stdin password)
echo "Metoda 1: sudo -S"
ssh $USER@$VPS_IP "echo 'admin_password' | sudo -S ~/deploy_on_server.sh" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "✅ Deployment zakończony pomyślnie!"
else
    echo "⚠️  Metoda 1 nie powiodła się, próbując alternatywnej metody..."
    
    # Method 2: Manual commands without sudo script
    echo "Metoda 2: Manualne komendy..."
    
    # Execute essential commands manually
    ssh $USER@$VPS_IP << 'MANUAL_COMMANDS'
set -e

echo "🔄 Manual deployment process..."

# Check if we can use sudo
if sudo -n true 2>/dev/null; then
    echo "✅ Sudo access available"
    SUDO="sudo"
elif groups | grep -q 'admin\|sudo\|wheel'; then
    echo "⚠️  User in admin group, will try sudo"
    SUDO="sudo"
else
    echo "❌ No sudo access, trying without sudo..."
    SUDO=""
fi

# Try to extract files to home directory first
echo "📂 Extracting files to home directory..."
cd ~/
tar -xzf /tmp/TRADING_BOT_V2_FINAL.tar.gz

# Check what we have
echo "📋 Files extracted:"
ls -la

echo "✅ Files ready for manual deployment"
echo "Next steps require admin privileges on the server"

MANUAL_COMMANDS

fi

echo ""
echo "📊 Sprawdzanie statusu serwera..."

# Check if application is running
SERVER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://$VPS_IP/login 2>/dev/null || echo "000")

if [ "$SERVER_STATUS" = "200" ]; then
    echo "✅ Serwer działa poprawnie!"
    echo "🌐 Login page: http://$VPS_IP/login"
    echo "📝 Register page: http://$VPS_IP/register"
else
    echo "⚠️  Serwer potrzebuje finalnej konfiguracji (Status: $SERVER_STATUS)"
    
    # Provide manual steps
    echo ""
    echo "📋 FINALNE KROKI NA SERWERZE:"
    echo "═══════════════════════════════════════"
    echo ""
    echo "Zaloguj się na serwer i wykonaj:"
    echo "ssh $USER@$VPS_IP"
    echo ""
    echo "Następnie uruchom te komendy jako root/sudo:"
    echo ""
    echo "# 1. Backup poprzedniej instalacji"
    echo "sudo cp -r /opt/trading-bot /opt/trading-bot-backup-\$(date +%Y%m%d) 2>/dev/null || true"
    echo ""
    echo "# 2. Stwórz katalog i skopiuj pliki"
    echo "sudo mkdir -p /opt/trading-bot"
    echo "sudo cp -r ~/enhanced_server_gpt5.py ~/user_database.py ~/index.html ~/login.html ~/register.html ~/nginx_8009.conf ~/requirements.txt ~/simple_openai_client.py ~/web_search_tool.py /opt/trading-bot/"
    echo ""
    echo "# 3. Ustaw uprawnienia"
    echo "sudo chown -R www-data:www-data /opt/trading-bot"
    echo "sudo chmod +x /opt/trading-bot/enhanced_server_gpt5.py"
    echo ""
    echo "# 4. Zainstaluj dependencies"
    echo "sudo python3 -m pip install -r /opt/trading-bot/requirements.txt"
    echo ""
    echo "# 5. Skonfiguruj Nginx"
    echo "sudo cp /opt/trading-bot/nginx_8009.conf /etc/nginx/sites-available/trading-bot"
    echo "sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/"
    echo "sudo nginx -t && sudo systemctl reload nginx"
    echo ""
    echo "# 6. Stwórz systemd service"
    echo "sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'EOF'"
    echo "[Unit]"
    echo "Description=Trading Bot Server with Registration"
    echo "After=network.target"
    echo ""
    echo "[Service]"
    echo "Type=simple"
    echo "User=www-data"
    echo "WorkingDirectory=/opt/trading-bot"
    echo "ExecStart=/usr/bin/python3 enhanced_server_gpt5.py"
    echo "Restart=always"
    echo "RestartSec=3"
    echo "Environment=PYTHONUNBUFFERED=1"
    echo ""
    echo "[Install]"
    echo "WantedBy=multi-user.target"
    echo "EOF"
    echo ""
    echo "# 7. Uruchom serwis"
    echo "sudo systemctl daemon-reload"
    echo "sudo systemctl enable trading-bot"
    echo "sudo systemctl stop trading-bot 2>/dev/null || true"
    echo "sudo systemctl start trading-bot"
    echo ""
    echo "# 8. Sprawdź status"
    echo "sudo systemctl status trading-bot"
    echo ""
    echo "# 9. Inicjalizuj bazę danych"
    echo "cd /opt/trading-bot && sudo -u www-data python3 user_database.py"
    echo ""
fi

echo ""
echo "🎯 PODSUMOWANIE AKTUALIZACJI:"
echo "═══════════════════════════════════════"
echo "✅ Pliki przesłane na serwer"
echo "✅ Skrypt deployment przygotowany"
echo "⏳ Wymagana finalna konfiguracja na serwerze"
echo ""
echo "🔑 Po ukończeniu będzie dostępne:"
echo "🌐 Website: http://$VPS_IP"
echo "🔐 Login: http://$VPS_IP/login"
echo "📝 Register: http://$VPS_IP/register"
echo ""
echo "📊 Default admin account:"
echo "   Username: admin"
echo "   Password: password"
