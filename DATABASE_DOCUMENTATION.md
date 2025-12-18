# 💾 BAZA DANYCH UŻYTKOWNIKÓW - DOKUMENTACJA

## 📋 AKTUALNY SYSTEM BAZY DANYCH

### 🔍 **LOKALIZACJA DANYCH:**
- **Format:** JSON (NIE PostgreSQL)
- **Plik:** `/opt/trading-bot/users.json`
- **Właściciel:** www-data:www-data
- **Uprawnienia:** rw-r--r--

### 📊 **STRUKTURA DANYCH UŻYTKOWNIKA:**
```json
{
  "username": {
    "username": "user123",
    "password_hash": "sha256_hash",
    "salt": "random_salt",
    "email": "user@example.com",
    "first_name": "Jan",
    "last_name": "Kowalski",
    "created_at": "2025-09-09T14:30:00",
    "last_login": "2025-09-09T15:00:00",
    "is_active": true,
    "account_type": "free",  // free, pro, enterprise, oauth_google, oauth_github
    "settings": {
      "theme": "light",
      "notifications": true,
      "two_factor": false
    }
  }
}
```

### 🔐 **BEZPIECZEŃSTWO:**
- **Hashowanie:** SHA-256 + unique salt dla każdego użytkownika
- **Sesje:** Token-based authentication w pamięci serwera
- **Walidacja:** Minimum 8 znaków hasła, sprawdzanie duplikatów

## 📧 POWIADOMIENIA EMAIL

### ❌ **AKTUALNY STATUS:**
**Email powiadomienia są WYŁĄCZONE** - funkcja zaimplementowana ale wymaga konfiguracji SMTP.

### ✅ **JAK WŁĄCZYĆ EMAIL:**

1. **Skonfiguruj zmienne środowiskowe:**
   ```bash
   export SMTP_SERVER="smtp.gmail.com"
   export SMTP_PORT="587"
   export SMTP_USERNAME="your-email@gmail.com"
   export SMTP_PASSWORD="your-app-password"
   ```

2. **Restart serwisu:**
   ```bash
   sudo systemctl restart trading-bot
   ```

### 📝 **PRZYKŁAD MAILA POWITALNEGO:**
```
Cześć Jan!

Dziękujemy za rejestrację w Trading Panel! 🎉

Twoje konto zostało pomyślnie utworzone:
• Nazwa użytkownika: jan123
• Email: jan@example.com
• Data rejestracji: 09.09.2025 14:30

Możesz teraz zalogować się i rozpocząć handel:
http://185.70.196.214/login

Zespół Trading Panel
```

## 🔄 MIGRACJA DO POSTGRESQL (OPCJONALNA)

### **Jeśli chcesz przejść na PostgreSQL:**

1. **Zainstaluj PostgreSQL:**
   ```bash
   sudo apt install postgresql postgresql-contrib python3-psycopg2
   ```

2. **Stwórz bazę danych:**
   ```sql
   CREATE DATABASE trading_bot;
   CREATE USER trading_user WITH PASSWORD 'password';
   GRANT ALL PRIVILEGES ON DATABASE trading_bot TO trading_user;
   ```

3. **Utwórz tabelę users:**
   ```sql
   CREATE TABLE users (
     id SERIAL PRIMARY KEY,
     username VARCHAR(50) UNIQUE NOT NULL,
     password_hash VARCHAR(64) NOT NULL,
     salt VARCHAR(32) NOT NULL,
     email VARCHAR(100) UNIQUE NOT NULL,
     first_name VARCHAR(50),
     last_name VARCHAR(50),
     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
     last_login TIMESTAMP,
     is_active BOOLEAN DEFAULT TRUE,
     account_type VARCHAR(20) DEFAULT 'free',
     settings JSONB DEFAULT '{}'
   );
   ```

4. **Zaktualizuj user_database.py** - dodaj obsługę PostgreSQL

### **ZALECENIE:**
Dla początkowego użytku **JSON jest wystarczający**. PostgreSQL polecany przy >1000 użytkowników.

## 📊 STATYSTYKI UŻYTKOWNIKÓW

### **Sprawdź statystyki bieżące:**
```bash
cd /opt/trading-bot
python3 -c "from user_database import UserDatabase; db = UserDatabase(); print(db.get_user_stats())"
```

### **Przykładowe statystyki:**
```json
{
  "total_users": 15,
  "active_users": 14,
  "inactive_users": 1,
  "account_types": {
    "free": 10,
    "oauth_google": 3,
    "oauth_github": 2
  }
}
```

## 🎯 PODSUMOWANIE

✅ **CO DZIAŁA:**
- Rejestracja użytkowników z nowym designem
- Przechowywanie w JSON z hashowaniem SHA-256
- OAuth Google/GitHub ready
- Backend połączony z frontendem

❌ **CO NIE DZIAŁA (do konfiguracji):**
- Wysyłanie emaili (wymaga SMTP setup)
- PostgreSQL (obecnie JSON)

⏳ **NASTĘPNE KROKI:**
1. Prześlij nowy register.html na serwer
2. Skonfiguruj SMTP jeśli chcesz email (opcjonalne)
3. Test nowego panelu rejestracji
