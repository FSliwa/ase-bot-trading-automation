# 🚀 Manual Deployment Guide - Trading Bot v2 with Registration System

## 📋 Co zostało zaktualizowane:
1. **System rejestracji** - Nowi użytkownicy mogą się rejestrować
2. **Nowoczesny design** - Glass effect i gradient na wszystkich stronach
3. **Bezpieczna autentykacja** - Haszowanie haseł z salt
4. **Port 8009** - Serwer skonfigurowany na właściwy port
5. **Nginx config** - Dodano route dla /register

## 📦 Pliki do przesłania na serwer:

### Główne pliki aplikacji:
- `enhanced_server_gpt5.py` - Główny serwer z systemem rejestracji
- `user_database.py` - System zarządzania użytkownikami
- `index.html` - Główna strona z nowym designem
- `login.html` - Strona logowania z nowoczesnym UI
- `register.html` - Nowa strona rejestracji
- `requirements.txt` - Dependencies Python

### Pliki konfiguracyjne:
- `nginx_8009.conf` - Zaktualizowana konfiguracja Nginx
- `simple_openai_client.py` - Klient OpenAI
- `web_search_tool.py` - Narzędzie wyszukiwania

## 🔧 Instrukcje deployment na VPS (185.70.196.214):

### 1. Przesłanie plików:
```bash
# Połącz się z serwerem
ssh root@185.70.196.214

# Przejdź do katalogu aplikacji
cd /opt/trading-bot

# Backup poprzedniej wersji
cp -r /opt/trading-bot /opt/trading-bot-backup-$(date +%Y%m%d)

# Zatrzymaj poprzednią wersję
systemctl stop trading-bot

# Skopiuj nowe pliki (przesłane przez FTP/SCP)
# Wszystkie pliki powinny być w /opt/trading-bot/
```

### 2. Instalacja dependencies:
```bash
cd /opt/trading-bot
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### 3. Konfiguracja Nginx:
```bash
# Kopiuj nową konfigurację
cp nginx_8009.conf /etc/nginx/sites-available/trading-bot

# Włącz konfigurację
ln -sf /etc/nginx/sites-available/trading-bot /etc/nginx/sites-enabled/

# Testuj konfigurację
nginx -t

# Przeładuj Nginx
systemctl reload nginx
```

### 4. Inicjalizacja bazy danych:
```bash
cd /opt/trading-bot
python3 user_database.py
```

### 5. Aktualizacja systemd service:
```bash
cat > /etc/systemd/system/trading-bot.service << 'EOF'
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

# Przeładuj systemd
systemctl daemon-reload
systemctl enable trading-bot
```

### 6. Uruchomienie aplikacji:
```bash
# Ustaw uprawnienia
chown -R www-data:www-data /opt/trading-bot
chmod +x enhanced_server_gpt5.py

# Uruchom serwis
systemctl start trading-bot

# Sprawdź status
systemctl status trading-bot
```

### 7. Sprawdzenie logów:
```bash
# Logi aplikacji
journalctl -u trading-bot -f

# Logi Nginx
tail -f /var/log/nginx/error.log
tail -f /var/log/nginx/access.log
```

## 🌐 URLs po deployment:

- **Główna strona**: http://185.70.196.214/
- **Logowanie**: http://185.70.196.214/login
- **Rejestracja**: http://185.70.196.214/register
- **API**: http://185.70.196.214/api/

## 🔐 Domyślne konto administratora:

- **Username**: admin
- **Password**: password
- **Email**: admin@tradingbot.com

## ✅ Funkcje do przetestowania:

1. **Rejestracja nowego użytkownika**:
   - Przejdź na /register
   - Wypełnij formularz rejestracji
   - Sprawdź walidację formularza

2. **Logowanie**:
   - Przejdź na /login
   - Zaloguj się jako admin lub nowy użytkownik
   - Sprawdź przekierowanie na dashboard

3. **Dashboard**:
   - Sprawdź czy nowy design się załadował
   - Sprawdź czy informacje o użytkowniku są wyświetlane
   - Sprawdź funkcje GPT-5 i Web Search

4. **Wylogowanie**:
   - Kliknij przycisk "Wyloguj"
   - Sprawdź przekierowanie na stronę logowania

## 🐛 Troubleshooting:

### Serwer nie uruchamia się:
```bash
journalctl -u trading-bot --since "5 minutes ago"
python3 /opt/trading-bot/enhanced_server_gpt5.py
```

### Problemy z Nginx:
```bash
nginx -t
systemctl status nginx
```

### Problemy z bazą danych:
```bash
cd /opt/trading-bot
python3 -c "from user_database import UserDatabase; db = UserDatabase(); print(db.get_user_stats())"
```

### Port zajęty:
```bash
lsof -i :8009
kill -9 <PID>
```

## 📊 Monitoring:

- **Status serwisu**: `systemctl status trading-bot`
- **Logi na żywo**: `journalctl -u trading-bot -f`
- **Sprawdzenie portu**: `curl -I http://localhost:8009/login`
- **Statystyki użytkowników**: `python3 user_database.py`

## 🎉 Po successful deployment:

Aplikacja będzie dostępna z:
- ✅ Pełnym systemem rejestracji użytkowników
- ✅ Nowoczesnym designem glass effect
- ✅ Bezpieczną autentykacją
- ✅ Responsywnym interfejsem
- ✅ Integracją GPT-5 i Web Search
- ✅ Zarządzaniem sesjami użytkowników
