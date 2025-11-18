# 🔐 GOOGLE & GITHUB OAUTH SETUP
# Konfiguracja logowania przez Google i GitHub

## 📋 INSTRUKCJE KONFIGURACJI

### 🟢 Google OAuth Setup

1. **Przejdź do Google Cloud Console:**
   - https://console.cloud.google.com/

2. **Utwórz nowy projekt lub wybierz istniejący**

3. **Włącz Google+ API:**
   - APIs & Services → Library
   - Szukaj "Google+ API" i włącz

4. **Utwórz OAuth 2.0 Credentials:**
   - APIs & Services → Credentials
   - Create Credentials → OAuth 2.0 Client IDs
   - Application type: Web application
   - Name: Trading Bot
   - Authorized redirect URIs: 
     ```
     http://localhost:8009/auth/google/callback
     http://185.70.196.214/auth/google/callback
     ```

5. **Zapisz Client ID i Client Secret**

### 🐙 GitHub OAuth Setup

1. **Przejdź do GitHub Settings:**
   - https://github.com/settings/developers

2. **Utwórz nową OAuth App:**
   - New OAuth App
   - Application name: Trading Bot
   - Homepage URL: http://185.70.196.214
   - Authorization callback URL: 
     ```
     http://localhost:8009/auth/github/callback
     http://185.70.196.214/auth/github/callback
     ```

3. **Zapisz Client ID i Client Secret**

### 🔧 KONFIGURACJA VNC

W VNC wklej te komendy:

```bash
# Ustawienie zmiennych środowiskowych
export GOOGLE_CLIENT_ID="your-google-client-id"
export GOOGLE_CLIENT_SECRET="your-google-client-secret"
export GITHUB_CLIENT_ID="your-github-client-id"  
export GITHUB_CLIENT_SECRET="your-github-client-secret"

# Skopiowanie zaktualizowanych plików
sudo cp ~/login.html /opt/trading-bot/
sudo cp ~/enhanced_server_gpt5.py /opt/trading-bot/
sudo cp ~/user_database.py /opt/trading-bot/

# Restart aplikacji
sudo systemctl restart trading-bot
```

### ✅ TESTOWANIE

1. **Otwórz:** http://185.70.196.214/login
2. **Nowy design z przyciskami OAuth**
3. **Kliknij przycisk Google lub GitHub**
4. **Przekierowanie do OAuth provider**

### 📊 STATUS IMPLEMENTACJI

- ✅ Frontend - nowy design login.html z przyciskami OAuth
- ✅ Backend - endpointy /auth/google i /auth/github dodane
- ✅ Obsługa callback URLs
- ✅ Automatyczna rejestracja użytkowników OAuth
- ✅ User database obsługuje konta oauth_google i oauth_github
- ⏳ Wymagana konfiguracja Client ID i Secret

### 🎯 NASTĘPNE KROKI

1. Skonfiguruj OAuth apps w Google i GitHub
2. Wklej komendy w VNC aby zaktualizować serwer
3. Ustaw zmienne środowiskowe z prawdziwymi kluczami
4. Test logowania OAuth
