# Sentry Node.js Integration Setup

## 📊 Integracja z Sentry została pomyślnie dodana do projektu!

### 🔧 Pliki zostały utworzone/zmodyfikowane:

1. **`instrument.js`** - Główny plik konfiguracji Sentry
2. **`frontend_server.js`** - Zaktualizowany z integracją Sentry
3. **`sentry-verify.js`** - Skrypt weryfikacji działania Sentry
4. **`package.json`** - Dodano nowy skrypt testowy

### 🚀 Jak używać:

#### Uruchomienie aplikacji z Sentry:
```bash
npm start
```

#### Testowanie integracji Sentry:
```bash
npm run test-sentry
```

#### Endpoints do testowania:
- `http://localhost:3000/health` - Status aplikacji i Sentry
- `http://localhost:3000/test-sentry` - Testowy błąd do Sentry

### 🔍 Funkcjonalności Sentry:

1. **Automatyczne przechwytywanie błędów** - wszystkie nieobsłużone wyjątki
2. **Performance monitoring** - śledzenie wydajności requestów
3. **Request/Response tracking** - monitorowanie HTTP
4. **Custom error handling** - możliwość ręcznego wysyłania błędów
5. **User context** - śledzenie kontekstu użytkownika
6. **Custom tags & context** - dodatkowe metadane

### 📊 Sentry Dashboard:
- **DSN**: `https://fcda42005fb2d11f5234184f073dace7@o4509973348941824.ingest.de.sentry.io/4510001992171600`
- **URL**: https://sentry.io/organizations/[your-org]/projects/[your-project]/

### 🛠️ Przykład użycia w kodzie:

```javascript
const Sentry = require("@sentry/node");

// Przechwytywanie błędu
try {
    riskyOperation();
} catch (error) {
    Sentry.captureException(error);
}

// Wysyłanie wiadomości
Sentry.captureMessage("Ważna informacja", "info");

// Ustawianie kontekstu użytkownika
Sentry.setUser({
    id: "123",
    email: "user@example.com"
});

// Dodawanie tagów
Sentry.setTag("environment", "production");
```

### ✅ Status integracji:
- ✅ Sentry SDK zainstalowany (`@sentry/node`)
- ✅ Konfiguracja w `instrument.js`
- ✅ Express.js middleware dodane
- ✅ Error handlers skonfigurowane
- ✅ Test endpoints utworzone
- ✅ Verification script gotowy

### 🔄 Następne kroki:
1. Uruchom `npm run test-sentry` aby zweryfikować połączenie
2. Sprawdź dashboard Sentry pod adresem projektu
3. Dodaj Sentry do innych części aplikacji (Python FastAPI)
4. Skonfiguruj alerty i powiadomienia w Sentry

### 🐍 Integracja z Python (FastAPI):
Do dodania w przyszłości:
```bash
pip install sentry-sdk[fastapi]
```
