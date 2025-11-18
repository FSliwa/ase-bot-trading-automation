# 🚀 QUICK DEPLOYMENT COMMANDS - Copy & Paste na serwerze

## Zaloguj się na serwer:
```bash
ssh admin@185.70.196.214
```

## Następnie wykonaj te komendy jedna po drugiej:

### 1. Backup i przygotowanie
```bash
sudo cp -r /opt/trading-bot /opt/trading-bot-backup-$(date +%Y%m%d) 2>/dev/null || true
sudo mkdir -p /opt/trading-bot
```

### 2. Kopiowanie plików
```bash
sudo cp ~/enhanced_server_gpt5.py ~/user_database.py ~/index.html ~/login.html ~/register.html ~/nginx_8009.conf ~/requirements.txt ~/simple_openai_client.py ~/web_search_tool.py ~/users.json /opt/trading-bot/
```

### 3. Uprawnienia
```bash
sudo chown -R www-data:www-data /opt/trading-bot
sudo chmod +x /opt/trading-bot/enhanced_server_gpt5.py
```

### 4. Python dependencies
```bash
sudo python3 -m pip install --upgrade pip
sudo python3 -m pip install -r /opt/trading-bot/requirements.txt
```

### 5. Nginx konfiguracja
```bash
sudo cp /opt/trading-bot/nginx_8009.conf /etc/nginx/sites-available/trading-bot
sudo ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 6. Systemd service (jedna komenda)
```bash
sudo tee /etc/systemd/system/trading-bot.service > /dev/null << 'EOF'
[Unit]
Description=Trading Bot Server with Registration
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trading-bot
ExecStart=/usr/bin/python3 enhanced_server_gpt5.py
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
```

### 7. Uruchomienie serwisu
```bash
sudo systemctl daemon-reload
sudo systemctl enable trading-bot
sudo systemctl stop trading-bot 2>/dev/null || true
sudo systemctl start trading-bot
```

### 8. Sprawdzenie statusu
```bash
sudo systemctl status trading-bot
```

### 9. Inicjalizacja bazy danych
```bash
cd /opt/trading-bot && sudo -u www-data python3 user_database.py
```

### 10. Test końcowy
```bash
curl http://localhost:8009/login
curl http://localhost:8009/register
```

## 🎉 Po ukończeniu:

- **Website**: http://185.70.196.214
- **Login**: http://185.70.196.214/login
- **Register**: http://185.70.196.214/register

## 🔑 Default Login:
- **Username**: admin
- **Password**: password

## 📊 Monitoring:
```bash
sudo journalctl -u trading-bot -f    # Logi na żywo
sudo systemctl restart trading-bot   # Restart serwisu
```
