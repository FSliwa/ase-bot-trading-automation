# 🔐 PrimeXBT Login Integration

## ✅ Co zostało zaimplementowane:

### 1. **Strona logowania** (`/login`)
- Elegancki interfejs w ciemnym motywie
- Możliwość wyboru między PrimeXBT i Binance
- Formularz logowania dostosowany do każdej giełdy
- Opcja Testnet (tryb demo)
- Opcja Paper Trading (bez logowania)

### 2. **PrimeXBT Broker**
- Dedykowana implementacja dla PrimeXBT
- Symulacja połączenia z giełdą
- Wsparcie dla:
  - Kryptowalut (BTC, ETH, LTC, XRP, EOS)
  - Par Forex (EUR/USD, GBP/USD, USD/JPY)
  - Towarów (Złoto, Srebro, Ropa)
  - Indeksów (S&P500, NASDAQ, DAX30)
- Leverage do 1000x (w zależności od instrumentu)

### 3. **Zarządzanie sesją**
- Automatyczne przekierowanie do logowania
- Przechowywanie danych sesji
- Przycisk wylogowania w dashboardzie
- Wyświetlanie połączonej giełdy

## 🚀 Jak używać:

### 1. **Uruchom aplikację:**
```bash
cd "Algorytm Uczenia Kwantowego LLM"
source ../.venv/bin/activate
python -m uvicorn web.app:app --host 0.0.0.0 --port 8010
```

### 2. **Otwórz w przeglądarce:**
```
http://localhost:8010
```

### 3. **Zaloguj się do PrimeXBT:**

#### Opcja A: Testnet (zalecane)
1. Wybierz **PrimeXBT**
2. Wprowadź dowolny email (np. `test@example.com`)
3. Wprowadź dowolne hasło (np. `password123`)
4. Zaznacz opcję **"Użyj Testnet"**
5. Kliknij **"Połącz z PrimeXBT"**

#### Opcja B: Paper Trading
1. Kliknij **"Rozpocznij Paper Trading"**
2. Nie wymaga logowania
3. Symulacja z wirtualnym saldem $10,000

### 4. **Po zalogowaniu:**
- Dashboard pokazuje połączoną giełdę (np. "PRIMEXBT")
- Status pokazuje "TESTNET" lub "LIVE"
- Wszystkie funkcje tradingowe są dostępne
- Możesz się wylogować klikając ikonę wylogowania

## 🔧 Funkcje logowania:

### **Formularz PrimeXBT:**
- Email
- Hasło
- 2FA Code (opcjonalne)
- Opcja Testnet
- Zapamiętaj dane logowania

### **Formularz Binance:**
- API Key
- API Secret
- Opcja Testnet

### **Bezpieczeństwo:**
- Dane są przechowywane tylko w sesji
- Połączenie SSL/TLS
- Opcja testnet dla bezpiecznego testowania

## 📊 Po zalogowaniu możesz:
- Handlować na wszystkich parach PrimeXBT
- Używać leverage do 1000x (Forex)
- Monitorować pozycje w czasie rzeczywistym
- Analizować wyniki tradingowe
- Korzystać z automatycznych strategii

## ⚠️ Uwaga:
- Obecnie PrimeXBT działa w trybie symulacji
- Prawdziwe API PrimeXBT wymaga dodatkowej integracji
- Testnet jest bezpieczny do nauki i testowania
- Paper Trading nie wymaga żadnych danych logowania

## 🔗 Linki:
- **Aplikacja**: http://localhost:8010
- **Login bezpośrednio**: http://localhost:8010/login
- **Dashboard (po zalogowaniu)**: http://localhost:8010/

Aplikacja automatycznie przekieruje do logowania jeśli nie jesteś zalogowany!

