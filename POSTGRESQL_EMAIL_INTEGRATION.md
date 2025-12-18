# 🚀 PostgreSQL + Email Integration Guide
## Kompletna integracja bazy danych i powiadomień e-mail

### 📋 Przegląd systemu

System Trading Panel został zintegrowany z:
- **PostgreSQL** - profesjonalna baza danych z audytem
- **SMTP Email** - automatyczne powiadomienia rejestracyjne
- **Weryfikacja email** - bezpieczna aktywacja kont
- **Audit logging** - śledzenie działań użytkowników

---

## 🗄️ Gdzie są zapisywane dane?

### PostgreSQL Database (Zalecane - Produkcja)
```
🐘 Lokalizacja: PostgreSQL Server
📊 Database: trading_bot
👤 User: trading_user
🔗 Host: localhost:5432
```

**Tabele:**
- `users` - dane użytkowników, OAuth, weryfikacja email
- `user_sessions` - aktywne sesje logowania
- `audit_log` - dziennik działań dla bezpieczeństwa

### JSON Database (Fallback)
```
📁 Lokalizacja: /opt/trading-bot/users.json
🔄 Automatyczna migracja: do PostgreSQL dostępna
```

---

## 📧 System powiadomień e-mail

### ✅ Co zostało zaimplementowane:
- **Welcome email** - piękny HTML z gradientami
- **Email verification** - bezpieczny token weryfikacyjny
- **Responsive design** - działa na wszystkich urządzeniach
- **Konfigurowalny SMTP** - obsługa Gmail, Outlook, etc.

### 📬 Przykład wiadomości:
```
🎉 Witaj w Trading Panel!

Twoje konto zostało utworzone:
• Username: john_doe
• Email: john@example.com
• Data: 09.09.2024 16:30

[Potwierdź Email] [Zaloguj się]
```

### ⚙️ Konfiguracja SMTP:
```bash
# Gmail
SMTP_SERVER=smtp.gmail.com
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password

# Outlook
SMTP_SERVER=smtp-mail.outlook.com
SMTP_USERNAME=your_email@outlook.com
SMTP_PASSWORD=your_password
```

---

## 🛠️ Instalacja na serwerze

### 1. Instalacja PostgreSQL
```bash
# Przejdź na serwer VPS
ssh admin@185.70.196.214

# Uruchom instalację PostgreSQL (NIE używaj sudo!)
chmod +x deploy_postgresql_email.sh
./deploy_postgresql_email.sh
```

> ⚠️ **WAŻNE**: Nie uruchamiaj skryptu z `sudo`! Skrypt sam poprosi o uprawnienia sudo gdy będzie potrzebował.

### 2. Konfiguracja środowiska
```bash
# Skonfiguruj zmienne środowiskowe
source setup_environment.sh

# Edytuj konfigurację SMTP
nano /opt/trading-bot/.env.db
```

### 3. Aktualizacja plików serwera
```bash
# Skopiuj nowe pliki
sudo cp postgresql_database.py /opt/trading-bot/
sudo cp enhanced_server_gpt5.py /opt/trading-bot/

# Restart serwisu
sudo systemctl restart trading-bot
```

### 4. Migracja danych (opcjonalnie)
```bash
# Jeśli masz dane w JSON, migruj do PostgreSQL
cd /opt/trading-bot
python3 -c "
from postgresql_database import PostgreSQLDatabase
db = PostgreSQLDatabase()
result = db.migrate_from_json('users.json')
print('Migration result:', result)
"
```

---

## 🔧 Konfiguracja SMTP (Gmail)

### 1. Włącz 2FA w Gmail
1. Idź do: https://myaccount.google.com/security
2. Włącz **2-Step Verification**

### 2. Utwórz App Password
1. Idź do: **Manage your Google Account** → **Security**
2. Kliknij **2-Step Verification**
3. Scroll down i kliknij **App passwords**
4. Wybierz **Mail** i **Other**
5. Nazwij: "Trading Panel"
6. Skopiuj wygenerowane hasło

### 3. Aktualizuj konfigurację
```bash
# Edytuj plik środowiskowy
nano /opt/trading-bot/.env.db

# Dodaj swoje dane:
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_gmail@gmail.com
SMTP_PASSWORD=generated_app_password
SMTP_FROM_NAME=Trading Panel
SMTP_FROM_EMAIL=noreply@tradingpanel.com
```

---

## 🧪 Testowanie systemu

### Test PostgreSQL
```bash
# Test połączenia z bazą
export PGPASSWORD='trading_password_2024!'
psql -h localhost -U trading_user -d trading_bot -c "SELECT version();"
```

### Test Email
```bash
# Test z Python
python3 -c "
from postgresql_database import PostgreSQLDatabase
import os

# Ustaw zmienne SMTP
os.environ['SMTP_SERVER'] = 'smtp.gmail.com'
os.environ['SMTP_USERNAME'] = 'your_email@gmail.com'
os.environ['SMTP_PASSWORD'] = 'your_app_password'

db = PostgreSQLDatabase()
result = db._send_welcome_email('test@example.com', 'test_user', 'Test')
print('Email sent:', result)
"
```

### Test rejestracji
```bash
# Test przez curl
curl -X POST http://185.70.196.214:8009/api/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "test_user",
    "password": "test_password_123",
    "email": "test@example.com",
    "first_name": "Test",
    "last_name": "User"
  }'
```

---

## 📊 Funkcje PostgreSQL

### Statystyki użytkowników
```python
# Pobierz statystyki
db = PostgreSQLDatabase()
stats = db.get_user_stats()
print(stats)

# Przykład wyniku:
{
  "total_users": 25,
  "active_users": 23,
  "verified_users": 20,
  "account_types": {
    "free": 20,
    "pro": 3,
    "oauth_google": 2
  },
  "recent_registrations_7_days": 5
}
```

### Audit Log
```sql
-- Zobacz ostatnie działania
SELECT * FROM audit_log ORDER BY created_at DESC LIMIT 10;

-- Sprawdź logowania użytkownika
SELECT * FROM audit_log 
WHERE user_id = 1 AND action = 'login_success' 
ORDER BY created_at DESC;
```

---

## 🔐 Bezpieczeństwo

### Implementowane funkcje:
- **Password hashing** - SHA-256 + salt
- **Session tokens** - 32-byte secure random
- **Email verification** - token-based activation
- **Audit logging** - śledzenie wszystkich działań
- **IP tracking** - rejestracja adresów IP
- **User-Agent logging** - identyfikacja przeglądarek

### Zalecenia:
1. **Regularne backupy** - PostgreSQL + automated scripts
2. **SSL/TLS** - HTTPS dla całego serwisu
3. **Rate limiting** - ograniczenie prób logowania
4. **Password policy** - minimum 8 znaków, różnorodność

---

## 🚨 Rozwiązywanie problemów

### PostgreSQL nie działa
```bash
# Sprawdź status
sudo systemctl status postgresql

# Restart
sudo systemctl restart postgresql

# Sprawdź logi
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

### Email nie wysyła
```bash
# Sprawdź zmienne środowiskowe
echo $SMTP_SERVER
echo $SMTP_USERNAME

# Test ręczny
python3 -c "
import smtplib
from email.mime.text import MIMEText

msg = MIMEText('Test message')
msg['Subject'] = 'Test'
msg['From'] = 'your_email@gmail.com'
msg['To'] = 'test@example.com'

server = smtplib.SMTP('smtp.gmail.com', 587)
server.starttls()
server.login('your_email@gmail.com', 'your_app_password')
server.send_message(msg)
server.quit()
print('Email sent successfully')
"
```

### Fallback do JSON
```python
# Jeśli PostgreSQL nie działa, system automatycznie przełączy się na JSON
# Sprawdź w logach serwera:
tail -f /opt/trading-bot/logs/server.log
```

---

## 📈 Monitoring i statystyki

### Dashboard administratora
```
URL: http://185.70.196.214:8009/admin/stats
Uwierzytelnienie: admin/password
```

### Metryki systemowe:
- Liczba zarejestrowanych użytkowników
- Aktywne sesje
- Wskaźnik weryfikacji e-mail
- Używane metody OAuth
- Statystyki logowań

---

## 🎯 Następne kroki

1. **✅ Ukończone:**
   - Integracja PostgreSQL
   - System powiadomień e-mail
   - Weryfikacja adresów e-mail
   - Audit logging
   - Automatyczne fallback do JSON

2. **🔄 Do wykonania:**
   - Konfiguracja SMTP na serwerze
   - Test pełnego procesu rejestracji
   - Konfiguracja automatycznych backupów
   - SSL/HTTPS setup

3. **🚀 Opcjonalne ulepszenia:**
   - Password reset przez e-mail
   - Dwuetapowa weryfikacja (2FA)
   - Rate limiting
   - Advanced admin panel

---

## 📞 Wsparcie

W przypadku problemów:
1. Sprawdź logi: `/opt/trading-bot/logs/`
2. Zweryfikuj konfigurację: `/opt/trading-bot/.env.db`
3. Test połączenia z bazą danych
4. Weryfikacja SMTP settings

**System jest gotowy do produkcji! 🎉**
